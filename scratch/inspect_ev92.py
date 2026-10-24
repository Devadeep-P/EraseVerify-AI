import json
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
ev92_path = repo_root / "dataset" / "evidence" / "records" / "service_resource_export_20260915_114455.json"

with open(ev92_path, encoding="utf-8") as f:
    data = json.load(f)

print("Top keys in ev92:", list(data.keys()))
if "service_exports" in data:
    for s, items in data["service_exports"].items():
        print(f"Service {s}: {len(items)} items")
        # Check if user_26 is in any item
        matches = [it for it in items if "user_26" in str(it) or "almeida" in str(it)]
        if matches:
            print(f"  Matches for user_26 in {s}:", matches)
