import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from case_score_diff.cli import main


class CaseScoreDiffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def run_cli(self, baseline, candidate, *args):
        old_path = self.root / "baseline.jsonl"
        new_path = self.root / "candidate.jsonl"
        old_path.write_text(baseline, encoding="utf-8")
        new_path.write_text(candidate, encoding="utf-8")
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = main([str(old_path), str(new_path), "--json", *args])
        return status, json.loads(output.getvalue()) if output.getvalue() else None, errors.getvalue()

    def test_pairs_by_id_and_flags_regression_despite_improvement_elsewhere(self):
        baseline = '{"id":"checkout","score":0.9}\n{"id":"search","score":0.7}\n'
        candidate = '{"id":"search","score":0.9}\n{"id":"checkout","score":0.8}\n'
        status, result, _ = self.run_cli(baseline, candidate, "--tolerance", "0.02")
        self.assertEqual(status, 1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["counts"]["regressed"], 1)
        self.assertEqual(result["counts"]["improved"], 1)
        self.assertEqual(result["cases"][0]["delta"], "-0.1")

    def test_tolerance_is_inclusive_and_uses_decimal_arithmetic(self):
        status, result, _ = self.run_cli(
            '{"id":"a","score":0.3}\n', '{"id":"a","score":0.2}\n', "--tolerance", "0.1",
        )
        self.assertEqual(status, 0)
        self.assertEqual(result["cases"][0]["status"], "within_tolerance")

    def test_lower_is_better_with_missing_and_added_ids(self):
        status, result, _ = self.run_cli(
            '{"id":"a","score":42}\n{"id":"b","score":0}\n',
            '{"id":"a","score":43}\n{"id":"c","score":11}\n',
            "--direction", "lower",
        )
        self.assertEqual(status, 1)
        self.assertEqual([case["status"] for case in result["cases"]], [
            "regressed", "missing", "added",
        ])
        self.assertEqual(result["cases"][1]["baseline"], "0")
        self.assertIsNone(result["cases"][1]["candidate"])

    def test_blank_lines_and_metadata_are_accepted(self):
        status, result, _ = self.run_cli(
            '\ufeff\n{"id":"a","score":1,"metadata":{"label":"ok"}}\n',
            '\n{"id":"a","score":1}\n\n{"id":"b","score":1}\n',
        )
        self.assertEqual(status, 0)
        self.assertEqual(result["counts"]["added"], 1)

    def test_empty_baseline_is_an_error_but_empty_candidate_is_a_regression(self):
        row = '{"id":"a","score":0}\n'
        status, _, errors = self.run_cli("\n", row)
        self.assertEqual(status, 2)
        self.assertIn("baseline has no cases", errors)
        status, result, _ = self.run_cli(row, "")
        self.assertEqual(status, 1)
        self.assertEqual(result["counts"]["missing"], 1)

    def test_invalid_rows_report_filename_and_line(self):
        baseline = '{"id":"a","score":1}\n'
        for row in (
            '{"id":"a","score":null}', '{"id":"a","score":true}', '{"id":"a","score":NaN}',
            '{"id":" ","score":1}', '{"id":"a","score":1e1001}', '[]',
            '{"id":"a","score":1,"score":2}', '{',
        ):
            with self.subTest(row=row):
                status, result, errors = self.run_cli(baseline, "\n" + row + "\n")
                self.assertEqual(status, 2)
                self.assertIsNone(result)
                self.assertIn("candidate.jsonl:2:", errors)

    def test_duplicate_case_ids_are_rejected(self):
        row = '{"id":"a","score":1}\n'
        status, _, errors = self.run_cli(row, row * 2)
        self.assertEqual(status, 2)
        self.assertIn('duplicate case id "a"', errors)
