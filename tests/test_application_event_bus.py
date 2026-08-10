import threading
import unittest

from src.core.application_events import ApplicationEvent, ApplicationEventBus, PopupDismissedEvent


def event():
    return PopupDismissedEvent(source="test", popup_type="unknown", reason="user")


class ApplicationEventBusTests(unittest.TestCase):
    def test_order_base_subscription_duplicate_handler_and_idempotent_unsubscribe(self):
        bus = ApplicationEventBus(); calls = []
        handler = lambda value: calls.append(("same", value.event_type))
        base = bus.subscribe(ApplicationEvent, lambda _value: calls.append(("base", "")))
        first = bus.subscribe(PopupDismissedEvent, handler)
        bus.subscribe(PopupDismissedEvent, lambda _value: calls.append(("specific", "")))
        bus.subscribe(PopupDismissedEvent, handler)
        self.assertEqual(bus.publish(event()), 4)
        self.assertEqual([item[0] for item in calls], ["base", "same", "specific", "same"])
        self.assertTrue(bus.unsubscribe(first)); self.assertFalse(bus.unsubscribe(first))
        self.assertTrue(bus.unsubscribe(base)); self.assertEqual(bus.subscriber_count(), 2)
        bus.clear(); self.assertEqual(bus.subscriber_count(), 0)

    def test_subscriber_failure_isolated_and_nested_publish_supported(self):
        bus = ApplicationEventBus(max_publish_depth=3); calls = []
        bus.subscribe(PopupDismissedEvent, lambda _value: (_ for _ in ()).throw(RuntimeError()))
        bus.subscribe(PopupDismissedEvent, lambda value: calls.append(value.reason))
        self.assertEqual(bus.publish(event()), 2); self.assertEqual(calls, ["user"])
        nested = ApplicationEventBus(max_publish_depth=2); depths = []
        def again(value):
            depths.append(len(depths))
            nested.publish(value)
        nested.subscribe(PopupDismissedEvent, again)
        nested.publish(event())
        self.assertEqual(len(depths), 2)

    def test_disabled_and_concurrent_publish(self):
        disabled = ApplicationEventBus(enabled=False); calls = []
        disabled.subscribe(ApplicationEvent, calls.append)
        self.assertEqual(disabled.publish(event()), 0); self.assertFalse(calls)
        bus = ApplicationEventBus(); lock = threading.Lock(); count = 0
        def receive(_value):
            nonlocal count
            with lock: count += 1
        bus.subscribe(ApplicationEvent, receive)
        threads = [threading.Thread(target=lambda: [bus.publish(event()) for _ in range(50)])
                   for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(count, 200)


if __name__ == "__main__": unittest.main()
