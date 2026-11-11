"""Журнал агента в обязательном формате: JSON Lines, одна строка на
событие. По нему ревьюер восстанавливает, что агент сделал.

Использование:
    from support import journal
    journal.start_trace("m01")          # открыть logs/trace_m01.jsonl
    journal.trace("thought", step=1, text="проверю заказ")
    journal.log_call("GET", "/payment_status", {"order_id": "4106"},
                     200, attempt=1, took=0.02)
    journal.stop_trace()

Обязательные события: request, input_guardrail, thought, tool_guardrail,
api_call (каждая попытка внешнего вызова), observation, answer.
Секреты из SECRET_FIELDS маскируются автоматически.
"""
import json
import os
from datetime import datetime

LOG_DIR = os.getenv("LOG_DIR", "logs")
SECRET_FIELDS = {"api_key", "token", "password", "request_id"}

API_LOG: list[dict] = []   # все попытки внешних вызовов за процесс
VERBOSE = False            # печатать события в консоль
_trace_file = None


def start_trace(request_id: str) -> None:
    """Открывает журнал одного обращения."""
    global _trace_file
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, f"trace_{request_id}.jsonl")
    _trace_file = open(path, "w", encoding="utf-8")


def trace(event: str, **fields) -> None:
    """Пишет одно событие в журнал обращения."""
    record = {"ts": datetime.now().isoformat(timespec="seconds"),
              "event": event, **fields}
    if _trace_file is not None:
        _trace_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        _trace_file.flush()
    if VERBOSE:
        short = {k: (str(v)[:90] if k != "result" else "...")
                 for k, v in fields.items()}
        print(f"  [{event}] {short}", flush=True)


def stop_trace() -> None:
    global _trace_file
    if _trace_file is not None:
        _trace_file.close()
        _trace_file = None


def masked(params: dict) -> dict:
    """Секреты заменяются звёздочками до записи в журнал."""
    return {k: ("***" if k in SECRET_FIELDS else v)
            for k, v in params.items()}


def log_call(method, path, params, status, attempt, took) -> None:
    """Одна запись на каждую попытку вызова внешнего API."""
    API_LOG.append({"method": method, "path": path, "status": status,
                    "attempt": attempt, "took": round(took, 2)})
    trace("api_call", method=method, path=path, params=masked(params),
          status=status, attempt=attempt, took=round(took, 2))


def trace_path(request_id: str) -> str:
    return os.path.join(LOG_DIR, f"trace_{request_id}.jsonl")
