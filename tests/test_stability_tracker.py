import threading
import unittest

from src.engine.stability import (
    StabilityObservation, StabilityPolicy, StabilityState, StabilityTracker,
    StabilityValidationError,
)


def observation(
    timestamp, person="person-a", *, state="NOT_EVALUATED", similarity=.8,
    faces=1, quality=80,
):
    return StabilityObservation(timestamp, person, state, similarity, faces, quality, "run-1")


class StabilityTrackerTests(unittest.TestCase):
    def tracker(self, **changes):
        values = dict(
            minimum_observations=3, minimum_duration_seconds=1,
            maximum_gap_seconds=.75, policy_name="test", policy_version="1",
        )
        values.update(changes)
        return StabilityTracker(StabilityPolicy(**values))

    def test_first_observation_and_insufficient_conditions(self):
        tracker = self.tracker()
        first = tracker.observe(observation(0))
        self.assertEqual(first.state, StabilityState.STABILIZING)
        self.assertEqual((first.observations_count, first.stable_duration_seconds), (1, 0))
        second = tracker.observe(observation(.6))
        self.assertEqual(second.state, StabilityState.STABILIZING)
        third = tracker.observe(observation(.9))
        self.assertEqual(third.state, StabilityState.STABILIZING)  # count passes, duration does not

    def test_stable_requires_count_and_duration(self):
        tracker = self.tracker(maximum_gap_seconds=1)
        for timestamp in (0, .5):
            tracker.observe(observation(timestamp))
        result = tracker.observe(observation(1.0))
        self.assertEqual(result.state, StabilityState.STABLE)
        self.assertEqual(result.reason, "temporal_continuity_stable")

    def test_lost_multiple_incompatible_and_reset(self):
        tracker = self.tracker()
        tracker.observe(observation(0))
        lost = tracker.observe(observation(.1, person=None, faces=0, similarity=None))
        self.assertEqual(lost.state, StabilityState.LOST)
        tracker.observe(observation(.2))
        multiple = tracker.observe(observation(.3, person=None, faces=2, similarity=None))
        self.assertEqual(multiple.state, StabilityState.MULTIPLE_FACES)
        self.assertEqual(tracker.snapshot().observations_count, 0)
        tracker.observe(observation(.4))
        incompatible = tracker.observe(observation(
            .5, state="INCOMPATIBLE", person=None, similarity=None,
        ))
        self.assertEqual(incompatible.state, StabilityState.INCOMPATIBLE)
        self.assertEqual(tracker.reset().state, StabilityState.NO_OBSERVATION)

    def test_candidate_change_does_not_transfer_sequence(self):
        tracker = self.tracker()
        tracker.observe(observation(0, "a"))
        tracker.observe(observation(.4, "a"))
        changed = tracker.observe(observation(.5, "b", similarity=.7))
        self.assertEqual(changed.state, StabilityState.CHANGED)
        snapshot = tracker.snapshot()
        self.assertEqual((snapshot.state, snapshot.person_id, snapshot.observations_count),
                         (StabilityState.STABILIZING, "b", 1))
        self.assertEqual(snapshot.stable_duration_seconds, 0)
        self.assertEqual(snapshot.average_similarity, .7)

    def test_gap_starts_new_sequence_without_gap_duration(self):
        tracker = self.tracker(maximum_gap_seconds=.5)
        tracker.observe(observation(0))
        result = tracker.observe(observation(1))
        self.assertEqual(result.observations_count, 1)
        self.assertEqual(result.stable_duration_seconds, 0)
        self.assertEqual(result.reason, "continuity_gap_reset")

    def test_similarity_none_and_statistics(self):
        tracker = self.tracker(maximum_gap_seconds=1)
        tracker.observe(observation(0, similarity=None))
        tracker.observe(observation(.5, similarity=.6))
        result = tracker.observe(observation(1, similarity=.9))
        self.assertAlmostEqual(result.average_similarity, .75)
        self.assertEqual((result.minimum_similarity, result.maximum_similarity), (.6, .9))

    def test_minimum_similarity_breaks_and_does_not_contribute(self):
        tracker = self.tracker(minimum_similarity=.7)
        tracker.observe(observation(0, similarity=.8))
        result = tracker.observe(observation(.2, similarity=.6))
        self.assertEqual(result.state, StabilityState.STABILIZING)
        self.assertEqual(result.reason, "similarity_below_stability_minimum")
        self.assertEqual(result.observations_count, 0)
        self.assertIsNone(result.average_similarity)
        next_result = tracker.observe(observation(.3, similarity=.8))
        self.assertEqual(next_result.observations_count, 1)

    def test_backwards_timestamp_preserves_exact_snapshot(self):
        tracker = self.tracker()
        tracker.observe(observation(2))
        before = tracker.snapshot()
        with self.assertRaises(StabilityValidationError):
            tracker.observe(observation(1))
        self.assertEqual(tracker.snapshot(), before)

    def test_snapshot_has_no_clock_or_observation_side_effect(self):
        calls = []
        tracker = StabilityTracker(self.tracker().policy, monotonic=lambda: calls.append(1) or 5)
        tracker.observe(observation(0))
        before = tracker.snapshot()
        self.assertEqual(tracker.snapshot(), before)
        self.assertEqual(calls, [])

    def test_disabled_and_thread_safe_reads(self):
        tracker = self.tracker(enabled=False)
        self.assertEqual(tracker.observe(observation(0)).reason, "disabled")
        threads = [threading.Thread(target=tracker.snapshot) for _ in range(10)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(tracker.snapshot().state, StabilityState.NO_OBSERVATION)


if __name__ == "__main__":
    unittest.main()
