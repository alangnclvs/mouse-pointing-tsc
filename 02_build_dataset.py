"""Builds data/train and data/test from the raw sessions in data/raw.

Sessions 1, 3 and 5 go to train; sessions 2, 4 and 6 go to test, so no session
is split between the two sets. Each trial is copied to
data/<split>/<size_label>/session_XX_trial_YYY.csv, and data/trials.csv gathers
the metadata of every trial together with its split and path.

Usage:
    python 02_build_dataset.py
"""

import csv
import shutil
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
SPLITS = {"train": {1, 3, 5}, "test": {2, 4, 6}}


def split_of(session):
    for split, sessions in SPLITS.items():
        if session in sessions:
            return split
    return None


def main():
    for split in SPLITS:
        shutil.rmtree(DATA / split, ignore_errors=True)

    rows = []
    for session_dir in sorted((DATA / "raw").glob("session_*")):
        session = int(session_dir.name.split("_")[1])
        split = split_of(session)
        if split is None:
            continue
        with open(session_dir / "trials.csv", newline="", encoding="utf-8") as f:
            for trial in csv.DictReader(f):
                name = f"session_{session:02d}_trial_{int(trial['trial']):03d}.csv"
                target = DATA / split / trial["size_label"] / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(session_dir / trial["file"], target)
                rows.append({"split": split, "path": target.relative_to(DATA).as_posix(), **trial})

    with open(DATA / "trials.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter((row["split"], row["size_label"]) for row in rows)
    for (split, label), n in sorted(counts.items()):
        print(f"{split:<5} {label:<6} {n}")
    print(f"total {len(rows)} trials -> {DATA / 'trials.csv'}")


if __name__ == "__main__":
    main()
