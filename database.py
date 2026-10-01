from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import current_app, g


SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS face_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    image_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    attendance_date TEXT NOT NULL,
    checked_in_at TEXT NOT NULL,
    UNIQUE(employee_id, attendance_date)
);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE"])
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(_error: BaseException | None = None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_app(app) -> None:
    database_path = Path(app.config["DATABASE"])
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
    app.teardown_appcontext(close_db)


def save_employee_and_samples(employee_code: str, name: str, image_paths: list[str]) -> list[str]:
    connection = get_db()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    old_paths: list[str] = []
    with connection:
        connection.execute(
            "INSERT INTO employees (employee_code, name, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(employee_code) DO UPDATE SET name = excluded.name",
            (employee_code, name, now),
        )
        employee_id = connection.execute(
            "SELECT id FROM employees WHERE employee_code = ?", (employee_code,)
        ).fetchone()["id"]
        old_paths = [
            row["image_path"]
            for row in connection.execute(
                "SELECT image_path FROM face_samples WHERE employee_id = ?", (employee_id,)
            ).fetchall()
        ]
        connection.execute("DELETE FROM face_samples WHERE employee_id = ?", (employee_id,))
        connection.executemany(
            "INSERT INTO face_samples (employee_id, image_path, created_at) VALUES (?, ?, ?)",
            [(employee_id, image_path, now) for image_path in image_paths],
        )
    return old_paths


def load_training_samples() -> list[tuple[int, str]]:
    rows = get_db().execute(
        "SELECT employee_id, image_path FROM face_samples ORDER BY employee_id, id"
    ).fetchall()
    return [(row["employee_id"], row["image_path"]) for row in rows]


def find_employee(employee_id: int) -> tuple[str, str] | None:
    row = get_db().execute(
        "SELECT employee_code, name FROM employees WHERE id = ?", (employee_id,)
    ).fetchone()
    return (row["employee_code"], row["name"]) if row else None


def record_attendance(employee_id: int) -> bool:
    checked_in_at = datetime.now().astimezone().isoformat(timespec="seconds")
    cursor = get_db().execute(
        "INSERT OR IGNORE INTO attendance (employee_id, attendance_date, checked_in_at) VALUES (?, ?, ?)",
        (employee_id, date.today().isoformat(), checked_in_at),
    )
    get_db().commit()
    return cursor.rowcount == 1


def list_attendance(selected_date: str) -> list[dict[str, str]]:
    rows = get_db().execute(
        "SELECT employees.employee_code, employees.name, attendance.attendance_date, attendance.checked_in_at "
        "FROM attendance JOIN employees ON employees.id = attendance.employee_id "
        "WHERE attendance.attendance_date = ? ORDER BY attendance.checked_in_at, employees.name",
        (selected_date,),
    ).fetchall()
    return [dict(row) for row in rows]
