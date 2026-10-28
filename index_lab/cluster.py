"""Я запускаю только собственный временный PostgreSQL 16 без TCP и чужих DSN."""

from contextlib import contextmanager
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile


class LabError(RuntimeError):
    pass


def binaries(folder: Path) -> Path:
    folder = Path(folder).resolve()
    if os.name != "posix":
        raise LabError("Я поддерживаю запуск кластера только на Linux; unit-тесты доступны отдельно.")
    if os.geteuid() == 0:
        raise LabError("Я запускаю initdb от обычной учётной записи, не от root.")
    for name in ("postgres", "initdb", "pg_ctl", "psql"):
        if not (folder / name).is_file():
            raise LabError("Я не нашёл полный набор PostgreSQL binaries.")
        result = subprocess.run([str(folder / name), "--version"], capture_output=True,
                                text=True, encoding="utf-8", timeout=10, check=True)
        if not re.search(r"PostgreSQL\)? 16\.\d+", result.stdout):
            raise LabError("Я ожидаю одну установленную версию PostgreSQL 16.x.")
    return folder


class Session:
    def __init__(self, binary: Path, socket_dir: Path, password: str):
        self.binary, self.socket_dir = binary, socket_dir
        # Я исключаю все PG* настройки и стартовые SQL-файлы вызывающей среды.
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
        self.env["PGPASSWORD"] = password
        self.env["PGCLIENTENCODING"] = "UTF8"

    def sql(self, value: str, *, rows=60000, merchant=42, limit=50) -> str:
        command = [str(self.binary / "psql"), "--no-psqlrc", "--no-password",
                   "--quiet", "--tuples-only", "--no-align", "--host", str(self.socket_dir),
                   "--port", "5432", "--username", "lab_owner", "--dbname", "postgres",
                   "--set", "ON_ERROR_STOP=1", "--set", f"row_count={rows}",
                   "--set", f"merchant_id={merchant}", "--set", f"row_limit={limit}"]
        # Я отключаю JIT и parallel только для сопоставимости фаз; выбор scan
        # оставляю оптимизатору. Время в отчёте не включает запуск процесса psql.
        settings = "SET TIME ZONE 'UTC'; SET max_parallel_workers_per_gather=0; SET jit=off; SET statement_timeout='30s';\n"
        try:
            result = subprocess.run(command, input=settings + value, capture_output=True,
                                    text=True, encoding="utf-8", env=self.env, timeout=45)
        except subprocess.TimeoutExpired as error:
            raise LabError("Я прервал SQL по лимиту времени.") from error
        if result.returncode:
            # Я не вывожу stderr: он может содержать локальные пути. Исходный SQL
            # и стадия известны в вызывающем коде, секрет остаётся только в env.
            raise LabError("Я получил отказ SQL; результат этой фазы не публикую.")
        return result.stdout.strip()


@contextmanager
def temporary_cluster(pg_bin: Path):
    binary = binaries(pg_bin)
    folder = Path(tempfile.mkdtemp(prefix="index-pg-"))
    folder.chmod(0o700)
    data, socket_dir = folder / "data", folder / "socket"
    socket_dir.mkdir(mode=0o700)
    secret = folder / "initial-password"
    password = secrets.token_urlsafe(24)
    secret.write_text(password + "\n", encoding="utf-8")
    secret.chmod(0o600)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    ctl = str(binary / "pg_ctl")
    try:
        result = subprocess.run([str(binary / "initdb"), "-D", str(data), "-U", "lab_owner",
                                 "--pwfile=" + str(secret), "--auth-local=scram-sha-256",
                                 "--auth-host=reject", "--no-locale", "--encoding=UTF8"],
                                capture_output=True, env=env, timeout=45)
        if result.returncode:
            raise LabError("Я не смог создать свой временный кластер.")
        secret.unlink()
        # Каталог создан tempfile, но я всё равно экранирую его для PostgreSQL conf.
        socket_value = str(socket_dir).replace("'", "''")
        (data / "postgresql.auto.conf").write_text(
            "listen_addresses = ''\nunix_socket_directories = '" + socket_value +
            "'\nunix_socket_permissions = 0700\nmax_connections = 10\nshared_buffers = '32MB'\n",
            encoding="utf-8")
        started = subprocess.run([ctl, "-D", str(data), "-l", str(folder / "server.log"),
                                  "-w", "-t", "30", "start"], capture_output=True, env=env, timeout=40)
        if started.returncode:
            raise LabError("Я не смог запустить собственный PostgreSQL без TCP.")
        yield Session(binary, socket_dir, password)
    finally:
        if (data / "postmaster.pid").exists():
            subprocess.run([ctl, "-D", str(data), "-m", "fast", "-w", "-t", "20", "stop"],
                           capture_output=True, env=env, timeout=30)
        if (data / "postmaster.pid").exists():
            # Я сохраняю только свой runtime, если остановка не подтверждена.
            raise LabError("Я не подтвердил остановку; собственный runtime оставлен для диагностики.")
        shutil.rmtree(folder)
