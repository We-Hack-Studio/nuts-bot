import logging
import logging.config
import os
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "default": {
            "format": "%(levelname)s %(asctime)s %(module)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "level": logging.DEBUG,
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
        "file": {
            "level": logging.DEBUG,
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "default",
            "filename": os.path.join(BASE_DIR, ".logs", "bot.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 30,
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "bot": {
            "handlers": ["console", "file"],
            "level": logging.DEBUG,
        },
        "yufuquantsdk": {
            "handlers": ["console"],
            "level": logging.DEBUG,
        },
    },
}


def config_logging():
    Path(".logs/bot.log").parent.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(DEFAULT_LOGGING)
