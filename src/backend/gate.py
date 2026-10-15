# Capacity gate for the slow AI work: bounded concurrency plus time limits
import asyncio
from collections.abc import Callable
from threading import BoundedSemaphore
from typing import Any


class BusyError(Exception):
    """No free slot appeared within the queue timeout."""


class AiTimeoutError(Exception):
    """The work did not finish within the run timeout."""


class Gate:
    def __init__(
        self, concurrency: int = 2, queue_timeout_s: float = 5.0, run_timeout_s: float = 30.0
    ) -> None:
        self._slots = BoundedSemaphore(concurrency)
        self._queue_timeout_s = queue_timeout_s
        self._run_timeout_s = run_timeout_s

    def _call(self, fn: Callable[..., Any], args : tuple) -> Any:
        if not self._slots.acquire(timeout=self._queue_timeout_s):
            raise BusyError
        try:
            return fn(*args)
        finally:
            # Released by the thread itself, so a request that timed out keeps its
            # slot until the work really ends. Threads cannot be killed.
            self._slots.release()

    async def run(self, fn: Callable[..., Any], *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, self._call, fn, args)
        try:
            # run_timeout_s is the total deadline, including the wait for a slot
            return await asyncio.wait_for(future, self._run_timeout_s)
        except asyncio.TimeoutError:
            raise AiTimeoutError from None