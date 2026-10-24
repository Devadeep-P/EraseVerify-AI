import csv
import json
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
sample_out = repo_root / "dataset" / "sample_output.csv"

with open(sample_out, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        steps = json.loads(r["steps_json"])
        for s in steps:
            if s["resource_id"].startswith("support_"):
                print(f"{r['case_id']}: phase={s['phase']} res={s['resource_id']} op={s['operation']} state={s['state']} ev={s['evidence_id']}")
