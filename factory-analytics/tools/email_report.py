"""HTML-письмо о сверке события 1С с видео.

Главное отличие от старого письма — признаки показаны раздельно,
чтобы руководство не путало эвристику с реальным распознаванием:

  1. «Человек на рабочем месте»          — детекция person в зоне
  2. «Мотор/ротор распознан моделью»     — YOLO electric_motor / rotor
  3. «Есть изменение в зоне деталей»     — эвристика по эталону, СПРАВОЧНО

Вердикт (цвет письма) определяется только пунктами 1–2 (см. verdict.py).
"""

import html

GREEN = "#1e7d34"
RED = "#b02a37"
AMBER = "#b8860b"
GRAY = "#6c757d"

_VERDICT_STYLE = {
    "confirmed": (GREEN, "ПОДТВЕРЖДЕНО"),
    "mismatch": (RED, "РАСХОЖДЕНИЕ"),
    "uncertain": (AMBER, "НЕ ПОДТВЕРЖДЕНО"),
}

_EVENT_LABEL = {"start": "СТАРТ", "stop": "СТОП"}


def build_subject(check: dict) -> str:
    _, verdict_label = _VERDICT_STYLE.get(check.get("verdict"), (GRAY, "?"))
    event = _EVENT_LABEL.get(check.get("event_type"), "?")
    executor = _short_name(check.get("executor", ""))
    workplace = check.get("workplace") or ""
    time_part = (check.get("event_time") or "")[11:16]
    return f"[{verdict_label}] {event} {time_part} — {executor} — {workplace}"


def build_html(check: dict) -> str:
    color, verdict_label = _VERDICT_STYLE.get(check.get("verdict"), (GRAY, "?"))
    event = _EVENT_LABEL.get(check.get("event_type"), "?")

    one_c_rows = _rows([
        ("Событие", f"{event} операции"),
        ("Время по 1С", check.get("event_time")),
        ("Исполнитель", check.get("executor")),
        ("РК", check.get("rk")),
        ("Производственный этап", check.get("stage")),
        ("Номенклатура", check.get("product")),
        ("Рабочее место", check.get("workplace")),
        ("Файл выгрузки", check.get("source_file")),
    ])

    person = bool(check.get("person_present"))
    model_obj = bool(check.get("motor_present") or check.get("rotor_present")
                     or check.get("motor_partial"))
    ref_change = bool(check.get("reference_change"))

    what_model = []
    if check.get("motor_present"):
        what_model.append("двигатель")
    if check.get("rotor_present"):
        what_model.append("ротор")
    if not what_model and check.get("motor_partial"):
        what_model.append("двигатель частично")
    model_note = " (" + ", ".join(what_model) + ")" if what_model else ""

    person_note = ""
    if check.get("person_frames") is not None and check.get("frames_checked"):
        person_note = f" — на {check['person_frames']} из {check['frames_checked']} кадров"

    camera_rows = _rows([
        ("Камера", check.get("camera")),
        ("Окно проверки", f"{check.get('window_start') or '?'} — {check.get('window_end') or '?'}"),
        ("Проверено кадров", check.get("frames_checked")),
    ])
    signal_rows = (
        _signal_row("Человек на рабочем месте", person, person_note)
        + _signal_row("Мотор/ротор распознан моделью", model_obj, model_note)
        + _signal_row("Есть изменение в зоне деталей (справочно, на вердикт не влияет)",
                      ref_change, "", informational=True)
    )

    frame = check.get("best_frame_path")
    frame_row = _rows([("Использованный кадр", frame)]) if frame else ""

    reason = html.escape(check.get("verdict_reason") or "")

    return f"""\
<div style="font-family:Segoe UI,Arial,sans-serif;max-width:640px;color:#212529">
  <div style="background:{color};color:#fff;padding:12px 16px;font-size:18px;font-weight:bold">
    {verdict_label}: {event} — {html.escape(str(check.get('executor') or ''))}
  </div>
  <div style="border:1px solid #dee2e6;border-top:none;padding:16px">
    <p style="margin:0 0 12px;font-size:15px">{reason}</p>

    <h3 style="font-size:14px;margin:16px 0 4px;color:{GRAY}">ЧТО ПРИШЛО ИЗ 1С</h3>
    <table style="border-collapse:collapse;width:100%;font-size:13px">{one_c_rows}</table>

    <h3 style="font-size:14px;margin:16px 0 4px;color:{GRAY}">ЧТО УВИДЕЛА КАМЕРА</h3>
    <table style="border-collapse:collapse;width:100%;font-size:13px">{camera_rows}{signal_rows}{frame_row}</table>

    <p style="margin:16px 0 0;font-size:11px;color:{GRAY}">
      Камера подтверждает признаки (человек, деталь, зона, время), а не саму операцию.
      Кадр во вложении. Автоматическое письмо системы сверки 1С/видео.
    </p>
  </div>
</div>"""


def _short_name(full_name: str) -> str:
    """«Бободжонов Мансурджон Исманович» -> «Бободжонов М. И.»"""
    parts = full_name.split()
    if len(parts) < 2:
        return full_name
    return parts[0] + " " + " ".join(p[0] + "." for p in parts[1:3])


def _rows(pairs) -> str:
    out = []
    for label, value in pairs:
        if value in (None, ""):
            continue
        out.append(
            f'<tr><td style="border:1px solid #dee2e6;padding:4px 8px;width:40%;'
            f'color:{GRAY}">{html.escape(str(label))}</td>'
            f'<td style="border:1px solid #dee2e6;padding:4px 8px">{html.escape(str(value))}</td></tr>'
        )
    return "".join(out)


def _signal_row(label: str, value: bool, note: str, informational: bool = False) -> str:
    if informational:
        mark, mark_color = ("есть", GRAY) if value else ("нет", GRAY)
    else:
        mark, mark_color = ("ДА", GREEN) if value else ("НЕТ", RED)
    return (
        f'<tr><td style="border:1px solid #dee2e6;padding:4px 8px;width:40%;color:{GRAY}">'
        f'{html.escape(label)}</td>'
        f'<td style="border:1px solid #dee2e6;padding:4px 8px;font-weight:bold;'
        f'color:{mark_color}">{mark}{html.escape(note)}</td></tr>'
    )


if __name__ == "__main__":
    # Быстрая проверка вёрстки: генерирует пример письма в HTML-файл.
    import sys
    sample = {
        "verdict": "uncertain",
        "verdict_reason": "Сотрудник на месте, но мотор/ротор не распознан. "
                          "Возможно, деталь перекрыта или зона требует настройки.",
        "event_type": "stop",
        "event_time": "2026-07-04T14:32:00",
        "executor": "Бободжонов Мансурджон Исманович",
        "rk": "РК-00123",
        "stage": "Намотка статора",
        "product": "Двигатель АИР80",
        "workplace": "Намотка - рабочее место 1",
        "source_file": "выгрузка_20260704_1430.csv",
        "camera": "namotka_obshiy_vid",
        "window_start": "14:30:30", "window_end": "14:33:30",
        "frames_checked": 7, "person_present": True, "person_frames": 6,
        "motor_present": False, "rotor_present": False, "motor_partial": False,
        "reference_change": True,
        "best_frame_path": "reports/1c_realtime_checks/20260704_143200_stop.jpg",
    }
    out = sys.argv[1] if len(sys.argv) > 1 else "email_sample.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"<p>Тема: {build_subject(sample)}</p>" + build_html(sample))
    print(f"Пример письма: {out}")
