"""Tests for PROMPT 13: evaluation suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evals.run_eval import run_eval

SAMPLE_DIR = Path(__file__).parents[3] / "sample_data"
GOLD_DIR = SAMPLE_DIR / "gold"


class TestEvalSuite:
    def test_gold_dir_exists(self):
        assert GOLD_DIR.is_dir()

    def test_at_least_one_gold_file(self):
        assert len(list(GOLD_DIR.glob("*.json"))) >= 1

    def test_gold_file_has_required_keys(self):
        for gf in GOLD_DIR.glob("*.json"):
            data = json.loads(gf.read_text())
            for key in ("gold_id", "candidate_id", "debrief_files", "concerns", "disagreements", "coverage_gaps"):
                assert key in data, f"Missing key '{key}' in {gf.name}"

    def test_run_eval_all_pass(self):
        """Full pipeline against gold data must meet all release gates."""
        passed = run_eval(GOLD_DIR, output_path=None)
        assert passed, "Eval suite failed — pipeline does not meet release gates"

    def test_citation_validity_is_100_pct(self, capsys):
        run_eval(GOLD_DIR, output_path=None)
        captured = capsys.readouterr()
        assert "citation_validity_rate: 1.00" in captured.out

    def test_no_critical_concerns_omitted(self, capsys):
        run_eval(GOLD_DIR, output_path=None)
        captured = capsys.readouterr()
        assert "missed 0/" in captured.out

    def test_disagreement_recall_meets_target(self, capsys):
        run_eval(GOLD_DIR, output_path=None)
        captured = capsys.readouterr()
        assert "[PASS] disagreement_recall" in captured.out
