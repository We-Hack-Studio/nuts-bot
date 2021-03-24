import asyncio
import logging
from collections import namedtuple
from typing import Any, Dict, Union

import pandas as pd

from bot.enums import OrderType, Side
from bot.exchanges.base import Exchange
from bot.utils.math import cal_ewm, fib

logger: logging.Logger = logging.getLogger(__name__)


Indicator = namedtuple("Indicator", ["side", "rw"])
ShouldTradeResult = namedtuple("ShouldTradeResult", ["code", "reason"])

# todo: cleanup when robot stop
# todo: feedback balance


def _cal_indicator(prices: pd.Series) -> Indicator:
    ema7 = cal_ewm(data=prices, span=7)
    ema14 = cal_ewm(data=prices, span=14)
    ema21 = cal_ewm(data=prices, span=21)
    fu = 0
    fd = 0
    en1 = ema7.values[-1] * 3 - ema7.values[-2] * 2
    en2 = ema14.values[-1] * 3 - ema14.values[-2] * 2
    en3 = ema21.values[-1] * 3 - ema21.values[-2] * 2
    if en1 > en2:
        fu += 1
    if en1 > en3:
        fu += 1
    if en2 > en3:
        fu += 1
    if en1 < en2:
        fd += 1
    if en1 < en3:
        fd += 1
    if en2 < en3:
        fd += 1

    last_price = prices.values[-1]
    rw = (
        max(
            abs(ema14.values[-1] - ema7.values[-2]),
            abs(ema21.values[-1] - ema14.values[-2]),
            abs(ema21.values[-1] - ema7.values[-2]),
        )
        / last_price
        * 100
    )
    side = Side.no
    if fu == 3:
        side = 1

    if fd == 3:
        side = -1

    return Indicator(side=side, rw=rw)


