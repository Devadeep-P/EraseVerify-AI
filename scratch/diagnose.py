import sys
from pathlib import Path
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT / "code"))
sys.path.insert(0, str(REPO_ROOT / "code" / "evaluation"))
import evaluator
import config
import json

res = evaluator.evaluate(config.SAMPLE_DELETION_REQUESTS, config.SAMPLE_OUTPUT_CSV)
print("=== STATUS MISMATCHES ===")
for d in res["diagnostics"]:
    if not d["status_match"]:
        print(f"Case {d['case_id']}: Pred={d['pred_status']} vs Gold={d['gold_status']}")
        print(f"  Pred steps ({d['pred_step_count']}): {json.dumps(d['pred_steps'], indent=2)}")
        print(f"  Gold steps ({d['gold_step_count']}): {json.dumps(d['gold_steps'], indent=2)}")

print("\n=== SAMPLE SEQUENCE MISMATCHES (first 3) ===")
count = 0
for d in res["diagnostics"]:
    if d["status_match"] and not d["exact_sequence_match"] and count < 3:
        count += 1
        print(f"\n--- Case {d['case_id']} ({d['pred_status']}) ---")
        print(f"Pred steps ({d['pred_step_count']}):")
        for s in d['pred_steps']:
            print("  ", s)
        print(f"Gold steps ({d['gold_step_count']}):")
        for s in d['gold_steps']:
            print("  ", s)
