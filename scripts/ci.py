"""Я разделяю переносимые unit-тесты и полный PostgreSQL-профиль Linux."""

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["full", "unit"], required=True)
    args = parser.parse_args()
    commands = [["-m", "unittest", "discover", "-s", "tests", "-v"]]
    if args.mode == "full":
        commands += [["-m", "unittest", "discover", "-s", "tests", "-p", "integration.py", "-v"], ["scripts/smoke.py"]]
    commands += [["scripts/zip_smoke.py"] + (["--postgres"] if args.mode == "full" else [])]
    for command in commands:
        subprocess.run([sys.executable, "-X", "utf8", *command], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
