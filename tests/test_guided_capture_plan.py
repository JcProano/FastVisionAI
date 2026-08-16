from __future__ import annotations

import unittest

from src.engine.capture_quality import CapturePose, GuidedCapturePlan


class GuidedCapturePlanTests(unittest.TestCase):
    def test_plan_advances_only_on_acceptance_and_repeats_deterministically(self):
        plan = GuidedCapturePlan(5)
        self.assertEqual(plan.current.requested_pose, CapturePose.FRONTAL)
        poses = []
        for _ in range(5):
            poses.append(plan.accept().key)
        self.assertEqual(poses, ["frontal", "slight_left", "slight_right",
                                 "frontal_stable", "natural"])
        self.assertTrue(plan.completed)
        self.assertEqual(plan.covered_poses(), tuple(poses))


if __name__ == "__main__": unittest.main()
