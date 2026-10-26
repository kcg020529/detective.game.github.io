"""LLM 호출 (D01 초안). 공급자·모델·키는 저장소 최상위 .env에서 읽는다.

지금은 DeepSeek만 지원한다. 표준 라이브러리만 쓰므로 따로 설치할 것이 없다.
[검토11] 요청 필드와 모델 이름은 DeepSeek 공식 문서(2026-10-21) 기준이고, 같은 날 실제 호출(10/21~22, 총 289건)로 동작을 확인했다.
         사고(thinking) 토큰이 과금되는지는 문서에 없어 확인하지 못했다.
[검토16] 재시도: JSON 모드는 가끔 빈 응답을 내므로(공식 문서에도 있음, 2026-10-21 90건 중 1건) 일시적 오류는 자동으로 다시 보낸다.
         기본 1회(.env의 LLM_RETRIES, 0~5). 다시 보내는 경우는 빈 응답, JSON 아님, reply 없음, 429/500/503, 연결 실패, 시간 초과뿐이다.
         키 오류(401)·잔액 부족(402)·요청 오류(400/422)·응답 잘림(max_tokens)은 반복해도 같아서 바로 실패로 처리한다.
         재시도해도 실패했을 때 사용자에게 무엇을 보여 줄지는 서버 쪽 설계(D01 남은 안건)이며 여기서는 정하지 않는다.
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # 저장소 최상위 (.env 위치)

# 공식 오류 코드 문서(2026-10-21): 429 요청이 너무 빠름, 500 서버 오류, 503 서버 과부하는 잠시 후 다시 시도하라고 안내한다.
RETRYABLE_HTTP = (429, 500, 503)
RETRY_WAIT_SEC = 1.0   # 서버·네트워크 문제일 때만 다시 보내기 전에 기다린다. 빈 응답은 바로 다시 보낸다.
MAX_RETRIES = 5

PROVIDERS = {
    "deepseek": {
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "default_model": "deepseek-flash",
        # 사고(thinking) 모드가 기본값이라 끈다. 캐릭터 대화에는 불필요하고 시간·토큰이 더 든다.
        "extra_body": {"thinking": {"type": "disabled"}},
    },
}


class LLMError(Exception):
    """LLM 호출이나 응답 해석 실패. 메시지에 API 키를 넣지 않는다.

    retryable: 다시 보내면 성공할 수 있는 일시적 실패인지. wait: 다시 보내기 전에 기다릴 초.
    attempts: 지금까지 보낸 횟수. usage: 실패한 시도를 포함해 이미 쓴 토큰(응답이 왔던 경우만).
    """

    def __init__(self, message, retryable=False, wait=0.0):
        super().__init__(message)
        self.retryable = retryable
        self.wait = wait
        self.attempts = 1
        self.usage = {}


def load_env(path=None):
    """.env의 KEY=VALUE 줄을 환경변수에 넣는다. 이미 설정된 값은 덮어쓰지 않는다."""
    path = Path(path) if path else ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _settings():
    load_env()
    name = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
    if name not in PROVIDERS:
        raise LLMError(f"지원하지 않는 LLM_PROVIDER: {name} (지원: {', '.join(PROVIDERS)})")
    p = PROVIDERS[name]
    key = os.environ.get(p["key_env"], "").strip()
    if not key:
        raise LLMError(f"{p['key_env']}가 비어 있습니다. 저장소 최상위 .env에 값을 넣어 주세요.")
    try:
        temperature = float(os.environ.get("LLM_TEMPERATURE") or "0.8")
        max_tokens = int(os.environ.get("LLM_MAX_TOKENS") or "400")
        timeout = float(os.environ.get("LLM_TIMEOUT_SEC") or "30")
        retries = int(os.environ.get("LLM_RETRIES") or "1")
    except ValueError:
        raise LLMError("LLM_TEMPERATURE, LLM_MAX_TOKENS, LLM_TIMEOUT_SEC, LLM_RETRIES는 숫자여야 합니다.") from None
    if not 0 <= retries <= MAX_RETRIES:
        raise LLMError(f"LLM_RETRIES는 0~{MAX_RETRIES} 사이여야 합니다.")
    return {
        "provider": name,
        "url": p["url"],
        "key": key,
        "model": os.environ.get(p["model_env"], "").strip() or p["default_model"],
        "extra_body": p["extra_body"],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
        "retries": retries,
    }


def _http_post(url, headers, body, timeout):
    secret = headers.get("Authorization", "").replace("Bearer ", "")
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        if secret:
            detail = detail.replace(secret, "***")
        raise LLMError(f"HTTP {e.code}: {detail}", retryable=e.code in RETRYABLE_HTTP, wait=RETRY_WAIT_SEC) from None
    except urllib.error.URLError as e:
        raise LLMError(f"연결 실패: {e.reason}", retryable=True, wait=RETRY_WAIT_SEC) from None
    except (TimeoutError, json.JSONDecodeError) as e:
        raise LLMError(f"응답 오류: {type(e).__name__}", retryable=True, wait=RETRY_WAIT_SEC) from None


def _add_usage(total, usage):
    """응답의 토큰 사용량(숫자 항목)을 total에 더한다. 실패해서 버린 시도의 토큰도 요금에는 잡히므로 함께 센다."""
    if isinstance(usage, dict):
        for k, v in usage.items():
            if isinstance(v, int) and not isinstance(v, bool):
                total[k] = total.get(k, 0) + v


def _parse(res, default_model):
    """응답 dict에서 JSON 답변을 꺼낸다. 다시 보내면 나아질 수 있는 실패는 retryable로 표시한다."""
    try:
        choice = res["choices"][0]
        raw = choice["message"]["content"] or ""
        finish = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise LLMError("응답 형식이 예상과 다릅니다.") from None
    if finish == "length":
        raise LLMError("응답이 max_tokens에서 잘렸습니다. .env의 LLM_MAX_TOKENS를 늘려 보세요.")
    if not raw.strip():
        raise LLMError("모델 응답이 비어 있습니다(빈 문자열 또는 공백뿐).", retryable=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise LLMError("모델 응답이 JSON이 아닙니다: " + raw[:200], retryable=True) from None
    if not isinstance(data, dict) or not isinstance(data.get("reply"), str):
        raise LLMError('JSON에 문자열 "reply"가 없습니다: ' + raw[:200], retryable=True)
    return {"data": data, "raw": raw, "model": res.get("model") or default_model}


def chat_json(system_prompt, user_message, post=None, sleep=time.sleep):
    """시스템 프롬프트와 사용자 질문을 보내고, JSON 객체로 된 응답을 받는다. 일시적 실패는 LLM_RETRIES만큼 다시 보낸다.

    반환: {"data": 해석한 dict(reply 포함), "raw": 응답 원문, "usage": 토큰 사용량(재시도로 버린 시도 포함),
           "model": 모델 이름, "attempts": 보낸 횟수(1이면 재시도 없음)}
    실패: LLMError. e.attempts에 보낸 횟수, e.usage에 이미 쓴 토큰이 들어 있다.
    post, sleep: 테스트용. post는 (url, headers, body, timeout)을 받아 응답 dict를 돌려주는 함수로, sleep은 대기 함수로 바꿔 끼울 수 있다.
    """
    s = _settings()
    body = {
        "model": s["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "response_format": {"type": "json_object"},
        "temperature": s["temperature"],
        "max_tokens": s["max_tokens"],
        "stream": False,
    }
    body.update(s["extra_body"])
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + s["key"]}
    allowed = 1 + s["retries"]
    spent = {}
    for attempt in range(1, allowed + 1):
        try:
            res = (post or _http_post)(s["url"], headers, body, s["timeout"])
            if isinstance(res, dict):
                _add_usage(spent, res.get("usage"))
            out = _parse(res, s["model"])
            out["usage"] = spent
            out["attempts"] = attempt
            return out
        except LLMError as e:
            e.attempts = attempt
            e.usage = spent
            if not e.retryable or attempt >= allowed:
                if attempt > 1:
                    e.args = (f"{e} (재시도 {attempt - 1}회 후에도 실패)",)
                raise
            if e.wait:
                sleep(e.wait)
