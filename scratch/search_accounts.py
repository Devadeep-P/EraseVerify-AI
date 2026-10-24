import os
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
accounts = ["account_3136", "account_3866", "account_5482", "account_5684", "account_6440", "account_7566"]

for acc in accounts:
    print(f"\n=== Searching for {acc} ===")
    for root, dirs, files in os.walk(repo_root / "dataset"):
        for f in files:
            if f == "sample_output.csv":
                continue
            p = Path(root) / f
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                if acc in text:
                    print(f"  Found in: {p.relative_to(repo_root)}")
            except Exception:
                pass
