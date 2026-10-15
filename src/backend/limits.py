import asyncio
import time
from typing import Any
from datetime import timedelta
from collections.abc import Callable

from backend.gate import BusyError
from starlette.concurrency import run_in_threadpool


_MAX_KEYS = 10_000

class RateLimitedError(Exception):
    # Same shape as AccountLockerError
    def __init__(self , retry_after : timedelta):
        super().__init__()
        self.retry_after = retry_after
        
class RateLimiter:
    # Token bucket per key. Memory only : every woker counts on its own
    
    def __init__(
        self,
        burst : int,
        per_minute : float,
        clock : Callable[[], float] = time.monotonic,
    ) -> None:
        self._burst = burst
        self._rate = per_minute / 60.0
        self._clock = clock
        self._buckets : dict[str , tuple[float , float]] = {} # key -> {tokens , last_seen}
        
    
    def hit(self , key : str) -> None:
        now = self._clock()
        tokens , last = self._buckets.get(key , (float(self._burst) , now))
        tokens = min(float(self._burst) , tokens + (now - last) * self._rate)
        
        if tokens < 1:
            self._buckets[key] = (tokens , now)
            raise RateLimitedError(timedelta(seconds=(1 - tokens) / self._rate))
        
        self._buckets[key] = (tokens - 1 , now)
        if len(self._buckets) > _MAX_KEYS:
            self._drop_idle(now)
            
    def _drop_idle(self , now : float) -> None:
        self._buckets = {
            k : (t , s)
            for k , (t , s) in self._buckets.items()
            if t + (now - s) * self._rate < self._burst
        }
        

class HashGate:
    # Bounds concurrent password hashes. Wait too long for a slot -> BusyError
    
    def __init__(self , concurrency : int = 4 , queue_timeout_s : float = 2.0) -> None:
        self._slots = asyncio.Semaphore(concurrency)
        self._queue_timeout_s = queue_timeout_s
        
    
    async def run(self , func : Callable[... , Any] , *args : Any) -> Any:
        try:
            await asyncio.wait_for(self._slots.acquire() , self._queue_timeout_s)
        except asyncio.TimeoutError:
            raise BusyError() from None
        
        try: return await run_in_threadpool(func , *args)
        finally: self._slots.release()
        