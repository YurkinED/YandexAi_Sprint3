"""Одно обращение из командной строки.

python run.py "Клиент по заказу 4104 спрашивает, прошёл ли платёж"
python run.py "Оформи возврат по заказу 4126" --confirm 4126

Ожидает в agent/agent.py функцию run_agent(text, context, request_id)
и в agent/guardrails.py класс PolicyContext(confirmed_refunds=set()).
"""
import argparse
import json

from agent.agent import run_agent
from agent.guardrails import PolicyContext
from support import journal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", help="текст обращения")
    parser.add_argument("--confirm", action="append", default=[],
                        help="заказ, по которому оператор подтвердил возврат")
    parser.add_argument("--quiet", action="store_true",
                        help="не печатать ход работы, только результат")
    args = parser.parse_args()
    journal.VERBOSE = not args.quiet
    context = PolicyContext(confirmed_refunds=set(args.confirm))
    result = run_agent(args.text, context, request_id="cli")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
