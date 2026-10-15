"""Conexión a SQLite (WAL) y migraciones numeradas con `PRAGMA user_version`."""

import sqlite3
from importlib import resources
from pathlib import Path


def _migrations() -> list[tuple[int, str]]:
    files = resources.files("hunter.store").joinpath("migrations")
    found = []
    for entry in files.iterdir():
        name = entry.name
        if name.endswith(".sql") and name[:3].isdigit():
            found.append((int(name[:3]), entry.read_text(encoding="utf-8")))
    return sorted(found)


def connect(path: Path | str) -> sqlite3.Connection:
    """Abre (y crea si no existe) la base de datos y aplica las migraciones pendientes.

    `":memory:"` sirve para los tests.
    """
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(path), timeout=30, isolation_level=None
    )  # autocommit; transacciones explícitas
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, sql in _migrations():
        if number <= current:
            continue
        conn.execute("BEGIN")
        try:
            # executescript haría COMMIT por su cuenta; se separan las sentencias a mano.
            for statement in _split_sql(sql):
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {number:d}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        current = number
    return current


def _split_sql(sql: str) -> list[str]:
    lines = [line.split("--", 1)[0] for line in sql.splitlines()]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
