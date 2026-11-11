"""Три уровня защиты: вход, действие, выход."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from support.data import ORDERS
from support.schemas import TOOL_SCHEMAS

_TOOL_PROPS: dict[str, dict] = {}
_TOOL_REQUIRED: dict[str, set[str]] = {}
for item in TOOL_SCHEMAS:
    fn = item["function"]
    name = fn["name"]
    props = dict(fn["parameters"].get("properties", {}))
    props.pop("thought", None)
    _TOOL_PROPS[name] = props
    required = set(fn["parameters"].get("required", []))
    required.discard("thought")
    _TOOL_REQUIRED[name] = required

ALLOWED_TOOLS = set(_TOOL_PROPS)


@dataclass
class PolicyContext:
    """Доверенный контекст сессии: подтверждённые оператором возвраты."""

    confirmed_refunds: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Decision:
    """Решение guardrail."""

    status: str
    reason: str


_INJECTION_PATTERNS = [
    r"игнорируй\s+все\s+регламент",
    r"игнорируй\s+регламент",
    r"системное\s+сообщение",
    r"подтверждение\s+не\s+требуется",
    r"без\s+подтверждения\s+оператора",
    r"вызови\s+create_refund",
    r"новый\s+регламент",
    r"действуй\s+по\s+нему",
    r"системный\s+промпт",
    r"ключ\s+доступа\s+к\s+шлюз",
    r"выведи\s+полностью\s+свой",
]

_OUT_OF_SCOPE_PATTERNS = [
    r"резюме",
    r"стихотворен",
    r"поэм",
    r"сочинить\s+песн",
    r"рецепт\s+торта",
]


def check_input(text: str) -> Decision:
    """Пропускает обращение или отказывает до вызова модели."""
    lowered = (text or "").lower().replace("ё", "е")

    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return Decision(
                "block",
                "обнаружена попытка обойти правила; нужен оператор",
            )

    for pattern in _OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, lowered):
            return Decision(
                "block",
                "тема вне компетенции ассистента операционной команды",
            )

    return Decision("allow", "обращение допущено")


def _type_ok(expected: str, value: object) -> bool:
    if expected == "string":
        return type(value) is str
    if expected == "integer":
        return type(value) is int and not isinstance(value, bool)
    if expected == "number":
        return type(value) in (int, float) and not isinstance(value, bool)
    if expected == "boolean":
        return type(value) is bool
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def validate_tool_call(
    name: str,
    arguments: dict,
    context: PolicyContext,
) -> Decision:
    """Проверяет инструмент, типы аргументов и политику возврата."""
    if name not in ALLOWED_TOOLS:
        return Decision("block", f"неизвестный инструмент: {name}")

    args = {k: v for k, v in (arguments or {}).items() if k != "thought"}
    required = _TOOL_REQUIRED[name]
    missing = required - set(args)
    if missing:
        return Decision("block", f"нет аргументов: {sorted(missing)}")

    for key, prop in _TOOL_PROPS[name].items():
        if key not in args:
            continue
        expected = prop.get("type")
        if expected and not _type_ok(expected, args[key]):
            return Decision(
                "block",
                f"поле {key}: ожидался тип {expected}, "
                f"получен {type(args[key]).__name__}",
            )

    if name in {"get_order", "get_payment_status", "create_refund"}:
        order_id = args.get("order_id")
        if type(order_id) is not str:
            return Decision("block", "order_id должен быть строкой")
        if order_id not in ORDERS:
            return Decision("block", f"заказ {order_id} не найден в базе")

    if name == "business_days_after":
        days = args.get("days")
        if type(days) is not int or isinstance(days, bool):
            return Decision("block", "days должен быть целым числом")
        if days < 1 or days > 30:
            return Decision("block", "days должен быть от 1 до 30")

    if name != "create_refund":
        return Decision("allow", "действие разрешено")

    order_id = args["order_id"]
    order = ORDERS[order_id]

    if order["status"] != "cancelled":
        return Decision("block", f"заказ {order_id} не отменён")

    if order.get("refund_created"):
        return Decision("block", f"возврат по заказу {order_id} уже создан")

    amount = args["amount"]
    if type(amount) is not int or isinstance(amount, bool):
        return Decision("block", "сумма возврата должна быть целым числом")

    if amount != order["amount"]:
        return Decision(
            "block",
            f"сумма {amount} не совпадает с суммой заказа {order['amount']}",
        )

    if order_id not in context.confirmed_refunds:
        return Decision(
            "needs_confirmation",
            "нужно подтверждение оператора в системе",
        )

    return Decision("allow", "возврат подтверждён оператором")


_CARD_RE = re.compile(r"(?:\d[\s\-]*){12,18}\d")
_PHONE_RE = re.compile(
    r"(?:\+?7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
)


def check_output(text: str) -> str:
    """Удаляет из ответа полные номера карт, телефоны и ключ шлюза."""
    cleaned = text or ""
    api_key = os.environ.get("PARTNER_API_KEY") or ""
    if api_key:
        cleaned = cleaned.replace(api_key, "***")
    cleaned = re.sub(r"PARTNER_API_KEY\s*=\s*\S+", "PARTNER_API_KEY=***", cleaned, flags=re.I)
    cleaned = _CARD_RE.sub("[карта скрыта]", cleaned)
    cleaned = _PHONE_RE.sub("[телефон скрыт]", cleaned)
    return cleaned
