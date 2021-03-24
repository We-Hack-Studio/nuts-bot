from enum import Enum


class OrderType(str, Enum):
    market = "market"
    limit = "limit"
    trigger = "trigger"


class Side(int, Enum):
    """
    Side Math:

    Given a base price and an offset value, we can get a better price according to the order side by equation:
        better = base - Side*offset

    Given an order book ticker (ask0, bid0), we can get the best price according to the order side by equation:
        best = ticker[(1-side)//2]
    """

    short = -1
    no = 0
    long = 1
