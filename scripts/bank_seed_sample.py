"""Seed 15 FAKE sample questions into a THROW-AWAY bank database. Refuses the real bank path. Usage: python scripts/bank_seed_sample.py /tmp/demo/bank.db"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.qbank import sample, store

if len(sys.argv) != 2 or Path(sys.argv[1]).resolve() == store.DB_PATH.resolve():
    sys.exit("Give a throw-away database path (not the real bank).")
b = store.BankStore(sys.argv[1])
for q in sample.sample_questions():
    b.create(q, "sample", "sample question (fake)")
print(len(b.all()), "sample questions in", sys.argv[1])
