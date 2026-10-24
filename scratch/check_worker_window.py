import csv
from datetime import datetime
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
activity_csv = repo_root / "dataset" / "system_activity.csv"
sample_req = repo_root / "dataset" / "sample_deletion_requests.csv"
sample_out = repo_root / "dataset" / "sample_output.csv"

def parse_iso(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

with open(activity_csv, encoding="utf-8") as f:
    act_rows = list(csv.DictReader(f))
    for r in act_rows:
        r["_dt"] = parse_iso(r["event_time"])

with open(sample_req, encoding="utf-8") as f:
    requests = list(csv.DictReader(f))

for req in requests[:15]:
    cid = req["case_id"]
    req_dt = parse_iso(req["requested_at"])
    rep_dt = parse_iso(req["reported_at"])
    
    # Deletion worker events within [req_dt, rep_dt + 1 hour]
    matches = [
        r for r in act_rows
        if r["source_system"] == "deletion_worker"
        and req_dt <= r["_dt"] <= rep_dt
    ]
    print(f"\n{cid} ({req['email']}) [{req['requested_at']} to {req['reported_at']}]: {len(matches)} worker events")
    for m in matches:
        print(f"   act_{m['activity_id']} {m['event_time']} | {m['target_system']:18s} | {m['resource_id']:15s} | {m['event_type']}")
