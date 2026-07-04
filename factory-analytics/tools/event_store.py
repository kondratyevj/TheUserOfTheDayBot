"""Накопление событий сверки 1С ↔ видео в SQLite и экспорт в CSV.

Только стандартная библиотека — работает в /opt/yolo-worker/venv без
дополнительных зависимостей.

Использование из realtime_1c_namotka_check.py:

    import event_store
    event_store.record("/opt/factory-analytics/db/checks.sqlite3", check)

CLI:
    python event_store.py --db checks.sqlite3 --export-csv out.csv [--since 2026-07-01]
"""

import argparse
import csv
import os
import sqlite3

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "db", "schema.sql")

# Если schema.sql лежит рядом (после копирования на VM единой папкой) — берём его.
_LOCAL_SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
if not os.path.exists(SCHEMA_PATH) and os.path.exists(_LOCAL_SCHEMA):
    SCHEMA_PATH = _LOCAL_SCHEMA

ONE_C_FIELDS = ("op_uid", "rk", "stage", "executor", "event_type", "event_time",
                "product", "workplace", "source_file")
CHECK_FIELDS = ("camera", "person_zone", "detail_zone", "window_start", "window_end",
                "frames_checked", "person_present", "person_frames",
                "motor_present", "rotor_present", "motor_partial",
                "reference_change", "object_confirmed",
                "best_frame_path", "verdict", "verdict_reason", "email_sent")

# Флаги NOT NULL в схеме: отсутствующее значение означает «не обнаружено».
FLAG_FIELDS = ("person_present", "motor_present", "rotor_present", "motor_partial",
               "reference_change", "object_confirmed", "email_sent")


def init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = f.read()
    con = sqlite3.connect(db_path)
    try:
        con.executescript(schema)
        con.commit()
    finally:
        con.close()


def _connect(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        init_db(db_path)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def record(db_path: str, check: dict) -> int:
    """Записывает событие 1С и результат его видео-проверки.

    Повторное событие с тем же op_uid+event_type не дублируется —
    к нему просто добавляется новая проверка.
    Возвращает id строки в video_checks.
    """
    con = _connect(db_path)
    try:
        event_id = None
        op_uid = check.get("op_uid")
        if op_uid:
            row = con.execute(
                "SELECT id FROM one_c_events WHERE op_uid = ? AND event_type = ?",
                (op_uid, check.get("event_type")),
            ).fetchone()
            if row:
                event_id = row[0]

        if event_id is None:
            cols = ", ".join(ONE_C_FIELDS)
            marks = ", ".join("?" for _ in ONE_C_FIELDS)
            cur = con.execute(
                f"INSERT INTO one_c_events ({cols}) VALUES ({marks})",
                [check.get(k) for k in ONE_C_FIELDS],
            )
            event_id = cur.lastrowid

        cols = ", ".join(CHECK_FIELDS)
        marks = ", ".join("?" for _ in CHECK_FIELDS)
        cur = con.execute(
            f"INSERT INTO video_checks (one_c_event_id, {cols}) VALUES (?, {marks})",
            [event_id] + [_as_db(k, check.get(k)) for k in CHECK_FIELDS],
        )
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def _as_db(field, value):
    if field in FLAG_FIELDS:
        return int(bool(value))
    return value


def export_csv(db_path: str, out_path: str, since: str = None, until: str = None) -> int:
    """Выгружает v_reconciliation в CSV (UTF-8 с BOM, разделитель ';' — удобно
    открывать в Excel и загружать обратно в 1С). Возвращает число строк."""
    con = _connect(db_path)
    try:
        query = "SELECT * FROM v_reconciliation WHERE 1=1"
        params = []
        if since:
            query += " AND event_time >= ?"
            params.append(since)
        if until:
            query += " AND event_time < ?"
            params.append(until)
        query += " ORDER BY event_time"
        cur = con.execute(query, params)
        headers = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        con.close()

    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(headers)
        writer.writerows(rows)
    os.replace(tmp_path, out_path)  # атомарно: наблюдатели не увидят полфайла
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Хранилище сверки 1С/видео")
    parser.add_argument("--db", required=True, help="путь к SQLite-базе")
    parser.add_argument("--export-csv", help="выгрузить сверку в CSV")
    parser.add_argument("--since", help="фильтр от даты, напр. 2026-07-01")
    parser.add_argument("--until", help="фильтр до даты (не включая)")
    args = parser.parse_args()

    if args.export_csv:
        n = export_csv(args.db, args.export_csv, args.since, args.until)
        print(f"Выгружено строк: {n} -> {args.export_csv}")
    else:
        init_db(args.db)
        print(f"База инициализирована: {args.db}")


if __name__ == "__main__":
    main()
