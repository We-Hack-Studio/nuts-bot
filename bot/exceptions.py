class BotException(Exception):
    pass


class TradingException(BotException):
    pass


class ConfigException(BotException):
    pass


class ImproperConfig(ConfigException):
    pass


class UnsupportedMarketType(ImproperConfig):
    pass


class UnsupportedExchange(ImproperConfig):
    pass


class InvalidParameter(BotException):
    pass


class RiskControlException(InvalidParameter):
    pass


class PositionException(BotException):
    pass


class ExchangeException(BotException):
    pass


class ServerUnavailable(BotException):
    pass
