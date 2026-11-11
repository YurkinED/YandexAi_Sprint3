"""Мок-шлюз платёжного партнёра.

Запуск отдельным процессом: python mock_gateway.py
Адрес: http://127.0.0.1:8010

Ручки:
  GET  /payment_status?order_id=N   статус платежа по заказу (со сбоями)
  POST /refund  {"order_id": N, "amount": X, "request_id": "..."}
                                     создаёт возврат (со сбоями)
  GET  /refund_count?order_id=N     служебная: сколько возвратов создано
  POST /reset                        служебная: сбросить состояние и seed

Сбои воспроизводимы: random.seed(42) при старте и после /reset.
Долю сбоев задаёт переменная окружения GATEWAY_FAIL_RATE (по умолчанию 0.3,
0 отключает сбои для отладки).
"""
import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ORDERS_PATH = os.path.join(HERE, "..", "data", "orders.json")
FAIL_RATE = float(os.getenv("GATEWAY_FAIL_RATE", "0.3"))
API_KEY = os.getenv("PARTNER_API_KEY", "demo-key")

with open(ORDERS_PATH, encoding="utf-8") as f:
    ORDERS = {str(o["order_id"]): o for o in json.load(f)}

STATE = {"refunds": {}, "seen": set()}


def reset_state() -> None:
    STATE["refunds"] = {}
    STATE["seen"] = set()
    random.seed(42)


reset_state()


def roll_failure() -> str:
    roll = random.random()
    if roll >= FAIL_RATE:
        return "ok"
    if roll < 0.04:
        return "limit"
    if roll < 0.12:
        return "rejected"
    if roll < 0.24:
        return "crashed"
    return "hang"


class PartnerGateway(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def _fail(self, outcome: str, order_id: str) -> None:
        if outcome == "limit":
            self._reply(429, {"error": "too many requests"})
        elif outcome == "rejected":
            self._reply(503, {"error": "temporarily unavailable"})
        elif outcome == "crashed":
            self._reply(500, {"error": "internal error"})
        else:
            time.sleep(7)
            self._reply(200, {"order_id": order_id, "late": True})

    def _authorized(self) -> bool:
        return self.headers.get("X-Api-Key") == API_KEY

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        order_id = query.get("order_id", ["?"])[0]
        if url.path == "/refund_count":
            self._reply(200, {"order_id": order_id,
                              "count": STATE["refunds"].get(order_id, 0)})
            return
        if url.path != "/payment_status":
            self._reply(404, {"error": "unknown path"})
            return
        if not self._authorized():
            self._reply(401, {"error": "invalid api key"})
            return
        order = ORDERS.get(order_id)
        if order is None:
            self._reply(404, {"error": "order not found"})
            return
        outcome = roll_failure()
        if outcome != "ok":
            self._fail(outcome, order_id)
            return
        status = order["status"]
        if order["refund_created"] or STATE["refunds"].get(order_id):
            status = "refunded"
        self._reply(200, {
            "order_id": order_id, "status": status,
            "amount": order["amount"],
            "cancel_confirmed_date": order["cancel_confirmed_date"],
        })

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/reset":
            reset_state()
            self._reply(200, {"reset": True})
            return
        if url.path != "/refund":
            self._reply(404, {"error": "unknown path"})
            return
        if not self._authorized():
            self._reply(401, {"error": "invalid api key"})
            return
        size = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(size) or b"{}")
        order_id = str(payload.get("order_id", "?"))
        request_id = payload.get("request_id")
        if order_id not in ORDERS:
            self._reply(404, {"error": "order not found"})
            return
        if request_id and request_id in STATE["seen"]:
            self._reply(200, {"order_id": order_id, "duplicate": True})
            return
        outcome = roll_failure()
        if outcome in ("limit", "rejected"):
            self._fail(outcome, order_id)
            return
        STATE["refunds"][order_id] = STATE["refunds"].get(order_id, 0) + 1
        if request_id:
            STATE["seen"].add(request_id)
        if outcome != "ok":
            self._fail(outcome, order_id)
            return
        self._reply(200, {"order_id": order_id, "refund": "created",
                          "amount": payload.get("amount")})


if __name__ == "__main__":
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 8010), PartnerGateway)
    except OSError:
        raise SystemExit("Порт 8010 занят: шлюз уже запущен в другом окне.")
    print(f"Шлюз партнёра: http://127.0.0.1:8010  (сбоев: {FAIL_RATE:.0%})")
    server.serve_forever()
