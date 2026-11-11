"""Клиент модели: любой OpenAI-совместимый сервер, адрес и модель из
переменных окружения LLM_BASE_URL и LLM_MODEL.

Использование:
    from support.llm import LLMClient
    llm = LLMClient()
    calls, usage = llm.chat(messages, TOOL_SCHEMAS)
    # calls: [{"id": ..., "name": ..., "arguments": {...}}, ...]
    # usage: {"prompt": int, "completion": int, "content": str}
    # content - текст, если модель ответила словами вместо вызова.

Клиент не повторяет запросы сам: ретраи при 429 и обрывах - ваша
обёртка.
"""
import json
import os

from openai import OpenAI

from support import journal

BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))


class LLMClient:
    def __init__(self):
        self.client = OpenAI(base_url=BASE_URL, api_key="ollama",
                             timeout=TIMEOUT, max_retries=0)

    def chat(self, messages: list, tools: list) -> tuple[list, dict]:
        journal.trace("llm_call", model=MODEL, url=BASE_URL,
                      messages=len(messages))
        response = self.client.chat.completions.create(
            model=MODEL, messages=messages, tools=tools,
            tool_choice="required", temperature=0,
        )
        message = response.choices[0].message
        calls = []
        for tc in message.tool_calls or []:
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except ValueError:
                arguments = {}
            calls.append({"id": tc.id, "name": tc.function.name,
                          "arguments": arguments})
        usage = response.usage
        return calls, {"prompt": usage.prompt_tokens if usage else 0,
                       "completion": usage.completion_tokens if usage else 0,
                       "content": message.content or ""}


def as_openai_tool_calls(calls: list) -> list:
    """Переводит вызовы обратно в формат assistant-сообщения."""
    return [{"id": call["id"], "type": "function",
             "function": {"name": call["name"],
                          "arguments": json.dumps(call["arguments"],
                                                  ensure_ascii=False)}}
            for call in calls]
