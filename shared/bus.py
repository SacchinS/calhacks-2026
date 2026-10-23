"""Tiny in-process pub/sub on asyncio queues.

    bus = Bus()
    sub = bus.subscribe(SignEvent)        # or bus.subscribe() for every event
    bus.publish(SignEvent("HELLO", 0.9, "isolated"))
    event = await sub.get()
    async for event in sub: ...

Subscriptions match by isinstance, so `subscribe(object)` also gets everything.
"""

from __future__ import annotations

import asyncio
from typing import Any


class Subscription:
    def __init__(self, bus: Bus, types: tuple[type, ...], maxsize: int) -> None:
        self._bus = bus
        self.types = types
        self.queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=maxsize)

    def matches(self, event: Any) -> bool:
        return not self.types or isinstance(event, self.types)

    def put(self, event: Any) -> None:
        if self.queue.full():  # bounded queue: drop the oldest event, keep the newest
            self.queue.get_nowait()
        self.queue.put_nowait(event)

    async def get(self) -> Any:
        return await self.queue.get()

    def get_nowait(self) -> Any:
        return self.queue.get_nowait()

    def close(self) -> None:
        self._bus.unsubscribe(self)

    def __aiter__(self) -> Subscription:
        return self

    async def __anext__(self) -> Any:
        return await self.queue.get()


class Bus:
    def __init__(self) -> None:
        self._subs: list[Subscription] = []

    def subscribe(self, *types: type, maxsize: int = 0) -> Subscription:
        """Subscribe to events of the given types (all events if none). 0 = unbounded."""
        sub = Subscription(self, types, maxsize)
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        if sub in self._subs:
            self._subs.remove(sub)

    def publish(self, event: Any) -> None:
        """Deliver to every matching subscriber. Never blocks; safe from any coroutine."""
        for sub in list(self._subs):
            if sub.matches(event):
                sub.put(event)
