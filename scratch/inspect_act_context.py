import csv
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
activity_csv = repo_root / "dataset" / "system_activity.csv"

rows = []
with open(activity_csv, encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

targets = ["account_3136", "account_3866", "account_5482", "account_6440", "account_7566"]

for t in targets:
    for i, r in enumerate(rows):
        if r["resource_id"] == t:
            print(f"\n=== Context for {t} (row {i}, activity {r['activity_id']}, time {r['event_time']}) ===")
            start = max(0, i - 5)
            end = min(len(rows), i + 6)
            for j in range(start, end):
                row = rows[j]
                marker = ">>> " if j == i else "    "
                print(f"{marker}act_{row['activity_id']:12s} {row['event_time']} | {row['source_system']:15s} | {row['event_type']:18s} | {row['target_system']:18s} | {row['resource_id']:20s} | {row['reported_result']}")
