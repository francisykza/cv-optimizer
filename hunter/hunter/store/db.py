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
        # check_same_thread=False: en la API cada petición tiene su conexión, pero FastAPI puede
        # abrirla en un hilo del pool y usarla en el del bucle; nunca se comparte entre peticiones.
        str(path),
        timeout=30,
        isolation_level=None,
        check_same_thread=False,
    )  # autocommit; transacciones explícitas
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """Cada migración va en su propia transacción IMMEDIATE y la versión se relee dentro: si dos
    procesos abren la base de datos a la vez (el lanzador y la API), el segundo espera y no la repite."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, sql in _migrations():
        if number <= current:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = conn.execute("PRAGMA user_version").fetchone()[0]
            if number > current:
                # executescript haría COMMIT por su cuenta; se separan las sentencias a mano.
                for statement in _split_sql(sql):
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {number:d}")
                current = number
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return current


def _split_sql(sql: str) -> list[str]:
    lines = [line.split("--", 1)[0] for line in sql.splitlines()]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
