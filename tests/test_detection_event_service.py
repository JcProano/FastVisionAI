import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core.detection_events import (
    DetectionEventInput, DetectionEventRepository, DetectionEventService, DetectionEventType,
)


def observation(kind=DetectionEventType.REGISTERED_CANDIDATE, person="person-1", camera="0"):
    if kind is not DetectionEventType.REGISTERED_CANDIDATE: person = None
    return DetectionEventInput(kind, person, datetime.now(timezone.utc), camera,
        "Temporary" if person else None, .9 if person else None, 80, "NOT_EVALUATED",
        "ACTIVE" if person else None, "session")


class FailingRepository:
    def create(self, _event): raise OSError("controlled")


class DetectionEventServiceTests(unittest.TestCase):
    def service(self, clock, cache=3):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        repository = DetectionEventRepository(Path(temporary.name) / "events.db")
        repository.initialize()
        return repository, DetectionEventService(
            repository, registered_cooldown_seconds=60,
            unregistered_cooldown_seconds=60, cache_limit=cache,
            monotonic=lambda: clock[0],
        )

    def test_registered_cooldown_expiry_camera_and_new_session_reset(self):
        clock = [0.0]; repository, service = self.service(clock)
        self.assertTrue(service.observe(observation()).recorded)
        self.assertFalse(service.observe(observation()).recorded)
        self.assertTrue(service.observe(observation(camera="1")).recorded)
        clock[0] = 60; self.assertTrue(service.observe(observation()).recorded)
        restarted = DetectionEventService(repository, monotonic=lambda: clock[0])
        self.assertTrue(restarted.observe(observation()).recorded)

    def test_unknown_incompatible_multiple_are_aggregate_per_camera_and_cache_limited(self):
        clock = [0.0]; _, service = self.service(clock, cache=2)
        for kind in (DetectionEventType.UNREGISTERED, DetectionEventType.INCOMPATIBLE,
                     DetectionEventType.MULTIPLE_FACES):
            self.assertTrue(service.observe(observation(kind)).recorded)
            self.assertFalse(service.observe(observation(kind)).recorded)
        self.assertEqual(len(service.recent(50)), 2)
        self.assertTrue(service.observe(observation(DetectionEventType.UNREGISTERED, camera="1")).recorded)

    def test_repository_failure_is_safe(self):
        service = DetectionEventService(FailingRepository())
        result = service.observe(observation())
        self.assertFalse(result.success); self.assertEqual(result.message, "persistence_error")


if __name__ == "__main__": unittest.main()
