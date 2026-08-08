from __future__ import annotations

import dataclasses
import unittest

import numpy as np

from src.ui.dashboard import contracts


class DashboardContractTests(unittest.TestCase):
    def test_dashboard_dtos_are_scalar_only(self):
        dto_types = (
            contracts.DashboardSystemDTO, contracts.DashboardMetricsDTO,
            contracts.DashboardRecognitionDTO, contracts.DashboardGalleryDTO,
            contracts.DashboardQualityDTO, contracts.DashboardEventDTO,
        )
        forbidden = {"embedding", "template", "image", "frame", "model", "aligned_face"}
        for dto_type in dto_types:
            names = {field.name.casefold() for field in dataclasses.fields(dto_type)}
            self.assertTrue(names.isdisjoint(forbidden), (dto_type.__name__, names & forbidden))
            for field in dataclasses.fields(dto_type):
                self.assertNotIn("ndarray", str(field.type).casefold())

    def test_missing_metrics_are_not_available_without_exceptions(self):
        metrics = contracts.DashboardMetricsDTO()
        self.assertIsNone(metrics.effective_capture_fps)
        self.assertIsNone(metrics.effective_processing_fps)
        self.assertIsNone(metrics.inference_latency_ms)
        self.assertNotIn(np.ndarray, [type(value) for value in dataclasses.astuple(metrics)])


if __name__ == "__main__": unittest.main()
