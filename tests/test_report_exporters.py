import csv
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.core.reports import (
    ReportExportError, ReportExportUnavailableError, ReportExporter,
)


@dataclass(frozen=True)
class SafeReport:
    title: str
    count: int


class ReportExporterTests(unittest.TestCase):
    def test_csv_utf8_injection_and_no_overwrite(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.csv"; exporter = ReportExporter()
            result = exporter.export_csv(SafeReport("=FÓRMULA", 2), path)
            self.assertTrue(result.success); self.assertEqual(result.display_target, "report.csv")
            with path.open(encoding="utf-8", newline="") as stream:
                rows = tuple(csv.reader(stream))
            self.assertEqual(rows[1][0], "'=FÓRMULA")
            with self.assertRaises(ReportExportError):
                exporter.export_csv(SafeReport("safe", 1), path)

    def test_excel_and_pdf_unavailable_without_side_effects(self):
        exporter = ReportExporter()
        with TemporaryDirectory() as directory, patch.object(
            ReportExporter, "excel_available", return_value=False,
        ):
            excel = Path(directory) / "x.xlsx"; pdf = Path(directory) / "x.pdf"
            with self.assertRaises(ReportExportUnavailableError):
                exporter.export_excel(SafeReport("safe", 1), excel)
            with self.assertRaises(ReportExportUnavailableError):
                exporter.export_pdf(SafeReport("safe", 1), pdf)
            self.assertFalse(excel.exists()); self.assertFalse(pdf.exists())


if __name__ == "__main__": unittest.main()
