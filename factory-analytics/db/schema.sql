-- Схема хранилища сверки 1С ↔ видео.
-- SQLite; типы и синтаксис выбраны так, чтобы позже переноситься на PostgreSQL
-- с минимальными правками (AUTOINCREMENT -> GENERATED, datetime('now') -> now()).

PRAGMA journal_mode = WAL;

-- События, пришедшие из выгрузки 1С (одна строка = один старт или стоп).
CREATE TABLE IF NOT EXISTS one_c_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    op_uid       TEXT,                 -- уникальный ID операции из 1С (если 1С его даёт)
    rk           TEXT,                 -- РК
    stage        TEXT,                 -- производственный этап
    executor     TEXT NOT NULL,        -- исполнитель, как в 1С
    event_type   TEXT NOT NULL CHECK (event_type IN ('start', 'stop')),
    event_time   TEXT NOT NULL,        -- ISO 8601, локальное время
    product      TEXT,                 -- номенклатура / изделие
    workplace    TEXT,                 -- рабочее место / участок
    source_file  TEXT,                 -- файл выгрузки, из которого взято событие
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Дедупликация: одно и то же событие из повторной выгрузки не должно
-- обрабатываться дважды.
CREATE UNIQUE INDEX IF NOT EXISTS ux_one_c_events_op
    ON one_c_events (op_uid, event_type)
    WHERE op_uid IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_one_c_events_time ON one_c_events (event_time);
CREATE INDEX IF NOT EXISTS ix_one_c_events_executor ON one_c_events (executor);

-- Результат видео-проверки события.
CREATE TABLE IF NOT EXISTS video_checks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    one_c_event_id   INTEGER NOT NULL REFERENCES one_c_events (id),
    camera           TEXT,
    person_zone      TEXT,
    detail_zone      TEXT,
    window_start     TEXT,             -- начало окна кадров вокруг события
    window_end       TEXT,
    frames_checked   INTEGER,

    -- раздельные признаки: не смешивать эвристику и распознавание
    person_present   INTEGER NOT NULL DEFAULT 0,  -- человек в зоне рабочего места
    person_frames    INTEGER,                     -- на скольких кадрах виден человек
    motor_present    INTEGER NOT NULL DEFAULT 0,  -- YOLO: electric_motor
    rotor_present    INTEGER NOT NULL DEFAULT 0,  -- YOLO: rotor / rotor_or_armature
    motor_partial    INTEGER NOT NULL DEFAULT 0,  -- частичный признак двигателя
    reference_change INTEGER NOT NULL DEFAULT 0,  -- эвристика по эталону: ТОЛЬКО справочно
    object_confirmed INTEGER NOT NULL DEFAULT 0,  -- итог по детали: только YOLO/partial

    best_frame_path  TEXT,
    verdict          TEXT NOT NULL CHECK (verdict IN ('confirmed', 'mismatch', 'uncertain')),
    verdict_reason   TEXT,
    email_sent       INTEGER NOT NULL DEFAULT 0,
    manual_review    TEXT,             -- итог ручной проверки: 'ok' / 'false_green' / 'false_red'
    created_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS ix_video_checks_event ON video_checks (one_c_event_id);
CREATE INDEX IF NOT EXISTS ix_video_checks_verdict ON video_checks (verdict);

-- Плоское представление для экспорта в CSV и сопоставления с 1С.
CREATE VIEW IF NOT EXISTS v_reconciliation AS
SELECT
    e.id            AS event_id,
    e.op_uid, e.rk, e.stage, e.executor, e.event_type, e.event_time,
    e.product, e.workplace, e.source_file,
    c.camera, c.window_start, c.window_end, c.frames_checked,
    c.person_present, c.person_frames,
    c.motor_present, c.rotor_present, c.motor_partial,
    c.reference_change, c.object_confirmed,
    c.verdict, c.verdict_reason, c.best_frame_path,
    c.manual_review, c.created_at AS checked_at
FROM one_c_events e
LEFT JOIN video_checks c ON c.one_c_event_id = e.id;

-- Последняя (актуальная) проверка по каждому событию — для сводок,
-- чтобы повторные проверки одного события не задваивали статистику.
CREATE VIEW IF NOT EXISTS v_latest_checks AS
SELECT vc.*
FROM video_checks vc
JOIN (SELECT one_c_event_id, MAX(id) AS max_id
      FROM video_checks GROUP BY one_c_event_id) m
  ON m.max_id = vc.id;

-- Пары старт/стоп для расчёта длительности по 1С.
-- Сопоставление по op_uid, а при его отсутствии — по (РК, этап, исполнитель).
CREATE VIEW IF NOT EXISTS v_operations AS
SELECT
    s.executor, s.rk, s.stage, s.product, s.workplace,
    s.op_uid,
    s.event_time  AS start_time,
    p.event_time  AS stop_time,
    CAST((julianday(p.event_time) - julianday(s.event_time)) * 24 * 60 AS INTEGER)
                  AS duration_min_1c,
    cs.verdict    AS start_verdict,
    cp.verdict    AS stop_verdict
FROM one_c_events s
LEFT JOIN one_c_events p
    ON p.event_type = 'stop'
   AND ((s.op_uid IS NOT NULL AND p.op_uid = s.op_uid)
        OR (s.op_uid IS NULL AND p.rk = s.rk AND p.stage = s.stage
            AND p.executor = s.executor AND p.event_time >= s.event_time))
LEFT JOIN v_latest_checks cs ON cs.one_c_event_id = s.id
LEFT JOIN v_latest_checks cp ON cp.one_c_event_id = p.id
WHERE s.event_type = 'start';

-- Дневная сводка по исполнителям для отчёта руководству.
CREATE VIEW IF NOT EXISTS v_daily_summary AS
SELECT
    date(e.event_time)  AS day,
    e.executor,
    e.workplace,
    COUNT(*)                                                  AS events_total,
    SUM(CASE WHEN c.verdict = 'confirmed' THEN 1 ELSE 0 END)  AS confirmed,
    SUM(CASE WHEN c.verdict = 'mismatch'  THEN 1 ELSE 0 END)  AS mismatch,
    SUM(CASE WHEN c.verdict = 'uncertain' THEN 1 ELSE 0 END)  AS uncertain,
    SUM(CASE WHEN c.id IS NULL THEN 1 ELSE 0 END)             AS unchecked
FROM one_c_events e
LEFT JOIN v_latest_checks c ON c.one_c_event_id = e.id
GROUP BY date(e.event_time), e.executor, e.workplace;
