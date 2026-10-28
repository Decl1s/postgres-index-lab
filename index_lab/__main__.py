"""Я запускаю одноразовый эксперимент или проверяю уже сохранённый bundle."""

import argparse
import json
from pathlib import Path
import sys

from .cluster import LabError
from .core import Config, experiment
from .output import publish, verify


def main(argv=None):
    parser = argparse.ArgumentParser(description="Я сравниваю PostgreSQL SELECT до и после индекса.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("demo", help="Я создаю синтетический кластер и сохраняю измерения.")
    run.add_argument("--pg-bin", type=Path, default=Path("/usr/lib/postgresql/16/bin"))
    run.add_argument("--output", type=Path, default=Path("workspace/demo"))
    run.add_argument("--rows", type=int, default=60000)
    run.add_argument("--merchant", type=int, default=42)
    run.add_argument("--limit", type=int, default=50)
    run.add_argument("--runs", type=int, default=5)
    check = commands.add_parser("verify", help="Я сверяю состав и hashes готового bundle.")
    check.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            verify(args.folder)
            print(json.dumps({"verified": True}))
            return 0
        config = Config(args.rows, args.merchant, args.limit, args.runs)
        config.validate()
        if args.output.exists() or args.output.is_symlink():
            raise LabError("Я сохраняю прежний результат; укажи новый --output.")
        evidence = experiment(args.pg_bin, config)
        publish(args.output, evidence)
        print(json.dumps({"rows_returned": evidence["rows_returned"], "results_equal": True,
                          "before_median_ms": evidence["before"]["execution_ms"]["median"],
                          "after_median_ms": evidence["after"]["execution_ms"]["median"]}))
        return 0
    except (LabError, OSError) as error:
        # LabError не содержит DSN/пароль; OSError я намеренно не отражаю с путём.
        print(str(error) if isinstance(error, LabError) else "Я не смог выполнить файловую операцию.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
