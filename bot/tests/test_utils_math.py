import pytest

from bot.utils import math


@pytest.mark.parametrize(
    "n,f", [(1, 1), (2, 1), (3, 2), (4, 3), (5, 5), (6, 8), (7, 13), (8, 21)]
)
def test_fib(n, f):
    assert math.fib(n) == f
