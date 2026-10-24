import csv
import json
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
sample_out = repo_root / "dataset" / "sample_output.csv"
activity_csv = repo_root / "dataset" / "system_activity.csv"

# Load sample output steps
cases = ["case_21", "case_25", "case_26", "case_27", "case_28"]
expected_resources = {}
with open(sample_out, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["case_id"] in cases:
            steps = json.loads(r["steps_json"])
            expected_resources[r["case_id"]] = [s["resource_id"] for s in steps]

print("Expected resources per case:")
for cid, res in expected_resources.items():
    print(f"  {cid}: {res}")

# Check where these resources appear in system_activity.csv
with open(activity_csv, encoding="utf-8") as f:
    act_rows = list(csv.DictReader(f))

for cid, res_list in expected_resources.items():
    print(f"\n=== System activity for {cid} ===")
    found_acts = [r for r in act_rows if r["resource_id"] in res_list]
    for r in found_acts:
        print(f"  {r['activity_id']} | {r['event_time']} | {r['source_system']:15s} | {r['event_type']:18s} | {r['resource_id']}")
