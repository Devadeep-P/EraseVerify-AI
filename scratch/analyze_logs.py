import glob
import re
from collections import Counter
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
log_dir = repo_root / "dataset" / "evidence" / "logs"

event_counts = Counter()
services = Counter()
keys = Counter()

for p in log_dir.glob("*.log"):
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            for m in re.finditer(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)', line):
                k, v = m.group(1), m.group(2)
                keys[k] += 1
                if k == "event":
                    event_counts[v.strip('"')] += 1
                elif k == "service":
                    services[v.strip('"')] += 1

print("Top 35 events:")
for e, c in event_counts.most_common(35):
    print(f"  {e:35s}: {c}")

print("\nServices:")
for s, c in services.most_common(25):
    print(f"  {s:25s}: {c}")
