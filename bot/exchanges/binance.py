import logging
from typing import Any, Dict, List

import ccxt.async_support as ccxt

from bot.enums import OrderType
from bot.exceptions import ExchangeException, PositionException
from bot.exchanges.base import Exchange

logger = logging.getLogger(__name__)


class Binance(Exchange):
    code: str = "binance"
    name: str = "Binance"
    ccxt_exchange_class = ccxt.binance
    trigger_order_type_table = {
        OrderType.trigger: "stop_market",
    }

    async def fetch_position(self, pair: str):
        assert (
            self._ccxt_exchange.options["defaultType"] != "spot"
        ), "Doesn't support spots currently"

        default_type = self._ccxt_exchange.options["defaultType"]
        if default_type == "future":
            method = getattr(self._ccxt_exchange, "fapiPrivate_get_positionrisk")
        elif default_type == "delivery":
            method = getattr(self._ccxt_exchange, "dapiPrivate_get_positionrisk")
        else:
            raise ExchangeException(
                "Invalid binance defaultType option: {}.".format(default_type)
            )

        try:
            response = await method({"pair": pair})
        except Exception as exc:
            logger.exception(
                "Failed to fetch position. Error from %s: %s", self.name, exc
            )
            raise ExchangeException()

        positions = []
        for p in response:
            parsed = self.parse_position(p)
            if parsed["qty"] == 0:
                continue

            if parsed["pair"] != pair:
                continue

            positions.append(parsed)

        if len(positions) > 1:
            raise PositionException("Does not support multi positions of same pair.")

        if len(positions) == 0:
            return {
                "qty": 0.0,
                "side": 0,
                "liq_price": 0.0,
                "avg_price": 0.0,
                "unrealized_pnl": 0.0,
            }

        return positions[0]

    async def fetch_current_orders(self, pair: str) -> List[Dict[str, Any]]:
        # binance return all current orders(including trigger orders) at same time.
        # This is a little different from other exchanges which ones usually separate
        # active orders and trigger orders to different API.
        try:
            ccxt_symbol = self._pair_to_ccxt_symbol(pair)
            open_orders = await self._ccxt_exchange.fetch_open_orders(
                symbol=ccxt_symbol
            )
        except Exception as exc:
            logger.exception(
                "Failed to fetch current orders. Error from %s: %s", self.name, exc
            )
            raise ExchangeException()

        ret_orders = []
        for order in open_orders:
            if order["type"] == "limit":
                ret_orders.append(
                    self._adapt_ccxt_open_order(order, overrides={"pair": pair})
                )
            else:
                ret_orders.append(
                    self._adapt_ccxt_trigger_order(order, overrides={"pair": pair})
                )
        return ret_orders

    @staticmethod
    def parse_position(position) -> Dict[str, Any]:
        qty = position["positionAmt"]
        qty_in_float = float(qty)
        side = 0
        if qty_in_float > 0:
            side = 1
        if qty_in_float < 0:
            side = -1

        return {
            # todo: by market type
            "pair": position["symbol"],
            "qty": abs(qty_in_float),  # always > 0
            "side": side,
            "liq_price": float(position["liquidationPrice"]),
            "avg_price": float(position["entryPrice"]),
            "unrealized_pnl": float(position["unRealizedProfit"]),
        }

    @staticmethod
    def _adapt_ccxt_trigger_order(order, overrides=None):
        if overrides is None:
            overrides = {}

        if order["side"] == "buy":
            side = 1
        else:
            side = -1
        adapted = {
            "order_id": order["id"],
            "client_order_id": order["clientOrderId"],
            "timestamp": order["timestamp"]
            or order["info"]["updateTime"],  # in milliseconds
            "datetime": order["datetime"],
            "price": float(order["info"]["stopPrice"]),
            "qty": order["amount"],
            "pair": order["symbol"],
            "order_type": OrderType.trigger,
            "side": side,
        }
        adapted.update(overrides)
        return adapted

    def set_market_type(self, market_type: str):
        market_type_mapping = {
            "spots": "spot",
            "margin": "margin",
            "inverse_perpetual": "delivery",
            "inverse_delivery": "delivery",
            "linear_delivery": "future",
            "linear_perpetual": "future",
        }
        self._ccxt_exchange.options["defaultType"] = market_type_mapping[market_type]

    @staticmethod
    def get_trigger_order_extras(trigger_price):
        params = {
            "stopPrice": trigger_price,
            # https://binance-docs.github.io/apidocs/futures/cn/#trade-2
            "reduceOnly": True,
        }
        return params

    @staticmethod
    def get_tp_order_extras():
        params = {
            # https://binance-docs.github.io/apidocs/futures/cn/#trade-2
            "reduceOnly": True,
        }
        return params


async def main():
    from pprint import pprint

    from bot.enums import OrderType

    exchange = Binance()
    exchange.set_market_type("linear_perpetual")
    exchange.use_test_net()
    await exchange.prepare()
    exchange.auth(
        {
            "api_key": "",
            "secret": "",
        }
    )

    pprint(exchange._ccxt_exchange.markets["ETH/USDT"]["precision"])

    position = await exchange.fetch_position(pair="ETHUSDT")
    print("Position:")
    pprint(position)

    current_orders = await exchange.fetch_current_orders(pair="ETHUSDT")
    print("\n")
    print("Current Orders:")
    pprint(current_orders)

    account = await exchange.fetch_total_balance("USDT")
    print("\n")
    print("Balance:")
    pprint(account)

    last_price = await exchange.fetch_last_price("ETHUSDT")
    print("\n")
    print("Last Price: ", last_price)

    order_book_ticker = await exchange.fetch_order_book_ticker("ETHUSDT")
    print("\n")
    print("Order Book Ticker:")
    pprint(order_book_ticker)

    candles = await exchange.fetch_candles("ETHUSDT", period="1m")
    print("\n")
    print("Candles:")
    print(len(candles))
    pprint(candles)

    await exchange.cancel_current_orders("ETHUSDT")
    await exchange.place_order(
        pair="ETHUSDT",
        order_type=OrderType.limit,
        side=-1,
        qty=0.001,
        price=500,
    )
    await exchange.place_order(
        pair="ETHUSDT",
        order_type=OrderType.limit,
        side=1,
        qty=0.001,
        price=100,
    )
    await exchange.place_order(
        pair="ETHUSDT",
        order_type=OrderType.trigger,
        side=1,
        qty=0.001,
        price=600,
    )

    await exchange.place_orders_batch(
        [
            dict(
                pair="ETHUSDT",
                order_type=OrderType.limit,
                side=-1,
                qty=0.001,
                price=500,
            ),
            dict(
                pair="ETHUSDT",
                order_type=OrderType.limit,
                side=1,
                qty=0.001,
                price=100,
            ),
            dict(
                pair="ETHUSDT",
                order_type=OrderType.trigger,
                side=1,
                qty=0.001,
                price=500,
            ),
        ]
    )

    await exchange.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
