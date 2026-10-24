import glob
import re
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
log_dir = repo_root / "dataset" / "evidence" / "logs"

events_attrs = {}

for p in log_dir.glob("*.log"):
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            pairs = dict(re.findall(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)', line))
            ev = pairs.get("event")
            if ev:
                ev = ev.strip('"')
                if ev not in events_attrs:
                    events_attrs[ev] = set()
                events_attrs[ev].update(pairs.keys())

for ev, attrs in sorted(events_attrs.items()):
    print(f"{ev:35s}: {sorted(list(attrs))}")
