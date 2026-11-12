import logging
import os
import time
from functools import wraps
from typing import Callable, ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")
logger = logging.getLogger("docguard.timing")
if os.environ.get("DOCGUARD_TIMING") == "1":
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())
    logger.propagate = False


def timed(stage: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def measure(*args: P.args, **kwargs: P.kwargs) -> R:
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                logger.info("%s duration_seconds=%.6f", stage, time.perf_counter() - started)
        return measure
    return decorate
