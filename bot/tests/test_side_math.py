from bot.strategy import Side


def test():
    assert -Side.no == Side.no
    assert -Side.long == Side.short
    assert -Side.short == Side.long

    base_price = 10000
    offset = 5
    assert 9995 == base_price - Side.long * offset
    assert 10005 == base_price - Side.short * offset

    order_book_ticker = (10001, 9999)
    assert 10001 == order_book_ticker[(1 - Side.long) // 2]
    assert 9999 == order_book_ticker[(1 - Side.short) // 2]
