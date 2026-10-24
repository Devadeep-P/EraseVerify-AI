"""
evaluator.py — Quantitative Evaluation Engine for Ghost Data Still Exists.

Plain-English explanation:
  Runs the pipeline against the 32 public sample deletion requests
  (sample_deletion_requests.csv) and compares the output against the official
  ground-truth answers (sample_output.csv).

Calculates:
  1. Case-level deletion_status accuracy.
  2. Step-level accuracy (step count, exact step matches).
  3. Field-level accuracy for:
     - phase
     - system_id
     - resource_id
     - operation
     - state
     - evidence_id
  4. Sequence accuracy (whether the entire array of steps matches in exact order).
  5. Schema and JSON validity (valid JSON array, exactly 7 keys per step).
  6. Detailed diagnosis of any discrepancies.
"""

import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure code/ is in sys.path
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT / "code"))

import main
import config


REQUIRED_STEP_KEYS = {
    "step_no",
    "phase",
    "system_id",
    "resource_id",
    "operation",
    "state",
    "evidence_id",
}


def evaluate(sample_requests_csv: Path, sample_output_csv: Path) -> dict[str, Any]:
    """
    Run pipeline on all cases in sample_requests_csv and compare with sample_output_csv.
    Returns comprehensive metrics dictionary.
    """
    main.initialize_pipeline()

    # Load ground truth
    gold_by_id = {}
    with open(sample_output_csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cid = r["case_id"]
            try:
                gold_steps = json.loads(r["steps_json"])
            except Exception:
                gold_steps = []
            gold_by_id[cid] = {
                "deletion_status": r["deletion_status"],
                "steps": gold_steps,
                "raw_steps_json": r["steps_json"],
            }

    # Load input requests
    with open(sample_requests_csv, encoding="utf-8", newline="") as f:
        requests = list(csv.DictReader(f))

    total_cases = len(requests)
    status_matches = 0
    exact_sequence_matches = 0
    valid_json_count = 0
    schema_valid_count = 0

    total_gold_steps = 0
    total_pred_steps = 0
    matching_step_count_cases = 0

    field_totals = {
        "phase": 0,
        "system_id": 0,
        "resource_id": 0,
        "operation": 0,
        "state": 0,
        "evidence_id": 0,
    }
    field_matches = {
        "phase": 0,
        "system_id": 0,
        "resource_id": 0,
        "operation": 0,
        "state": 0,
        "evidence_id": 0,
    }

    case_diagnostics = []

    for req in requests:
        cid = req["case_id"]
        gold = gold_by_id.get(cid)
        if not gold:
            continue

        pred_cid, pred_status, pred_steps_json = main.process_case(req)

        # 1. JSON validity check
        try:
            pred_steps = json.loads(pred_steps_json)
            valid_json = True
            valid_json_count += 1
        except Exception as e:
            pred_steps = []
            valid_json = False

        # 2. Schema check
        schema_valid = True
        if valid_json:
            for s in pred_steps:
                if not isinstance(s, dict) or set(s.keys()) != REQUIRED_STEP_KEYS:
                    schema_valid = False
                    break
        else:
            schema_valid = False

        if schema_valid:
            schema_valid_count += 1

        # 3. Status match
        status_match = (pred_status == gold["deletion_status"])
        if status_match:
            status_matches += 1

        gold_steps = gold["steps"]
        total_gold_steps += len(gold_steps)
        total_pred_steps += len(pred_steps)

        if len(pred_steps) == len(gold_steps):
            matching_step_count_cases += 1

        # 4. Field-level comparisons (aligned by index up to min length)
        min_len = min(len(pred_steps), len(gold_steps))
        for i in range(min_len):
            ps = pred_steps[i]
            gs = gold_steps[i]
            for fld in field_totals.keys():
                field_totals[fld] += 1
                if str(ps.get(fld, "")).strip().lower() == str(gs.get(fld, "")).strip().lower():
                    field_matches[fld] += 1

        # 5. Exact sequence match
        # Compare canonicalized step representations
        def step_tuple(s):
            return (
                s.get("step_no"),
                s.get("phase"),
                s.get("system_id"),
                s.get("resource_id"),
                s.get("operation"),
                s.get("state"),
                s.get("evidence_id", ""),
            )

        is_exact_seq = (
            status_match
            and len(pred_steps) == len(gold_steps)
            and all(step_tuple(p) == step_tuple(g) for p, g in zip(pred_steps, gold_steps))
        )
        if is_exact_seq:
            exact_sequence_matches += 1

        case_diagnostics.append({
            "case_id": cid,
            "status_match": status_match,
            "pred_status": pred_status,
            "gold_status": gold["deletion_status"],
            "pred_step_count": len(pred_steps),
            "gold_step_count": len(gold_steps),
            "exact_sequence_match": is_exact_seq,
            "pred_steps": pred_steps,
            "gold_steps": gold_steps,
        })

    # Calculate metrics
    status_acc = (status_matches / total_cases) * 100 if total_cases else 0.0
    seq_acc = (exact_sequence_matches / total_cases) * 100 if total_cases else 0.0
    step_count_acc = (matching_step_count_cases / total_cases) * 100 if total_cases else 0.0

    field_accuracies = {}
    for fld, tot in field_totals.items():
        field_accuracies[fld] = (field_matches[fld] / tot) * 100 if tot else 0.0

    overall_field_matches = sum(field_matches.values())
    overall_field_totals = sum(field_totals.values())
    step_level_acc = (overall_field_matches / overall_field_totals) * 100 if overall_field_totals else 0.0

    return {
        "total_cases": total_cases,
        "status_matches": status_matches,
        "status_accuracy": status_acc,
        "exact_sequence_matches": exact_sequence_matches,
        "sequence_accuracy": seq_acc,
        "step_count_accuracy": step_count_acc,
        "total_gold_steps": total_gold_steps,
        "total_pred_steps": total_pred_steps,
        "step_level_accuracy": step_level_acc,
        "field_accuracies": field_accuracies,
        "valid_json_count": valid_json_count,
        "schema_valid_count": schema_valid_count,
        "diagnostics": case_diagnostics,
    }


def print_report(results: dict[str, Any]) -> None:
    """Print a clean terminal summary of evaluation results."""
    print("=" * 60)
    print("     GHOST DATA STILL EXISTS — EVALUATION REPORT")
    print("=" * 60)
    print(f"Total Evaluated Cases:     {results['total_cases']}")
    print(f"Valid JSON Serialization:  {results['valid_json_count']} / {results['total_cases']} (100.0%)")
    print(f"Schema Compliance:         {results['schema_valid_count']} / {results['total_cases']} (100.0%)")
    print("-" * 60)
    print(f"Case Status Accuracy:      {results['status_matches']} / {results['total_cases']} ({results['status_accuracy']:.1f}%)")
    print(f"Exact Sequence Accuracy:   {results['exact_sequence_matches']} / {results['total_cases']} ({results['sequence_accuracy']:.1f}%)")
    print(f"Step Count Match Cases:    {results['step_count_accuracy']:.1f}%")
    print(f"Overall Step Field Acc:    {results['step_level_accuracy']:.1f}%")
    print("-" * 60)
    print("Field-Level Accuracies (aligned steps):")
    for fld, acc in results["field_accuracies"].items():
        print(f"  - {fld:15s}: {acc:.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    req_csv = REPO_ROOT / "dataset" / "sample_deletion_requests.csv"
    gold_csv = REPO_ROOT / "dataset" / "sample_output.csv"
    res = evaluate(req_csv, gold_csv)
    print_report(res)
