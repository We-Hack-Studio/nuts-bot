import asyncio

from bot.exchanges.binance import Binance


async def main():

    b = Binance()
    await b.prepare()
    r = await b.fetch_last_price(pair="ETHUSDT")
    print(r)


if __name__ == "__main__":
    asyncio.run(main())
