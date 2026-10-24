import csv
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
activity_csv = repo_root / "dataset" / "system_activity.csv"

# Print first 20 rows of system_activity.csv
with open(activity_csv, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    print("Fieldnames:", reader.fieldnames)
    for i, r in enumerate(reader):
        if i < 15:
            print(r)
