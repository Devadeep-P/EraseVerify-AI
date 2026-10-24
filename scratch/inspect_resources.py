import csv
import json
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
sample_out = repo_root / "dataset" / "sample_output.csv"
sample_req = repo_root / "dataset" / "sample_deletion_requests.csv"
identities = repo_root / "dataset" / "user_identities.csv"

# Load requests
requests = {}
with open(sample_req, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        requests[r["case_id"]] = r

# Load identities
users_by_email = {}
with open(identities, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        users_by_email[r["email"].lower()] = r

with open(sample_out, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        cid = r["case_id"]
        status = r["deletion_status"]
        steps = json.loads(r["steps_json"])
        if not steps:
            continue
        req = requests.get(cid, {})
        u = users_by_email.get(req.get("email", "").lower(), {})
        print(f"\nCase {cid} ({status}) user={u.get('user_id')} email={req.get('email')}:")
        for s in steps:
            print(f"  {s['phase']} | {s['system_id']:20s} | {s['resource_id']:20s} | {s['operation']} | ev={s['evidence_id']}")
