import csv
from datetime import datetime
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
activity_csv = repo_root / "dataset" / "system_activity.csv"

def parse_iso(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

worker_events = []
with open(activity_csv, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["source_system"] == "deletion_worker":
            r["_dt"] = parse_iso(r["event_time"])
            worker_events.append(r)

# Check time gaps between consecutive events
print(f"Total deletion worker events: {len(worker_events)}")
batches = []
current_batch = [worker_events[0]]

for prev, curr in zip(worker_events[:-1], worker_events[1:]):
    gap_seconds = (curr["_dt"] - prev["_dt"]).total_seconds()
    # If gap is small (e.g. < 2 hours) and they belong together
    # Wait, let's see distribution of gaps
    if gap_seconds > 7200: # 2 hours
        batches.append(current_batch)
        current_batch = [curr]
    else:
        current_batch.append(curr)
batches.append(current_batch)

print(f"Number of batches with >2h gap: {len(batches)}")
for i, b in enumerate(batches[:10]):
    print(f"\nBatch {i+1} ({len(b)} events) from {b[0]['event_time']} to {b[-1]['event_time']}:")
    for r in b:
        print(f"   {r['event_time']} | {r['target_system']:18s} | {r['resource_id']:15s} | {r['event_type']:18s} | {r['reported_result']}")
