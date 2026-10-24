"""
validate_output.py — Comprehensive validation script for output.csv.
"""

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
OUTPUT_CSV = REPO_ROOT / "output.csv"
INPUT_CSV = REPO_ROOT / "dataset" / "deletion_requests.csv"

ALLOWED_FINDING_OPS = {
    "REPORT_REMAINING_RECORD": "PRESENT",
    "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
    "REPORT_RESTORE_RISK": "ACTIVE",
}

ALLOWED_REMEDIATION_OPS = {
    "DISABLE_DATA_FLOW": "DISABLED",
    "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED",
    "ANONYMIZE_RECORD": "ANONYMIZED",
}

ALLOWED_VERIFICATION_OPS = {
    "VERIFY_RECORD_ABSENT": "ABSENT",
    "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}

ALLOWED_PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
REQUIRED_STEP_FIELDS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}


def validate():
    print(f"=== Validating {OUTPUT_CSV} ===")
    if not OUTPUT_CSV.exists():
        print(f"ERROR: {OUTPUT_CSV} does not exist!")
        sys.exit(1)

    # Read expected case IDs
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        expected_cases = [row["case_id"] for row in csv.DictReader(f)]

    expected_set = set(expected_cases)
    print(f"Input deletion requests expected: {len(expected_cases)}")

    # Read generated output
    with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    # 1. Header validation
    expected_header = ["case_id", "deletion_status", "steps_json"]
    if header != expected_header:
        print(f"ERROR: Header mismatch. Got {header}, expected {expected_header}")
        sys.exit(1)
    print("Header schema: VALID (case_id,deletion_status,steps_json)")

    # 2. Row count validation
    if len(rows) != len(expected_cases):
        print(f"ERROR: Row count mismatch. Got {len(rows)}, expected {len(expected_cases)}")
        sys.exit(1)
    print(f"Row count: VALID ({len(rows)} data rows)")

    # 3. Case ID matching and sorting
    output_case_ids = [r[0] for r in rows]
    if output_case_ids != sorted(expected_cases):
        if set(output_case_ids) != expected_set:
            missing = expected_set - set(output_case_ids)
            extra = set(output_case_ids) - expected_set
            print(f"ERROR: Case ID set mismatch. Missing: {len(missing)}, Extra: {len(extra)}")
            sys.exit(1)
        else:
            print("WARNING: Cases are not sorted in strict ascending order.")
    else:
        print("Case ID matching & sorting: VALID (100% matched, strictly sorted)")

    # 4. Content and schema validation
    status_counts = {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0}
    total_steps = 0
    errors = []

    for idx, (case_id, status, steps_str) in enumerate(rows, 1):
        if status not in status_counts:
            errors.append(f"Case {case_id}: Invalid status '{status}'")
            continue
        status_counts[status] += 1

        try:
            steps = json.loads(steps_str)
        except Exception as e:
            errors.append(f"Case {case_id}: JSON parse error: {e}")
            continue

        if not isinstance(steps, list):
            errors.append(f"Case {case_id}: steps_json is not an array")
            continue

        if status == "NOT_APPLICABLE":
            if len(steps) != 0:
                errors.append(f"Case {case_id}: NOT_APPLICABLE must have empty steps array, got {len(steps)} steps")
            continue

        total_steps += len(steps)
        current_phase_idx = 0

        for s_idx, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                errors.append(f"Case {case_id} step {s_idx}: Step is not an object")
                continue

            missing_fields = REQUIRED_STEP_FIELDS - set(step.keys())
            if missing_fields:
                errors.append(f"Case {case_id} step {s_idx}: Missing fields {missing_fields}")

            if step.get("step_no") != s_idx:
                errors.append(f"Case {case_id} step {s_idx}: step_no should be {s_idx}, got {step.get('step_no')}")

            phase = step.get("phase")
            if phase not in ALLOWED_PHASES:
                errors.append(f"Case {case_id} step {s_idx}: Invalid phase '{phase}'")
                continue

            phase_order_idx = ALLOWED_PHASES.index(phase)
            if phase_order_idx < current_phase_idx:
                errors.append(f"Case {case_id} step {s_idx}: Phase ordering violation ({phase} after {ALLOWED_PHASES[current_phase_idx]})")
            current_phase_idx = phase_order_idx

            op = step.get("operation")
            st = step.get("state")
            ev = step.get("evidence_id")

            if phase == "FINDING":
                if op not in ALLOWED_FINDING_OPS:
                    errors.append(f"Case {case_id} step {s_idx}: Invalid finding operation '{op}'")
                elif st != ALLOWED_FINDING_OPS[op]:
                    errors.append(f"Case {case_id} step {s_idx}: State '{st}' does not match operation '{op}' ({ALLOWED_FINDING_OPS[op]})")
                if not ev:
                    errors.append(f"Case {case_id} step {s_idx}: Finding must cite non-empty evidence_id")

            elif phase == "REMEDIATION":
                if op not in ALLOWED_REMEDIATION_OPS:
                    errors.append(f"Case {case_id} step {s_idx}: Invalid remediation operation '{op}'")
                elif st != ALLOWED_REMEDIATION_OPS[op]:
                    errors.append(f"Case {case_id} step {s_idx}: State '{st}' does not match operation '{op}' ({ALLOWED_REMEDIATION_OPS[op]})")
                if ev != "":
                    errors.append(f"Case {case_id} step {s_idx}: Remediation must use empty evidence_id (''), got '{ev}'")

            elif phase == "VERIFICATION":
                if op not in ALLOWED_VERIFICATION_OPS:
                    errors.append(f"Case {case_id} step {s_idx}: Invalid verification operation '{op}'")
                elif st != ALLOWED_VERIFICATION_OPS[op]:
                    errors.append(f"Case {case_id} step {s_idx}: State '{st}' does not match operation '{op}' ({ALLOWED_VERIFICATION_OPS[op]})")

                if status == "COMPLETE":
                    if not ev:
                        errors.append(f"Case {case_id} step {s_idx}: COMPLETE verification step must cite non-empty evidence_id")
                else: # INCOMPLETE
                    if ev != "":
                        errors.append(f"Case {case_id} step {s_idx}: Post-remediation verification must use empty evidence_id (''), got '{ev}'")

    if errors:
        print(f"FAILED with {len(errors)} errors:")
        for err in errors[:20]:
            print(f"  - {err}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors.")
        sys.exit(1)

    print("Step and Schema Integrity: 100% VALID")
    print(f"Status Breakdown across {len(rows)} cases:")
    for st, count in status_counts.items():
        print(f"  - {st:<16}: {count:>4} ({count / len(rows) * 100:.1f}%)")
    active_cases = status_counts["COMPLETE"] + status_counts["INCOMPLETE"]
    print(f"Total Steps across active cases: {total_steps} (average {total_steps / active_cases:.2f} steps/active case)")
    print("=== Validation PASSED Successfully ===")


if __name__ == "__main__":
    validate()
