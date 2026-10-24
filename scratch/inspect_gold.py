import csv
import json
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
gold_path = repo_root / "dataset" / "sample_output.csv"

with open(gold_path, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        steps = json.loads(row["steps_json"])
        print(f"\n{row['case_id']} ({row['deletion_status']}) [{len(steps)} steps]:")
        for s in steps:
            print(f"   [{s['phase']}] {s['system_id']} / {s['resource_id']} : {s['operation']} ({s['state']}) ev={s['evidence_id']}")
