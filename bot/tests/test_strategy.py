import pytest

from bot.strategy import Indicator, OrderType, Side, Strategy


@pytest.mark.parametrize(
    "n,base_price,offset_factor,side,expected_order",
    [
        # buy
        (
            1,
            350.5,
            0.01,
            1,
            {
                "pair": "ETHUSDT",
                "order_type": OrderType.limit,
                "price": 350.49,
                "side": 1,
                "qty": 0.5,
            },
        ),
        (
            2,
            350.5,
            0.01,
            1,
            {
                "pair": "ETHUSDT",
                "order_type": OrderType.limit,
                "price": 350.49,
                "side": 1,
                "qty": 0.5,
            },
        ),
        (
            3,
            350.5,
            0.01,
            1,
            {
                "pair": "ETHUSDT",
                "order_type": OrderType.limit,
                "price": 350.48,
                "side": 1,
                "qty": 0.5,
            },
        ),
        (
            4,
            350.5,
            0.01,
            1,
            {
                "pair": "ETHUSDT",
                "order_type": OrderType.limit,
                "price": 350.47,
                "side": 1,
                "qty": 0.5,
            },
        ),
        # sell
        (
            1,
            350.5,
            0.01,
            -1,
            {
                "pair": "ETHUSDT",
                "order_type": OrderType.limit,
                "price": 350.51,
                "side": -1,
                "qty": 0.5,
            },
        ),
        (
            2,
            350.5,
            0.01,
            -1,
            {
                "pair": "ETHUSDT",
                "order_type": OrderType.limit,
                "price": 350.51,
                "side": -1,
                "qty": 0.5,
            },
        ),
        (
            3,
            350.5,
            0.01,
            -1,
            {
                "pair": "ETHUSDT",
                "order_type": OrderType.limit,
                "price": 350.52,
                "side": -1,
                "qty": 0.5,
            },
        ),
        (
            4,
            350.5,
            0.01,
            -1,
            {
                "pair": "ETHUSDT",
                "order_type": OrderType.limit,
                "price": 350.53,
                "side": -1,
                "qty": 0.5,
            },
        ),
    ],
)
def test_get_fib_order(
    n,
    base_price,
    offset_factor,
    side,
    expected_order,
):
    strategy = Strategy.new()
    assert (
        strategy.get_fib_order(
            n=n,
            base_price=base_price,
            offset_factor=offset_factor,
            side=side,
        )
        == expected_order
    )


def test_get_stop_loss_order():
    # short position
    position = {
        "qty": 1.5,
        "side": Side.short,
        "liq_price": 0.0,
        "avg_price": 340.1,
        "unrealized_pnl": 0.0,
    }
    strategy = Strategy.new(position=position)
    sl_order = strategy.get_stop_loss_order()
    expected = {
        "pair": "ETHUSDT",
        "order_type": OrderType.trigger,
        "price": 350.1,
        "side": Side.long,
        "qty": 1.5,
    }
    assert sl_order == expected

    # long position
    position = {
        "qty": 1.5,
        "side": Side.long,
        "liq_price": 0.0,
        "avg_price": 340.1,
        "unrealized_pnl": 0.0,
    }
    strategy = Strategy.new(position=position)
    sl_order = strategy.get_stop_loss_order()
    expected = {
        "pair": "ETHUSDT",
        "order_type": OrderType.trigger,
        "price": 330.1,
        "side": Side.short,
        "qty": 1.5,
    }
    assert sl_order == expected


def test_get_take_profit_order():
    # short position
    position = {
        "qty": 1.5,
        "side": Side.short,
        "liq_price": 0.0,
        "avg_price": 340.1,
        "unrealized_pnl": 0.0,
    }
    strategy = Strategy.new(position=position)
    tp_order = strategy.get_take_profit_order()
    expected = {
        "pair": "ETHUSDT",
        "order_type": OrderType.limit,
        "price": 339.6,
        "side": Side.long,
        "qty": 1.5,
    }
    assert tp_order == expected

    # long position
    position = {
        "qty": 1.5,
        "side": Side.long,
        "liq_price": 0.0,
        "avg_price": 340.1,
        "unrealized_pnl": 0.0,
    }
    strategy = Strategy.new(position=position)
    tp_order = strategy.get_take_profit_order()
    expected = {
        "pair": "ETHUSDT",
        "order_type": OrderType.limit,
        "price": 340.6,
        "side": Side.short,
        "qty": 1.5,
    }
    assert tp_order == expected


