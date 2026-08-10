import unittest

from src.core.application_events import (
    ApplicationEventBus, ApplicationEventDiagnosticsStore, PopupDismissedEvent,
)
from src.ui.main import build_application_events


class ApplicationEventDiagnosticsTests(unittest.TestCase):
    def test_bounded_scalar_projection_and_clear(self):
        store = ApplicationEventDiagnosticsStore(limit=2)
        for reason in ("one", "two", "three"):
            store.record(PopupDismissedEvent(source=reason, popup_type="unknown", reason=reason))
        values = store.snapshot()
        self.assertEqual([value.source for value in values], ["two", "three"])
        self.assertEqual(set(values[0].__slots__), {"event_type", "timestamp", "source"})
        store.clear(); self.assertEqual(store.snapshot(), ())

    def test_composition_enabled_and_disabled(self):
        bus, diagnostics = build_application_events({
            "application_events": {"enabled": True, "max_diagnostic_events": 3}
        })
        self.assertIsInstance(bus, ApplicationEventBus)
        bus.publish(PopupDismissedEvent(source="test", popup_type="x", reason="user"))
        self.assertEqual(len(diagnostics.snapshot()), 1)
        self.assertEqual(build_application_events({
            "application_events": {"enabled": False, "max_diagnostic_events": 3}
        }), (None, None))


if __name__ == "__main__": unittest.main()
