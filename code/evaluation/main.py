"""
code/evaluation/main.py — CLI entry point for evaluation.

Runs quantitative evaluation against the 32 public sample cases and prints
the comprehensive metrics report.
"""

from pathlib import Path
import sys

# Ensure code/ is in sys.path
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT / "code"))
sys.path.insert(0, str(REPO_ROOT / "code" / "evaluation"))

import config
import evaluator


def main() -> None:
    req_csv = config.SAMPLE_DELETION_REQUESTS
    gold_csv = config.SAMPLE_OUTPUT_CSV
    results = evaluator.evaluate(req_csv, gold_csv)
    evaluator.print_report(results)


if __name__ == "__main__":
    main()