def test_sync_store():
    # linear contract
    strategy = Strategy.new()
    strategy.set_trading_context(
        {
            "market_type": "linear_perpetual",
            "qty_precision": 3,
        }
    )
    strategy._balance = 10000
    strategy.parameters = {
        "openPosPercent": 0.01,
        "maxLeverage": 3,
        "maxOpenPosCount": 10,
    }
    strategy.sync_store(last_price=350)
    assert strategy.store == {
        "open_pos_qty": 0.857,
        "max_pos_qty": 8.571,
    }

    strategy.parameters = {
        "openPosPercent": 0.01,
        "maxLeverage": 3,
        "maxOpenPosCount": 100000,
    }
    strategy.sync_store(last_price=350)
    assert strategy.store == {
        "open_pos_qty": 0.857,
        "max_pos_qty": 85.714,
    }

    # inverse contract
    strategy.set_trading_context({"market_type": "inverse_perpetual"})
    strategy._balance = 1.5
    strategy.parameters = {
        "openPosPercent": 0.01,
        "maxLeverage": 3,
        "maxOpenPosCount": 10,
    }
    strategy.sync_store(last_price=350)
    assert strategy.store == {
        "open_pos_qty": 15,
        "max_pos_qty": 150,
    }

    strategy.parameters = {
        "openPosPercent": 0.01,
        "maxLeverage": 3,
        "maxOpenPosCount": 100000,
    }
    strategy.sync_store(last_price=350)
    assert strategy.store == {
        "open_pos_qty": 15,
        "max_pos_qty": 1575,
    }


def test_prepare_open_pos_orders():
    # linear contract
    strategy = Strategy.new()
    strategy.set_trading_context(
        {
            "market_type": "linear_perpetual",
            "qty_precision": 3,
            "price_tick": 0.01,
        }
    )
    strategy._balance = 10000
    strategy.parameters = {
        "openPosPercent": 0.01,
        "maxLeverage": 3,
        "maxOpenPosCount": 10,
        "longAdditionDistance": 0.05,
        "shortAdditionDistance": 0.05,
    }
    strategy.sync_store(last_price=350)
    # long
    orders = strategy.prepare_open_pos_orders(side=1, base_price=350)
    expected = [
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.99,
            "side": 1,
            "qty": 0.857,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.98,
            "side": 1,
            "qty": 0.857,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.95,
            "side": 1,
            "qty": 0.857,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.95,
            "side": 1,
            "qty": 0.857,
        },
    ]
    assert sorted(orders, key=lambda o: o["price"]) == sorted(
        expected, key=lambda o: o["price"]
    )

    # short
    orders = strategy.prepare_open_pos_orders(side=-1, base_price=350)
    expected = [
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.01,
            "side": -1,
            "qty": 0.857,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.02,
            "side": -1,
            "qty": 0.857,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.05,
            "side": -1,
            "qty": 0.857,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.05,
            "side": -1,
            "qty": 0.857,
        },
    ]
    assert sorted(orders, key=lambda o: o["price"]) == sorted(
        expected, key=lambda o: o["price"]
    )

    # inverse contract
    strategy.set_trading_context({"market_type": "inverse_perpetual"})
    strategy._balance = 1.5
    strategy.parameters = {
        "openPosPercent": 0.01,
        "maxLeverage": 3,
        "maxOpenPosCount": 10,
    }
    strategy.sync_store(last_price=350)

    # long
    orders = strategy.prepare_open_pos_orders(side=1, base_price=350)
    expected = [
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.99,
            "side": 1,
            "qty": 15,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.98,
            "side": 1,
            "qty": 15,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.95,
            "side": 1,
            "qty": 15,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.95,
            "side": 1,
            "qty": 15,
        },
    ]
    assert sorted(orders, key=lambda o: o["price"]) == sorted(
        expected, key=lambda o: o["price"]
    )

    # short
    orders = strategy.prepare_open_pos_orders(side=-1, base_price=350)
    expected = [
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.01,
            "side": -1,
            "qty": 15,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.02,
            "side": -1,
            "qty": 15,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.05,
            "side": -1,
            "qty": 15,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.05,
            "side": -1,
            "qty": 15,
        },
    ]
    assert sorted(orders, key=lambda o: o["price"]) == sorted(
        expected, key=lambda o: o["price"]
    )


