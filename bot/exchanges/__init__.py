from bot.exchanges.binance import Binance

__all__ = ["exchange_factory"]

EXCHANGE_TABLE = {
    "binance": Binance,
}


def exchange_factory(exchange_code: str):
    return EXCHANGE_TABLE.get(exchange_code.lower())
