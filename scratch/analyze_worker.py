import csv
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
activity_csv = repo_root / "dataset" / "system_activity.csv"

worker_events = []
with open(activity_csv, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["source_system"] == "deletion_worker":
            worker_events.append(r)

print(f"Total deletion_worker events: {len(worker_events)}")
# Let's inspect some consecutive events
for r in worker_events[:25]:
    print(r["activity_id"], r["event_time"], r["event_type"], r["target_system"], r["resource_id"], r["reported_result"], r["details"])