class Strategy:
    def __init__(self, exchange: Exchange):
        self._exchange = exchange

        self._trading_context: Dict[str, Any] = {}
        self._parameters: Dict[str, Any] = {}
        self._store: Dict[str, Any] = {}
        self._position: Dict[str, Union[float, int, Side]] = {}
        self._balance: float = 0.0
        self._log_queue = asyncio.Queue()
        self._event_queue = asyncio.Queue()

    @property
    def pair(self):
        return self._trading_context["pair"]

    @property
    def parameters(self):
        return self._parameters

    @parameters.setter
    def parameters(self, value):
        self._parameters.update(value)

    @property
    def store(self):
        return self._store

    @property
    def balance(self):
        return self._balance

    @property
    def log_queue(self):
        return self._log_queue

    @property
    def event_queue(self):
        return self._event_queue

    @property
    def position(self):
        return self._position

    @property
    def trading_context(self):
        return self._trading_context

    def sync_store(self, last_price: float) -> None:
        market_type = self._trading_context["market_type"]
        assert market_type != "spots", "Doesn't support spots currently"

        max_leverage = self._parameters["maxLeverage"]
        open_pos_percent = self._parameters["openPosPercent"]
        leveraged_balance = self._balance * max_leverage
        # print('max_leverage', max_leverage)
        # print('open_pos_percent', open_pos_percent)
        # print('leveraged_balance', leveraged_balance)

        # inverse contract
        if market_type in {"inverse_perpetual", "inverse_delivery"}:
            open_pos_qty = int(leveraged_balance * open_pos_percent * last_price)
            max_pos_qty = min(
                int(open_pos_qty * self._parameters["maxOpenPosCount"]),
                # todo: introduce contract value
                int(leveraged_balance * last_price),
            )
            self._store = {
                "open_pos_qty": open_pos_qty,
                "max_pos_qty": max_pos_qty,
            }

        # linear contract
        if market_type in {"linear_perpetual", "linear_delivery"}:
            precision = self._trading_context["qty_precision"]
            open_pos_qty = leveraged_balance * open_pos_percent / last_price
            max_pos_qty = min(
                round(open_pos_qty * self._parameters["maxOpenPosCount"], precision),
                round(leveraged_balance / last_price, precision),
            )
            self._store = {
                "open_pos_qty": round(open_pos_qty, precision),
                "max_pos_qty": max_pos_qty,
            }
            # print('precision', precision)
            # print('open_pos_qty', open_pos_qty)
            # print('max_pos_qty', max_pos_qty)
            # print('leveraged_balance', leveraged_balance)
            # print('maxOpenPosCount', self._parameters["maxOpenPosCount"])
            # print('last_price', last_price)

    async def ensure_order(self):
        orders = await self._exchange.fetch_current_orders(self.pair)
        if self._position["qty"] == 0:  # No holding position
            # No current orders
            if len(orders) == 0:
                return

            await self._exchange.cancel_current_orders(self.pair)
            return
        else:  # Has holding position
            if len(orders) == 0:
                tp_order = self.get_take_profit_order()
                sl_order = self.get_stop_loss_order()
                await self._exchange.place_orders_batch([tp_order, sl_order])
                return
            elif len(orders) != 2:
                await self._exchange.cancel_current_orders(self.pair)
                tp_order = self.get_take_profit_order()
                sl_order = self.get_stop_loss_order()
                await self._exchange.place_orders_batch([tp_order, sl_order])
                return
            else:
                # Number of orders == 2, check orders
                tp_order_match = False
                sl_order_match = False

                tp_order = self.get_take_profit_order()
                sl_order = self.get_stop_loss_order()
                for order in orders:
                    real_order = dict(
                        side=order["side"],
                        qty=order["qty"],
                        price=order["price"],
                    )
                    # todo: precision
                    if order["order_type"] == OrderType.limit:
                        expected_order = dict(
                            side=tp_order["side"],
                            qty=tp_order["qty"],
                            price=tp_order["price"],
                        )
                        tp_order_match = real_order == expected_order
                        if not tp_order_match:
                            logger.warning("Unmatched take profit order")
                            await self._log_queue.put("止盈单不匹配")

                    if order["order_type"] == OrderType.trigger:
                        expected_order = dict(
                            side=sl_order["side"],
                            qty=sl_order["qty"],
                            price=sl_order["price"],
                        )
                        sl_order_match = real_order == expected_order
                        if not sl_order_match:
                            logger.warning("Unmatched stop loss order")
                            await self._log_queue.put("止损单不匹配")

                if not tp_order_match or not sl_order_match:
                    logger.info("Cancel all current orders...")
                    await self._log_queue.put("正在取消全部挂单...")
                    await self._exchange.cancel_current_orders(self.pair)

                    logger.info("Replace take profit order and stop loss order")
                    await self._log_queue.put("正在重挂止盈止损单...")
                    await self._exchange.place_orders_batch([tp_order, sl_order])
                    return

    def prepare_open_pos_orders(self, side: Side, base_price: float):
        orders = []
        offset_factor = self.get_offset_factor(side)
        for i in range(1, 3):
            order = self.get_fib_order(
                n=i,
                base_price=base_price,
                offset_factor=offset_factor,
                side=side,
            )

            orders.append(order)

        qty = self._store["open_pos_qty"]
        pair = self._trading_context["pair"]
        tick = self._trading_context["price_tick"]
        entry_order1 = {
            "pair": pair,
            "order_type": OrderType.limit,
            "price": base_price - int(side) * tick,
            "side": side,
            "qty": qty,
        }
        entry_order2 = {
            "pair": pair,
            "order_type": OrderType.limit,
            "price": base_price - int(side) * 2 * tick,
            "side": side,
            "qty": qty,
        }
        orders.extend([entry_order1, entry_order2])
        return orders

    def prepare_add_pos_orders(self, side: Side, base_price: float):
        orders = []
        offset_factor = self.get_offset_factor(side)
        for i in range(1, 4):
            order = self.get_fib_order(
                n=i,
                base_price=base_price,
                offset_factor=offset_factor,
                side=side,
            )

            if side == 1:
                if order["price"] < self._position["liq_price"]:
                    break

            if side == -1:
                if order["price"] > self._position["liq_price"]:
                    break

            orders.append(order)

        tp_order = self.get_take_profit_order()
        sl_order = self.get_stop_loss_order()
        orders.extend([tp_order, sl_order])
        return orders

    def get_take_profit_order(self):
        side = self._position["side"]
        if side == 1:
            price = (
                self._position["avg_price"] + self._parameters["longTakeProfitDistance"]
            )
        elif side == -1:
            price = (
                self._position["avg_price"]
                - self._parameters["shortTakeProfitDistance"]
            )
        else:
            logger.warning("Cannot take profit if no position.")
            return

        return {
            "pair": self.pair,
            "order_type": OrderType.limit,
            "price": round(price, self._trading_context["price_precision"]),
            "side": -side,
            "qty": self._position["qty"],
            "extras": self._exchange.get_tp_order_extras(),
        }

    def get_stop_loss_order(self):
        side = self._position["side"]
        if side == 1:
            price = (
                self._position["avg_price"] - self._parameters["longStopLossDistance"]
            )
        elif side == -1:
            price = (
                self._position["avg_price"] + self._parameters["shortStopLossDistance"]
            )
        else:
            logger.warning("Cannot stop loss if no position.")
            return

        return {
            "pair": self.pair,
            "order_type": OrderType.trigger,
            "price": round(price, self._trading_context["price_precision"]),
            "side": -side,
            "qty": self._position["qty"],
        }

    def get_fib_order(
        self,
        *,
        n: int,
        base_price: float,
        offset_factor: float,
        side: Side,
    ) -> Dict[str, Any]:
        offset = offset_factor * fib(n)
        price = base_price - int(side) * offset
        return {
            "pair": self.pair,
            "order_type": OrderType.limit,
            "side": side,
            "qty": self._store["open_pos_qty"],
            "price": price,
        }

    def get_offset_factor(self, side: Side):
        if side == Side.long:
            offset_factor = self._parameters["longAdditionDistance"]
        else:
            offset_factor = self._parameters["shortAdditionDistance"]
        return offset_factor

    async def trade_once(self):
        await asyncio.gather(self._sync_balance(), self._sync_position())

        # sync store, note parameters was updated by robot
        last_price = await self._exchange.fetch_last_price(pair=self.pair)
        self.sync_store(last_price=last_price)

        await self.ensure_order()

        # Calculate the indicator
        indicator = await self._indicator(
            period=self._parameters["candlePeriod"],
        )
        if not self._parameters["trendFollowing"]:
            indicator = Indicator(side=-indicator.side, rw=indicator.rw)

        logger.info("Indicator {side: %d, rw: %.4f}", indicator.side, indicator.rw)
        await self._log_queue.put(
            "当前指标 {side: %d, rw: %.4f}" % (indicator.side, indicator.rw)
        )
        # Should trade according to the indicator?
        result = self.should_trade(indicator)
        if result.code == 0:
            logger.info("Could not satisfy the trading condition: %s", result.reason)
            await self._log_queue.put("不满足交易条件：{}".format(result.reason))
            return

        order_book_ticker = await self._exchange.fetch_order_book_ticker(self.pair)
        base_price = order_book_ticker[(1 - indicator.side) // 2]
        if self._position["side"] == 0:
            logger.info("Preparing open position orders...")
            await self._log_queue.put("正在准备开仓订单...")
            orders = self.prepare_open_pos_orders(
                side=indicator.side, base_price=base_price
            )
        else:
            await self._log_queue.put("正在准备补仓订单...")
            logger.info("Preparing add position orders...")
            orders = self.prepare_add_pos_orders(
                side=indicator.side, base_price=base_price
            )

        await self._exchange.cancel_current_orders(pair=self._trading_context["pair"])
        await self._exchange.place_orders_batch(orders)
        logger.info("Orders was placed, waiting for filling...")
        await self._log_queue.put("已挂单，等待成交...")
        await asyncio.sleep(self._parameters["restInterval"])

    def set_trading_context(self, context):
        self._trading_context.update(context)

    def risk_control(self):
        pass

    def should_trade(self, indicator: Indicator) -> ShouldTradeResult:
        side = indicator.side
        rw = indicator.rw

        # 波动率过大
        if rw > self._parameters["maxRw"]:
            return ShouldTradeResult(
                code=0,
                reason="Rw ({:.4f}) exceeds maxRw ({:.4f})".format(
                    rw, self._parameters["maxRw"]
                ),
            )

        # 无方向，不交易
        if side == 0:
            return ShouldTradeResult(code=0, reason="No indicator side")

        # 指标方向与持仓方向相反，不交易
        if self._position["side"] != 0 and self._position["side"] != side:
            return ShouldTradeResult(
                code=0,
                reason="Current holding position side is opposite to indicator side",
            )

        # 浮盈状态等待止盈，不交易
        unrealized_pnl = self._position["unrealized_pnl"]
        if unrealized_pnl > 0:
            return ShouldTradeResult(
                code=0,
                reason="In profit (unrealized P&L is {:.2f})".format(unrealized_pnl),
            )

        # 不允许做多
        disallow_long = side == 1 and not self._parameters["allowLong"]
        if disallow_long:
            return ShouldTradeResult(
                code=0,
                reason="Disallow long side",
            )

        # 不允许做空
        disallow_short = side == -1 and not self._parameters["allowShort"]
        if disallow_short:
            return ShouldTradeResult(
                code=0,
                reason="Disallow short side",
            )

        # 满仓
        if self._position["qty"] >= self._store["max_pos_qty"]:
            return ShouldTradeResult(
                code=0,
                reason="Current holding position qty exceeds allowed max value",
            )

        return ShouldTradeResult(
            code=1,
            reason="Pass all checks",
        )

    async def _indicator(self, period: str) -> Indicator:
        pair = self._trading_context["pair"]
        candles = await self._exchange.fetch_candles(pair=pair, period=period)
        close_prices = pd.Series(c[3] for c in candles)
        return _cal_indicator(prices=close_prices)

    async def _sync_balance(self):
        currency = self._trading_context["target_currency"]
        print('currency', currency)
        self._balance = await self._exchange.fetch_total_balance(currency)

    async def _sync_position(self):
        pair = self._trading_context["pair"]
        result = await self._exchange.fetch_position(pair)
        self._position.update(result)

    @classmethod
    def new(cls, position=None):
        """
        Return a strategy instance for testing purpose.
        """
        from bot.exchanges.base import Exchange

        exchange = Exchange()
        context = {
            "pair": "ETHUSDT",
            "target_currency": "USDT",
            "market_type": "linear_perpetual",
        }
        strategy = cls(exchange=exchange)
        strategy.set_trading_context(context)
        strategy._parameters = {
            "openPosPercent": 0.01,
            "longAdditionDistance": 0.1,
            "shortAdditionDistance": 0.1,
            "maxLeverage": 3,
            "longTakeProfitDistance": 0.5,
            "shortTakeProfitDistance": 0.5,
            "longStopLossDistance": 10,
            "shortStopLossDistance": 10,
            "maxRw": 0.5,
            "maxOpenPosCount": 10,
            "trendFollowing": True,
            "disallowLong": False,
            "disallowShort": False,
            "candlePeriod": "5m",
        }

        # set position
        strategy._position = {
            "qty": 0.0,
            "side": Side.no,
            "liq_price": 0.0,
            "avg_price": 0.0,
            "unrealized_pnl": 0.0,
        }
        if position is not None:
            strategy._position.update(position)

        strategy._balance = 1000
        strategy._store = {
            "open_pos_qty": 0.5,
            "max_pos_qty": 1,
        }
        return strategy
