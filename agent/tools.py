"""Инструменты агента: внешние сервисы + реестр функций."""

from __future__ import annotations

import os
from datetime import date, timedelta

from agent.reliability import read_with_retry, write_with_check
from support.data import MONTHS, get_order, search_regulations

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8010")
ISDAYOFF_URL = "https://isdayoff.ru"


def _api_headers() -> dict[str, str]:
    key = os.environ.get("PARTNER_API_KEY", "demo-key")
    return {"X-Api-Key": key}


def get_payment_status(order_id: str) -> dict:
    """GET /payment_status у партнёра через обёртку чтения."""
    result = read_with_retry(
        f"{GATEWAY_URL}/payment_status",
        params={"order_id": str(order_id)},
        headers=_api_headers(),
    )
    if result is None:
        return {"error": "партнёр временно недоступен", "order_id": str(order_id)}
    return result


def _format_ru(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def _is_day_off(day: date) -> bool | None:
    """True = выходной/праздник, False = рабочий, None = календарь недоступен."""
    result = read_with_retry(
        f"{ISDAYOFF_URL}/{day.strftime('%Y%m%d')}",
        expect_json=False,
    )
    if result is None:
        return None
    text = str(result.get("text", "")).strip()
    if text in {"0", "1"}:
        return text == "1"
    return None


def business_days_after(start_date: str, days: int) -> dict:
    """Дата через N рабочих дней после start_date (сама дата не считается)."""
    try:
        start = date.fromisoformat(str(start_date)[:10])
    except (TypeError, ValueError) as exc:
        return {"error": f"некорректная дата: {exc}"}
    if type(days) is not int or isinstance(days, bool):
        return {"error": "days должен быть целым числом"}
    if days < 1 or days > 30:
        return {"error": "days должен быть от 1 до 30"}

    current = start
    got = 0
    holidays_unknown = False

    while got < days:
        current += timedelta(days=1)
        if current.weekday() >= 5:
            continue
        day_off = _is_day_off(current)
        if day_off is None:
            holidays_unknown = True
            got += 1
        elif day_off:
            continue
        else:
            got += 1

    result = {
        "date": current.isoformat(),
        "date_ru": _format_ru(current),
        "start_date": start.isoformat(),
        "business_days": days,
    }
    if holidays_unknown:
        result["note"] = "праздники не учтены"
    return result


def create_refund(order_id: str, amount: int) -> dict:
    """POST /refund с ключом идемпотентности refund-<order_id>."""
    result = write_with_check(
        f"{GATEWAY_URL}/refund",
        {"order_id": str(order_id), "amount": amount},
        request_id=f"refund-{order_id}",
        headers=_api_headers(),
    )
    if result is None:
        return {"error": "партнёр временно недоступен", "order_id": str(order_id)}
    return result


def finish(answer: str) -> dict:
    """Завершение работы агента с итоговым ответом."""
    return {"answer": answer, "done": True}


TOOL_FUNCTIONS = {
    "search_regulations": search_regulations,
    "get_order": get_order,
    "get_payment_status": get_payment_status,
    "business_days_after": business_days_after,
    "create_refund": create_refund,
    "finish": finish,
}
