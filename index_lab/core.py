"""Я сначала доказываю равенство результата, затем сравниваю планы и измерения."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import statistics

from . import __version__
from .cluster import LabError, temporary_cluster

SQL = Path(__file__).resolve().parent / "sql"


@dataclass(frozen=True)
class Config:
    rows: int = 60000
    merchant: int = 42
    limit: int = 50
    runs: int = 5

    def validate(self):
        for name, lower, upper in [("rows", 1000, 200000), ("merchant", 1, 100),
                                    ("limit", 1, 1000), ("runs", 1, 9)]:
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise LabError("Я отклонил параметр вне контракта: " + name)


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def plan_metrics(document) -> dict:
    if not isinstance(document, list) or len(document) != 1 or not isinstance(document[0], dict):
        raise LabError("Я ожидаю один JSON EXPLAIN document.")
    item = document[0]
    root = item.get("Plan")
    execution = item.get("Execution Time")
    if (type(execution) not in (int, float) or not math.isfinite(execution) or execution < 0
            or not isinstance(root, dict)):
        raise LabError("Я не нашёл корректный ANALYZE result.")
    nodes, indexes = [], []

    def walk(node, depth=0):
        if depth > 50 or not isinstance(node, dict) or not isinstance(node.get("Node Type"), str):
            raise LabError("Я отклонил неверное дерево плана.")
        nodes.append(node["Node Type"])
        if "Index Name" in node:
            indexes.append(node["Index Name"])
        children = node.get("Plans", [])
        if not isinstance(children, list):
            raise LabError("Я ожидаю список дочерних plan nodes.")
        for child in children:
            walk(child, depth + 1)

    walk(root)
    counts = {}
    for name in ("Shared Hit Blocks", "Shared Read Blocks", "Actual Rows"):
        value = root.get(name, 0)
        if type(value) is not int or value < 0:
            raise LabError("Я отклонил неверную счётную метрику.")
        counts[name] = value
    # Счётчики родителя уже включают потомков: я не суммирую их по дереву.
    return {"execution_ms": execution, "nodes": nodes, "indexes": indexes,
            "shared_hit_blocks": counts["Shared Hit Blocks"], "shared_read_blocks": counts["Shared Read Blocks"],
            "rows": counts["Actual Rows"]}


def summarize(plans: list) -> dict:
    if not plans:
        raise LabError("Я ожидаю хотя бы одно измерение.")
    metrics = [plan_metrics(p) for p in plans]
    times = [p["execution_ms"] for p in metrics]
    return {"samples": len(plans), "execution_ms": {"min": min(times), "median": statistics.median(times), "max": max(times)},
            "sample_metrics": metrics}


def measure(session, query, config):
    explain = "EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) " + query
    kwargs = {"rows": config.rows, "merchant": config.merchant, "limit": config.limit}
    # Я прогреваю каждый вариант отдельно и не включаю warm-up в median.
    session.sql(explain, **kwargs)
    return [json.loads(session.sql(explain, **kwargs)) for _ in range(config.runs)]


def experiment(pg_bin: Path, config: Config) -> dict:
    config.validate()
    query = (SQL / "query.sql").read_text(encoding="utf-8").strip().rstrip(";")
    values_query = "SELECT COALESCE(json_agg(q ORDER BY q.created_at DESC, q.order_id DESC), '[]'::json) FROM (" + query + ") q;"
    kwargs = {"rows": config.rows, "merchant": config.merchant, "limit": config.limit}
    with temporary_cluster(pg_bin) as session:
        version = session.sql("SHOW server_version;")
        session.sql((SQL / "schema.sql").read_text(encoding="utf-8"), **kwargs)
        before_rows = json.loads(session.sql(values_query, **kwargs))
        before = measure(session, query, config)
        session.sql((SQL / "index.sql").read_text(encoding="utf-8"), **kwargs)
        after_rows = json.loads(session.sql(values_query, **kwargs))
        after = measure(session, query, config)
        if canonical(before_rows) != canonical(after_rows):
            raise LabError("Я получил разные результаты; оптимизацию не принимаю.")
        sizes = json.loads(session.sql("""SELECT json_build_object(
            'table_rows', (SELECT count(*) FROM orders),
            'heap_bytes', pg_relation_size('orders'),
            'index_bytes', pg_relation_size('orders_paid_recent'),
            'tcp_disabled', current_setting('listen_addresses') = '');"""))
        # Контрольный SELECT без LIMIT показывает семантику границ независимо
        # от того, попали ли sentinel rows в последние 50 результатов.
        boundaries = json.loads(session.sql("""SELECT json_agg(order_id ORDER BY order_id)
            FROM orders WHERE order_id > :row_count AND merchant_id=42 AND status='paid'
            AND created_at >= timestamptz '2026-09-20 00:00:00+00'
            AND created_at < timestamptz '2026-10-01 00:00:00+00';""", **kwargs))
    return {"version": __version__, "postgres": version, "config": asdict(config), "results_equal": True,
            "rows_returned": len(before_rows), "result_sha256": sha256(canonical(before_rows)).hexdigest(),
            "before": summarize(before), "after": summarize(after), "sizes": sizes,
            "boundary_order_ids": boundaries, "result": before_rows,
            "before_plans": before, "after_plans": after,
            "sql_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(SQL.glob("*.sql"))}}
