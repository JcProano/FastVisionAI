import dataclasses
import unittest

from src.core.reports import ReportPolicy, ReportValidationError


class ReportContractTests(unittest.TestCase):
    def test_policy_validation_and_timezone(self):
        self.assertEqual(ReportPolicy().presentation_timezone, "America/Guayaquil")
        for values in ({"default_range_days": 0}, {"max_rows": 0},
                       {"presentation_timezone": "Invalid/Nowhere"}):
            with self.assertRaises(ReportValidationError): ReportPolicy(**values)

    def test_public_contracts_have_no_sensitive_or_biometric_fields(self):
        import src.core.reports.contracts as contracts
        forbidden = {"cedula", "embedding", "template", "image", "thumbnail",
                     "address", "phone", "email", "notes", "model", "repository"}
        for name in contracts.__all__ if hasattr(contracts, "__all__") else dir(contracts):
            value = getattr(contracts, name)
            if isinstance(value, type) and dataclasses.is_dataclass(value):
                fields = {field.name for field in dataclasses.fields(value)}
                self.assertFalse(fields & forbidden, name)


if __name__ == "__main__": unittest.main()
