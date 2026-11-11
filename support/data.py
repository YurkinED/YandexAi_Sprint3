"""Данные сервиса: регламенты и база заказов из папки data/.

Использование:
    from support.data import search_regulations, get_order, STATUS_RU
    search_regulations("сколько дней возврат после отмены")
    get_order("4106")
"""
import glob
import json
import os

DATA_DIR = os.getenv("DATA_DIR", "data")

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
STATUS_RU = {"paid": "оплачен", "cancelled": "отменён магазином",
             "refunded": "возврат оформлен", "overdue": "просрочен"}


def _load_regulations() -> list[dict]:
    docs = []
    pattern = os.path.join(DATA_DIR, "regulations", "*.md")
    for path in sorted(glob.glob(pattern)):
        text = open(path, encoding="utf-8").read().strip()
        title = text.split("\n", 1)[0].lstrip("# ").strip()
        docs.append({"code": os.path.basename(path)[:-3], "title": title,
                     "text": text})
    return docs


def _load_orders() -> dict[str, dict]:
    with open(os.path.join(DATA_DIR, "orders.json"), encoding="utf-8") as f:
        return {str(o["order_id"]): o for o in json.load(f)}


REGULATIONS = _load_regulations()
ORDERS = _load_orders()


def _stems(text: str) -> set[str]:
    """Грубая нормализация: ё -> е, слово обрезается до пяти букв."""
    stems = set()
    for word in text.split():
        word = word.strip(".,:;«»?!()").lower().replace("ё", "е")
        if len(word) > 3:
            stems.add(word[:5])
    return stems


def _doc_frequency() -> dict[str, int]:
    freq: dict[str, int] = {}
    for doc in REGULATIONS:
        for stem in _stems(doc["text"]):
            freq[stem] = freq.get(stem, 0) + 1
    return freq


DOC_FREQ = _doc_frequency()


def search_regulations(query: str, top_k: int = 2) -> dict:
    """Наивный поиск по регламентам: совпадение основ слов, редкие
    основы весят больше частых вроде «регламент» и «заказ»."""
    words = _stems(query)
    scored = []
    for doc in REGULATIONS:
        common = words & _stems(doc["text"])
        score = sum(1 / DOC_FREQ[stem] for stem in common)
        if doc["code"].lower() in query.lower():
            score += 10
        scored.append((score, doc))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    found = [{"code": d["code"], "title": d["title"], "text": d["text"]}
             for s, d in scored[:top_k] if s > 0]
    if not found:
        return {"found": [], "note": "ничего не найдено"}
    return {"found": found}


def get_order(order_id: str) -> dict:
    """Карточка заказа из базы сервиса."""
    order = ORDERS.get(str(order_id))
    if order is None:
        return {"error": f"заказ {order_id} не найден"}
    return {
        "order_id": order["order_id"], "shop": order["shop"],
        "amount": order["amount"], "purchase_date": order["purchase_date"],
        "status": order["status"], "status_ru": STATUS_RU[order["status"]],
        "cancel_confirmed_date": order["cancel_confirmed_date"],
        "refund_created": order["refund_created"],
        "card_last4": order["card_last4"],
    }
