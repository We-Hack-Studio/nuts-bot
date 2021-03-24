import ccxt

if __name__ == "__main__":
    bybit = ccxt.bybit()
    bybit.load_markets()
    print(bybit.markets["BTC/USDT"]["precision"])
