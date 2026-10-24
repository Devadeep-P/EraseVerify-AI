"""
main.py — Main pipeline orchestrator for Ghost Data Still Exists.

Plain-English explanation:
  This module coordinates the complete deletion-audit workflow for any given case:
  1. Determine whether the request authorizes deletion (request_classifier.py).
     If not, status = NOT_APPLICABLE and steps_json = [].
  2. Resolve current and historical identities (identity_resolver.py).
  3. Load valid evidence captured at or before audit_at (evidence_loader.py).
  4. Aggregate facts across SQL, JSON, logs, text, PDF, and image evidence (fact_aggregator.py).
  5. Apply deletion rules (policy_engine.py) to assess compliance.
  6. Determine status (COMPLETE or INCOMPLETE).
  7. Construct properly ordered and validated steps (step_builder.py).
"""

import csv
import json
import os
import sys
from pathlib import Path

# Add code/ to search path if run directly
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT / "code"))

import config
import identity_resolver
import request_classifier
import evidence_loader
import fact_aggregator
import policy_engine
import step_builder


def initialize_pipeline() -> None:
    """Load reference datasets into memory once."""
    identity_resolver.load_tables(config.USER_IDENTITIES_CSV, config.USER_AUDIT_LOG_CSV)
    evidence_loader.load_manifest(config.EVIDENCE_FILES_CSV)
    fact_aggregator.load_activity(config.SYSTEM_ACTIVITY_CSV)
    policy_engine.load_rules(config.DELETION_RULES_CSV)


def process_case(case_row: dict) -> tuple[str, str, str]:
    """
    Process a single deletion request row.

    Returns:
      (case_id, deletion_status, steps_json_string)
    """
    case_id = case_row["case_id"]
    email = case_row["email"]
    audit_at = case_row["audit_at"]
    request_text = case_row.get("request_text", "")

    # Step 1: Authorization check
    classification = request_classifier.classify(request_text)
    if classification == config.STATUS_NOT_APPLICABLE:
        return case_id, config.STATUS_NOT_APPLICABLE, "[]"

    # Step 2: Identity resolution
    identity = identity_resolver.resolve(email)
    if not identity:
        # Unknown identity: treat conservatively as INCOMPLETE with empty steps
        return case_id, config.STATUS_INCOMPLETE, "[]"

    # Step 3: Temporally valid evidence (captured_at <= audit_at)
    valid_evidence = evidence_loader.valid_evidence_for(audit_at, config.DATASET_DIR)

    # Step 4: Extract and aggregate facts
    fact_set = fact_aggregator.aggregate(identity, valid_evidence, audit_at)

    # Step 5: Policy decision
    decisions = policy_engine.decide(fact_set)
    status = policy_engine.overall_status(decisions)

    # Step 6: Step generation
    steps = step_builder.build_steps_for_case(status, decisions)
    steps_json = json.dumps(steps, separators=(",", ":"))

    return case_id, status, steps_json


def run_pipeline(input_path: Path = None, output_path: Path = None) -> int:
    """
    Run the full deletion-audit pipeline on an input CSV and write output.csv.

    Args:
        input_path: Path to input deletion_requests.csv (defaults to config.DELETION_REQUESTS_CSV)
        output_path: Path to target output.csv (defaults to config.OUTPUT_CSV at repo root)

    Returns:
        Number of processed cases.
    """
    if input_path is None:
        input_path = config.DELETION_REQUESTS_CSV
    if output_path is None:
        output_path = config.OUTPUT_CSV

    print(f"Initializing pipeline with configuration from {config.DATASET_DIR}...")
    initialize_pipeline()

    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    rows_to_process = []
    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_to_process.append(row)

    total = len(rows_to_process)
    print(f"Processing {total} evaluation cases from {input_path.name}...")

    results = []
    for idx, case_row in enumerate(rows_to_process, 1):
        res = process_case(case_row)
        results.append(res)
        if idx % 50 == 0 or idx == total:
            print(f"  Processed {idx}/{total} cases ({idx/total*100:.1f}%)")

    # Sort results by case_id per specification
    results.sort(key=lambda x: x[0])

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "deletion_status", "steps_json"])
        for case_id, status, steps_json in results:
            writer.writerow([case_id, status, steps_json])

    print(f"Successfully generated {len(results)} predictions in {output_path}")
    return len(results)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="EraseVerify-AI — Ghost Data Still Exists pipeline")
    parser.add_argument("--input", default=str(config.DELETION_REQUESTS_CSV), help="Path to deletion requests CSV")
    parser.add_argument("--output", default=str(config.OUTPUT_CSV), help="Path to output CSV")
    args = parser.parse_args()

    run_pipeline(Path(args.input), Path(args.output))

