# Какие технологии я использую

28.10.2026 я проверил установленную версию сервера и официальную документацию.
Прямых и транзитивных Python-пакетов нет: это зафиксировано в pyproject.toml
и DEPENDENCIES.txt. Runtime проекта состоит из Python и уже установленных
PostgreSQL binaries; глобальные компоненты я не устанавливаю.

| Компонент | Фактическая версия / ограничение | Для чего я использую | Официальный источник |
| --- | --- | --- | --- |
| PostgreSQL | Локально 16.15; runner Ubuntu 24.04 содержит 16.15; CLI требует одну установленную major 16.x | Я создаю временную БД, генерирую заказы и исследую планировщик | [Release 16.15](https://www.postgresql.org/docs/16/release-16-15.html) |
| SQL / EXPLAIN | Синтаксис PostgreSQL 16 | Я сохраняю фактические JSON plans и buffers; ANALYZE исполняет SELECT | [Using EXPLAIN](https://www.postgresql.org/docs/16/using-explain.html) |
| B-tree, partial index, INCLUDE | Возможности PostgreSQL 16 | Я связываю фильтр, порядок и покрытие запроса | [Multicolumn](https://www.postgresql.org/docs/16/indexes-multicolumn.html), [Partial](https://www.postgresql.org/docs/16/indexes-partial.html), [Index-only](https://www.postgresql.org/docs/16/indexes-index-only-scans.html) |
| VACUUM / ANALYZE | PostgreSQL 16 | Я обновляю visibility map и статистику перед фазой | [VACUUM](https://www.postgresql.org/docs/16/sql-vacuum.html), [ANALYZE](https://www.postgresql.org/docs/16/sql-analyze.html) |
| initdb / pg_ctl / psql | Из того же PostgreSQL bin, локально 16.15 | Я создаю и останавливаю собственный кластер, исполняю SQL с ON_ERROR_STOP и без psqlrc | [initdb](https://www.postgresql.org/docs/16/app-initdb.html), [pg_ctl](https://www.postgresql.org/docs/16/app-pg-ctl.html), [psql](https://www.postgresql.org/docs/16/app-psql.html) |
| CPython | 3.12.15 локально; диапазон 3.12.x; Windows unit CI 3.12.10 | Я управляю процессами, разбираю JSON и проверяю файлы | [Python 3.12](https://docs.python.org/3.12/) |
| unittest / unittest.mock | Стандартная библиотека Python 3.12 | Я проверяю контракт, сбои публикации и настоящую БД отдельным профилем | [unittest](https://docs.python.org/3.12/library/unittest.html) |
| pathlib, subprocess, tempfile, contextlib, secrets, os, shutil | Стандартная библиотека Python 3.12 | Я управляю только своими временными процессами и файлами; пароль не печатаю | [Library](https://docs.python.org/3.12/library/) |
| json, dataclasses, statistics, hashlib, math, zipfile, argparse, re | Стандартная библиотека Python 3.12 | Я формирую контракт, median, отчёт, hashes и source-only ZIP | [Statistics](https://docs.python.org/3.12/library/statistics.html), [Zipfile](https://docs.python.org/3.12/library/zipfile.html) |
| uv | 0.13.1 локально, необязательный инструмент | Я создал локальную venv; обычный запуск использует python -m venv | [uv](https://docs.astral.sh/uv/) |
| Git | 2.53.0 локально | Я использую собственный root, codex/ и явный PUBLIC_FILES | [Git](https://git-scm.com/docs) |
| GitHub Actions | checkout `3d3c42e5aac5ba805825da76410c181273ba90b1`, setup-python `5fda3b95a4ea91299a34e894583c3862153e4b97` | Я разделяю полный Linux-профиль и переносимый Windows unit/ZIP | [Checkout](https://github.com/actions/checkout), [Setup Python](https://github.com/actions/setup-python) |

Я проверил доступность PostgreSQL 16.15 в официальном
[описании Ubuntu 24.04 runner](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md).
Я не запускаю системный сервис runner и не выполняю sudo для создания кластера.
Сам образ runner обновляется; фактический server_version я сохраняю в каждом отчёте.

Я добавил опциональные tasks/launch для VS Code. Для отладки редактору может
потребоваться обычная Python/debugpy-интеграция; в runtime она не устанавливается.
Для SQL и JSON я не добавлял ORM, драйвер, сервер оркестрации и платный сервис.
