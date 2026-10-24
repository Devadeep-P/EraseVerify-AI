import csv
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
target_evs = {'evidence_01', 'evidence_03', 'evidence_05', 'evidence_51', 'evidence_54', 'evidence_56', 'evidence_57', 'evidence_58', 'evidence_59', 'evidence_61', 'evidence_92', 'evidence_93', 'evidence_94'}

with open(repo_root / "dataset" / "evidence_files.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["file_id"] in target_evs:
            print(f"{r['file_id']:12s} | {r['origin']:35s} | {r['captured_at']} | {r['file_path']}")
