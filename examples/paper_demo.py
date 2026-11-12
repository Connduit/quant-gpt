"""Experimental real historical replay, never live paper eligibility evidence."""

import argparse
from pathlib import Path

from quantlab.backtesting.report import dumps
from quantlab.paper.demo import demonstrate

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(dumps(demonstrate(args.output)))
