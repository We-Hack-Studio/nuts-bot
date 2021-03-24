import asyncio
import logging
from collections import namedtuple
from typing import Any, Dict, List, Optional

import ccxt.async_support as ccxt

from bot.enums import OrderType
from bot.exceptions import ExchangeException

OrderBookTicker = namedtuple("OrderBookTicker", ["ask0", "bid0"])

logger = logging.getLogger(__name__)


class Exchange:
    code: str = ""
    name: str = ""
    ccxt_exchange_class: Optional[ccxt.Exchange] = ccxt.Exchange
    trigger_order_type_table: Dict[str, str] = {}

    def __init__(self):
        self._ccxt_exchange = self.ccxt_exchange_class(
            {
                "enableRateLimit": True,
                "verbose": False,
                "options": {"adjustForTimeDifference": True},
            }
        )
        self._ccxt_exchange.aiohttp_proxy = 'http://127.0.0.1:7890'
        self._ccxt_exchange.aiohttp_trust_env = True

        # Public market data
    async def fetch_last_price(self, pair: str) -> float:
        ccxt_symbol = self._pair_to_ccxt_symbol(pair)
        try:
            ticker = await self._ccxt_exchange.fetch_ticker(ccxt_symbol)
        except (ccxt.ExchangeError, ccxt.NetworkError) as exc:
            logger.exception(exc)
            raise ExchangeException("Failed to fetch last price")
        return ticker["last"]

    async def fetch_order_book_ticker(self, pair: str) -> OrderBookTicker:
        ccxt_symbol = self._pair_to_ccxt_symbol(pair)
        try:
            order_book = await self._ccxt_exchange.fetch_order_book(ccxt_symbol)
        except (ccxt.ExchangeError, ccxt.NetworkError) as exc:
            logger.exception(exc)
            raise ExchangeException("Failed to fetch order book ticker")

        return OrderBookTicker(
            ask0=order_book["asks"][0][0],
            bid0=order_book["bids"][0][0],
        )

    async def fetch_candles(self, pair: str, period: str):
        ccxt_symbol = self._pair_to_ccxt_symbol(pair)
        try:
            result = await self._ccxt_exchange.fetch_ohlcv(
                ccxt_symbol, timeframe=period, limit=201
            )
        except (ccxt.ExchangeError, ccxt.NetworkError) as exc:
            logger.exception(exc)
            raise ExchangeException("Failed to fetch candles")

        return result

    async def fetch_total_balance(self, currency: str) -> float:
        try:
            balance = await self._ccxt_exchange.fetch_total_balance()
            print('balance', balance)
        except (ccxt.ExchangeError, ccxt.NetworkError) as exc:
            logger.exception(exc)
            raise ExchangeException("Failed to fetch total balance")

        return balance.get(currency, 0)

    async def cancel_current_orders(self, pair: str):
        ccxt_cancel_all_orders_method = getattr(
            self._ccxt_exchange, "cancel_all_orders", None
        )

        if ccxt_cancel_all_orders_method is None:
            raise ExchangeException(
                "{} does not support batch cancel.".format(self.name)
            )

        ccxt_symbol = self._pair_to_ccxt_symbol(pair)
        try:
            await ccxt_cancel_all_orders_method(ccxt_symbol)
        except (ccxt.ExchangeError, ccxt.NetworkError) as exc:
            logger.exception(exc)
            raise ExchangeException("Failed to cancel current orders")

    def auth(self, credential_key: Dict[str, str]) -> None:
        api_key = credential_key.get("api_key", "")
        secret = credential_key.get("secret", "")
        passphrase = credential_key.get("passphrase", "")
        self._ccxt_exchange.apiKey = api_key
        self._ccxt_exchange.secret = secret
        if passphrase:
            self._ccxt_exchange.password = passphrase

    def use_test_net(self) -> None:
        self._ccxt_exchange.set_sandbox_mode(enabled=True)

    async def place_orders_batch(self, orders: List[Dict[str, Any]]):
        place_order_tasks = [self.place_order(**order) for order in orders]
        await asyncio.gather(*place_order_tasks, return_exceptions=False)

    async def place_order(
        self,
        *,
        pair: str,
        order_type: OrderType,
        side: int,
        qty,
        price=None,
        extras=None,
    ):
        logger.debug(
            "Order args {pair: %s, order_type: %s, side: %s, qty: %s, price: %s}",
            pair,
            order_type,
            side,
            qty,
            price,
        )
        if extras is None:
            extras = {}

        ccxt_symbol = self._pair_to_ccxt_symbol(pair)
        if order_type == OrderType.trigger:
            order_type = self.trigger_order_type_table[OrderType.trigger]
            price = self._ccxt_exchange.price_to_precision(ccxt_symbol, price)
            trigger_order_extras = self.get_trigger_order_extras(price)
            extras.update(trigger_order_extras)

        qty = self._ccxt_exchange.amount_to_precision(ccxt_symbol, qty)
        if price is not None:
            price = self._ccxt_exchange.price_to_precision(ccxt_symbol, price)

        try:
            await self._ccxt_exchange.create_order(
                symbol=ccxt_symbol,
                type=order_type,
                side={-1: "sell", 1: "buy"}[side],
                amount=qty,
                price=price,
                params=extras,
            )
        except (ccxt.ExchangeError, ccxt.NetworkError) as exc:
            logger.exception(exc)
            raise ExchangeException("Failed to place order")

    async def prepare(self):
        await self._ccxt_exchange.load_markets()

    async def close(self):
        await self._ccxt_exchange.close()

    async def fetch_position(self, pair: str) -> Dict[str, Any]:
        raise NotImplementedError()

    async def fetch_current_orders(self, pair: str) -> List[Dict[str, Any]]:
        try:
            active_order_task = self._fetch_active_orders(pair)
            trigger_order_task = self._fetch_trigger_orders(pair)
            open_orders, trigger_orders = await asyncio.gather(
                active_order_task,
                trigger_order_task,
            )
        except (ccxt.ExchangeError, ccxt.NetworkError) as exc:
            logger.exception(exc)
            raise ExchangeException("Failed to fetch current orders")

        return open_orders + trigger_orders

    async def _fetch_active_orders(self, pair: str):
        try:
            ccxt_symbol = self._pair_to_ccxt_symbol(pair)
            open_orders = await self._ccxt_exchange.fetch_open_orders(
                symbol=ccxt_symbol
            )
        except Exception as exc:
            logger.exception(exc)
            raise ExchangeException("Failed to fetch active orders")

        return [
            self._adapt_ccxt_open_order(o, overrides={"pair": pair})
            for o in open_orders
        ]

    async def _fetch_trigger_orders(self, pair: str):
        raise NotImplementedError()

    def _pair_to_ccxt_symbol(self, pair: str) -> str:
        return self._ccxt_exchange.markets_by_id[pair]["symbol"]

    def price_precision(self, pair: str) -> int:
        ccxt_symbol = self._pair_to_ccxt_symbol(pair)
        result = self._ccxt_exchange.markets[ccxt_symbol]["precision"]["price"]
        # todo: different exchange has different precision mode
        return result

    def price_ticker(self, pair: str) -> int:
        precision = self.price_precision(pair)
        return 10 ** (-precision)

    def qty_precision(self, pair: str) -> int:
        ccxt_symbol = self._pair_to_ccxt_symbol(pair)
        return self._ccxt_exchange.markets[ccxt_symbol]["precision"]["amount"]

    @staticmethod
    def _adapt_ccxt_open_order(order, overrides=None):
        if overrides is None:
            overrides = {}

        order_type_table = {
            "limit": OrderType.limit,
            "market": OrderType.market,
        }
        adapted = {
            "order_id": order["id"],
            "client_order_id": order["clientOrderId"],
            "timestamp": order["timestamp"],  # in milliseconds
            "datetime": order["datetime"],
            "price": order["price"],
            "qty": order["amount"],
            "pair": order["symbol"],
            "order_type": order_type_table[order["type"]],
            "side": {"sell": -1, "buy": 1}[order["side"]],
        }
        adapted.update(overrides)
        return adapted

    @staticmethod
    def _adapt_ccxt_trigger_order(order, overrides=None):
        raise NotImplementedError()

    @staticmethod
    def get_trigger_order_extras(trigger_price: float):
        return {}

    @staticmethod
    def get_tp_order_extras():
        return {}
