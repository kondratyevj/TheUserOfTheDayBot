# Factory Analytics — сверка 1С ↔ видео (намотка)

Артефакты для контура «старт/стоп из 1С ↔ видео рабочего места».
Основной код работает на analytics-VM (10.55.50.195) в `/opt/factory-analytics/`;
здесь лежат новые модули и документация, которые нужно перенести туда.

## Состав

| Путь | Назначение |
|---|---|
| `db/schema.sql` | Схема SQLite для накопления событий 1С и результатов видео-проверок |
| `tools/verdict.py` | Единая логика вердикта (подтверждено / расхождение / не подтверждено) |
| `tools/event_store.py` | Запись событий в SQLite + экспорт в CSV |
| `tools/email_report.py` | HTML-письмо с раздельными признаками (человек / YOLO / эвристика) |
| `tools/reconcile_report.py` | Сводный отчёт из БД: по дням, исполнителям, расхождениям |
| `docs/1c_export_format.md` | Требования к формату выгрузки из 1С (передать команде 1С) |

## Установка на VM

```bash
# скопировать на VM (с Windows-машины или через scp)
scp -r factory-analytics/tools/*.py promtek@10.55.50.195:/opt/factory-analytics/
scp factory-analytics/db/schema.sql promtek@10.55.50.195:/opt/factory-analytics/db/

# инициализировать БД
/opt/yolo-worker/venv/bin/python -c "import event_store; event_store.init_db('/opt/factory-analytics/db/checks.sqlite3')"
```

## Интеграция в realtime_1c_namotka_check.py

После того как проверка события посчитана (перед отправкой письма):

```python
import event_store, email_report, verdict

check = {
    # событие 1С
    "op_uid": op_uid,            # если 1С даёт уникальный ID, иначе None
    "rk": rk,
    "stage": stage,
    "executor": executor,
    "event_type": "start",       # или "stop"
    "event_time": event_time_iso,
    "product": product,
    "workplace": workplace_name, # "Намотка - рабочее место 1"
    "source_file": src_file,

    # видео
    "camera": camera,
    "person_zone": person_zone,
    "detail_zone": detail_zone,
    "window_start": win_start_iso,
    "window_end": win_end_iso,
    "frames_checked": n_frames,
    "person_present": person_present,
    "person_frames": person_frames,
    "motor_present": motor_present,      # YOLO electric_motor
    "rotor_present": rotor_present,      # YOLO rotor/rotor_or_armature
    "motor_partial": motor_partial,      # частичный признак двигателя
    "reference_change": reference_change,  # эвристика, справочно
    "best_frame_path": best_frame_path,
}

v = verdict.compute(check)           # verdict + reason, reference_change НЕ влияет
check.update(v)

event_store.record(DB_PATH, check)   # накопление в SQLite

subject = email_report.build_subject(check)
html = email_report.build_html(check)
# отправить html как MIMEText(html, "html", "utf-8"), приложить best_frame_path
```

## Экспорт для сопоставления с 1С

```bash
/opt/yolo-worker/venv/bin/python event_store.py --db /opt/factory-analytics/db/checks.sqlite3 \
    --export-csv /mnt/dc2-share/IT/test/video_checks_export.csv --since 2026-07-01
```

Сводный отчёт:

```bash
/opt/yolo-worker/venv/bin/python reconcile_report.py --db /opt/factory-analytics/db/checks.sqlite3 --since 2026-07-01
```
