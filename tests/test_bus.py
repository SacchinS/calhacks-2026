import asyncio

from shared.bus import Bus
from shared.events import Caption, ModeChanged, SignEvent


async def test_subscriber_gets_only_its_types():
    bus = Bus()
    signs = bus.subscribe(SignEvent)
    bus.publish(ModeChanged("voice"))
    bus.publish(SignEvent("HELLO", 0.9, "isolated"))
    event = await asyncio.wait_for(signs.get(), 1)
    assert event.gloss == "HELLO"
    assert signs.queue.empty()


async def test_subscribe_all_and_multiple_subscribers():
    bus = Bus()
    everything = bus.subscribe()
    captions_a = bus.subscribe(Caption)
    captions_b = bus.subscribe(Caption, ModeChanged)
    bus.publish(Caption("hi"))
    bus.publish(ModeChanged("meet"))
    assert everything.queue.qsize() == 2
    assert captions_a.queue.qsize() == 1
    assert captions_b.queue.qsize() == 2


async def test_unsubscribe_stops_delivery():
    bus = Bus()
    sub = bus.subscribe(Caption)
    sub.close()
    bus.publish(Caption("hi"))
    assert sub.queue.empty()


async def test_bounded_queue_drops_oldest():
    bus = Bus()
    sub = bus.subscribe(Caption, maxsize=2)
    for text in ("a", "b", "c"):
        bus.publish(Caption(text))
    assert [sub.get_nowait().text, sub.get_nowait().text] == ["b", "c"]


async def test_async_iteration():
    bus = Bus()
    sub = bus.subscribe(Caption)
    bus.publish(Caption("one"))
    async for event in sub:
        assert event.text == "one"
        break
