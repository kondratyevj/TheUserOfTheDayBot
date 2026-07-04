"""Сводный отчёт по сверке 1С ↔ видео из SQLite-базы.

    python reconcile_report.py --db checks.sqlite3 [--since 2026-07-01] [--until 2026-08-01]
    python reconcile_report.py --db checks.sqlite3 --csv summary.csv

Показывает:
  * дневную сводку по исполнителям (подтверждено / расхождения / не подтверждено);
  * список расхождений с причинами — их стоит разобрать вручную;
  * пары старт/стоп с длительностью по 1С.
"""

import argparse
import csv
import sqlite3


def _fetch(con, query, params):
    cur = con.execute(query, params)
    return [d[0] for d in cur.description], cur.fetchall()


def _period_filter(column, since, until):
    clause, params = "", []
    if since:
        clause += f" AND {column} >= ?"
        params.append(since)
    if until:
        clause += f" AND {column} < ?"
        params.append(until)
    return clause, params


def _print_table(title, headers, rows):
    print(f"\n=== {title} ===")
    if not rows:
        print("(нет данных)")
        return
    str_rows = [[("" if v is None else str(v)) for v in row] for row in rows]
    widths = [max(len(h), *(len(r[i]) for r in str_rows)) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    for row in str_rows:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)))


def main():
    parser = argparse.ArgumentParser(description="Отчёт по сверке 1С/видео")
    parser.add_argument("--db", required=True)
    parser.add_argument("--since", help="от даты, напр. 2026-07-01")
    parser.add_argument("--until", help="до даты (не включая)")
    parser.add_argument("--csv", help="вместо консоли выгрузить дневную сводку в CSV")
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    try:
        clause, params = _period_filter("day", args.since, args.until)
        headers, rows = _fetch(
            con, f"SELECT * FROM v_daily_summary WHERE 1=1{clause} ORDER BY day, executor", params)

        if args.csv:
            with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(headers)
                writer.writerows(rows)
            print(f"Сводка сохранена: {args.csv} ({len(rows)} строк)")
            return

        _print_table("Дневная сводка", headers, rows)

        clause, params = _period_filter("event_time", args.since, args.until)
        headers, rows = _fetch(con, f"""
            SELECT event_time, event_type, executor, workplace, verdict, verdict_reason
            FROM v_reconciliation
            WHERE verdict IN ('mismatch', 'uncertain'){clause}
            ORDER BY event_time""", params)
        _print_table("Расхождения и неподтверждённые события", headers, rows)

        clause, params = _period_filter("start_time", args.since, args.until)
        headers, rows = _fetch(con, f"""
            SELECT executor, rk, stage, start_time, stop_time, duration_min_1c,
                   start_verdict, stop_verdict
            FROM v_operations WHERE 1=1{clause}
            ORDER BY start_time""", params)
        _print_table("Операции старт/стоп (длительность по 1С, мин)", headers, rows)
    finally:
        con.close()


if __name__ == "__main__":
    main()
