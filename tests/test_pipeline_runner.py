from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from src.engine.runner import run


class PipelineRunnerTests(unittest.TestCase):
    def test_limited_synthetic_run_closes_cleanly(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = run(3)
        self.assertEqual(status, 0)
        self.assertIn('"requested_frames": 3', output.getvalue())
        self.assertIn('"clean_stop": true', output.getvalue())


if __name__ == "__main__":
    unittest.main()
