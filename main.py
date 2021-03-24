import argparse
import asyncio
import json
import logging
import pathlib
from typing import Optional

from yufuquantsdk.clients import RESTAPIClient, WebsocketAPIClient

from bot.exceptions import (
    ConfigException,
    ExchangeException,
    ImproperConfig,
    InvalidParameter,
    TradingException,
    UnsupportedExchange,
)
from bot.exchanges import exchange_factory
from bot.log import config_logging
from bot.strategy import Strategy

logger = logging.getLogger("bot")


# todo: clean up


class Bot:
    def __init__(self, config):
        self._config = config
        self._robot_id = config["robotId"]
        self._rest_client = RESTAPIClient(
            base_url=config["restApiBaseUrl"],
            api_key=config["apiKey"],
        )
        self._ws_client = WebsocketAPIClient(
            uri=config["wsApiUri"],
        )
        self._strategy: Optional[Strategy] = None

    async def _prepare(self):
        await self._ws_client.auth(self._config["apiKey"])
        await self._ws_client.sub(topics=[f"robot#{self._robot_id}.log"])
        robot = await self._rest_client.get_robot(self._robot_id)
        credential_key = await self._rest_client.get_robot_credential_key(
            self._robot_id
        )

        exchange_code = robot["exchange"]["code"]
        exchange_cls = exchange_factory(exchange_code)
        if exchange_cls is None:
            raise UnsupportedExchange(
                "Unsupported exchange: {}".format(robot["exchange"]["name"])
            )
        exchange = exchange_cls()
        exchange.set_market_type(market_type=robot["market_type"])
        if robot["test_net"]:
            exchange.use_test_net()
        exchange.auth(credential_key=credential_key)
        await exchange.prepare()

        pair = robot["pair"]
        trading_context = {
            "pair": pair,
            "target_currency": robot["target_currency"],
            "market_type": robot["market_type"],
            "price_precision": exchange.price_precision(pair),
            "price_tick": exchange.price_ticker(pair),
            "qty_precision": exchange.qty_precision(pair),
        }
        trading_context_msg = (
            "Current trading context {pair: %s, target_currency: %s, market_type: %s, "
            "price_precision: %d,qty_precision: %d, price_tick: %f}"
            % (
                trading_context["pair"],
                trading_context["target_currency"],
                trading_context["market_type"],
                trading_context["price_precision"],
                trading_context["qty_precision"],
                trading_context["price_tick"],
            )
        )
        logger.info(trading_context_msg)
        await self._ws_client.robot_log(trading_context_msg)
        self._strategy = Strategy(exchange)
        self._strategy.set_trading_context(trading_context)

        asyncio.get_event_loop().create_task(self.ping_task())
        asyncio.get_event_loop().create_task(self.feedback_task())
        asyncio.get_event_loop().create_task(self.log_task())
        asyncio.get_event_loop().create_task(self.report())

    async def ping_task(self):
        while True:
            await asyncio.sleep(5)
            try:
                await self._rest_client.ping_robot(self._robot_id)
                # await self._ws_client.robot_log("ping")
            except Exception as exc:
                logger.exception(exc)

    async def log_task(self):
        while True:
            try:
                msg = await self._strategy.log_queue.get()
                await self._ws_client.robot_log(text=msg)
            except Exception as exc:
                logger.exception(exc)

    async def feedback_task(self):
        while True:
            await asyncio.sleep(5)
            try:
                data = {"total_balance": self._strategy.balance}
                await self._rest_client.update_robot_asset_record(
                    self._robot_id, data=data
                )
                # print('self._strategy.position', self._strategy.position)
                if self._strategy.position["side"] != 0:
                    data = [
                        {
                            "side": self._strategy.position["side"],
                            "qty": self._strategy.position["qty"],
                            "avgPrice": self._strategy.position["avg_price"],
                            "liqPrice": self._strategy.position["liq_price"],
                            "unrealizedPnl": self._strategy.position["unrealized_pnl"],
                        }
                    ]
                    await self._rest_client.update_robot_position_store(
                        self._robot_id,
                        data=data,
                    )
                    await self._ws_client.robot_position_store(positions=data)
                else:
                    await self._rest_client.update_robot_position_store(
                        self._robot_id,
                        data=[],
                    )
                    await self._ws_client.robot_position_store(positions=[])
            except Exception as exc:
                logger.exception(exc)

    async def report(self):
        while True:
            await asyncio.sleep(30)
            try:
                basic_msg = "总况 <pair: {}, target_currency: {}>".format(
                    self._strategy.pair,
                    self._strategy.trading_context["target_currency"],
                )
                logger.info(basic_msg)
                await self._ws_client.robot_log(basic_msg)

                position_msg = "当前持仓情况：{}@{}，强平价格：{}".format(
                    self._strategy.position["side"] * self._strategy.position["qty"],
                    self._strategy.position["avg_price"],
                    self._strategy.position["liq_price"],
                )
                logger.info(position_msg)
                await self._ws_client.robot_log(position_msg)

                store_msg = "Store：{}".format(self._strategy.store)
                logger.info(store_msg)
                await self._ws_client.robot_log(store_msg)
            except Exception as exc:
                logger.exception(exc)

    async def start(self):
        await self._prepare()
        logger.info("Robot is ready to start")
        await self._ws_client.robot_log("机器人正在启动...")
        while True:
            try:
                robot = await self._rest_client.get_robot(self._robot_id)
                if not robot["enabled"]:
                    logger.info("Robot it not enabled")
                    await self._ws_client.robot_log("未开启机器人...")
                    await asyncio.sleep(10)
                    continue

                parameters = await self._rest_client.get_robot_strategy_parameters(
                    self._robot_id
                )
                self._strategy.parameters = parameters
                await self._strategy.trade_once()
            except InvalidParameter as exc:
                logger.error(exc)
            except ExchangeException as exc:
                logger.error(exc)
            except TradingException as exc:
                logger.error(exc)
            except ImproperConfig as exc:
                logger.exception(exc)
                break
            except KeyboardInterrupt:
                logger.info("Ctrl + c pressed, stop trading...")
                await self._strategy.ensure_order()
                break
            except Exception as exc:
                logger.exception(
                    "Unexpected exception (%s) occurred, stop trading...",
                    exc.__class__.__name__,
                )
                await self._ws_client.robot_log(
                    "Unexpected exception (%s) occurred, stop trading..."
                    % (exc.__class__.__name__,),
                )
                await self._strategy.ensure_order()
                # break

            await asyncio.sleep(10)

    def run(self):
        logger.info("Starting robot...")
        loop = asyncio.get_event_loop()
        loop.set_debug(enabled=False)
        # note: asyncio.run doesn't work? why?
        loop.run_until_complete(self.start())
        loop.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run dynamic grid robot.")
    parser.add_argument("--config-file", default="config.json")

    # load settings
    args = parser.parse_args()
    config_file = pathlib.Path(args.config_file)
    # print('config_file', config_file)
    if not config_file.exists():
        raise ConfigException(
            "Config file does not exist. Searching path is: {}".format(config_file)
        )
    text = config_file.read_text(encoding="utf-8")
    bot_config = json.loads(text)

    config_logging()

    # start bot
    bot = Bot(config=bot_config)
    bot.run()
