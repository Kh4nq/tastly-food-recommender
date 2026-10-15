import asyncio
import time
from threading import Event, Lock

import pytest

from backend.gate import AiTimeoutError, BusyError, Gate


def test_returns_the_result():
    assert asyncio.run(Gate().run(lambda a, b: a + b, 1, 2)) == 3


def test_errors_propagate_and_free_the_slot():
    gate = Gate(concurrency=1, queue_timeout_s=0.2)

    def boom():
        raise ValueError("bad")

    async def scenario():
        with pytest.raises(ValueError):
            await gate.run(boom)
        return await gate.run(lambda: "still works")

    assert asyncio.run(scenario()) == "still works"


def test_never_runs_more_than_the_limit_at_once():
    gate = Gate(concurrency=2, queue_timeout_s=5)
    lock, state = Lock(), {"now": 0, "max": 0}

    def work():
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.05)
        with lock:
            state["now"] -= 1

    async def scenario():
        await asyncio.gather(*(gate.run(work) for _ in range(8)))

    asyncio.run(scenario())
    assert state["max"] == 2


def test_busy_when_no_slot_frees_up_in_time():
    gate = Gate(concurrency=1, queue_timeout_s=0.05, run_timeout_s=5)
    release = Event()

    async def scenario():
        first = asyncio.create_task(gate.run(release.wait, 5))
        await asyncio.sleep(0.05)  # let the first call take the only slot
        with pytest.raises(BusyError):
            await gate.run(lambda: None)
        release.set()
        await first

    asyncio.run(scenario())


def test_timeout_answers_early_but_the_slot_stays_held_until_the_work_ends():
    gate = Gate(concurrency=1, queue_timeout_s=0.05, run_timeout_s=0.3)
    release = Event()

    async def scenario():
        with pytest.raises(AiTimeoutError):
            await gate.run(release.wait, 5)
        # The abandoned thread still holds the slot, so the next call is refused
        with pytest.raises(BusyError):
            await gate.run(lambda: None)
        release.set()
        await asyncio.sleep(0.1)  # let the abandoned thread finish
        return await gate.run(lambda: "free again")

    assert asyncio.run(scenario()) == "free again"