"""Описания инструментов для модели - JSON Schema.

Использование:
    from support.schemas import TOOL_SCHEMAS
    calls, usage = llm.chat(messages, TOOL_SCHEMAS)

Имена инструментов - контракт: реализации в agent/tools.py должны
называться так же и принимать те же аргументы (thought - в схеме есть,
в функцию его не передавайте).
"""

THOUGHT = {"type": "string",
           "description": "Коротко: зачем нужен этот шаг."}

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_regulations",
        "description": "Ищет правила в регламентах сервиса по словам "
                       "запроса: сроки возвратов, переносы, комиссии, "
                       "просрочка, чарджбэк, двойное списание.",
        "parameters": {"type": "object", "properties": {
            "thought": THOUGHT,
            "query": {"type": "string",
                      "description": "Ключевые слова вопроса."}},
            "required": ["thought", "query"]}}},
    {"type": "function", "function": {
        "name": "get_order",
        "description": "Карточка заказа из базы сервиса: магазин, сумма, "
                       "статус, дата подтверждения отмены, был ли возврат.",
        "parameters": {"type": "object", "properties": {
            "thought": THOUGHT,
            "order_id": {"type": "string",
                         "description": "Номер заказа, например 4106."}},
            "required": ["thought", "order_id"]}}},
    {"type": "function", "function": {
        "name": "get_payment_status",
        "description": "Статус платежа по заказу у платёжного партнёра: "
                       "оплачен, отменён, возврат оформлен, просрочен.",
        "parameters": {"type": "object", "properties": {
            "thought": THOUGHT,
            "order_id": {"type": "string"}},
            "required": ["thought", "order_id"]}}},
    {"type": "function", "function": {
        "name": "business_days_after",
        "description": "Считает дату через N рабочих дней после указанной "
                       "даты по производственному календарю. Единственный "
                       "способ назвать срок: по регламентам возврат после "
                       "отмены - 5 дней от даты подтверждения отмены, "
                       "зачисление после оформления возврата - 3 дня, "
                       "выписка для чарджбэка - 2 дня.",
        "parameters": {"type": "object", "properties": {
            "thought": THOUGHT,
            "start_date": {"type": "string",
                           "description": "Дата в формате ГГГГ-ММ-ДД."},
            "days": {"type": "integer",
                     "description": "Число рабочих дней, 1-30."}},
            "required": ["thought", "start_date", "days"]}}},
    {"type": "function", "function": {
        "name": "create_refund",
        "description": "Оформляет возврат денег клиенту у партнёра. Вызывай "
                       "только по прямой просьбе оформить или создать "
                       "возврат; для вопросов о сроках и статусах не нужен. "
                       "Требует отменённого заказа без ранее созданного "
                       "возврата и подтверждения оператора в системе.",
        "parameters": {"type": "object", "properties": {
            "thought": THOUGHT,
            "order_id": {"type": "string"},
            "amount": {"type": "integer",
                       "description": "Сумма возврата - равна сумме заказа."}},
            "required": ["thought", "order_id", "amount"]}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Завершает работу: итоговый ответ сотруднику или "
                       "клиенту по-русски, 2-4 предложения, только по "
                       "результатам инструментов. Не сообщай о действиях, "
                       "которых не было в результатах: возврат считается "
                       "оформленным только после успешного create_refund.",
        "parameters": {"type": "object", "properties": {
            "thought": THOUGHT,
            "answer": {"type": "string"}},
            "required": ["thought", "answer"]}}},
]
