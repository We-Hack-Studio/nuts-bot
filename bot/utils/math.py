import pandas as pd


def fib(n: int) -> int:
    f = ((1 + 5 ** 0.5) / 2) ** n / 5 ** 0.5 + 0.5
    return int(f)


def cal_ewm(data: pd.Series, span: int) -> pd.Series:
    return data.ewm(span=span).mean()
