from __future__ import annotations

import unittest

from src.ui.contracts import VisualFrameDTO


class UIRuntimeAdapterContractTests(unittest.TestCase):
    def test_visual_frame_owns_strict_packed_bytes(self):
        source = bytearray(range(12))
        dto = VisualFrameDTO(2, 2, bytes(source), 1)
        source[:] = b"\x00" * len(source)
        self.assertEqual(dto.rgb_bytes, bytes(range(12)))
        self.assertIs(type(dto.rgb_bytes), bytes)

    def test_visual_frame_rejects_reusable_or_invalid_buffers(self):
        with self.assertRaises(ValueError):
            VisualFrameDTO(2, 2, bytearray(12), 1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            VisualFrameDTO(2, 2, b"short", 1)


if __name__ == "__main__":
    unittest.main()
