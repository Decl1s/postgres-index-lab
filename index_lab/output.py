"""Я публикую результаты только в новый каталог и сверяю контрольные суммы."""

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

from .cluster import LabError
from .core import canonical


def render(summary: dict) -> str:
    lines = ["# Как я сравнил планы PostgreSQL", "", f"PostgreSQL: {summary['postgres']}",
             f"Строк таблицы: {summary['sizes']['table_rows']}; результат: {summary['rows_returned']} строк.",
             "Я подтвердил одинаковый упорядоченный результат до и после индекса.", "",
             "| Фаза | Min / median / max, ms | Узлы первого измерения | Shared hit / read первого измерения |",
             "| --- | --- | --- | --- |"]
    for label, key in [("До индекса", "before"), ("После индекса", "after")]:
        phase = summary[key]
        times = phase["execution_ms"]
        first = phase["sample_metrics"][0]
        lines.append(f"| {label} | {times['min']} / {times['median']} / {times['max']} | " +
                     " → ".join(first["nodes"]) + f" | {first['shared_hit_blocks']} / {first['shared_read_blocks']} |")
    lines += ["", f"Размер дополнительного индекса: {summary['sizes']['index_bytes']} bytes.",
              "Я измерял прогретые SELECT после VACUUM ANALYZE; сборка индекса, запуск psql и загрузка не входят в execution_ms.",
              "Я не обнулял ОС/DB cache и не превращаю это сравнение в обещание SLA.",
              "Счётчики buffers я беру только из корня: дочерние значения повторно не суммирую.",
              "Я сохраняю сырые JSON plans, каждое измерение, результат и hash SQL рядом с этим отчётом.", ""]
    return "\n".join(lines)


def publish(destination: Path, evidence: dict):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise LabError("Я сохраняю существующий каталог результата; выбери новое имя.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.with_name(destination.name + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise LabError("Я обнаружил активную блокировку публикации.") from error
    os.close(descriptor)
    stage = None
    try:
        stage = Path(tempfile.mkdtemp(prefix=".index-stage-", dir=destination.parent))
        summary = {k: v for k, v in evidence.items() if k not in ("result", "before_plans", "after_plans")}
        files = {"summary.json": canonical(summary) + b"\n", "result.json": canonical(evidence["result"]) + b"\n",
                 "before.plans.json": canonical(evidence["before_plans"]) + b"\n",
                 "after.plans.json": canonical(evidence["after_plans"]) + b"\n",
                 "REPORT.md": render(summary).encode("utf-8")}
        manifest = {name: {"sha256": sha256(raw).hexdigest(), "bytes": len(raw)} for name, raw in files.items()}
        files["manifest.json"] = canonical(manifest) + b"\n"
        for name, raw in files.items():
            (stage / name).write_bytes(raw)
        verify(stage)
        if destination.exists() or destination.is_symlink():
            raise LabError("Я обнаружил чужой результат и сохранил его.")
        stage.rename(destination)
        stage = None
    finally:
        if stage is not None:
            shutil.rmtree(stage)
        lock.unlink()


def verify(folder: Path):
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        expected = {"summary.json", "result.json", "before.plans.json", "after.plans.json", "REPORT.md"}
        if not isinstance(manifest, dict) or set(manifest) != expected:
            raise ValueError("manifest contract")
        if {p.name for p in folder.iterdir()} != expected | {"manifest.json"}:
            raise ValueError("unexpected output")
        for name, record in manifest.items():
            file = folder / name
            if file.is_symlink() or not file.is_file():
                raise ValueError("file kind")
            raw = file.read_bytes()
            if sha256(raw).hexdigest() != record["sha256"] or len(raw) != record["bytes"]:
                raise ValueError("hash/size")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise LabError("Я не подтвердил целостность результата.") from error
