"""DeepSeek HTTP adapter; no fake plan or broad fallback on model failure."""

from dataclasses import dataclass, field
import math
import os

import httpx

from backend.planner.service import PlannerUnavailable

DEEPSEEK_CHAT_URL = 'https://api.deepseek.com/chat/completions'


@dataclass(frozen=True)
class DeepSeekPlannerModel:
    api_key: str = field(repr=False)
    model: str = 'deepseek-flash'
    timeout: float = 20.0

    @classmethod
    def from_environment(cls):
        key = os.getenv('DEEPSEEK_PLANNER_API_KEY', '').strip()
        model = os.getenv('DEEPSEEK_PLANNER_MODEL', 'deepseek-flash').strip()
        try:
            timeout = float(os.getenv('DEEPSEEK_PLANNER_TIMEOUT_SECONDS', '20'))
        except ValueError:
            raise PlannerUnavailable('INVALID_PLANNER_CONFIGURATION') from None
        if not key or not model or not math.isfinite(timeout) or not 0 < timeout <= 120:
            raise PlannerUnavailable('INVALID_PLANNER_CONFIGURATION')
        return cls(key, model, timeout)

    def complete(self, messages):
        try:
            response = httpx.post(
                DEEPSEEK_CHAT_URL,
                headers={'Authorization': 'Bearer ' + self.api_key},
                json=dict(model=self.model, messages=messages, thinking={'type': 'disabled'},
                          response_format={'type': 'json_object'}, max_tokens=1024,
                          temperature=0, stream=False),
                timeout=self.timeout, follow_redirects=False,
            )
            response.raise_for_status()
            if len(response.content) > 131072:
                raise ValueError('response too large')
            choice = response.json()['choices'][0]
            message = choice['message']
            content = message.get('content')
            if (choice.get('finish_reason') != 'stop' or message.get('role') != 'assistant'
                    or message.get('tool_calls') or not isinstance(content, str)
                    or not content.strip()):
                raise ValueError('incomplete model response')
            return content
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise PlannerUnavailable('DEEPSEEK_PLANNER_FAILED') from None
