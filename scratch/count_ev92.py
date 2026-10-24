import json
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
ev92_path = repo_root / "dataset" / "evidence" / "records" / "service_resource_export_20260915_114455.json"

with open(ev92_path, encoding="utf-8") as f:
    d = json.load(f)

for s, v in d["service_exports"].items():
    for subk, items in v.items():
        print(f"Service {s} -> {subk}: {len(items)} items")
