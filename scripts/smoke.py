"""Я проверяю CLI, сохранённый отчёт и отказ перезаписи на настоящей БД."""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory() as folder:
        output = Path(folder) / "measurement"
        command = [sys.executable, "-X", "utf8", "-m", "index_lab", "demo", "--output", str(output),
                   "--pg-bin", os.environ.get("INDEX_LAB_PG_BIN", "/usr/lib/postgresql/16/bin")]
        completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8", timeout=60)
        result = json.loads(completed.stdout)
        assert result["results_equal"] and result["rows_returned"] == 50
        subprocess.run([sys.executable, "-m", "index_lab", "verify", str(output)], cwd=ROOT, check=True, timeout=10)
        previous = {p.name: p.read_bytes() for p in output.iterdir()}
        repeat = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=10)
        assert repeat.returncode == 2
        assert previous == {p.name: p.read_bytes() for p in output.iterdir()}
        print(json.dumps({"cli": True, "repeat_preserved": True, **result}))


if __name__ == "__main__":
    main()
