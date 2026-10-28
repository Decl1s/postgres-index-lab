"""Я проверяю unit-тесты и опциональный эксперимент из распакованного архива."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile
from package_release import ROOT, NAME, archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres", action="store_true")
    args = parser.parse_args()
    evidence = archive()
    with TemporaryDirectory() as folder:
        with zipfile.ZipFile(ROOT / "artifacts" / NAME) as bundle:
            bundle.extractall(folder)
        subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests"],
                       cwd=folder, check=True, timeout=30)
        if args.postgres:
            command = [sys.executable, "-X", "utf8", "-m", "index_lab", "demo", "--output", "workspace/zip-demo",
                       "--rows", "1000", "--runs", "1", "--pg-bin",
                       os.environ.get("INDEX_LAB_PG_BIN", "/usr/lib/postgresql/16/bin")]
            completed = subprocess.run(command, cwd=folder, capture_output=True, text=True, encoding="utf-8", check=True, timeout=60)
            result = json.loads(completed.stdout)
            assert result["results_equal"] and result["rows_returned"] > 0
    print(json.dumps({"zip_round_trip": True, "postgres_checked": args.postgres, **evidence}))


if __name__ == "__main__":
    main()