def test_prepare_add_pos_orders():
    # linear contract
    # long position
    position = {
        "qty": 1.5,
        "side": 1,
        "liq_price": 0,
        "avg_price": 359.1,
        "unrealized_pnl": 0.0,
    }
    strategy = Strategy.new(position=position)
    strategy.set_trading_context(
        {
            "market_type": "linear_perpetual",
            "qty_precision": 3,
            "price_tick": 0.01,
        }
    )
    strategy._balance = 10000
    strategy.parameters = {
        "openPosPercent": 0.01,
        "maxLeverage": 3,
        "maxOpenPosCount": 10,
        "longAdditionDistance": 0.05,
        "shortAdditionDistance": 0.05,
        "longTakeProfitDistance": 0.5,
        "shortTakeProfitDistance": 0.5,
        "longStopLossDistance": 10,
        "shortStopLossDistance": 10,
    }
    strategy.sync_store(last_price=350)
    orders = strategy.prepare_add_pos_orders(side=1, base_price=350)
    expected = [
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.trigger,
            "price": 349.1,
            "side": -1,
            "qty": 1.5,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 359.6,
            "side": -1,
            "qty": 1.5,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.95,
            "side": 1,
            "qty": 0.857,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.95,
            "side": 1,
            "qty": 0.857,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.9,
            "side": 1,
            "qty": 0.857,
        },
    ]
    assert sorted(orders, key=lambda o: o["price"]) == sorted(
        expected, key=lambda o: o["price"]
    )

    # short position
    position = {
        "qty": 1.5,
        "side": -1,
        "liq_price": 999999,
        "avg_price": 349.1,
        "unrealized_pnl": 0.0,
    }
    strategy = Strategy.new(position=position)
    strategy.set_trading_context(
        {
            "market_type": "linear_perpetual",
            "qty_precision": 3,
            "price_tick": 0.01,
        }
    )
    strategy._balance = 10000
    strategy.parameters = {
        "openPosPercent": 0.01,
        "maxLeverage": 3,
        "maxOpenPosCount": 10,
        "longAdditionDistance": 0.05,
        "shortAdditionDistance": 0.05,
        "longTakeProfitDistance": 0.5,
        "shortTakeProfitDistance": 0.5,
        "longStopLossDistance": 10,
        "shortStopLossDistance": 10,
    }
    strategy.sync_store(last_price=350)
    orders = strategy.prepare_add_pos_orders(side=-1, base_price=350)
    expected = [
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.trigger,
            "price": 359.1,
            "side": 1,
            "qty": 1.5,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 348.6,
            "side": 1,
            "qty": 1.5,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.05,
            "side": -1,
            "qty": 0.857,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.05,
            "side": -1,
            "qty": 0.857,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.1,
            "side": -1,
            "qty": 0.857,
        },
    ]
    assert sorted(orders, key=lambda o: o["price"]) == sorted(
        expected, key=lambda o: o["price"]
    )

    # inverse contract
    # long position
    position = {
        "qty": 1000,
        "side": 1,
        "liq_price": 0,
        "avg_price": 359.1,
        "unrealized_pnl": 0.0,
    }
    strategy = Strategy.new(position=position)
    strategy.set_trading_context(
        {
            "market_type": "inverse_perpetual",
            "price_tick": 0.01,
        }
    )
    strategy._balance = 1.5
    strategy.parameters = {
        "openPosPercent": 0.01,
        "maxLeverage": 3,
        "maxOpenPosCount": 10,
        "longAdditionDistance": 0.05,
        "shortAdditionDistance": 0.05,
        "longTakeProfitDistance": 0.5,
        "shortTakeProfitDistance": 0.5,
        "longStopLossDistance": 10,
        "shortStopLossDistance": 10,
    }
    strategy.sync_store(last_price=350)
    orders = strategy.prepare_add_pos_orders(side=1, base_price=350)
    expected = [
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.trigger,
            "price": 349.1,
            "side": -1,
            "qty": 1000,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 359.6,
            "side": -1,
            "qty": 1000,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.95,
            "side": 1,
            "qty": 15,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.95,
            "side": 1,
            "qty": 15,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 349.9,
            "side": 1,
            "qty": 15,
        },
    ]
    assert sorted(orders, key=lambda o: o["price"]) == sorted(
        expected, key=lambda o: o["price"]
    )

    # short position
    position = {
        "qty": 1000,
        "side": -1,
        "liq_price": 999999,
        "avg_price": 349.1,
        "unrealized_pnl": 0.0,
    }
    strategy = Strategy.new(position=position)
    strategy.set_trading_context(
        {
            "market_type": "inverse_perpetual",
            "price_tick": 0.01,
        }
    )
    strategy._balance = 1.5
    strategy.parameters = {
        "openPosPercent": 0.01,
        "maxLeverage": 3,
        "maxOpenPosCount": 10,
        "longAdditionDistance": 0.05,
        "shortAdditionDistance": 0.05,
        "longTakeProfitDistance": 0.5,
        "shortTakeProfitDistance": 0.5,
        "longStopLossDistance": 10,
        "shortStopLossDistance": 10,
    }
    strategy.sync_store(last_price=350)
    orders = strategy.prepare_add_pos_orders(side=-1, base_price=350)
    expected = [
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.trigger,
            "price": 359.1,
            "side": 1,
            "qty": 1000,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 348.6,
            "side": 1,
            "qty": 1000,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.05,
            "side": -1,
            "qty": 15,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.05,
            "side": -1,
            "qty": 15,
        },
        {
            "pair": "ETHUSDT",
            "order_type": OrderType.limit,
            "price": 350.1,
            "side": -1,
            "qty": 15,
        },
    ]
    assert sorted(orders, key=lambda o: o["price"]) == sorted(
        expected, key=lambda o: o["price"]
    )


