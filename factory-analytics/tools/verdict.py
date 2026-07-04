"""Единая логика вердикта для сверки 1С ↔ видео.

Ключевое правило: reference_change (отличие от эталонного пустого стола)
НИКОГДА не участвует в вердикте — только YOLO (motor/rotor) и частичный
признак двигателя подтверждают деталь. Эвристика показывается в письме
отдельной строкой как справочная.
"""

CONFIRMED = "confirmed"    # зелёное письмо
MISMATCH = "mismatch"      # красное письмо
UNCERTAIN = "uncertain"    # жёлтое письмо


def object_confirmed(check: dict) -> bool:
    """Деталь подтверждена только распознаванием, не эвристикой."""
    return bool(
        check.get("motor_present")
        or check.get("rotor_present")
        or check.get("motor_partial")
    )


def compute(check: dict) -> dict:
    """Возвращает {'verdict': ..., 'verdict_reason': ..., 'object_confirmed': 0/1}.

    Логика (см. описание проекта):
      старт + человек + деталь        -> confirmed
      старт + нет человека            -> mismatch (старт есть, сотрудника нет)
      старт + человек, нет детали     -> uncertain (деталь не подтверждена)
      стоп  + человек и деталь        -> confirmed (нормальное закрытие)
      стоп  + чего-то не хватает      -> uncertain (закрытие не подтверждено видео)
    """
    person = bool(check.get("person_present"))
    obj = object_confirmed(check)
    event_type = check.get("event_type", "start")

    if event_type == "start":
        if person and obj:
            verdict, reason = CONFIRMED, "Старт подтверждён: человек на месте, деталь распознана."
        elif not person:
            verdict, reason = MISMATCH, "Старт в 1С есть, но сотрудника на рабочем месте не видно."
        else:
            verdict, reason = UNCERTAIN, ("Сотрудник на месте, но мотор/ротор не распознан. "
                                          "Возможно, деталь перекрыта или зона требует настройки.")
    else:  # stop
        if person and obj:
            verdict, reason = CONFIRMED, "Закрытие согласуется с видео: человек и деталь в кадре."
        elif not person and not obj:
            verdict, reason = UNCERTAIN, ("Закрытие в 1С не подтверждено видео: "
                                          "в окне вокруг события нет ни человека, ни детали.")
        elif person:
            verdict, reason = UNCERTAIN, "Человек на месте, но деталь при закрытии не распознана."
        else:
            verdict, reason = UNCERTAIN, "Деталь в кадре, но сотрудника при закрытии не видно."

    return {
        "verdict": verdict,
        "verdict_reason": reason,
        "object_confirmed": int(obj),
    }
