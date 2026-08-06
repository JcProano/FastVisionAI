from __future__ import annotations

import unittest
import numpy as np

from src.camera.frame import Frame
from src.engine.backends.simulated import SimulatedInferenceBackend
from src.engine.capabilities.contracts import Capability
from src.engine.capabilities.registry import CapabilitiesRegistry
from src.engine.config import SimulatedDetectorConfig
from src.engine.contracts.inference_context import InferenceContext
from src.engine.detectors.simulated import SimulatedDetector
from src.engine.events.bus import EventBus, ExternalEventBus, InternalEventBus
from src.engine.events.contracts import Event, RuntimeEvent
from src.engine.plugins.contracts import PluginDescriptor
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.runtime.model_runtime import ModelRuntime, RuntimeState
from src.engine.runtime.registry import RuntimeRegistry


class RuntimeLayerTests(unittest.TestCase):
    def backend(self):
        return SimulatedInferenceBackend(SimulatedDetector(SimulatedDetectorConfig()))

    def test_registry_and_runtime_lifecycle(self):
        registry = RuntimeRegistry()
        registry.register("test", lambda settings: self.backend())
        with self.assertRaises(ValueError):
            registry.register("test", lambda settings: self.backend())
        events = []
        bus = EventBus()
        bus.subscribe(Event, events.append)
        self.assertIsInstance(bus, InternalEventBus)
        self.assertIsInstance(bus, ExternalEventBus)
        runtime = ModelRuntime(registry, "test", event_bus=bus)
        self.assertEqual(runtime.state, RuntimeState.INITIALIZED)
        runtime.prepare()
        image = np.zeros((10, 10, 3))
        frame = Frame.create(image, sequence_id=1, source_name="test", monotonic_timestamp=0, connection_id=1)
        result = runtime.infer(MinimalPreprocessor().prepare(frame), InferenceContext(run_id="r1"))
        self.assertIs(result.frame, frame)
        runtime.release()
        runtime.release()
        self.assertEqual(runtime.state, RuntimeState.RELEASED)
        self.assertGreaterEqual(len(events), 3)

    def test_capabilities_are_structured_and_ordered(self):
        registry = CapabilitiesRegistry()
        def descriptor(identifier, priority, enabled=True):
            return PluginDescriptor(identifier, identifier, "1", "1.0", "a", "d", "b", (Capability("detect", "vision", False),), priority, enabled)
        registry.register(descriptor("late", 20))
        registry.register(descriptor("early", 10))
        registry.register(descriptor("off", 1, False))
        self.assertEqual([x.id for x in registry.find_by_capability("detect")], ["early", "late"])
        self.assertEqual(len(registry.find_by_capability("detect", include_disabled=True)), 3)

    def test_event_bus_subscription_and_isolation(self):
        bus = EventBus()
        received = []
        def bad(event): raise RuntimeError("expected")
        def good(event): received.append(event)
        self.assertTrue(bus.subscribe(RuntimeEvent, bad))
        self.assertFalse(bus.subscribe(RuntimeEvent, bad))
        bus.subscribe(Event, good)
        self.assertEqual(bus.publish(RuntimeEvent(runtime_name="x")), 2)
        self.assertEqual(len(received), 1)
        self.assertTrue(bus.unsubscribe(RuntimeEvent, bad))
        self.assertFalse(bus.unsubscribe(RuntimeEvent, bad))


if __name__ == "__main__": unittest.main()