class TestShouldTrade:
    def test_exceeds_max_rw(self):
        strategy = Strategy.new()
        strategy.parameters = {
            "maxRw": 0.12,
        }
        result = strategy.should_trade(Indicator(1, 0.121))
        assert result.code == 0
        assert "exceeds maxRw" in result.reason

    def test_no_side(self):
        strategy = Strategy.new()
        strategy.parameters = {
            "maxRw": 0.12,
        }
        result = strategy.should_trade(Indicator(0, 0.1))
        assert result.code == 0
        assert result.reason == "No indicator side"

    def test_opposite_side(self):
        position = {
            "qty": 1000,
            "side": -1,
            "liq_price": 999999,
            "avg_price": 349.1,
            "unrealized_pnl": 0.0,
        }
        strategy = Strategy.new(position=position)
        strategy.parameters = {
            "maxRw": 0.12,
        }
        result = strategy.should_trade(Indicator(1, 0.1))
        assert result.code == 0
        assert (
            result.reason
            == "Current holding position side is opposite to indicator side"
        )

    def test_(self):
        position = {
            "qty": 1000,
            "side": -1,
            "liq_price": 999999,
            "avg_price": 349.1,
            "unrealized_pnl": 0.1,
        }
        strategy = Strategy.new(position=position)
        strategy.parameters = {
            "maxRw": 0.12,
        }
        result = strategy.should_trade(Indicator(-1, 0.1))
        assert result.code == 0
        assert "In profit" in result.reason

    def test_disallow_long(self):
        strategy = Strategy.new()
        strategy.parameters = {
            "allowLong": False,
            "allowShort": True,
        }
        result = strategy.should_trade(Indicator(1, 0.1))
        assert result.code == 0
        assert result.reason == "Disallow long side"

    def test_disallow_short(self):
        strategy = Strategy.new()
        strategy.parameters = {
            "allowShort": False,
            "allowLong": True,
        }
        result = strategy.should_trade(Indicator(-1, 0.1))
        assert result.code == 0
        assert result.reason == "Disallow short side"

    def test_exceeds_max_qty(self):
        position = {
            "qty": 9,
            "side": -1,
            "liq_price": 999999,
            "avg_price": 349.1,
            "unrealized_pnl": 0.0,
        }
        strategy = Strategy.new(position=position)
        strategy.set_trading_context(
            {
                "market_type": "linear_perpetual",
                "qty_precision": 3,
            }
        )
        strategy._balance = 10000
        strategy.parameters = {
            "openPosPercent": 0.01,
            "maxLeverage": 3,
            "maxOpenPosCount": 10,
            "maxRw": 0.12,
            "allowShort": True,
            "allowLong": True,
        }
        strategy.sync_store(last_price=350)
        assert strategy.store == {
            "open_pos_qty": 0.857,
            "max_pos_qty": 8.571,
        }
        result = strategy.should_trade(Indicator(-1, 0.1))
        assert result.code == 0
        assert result.reason == "Current holding position qty exceeds allowed max value"

    def test_pass_all_checks(self):
        position = {
            "qty": 8,
            "side": -1,
            "liq_price": 999999,
            "avg_price": 349.1,
            "unrealized_pnl": 0.0,
        }
        strategy = Strategy.new(position=position)
        strategy.set_trading_context(
            {
                "market_type": "linear_perpetual",
                "qty_precision": 3,
            }
        )
        strategy._balance = 10000
        strategy.parameters = {
            "openPosPercent": 0.01,
            "maxLeverage": 3,
            "maxOpenPosCount": 10,
            "maxRw": 0.12,
            "allowShort": True,
            "allowLong": True,
        }
        strategy.sync_store(last_price=350)
        assert strategy.store == {
            "open_pos_qty": 0.857,
            "max_pos_qty": 8.571,
        }
        assert strategy.should_trade(Indicator(-1, 0.1)).code == 1
