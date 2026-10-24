import os
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
evidence_dir = repo_root / "dataset" / "evidence"

files_with_profiles = []
for root, dirs, files in os.walk(evidence_dir):
    for f in files:
        p = Path(root) / f
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            if "customer_profiles" in text or "customer_accounts" in text:
                files_with_profiles.append(p.name)
        except Exception:
            pass

print("Files with customer_profiles or customer_accounts:")
for fn in files_with_profiles:
    print(" ", fn)
