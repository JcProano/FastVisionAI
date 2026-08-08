import dataclasses
import unittest
from src.core.detection_events import DetectionEventDTO, DetectionEventInput, DetectionEventRecord


class DetectionEventContractTests(unittest.TestCase):
    def test_contracts_exclude_sensitive_and_biometric_payloads(self):
        forbidden = {"cedula", "address", "phone", "email", "notes", "embedding",
                     "template", "image", "array", "path", "model", "thumbnail"}
        for contract in (DetectionEventDTO, DetectionEventInput, DetectionEventRecord):
            names = {field.name.casefold() for field in dataclasses.fields(contract)}
            self.assertFalse(names & forbidden)


if __name__ == "__main__": unittest.main()
