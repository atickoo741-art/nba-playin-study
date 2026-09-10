#!/usr/bin/env python3
"""Single-command reproduction of the whole study.

    python run_all.py                 # full run, 500,000 tournaments per cell
    python run_all.py --replicates 50000
    python run_all.py --skip-audit    # skip the network-backed audit checks
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))

from nbaplayin import config, pipeline, report


class _Tee:
    """Send everything printed to both the terminal and a run log."""

    def __init__(self, path):
        self.file = open(path, "w")
        self.stdout = sys.stdout

    def write(self, data):
        self.stdout.write(data)
        self.file.write(data)

    def flush(self):
        self.stdout.flush()
        self.file.flush()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--replicates", type=int, default=config.MC_REPLICATES)
    ap.add_argument("--seed", type=int, default=config.MC_SEED)
    ap.add_argument("--skip-audit", action="store_true")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args()

    import time
    config.ensure_dirs()
    log_path = config.LOGS / f"run_{time.strftime('%Y%m%d_%H%M%S')}.log"
    tee = _Tee(log_path)
    sys.stdout = tee
    try:
        out = pipeline.run(replicates=args.replicates, seed=args.seed,
                           skip_audit=args.skip_audit)
        if not args.no_report:
            paths = report.write(out)
            print(f"report: {paths['markdown']}")
            print(f"report: {paths['html']}")
            if paths["pdf"]:
                print(f"report: {paths['pdf']}")
        print(f"log:    {log_path}")
    finally:
        sys.stdout = tee.stdout
        tee.file.close()


if __name__ == "__main__":
    main()
