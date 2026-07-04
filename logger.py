"""Centralized logging for SmartVersa. Replaces scattered print() calls."""

import logging
import sys
import functools

from config import Config

_LEVEL = getattr(logging, str(Config.LOG_LEVEL).upper(), logging.INFO)

logging.basicConfig(
    level=_LEVEL,
    stream=sys.stdout,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger("smartversa")


def safe(default=None, label=""):
    """
    Decorator: run a function, and if it raises, log the traceback and return
    `default` instead of crashing the request/webhook. Keeps the bot alive.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                log.exception("Handled error in %s", label or fn.__name__)
                return default
        return wrapper
    return deco
