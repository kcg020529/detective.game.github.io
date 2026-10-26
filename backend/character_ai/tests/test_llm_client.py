"""llm_client 테스트. 실제 API를 호출하지 않고 가짜 응답으로만 검사한다. 키는 시험용 가짜 값이다.

실행: python3 -I backend/character_ai/tests/test_llm_client.py   (pytest가 있으면 pytest로도 실행된다)
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm_client  # noqa: E402
from llm_client import LLMError, chat_json, load_env  # noqa: E402

FAKE_KEY = "sk-TEST-NOT-A-REAL-KEY"


@contextlib.contextmanager
def env(**values):
    """환경변수를 잠시 바꾸고 끝나면 되돌린다. 실제 .env가 있어도 영향받지 않도록 필요한 값을 모두 지정한다."""
    base = {"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": FAKE_KEY, "DEEPSEEK_MODEL": "",
            "LLM_TEMPERATURE": "0.8", "LLM_MAX_TOKENS": "400", "LLM_TIMEOUT_SEC": "30", "LLM_RETRIES": "1"}
    base.update(values)
    saved = {k: os.environ.get(k) for k in base}
    os.environ.update(base)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _ok(content, finish="stop"):
    return {"model": "deepseek-flash",
            "choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def test_load_env_parses_lines_and_keeps_existing():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / ".env"
        p.write_text('# 주석\n\nA_TEST_PLAIN=abc\nA_TEST_QUOTED="x y"\nA_TEST_EMPTY=\nA_TEST_KEEP=new\n', encoding="utf-8")
        for k in ("A_TEST_PLAIN", "A_TEST_QUOTED", "A_TEST_EMPTY"):
            os.environ.pop(k, None)
        os.environ["A_TEST_KEEP"] = "old"
        try:
            load_env(p)
            assert os.environ["A_TEST_PLAIN"] == "abc"
            assert os.environ["A_TEST_QUOTED"] == "x y"
            assert os.environ["A_TEST_EMPTY"] == ""
            assert os.environ["A_TEST_KEEP"] == "old"  # 이미 있는 값은 덮어쓰지 않는다
        finally:
            for k in ("A_TEST_PLAIN", "A_TEST_QUOTED", "A_TEST_EMPTY", "A_TEST_KEEP"):
                os.environ.pop(k, None)


def test_request_shape():
    seen = {}

    def fake(url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=body, timeout=timeout)
        return _ok('{"reply": "안녕하세요", "used": ["m1"]}')

    with env():
        res = chat_json("SYSTEM", "질문", post=fake)
    b = seen["body"]
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer " + FAKE_KEY
    assert b["model"] == "deepseek-flash"  # DEEPSEEK_MODEL이 비어 있으면 기본값
    assert [m["role"] for m in b["messages"]] == ["system", "user"]
    assert b["messages"][0]["content"] == "SYSTEM" and b["messages"][1]["content"] == "질문"
    assert b["response_format"] == {"type": "json_object"}
    assert b["thinking"] == {"type": "disabled"} and b["stream"] is False
    assert b["temperature"] == 0.8 and b["max_tokens"] == 400
    assert res["data"]["reply"] == "안녕하세요" and res["usage"]["completion_tokens"] == 5


def test_model_and_numbers_come_from_env():
    seen = {}

    def fake(url, headers, body, timeout):
        seen.update(body=body, timeout=timeout)
        return _ok('{"reply": "ok"}')

    with env(DEEPSEEK_MODEL="deepseek-v4-pro", LLM_TEMPERATURE="0.3", LLM_MAX_TOKENS="123", LLM_TIMEOUT_SEC="5"):
        chat_json("S", "Q", post=fake)
    assert seen["body"]["model"] == "deepseek-v4-pro"
    assert seen["body"]["temperature"] == 0.3 and seen["body"]["max_tokens"] == 123 and seen["timeout"] == 5.0


def _raises(fn, text):
    try:
        fn()
    except LLMError as e:
        assert text in str(e), str(e)
        assert FAKE_KEY not in str(e)
        return
    raise AssertionError("LLMError가 발생하지 않음: " + text)


def test_bad_responses_raise_clear_errors():
    with env():
        _raises(lambda: chat_json("S", "Q", post=lambda *a: _ok("JSON이 아님")), "JSON이 아닙니다")
        _raises(lambda: chat_json("S", "Q", post=lambda *a: _ok('{"text": "x"}')), '"reply"')
        _raises(lambda: chat_json("S", "Q", post=lambda *a: _ok('{"reply": "잘린', finish="length")), "max_tokens")
        _raises(lambda: chat_json("S", "Q", post=lambda *a: {"unexpected": 1}), "형식이 예상과 다릅니다")
        _raises(lambda: chat_json("S", "Q", post=lambda *a: _ok(None)), "비어 있습니다")  # content가 null
        _raises(lambda: chat_json("S", "Q", post=lambda *a: _ok("   \n  ")), "비어 있습니다")  # 공백뿐인 응답(2026-10-21 실제로 나옴)


def test_missing_key_and_bad_settings():
    with env(DEEPSEEK_API_KEY=""):
        _raises(lambda: chat_json("S", "Q", post=lambda *a: _ok("{}")), "DEEPSEEK_API_KEY")
    with env(LLM_PROVIDER="unknown"):
        _raises(lambda: chat_json("S", "Q", post=lambda *a: _ok("{}")), "지원하지 않는")
    with env(LLM_MAX_TOKENS="abc"):
        _raises(lambda: chat_json("S", "Q", post=lambda *a: _ok("{}")), "숫자")


def test_http_error_message_hides_key():
    def fake_urlopen(req, timeout=None):
        body = io.BytesIO(('{"error": "invalid key ' + FAKE_KEY + '"}').encode("utf-8"))
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, body)

    original = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        with env():
            try:
                chat_json("S", "Q")
            except LLMError as e:
                assert "401" in str(e) and FAKE_KEY not in str(e), str(e)
                return
            raise AssertionError("LLMError가 발생하지 않음")
    finally:
        urllib.request.urlopen = original


def test_connection_error_is_reported():
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("name resolution failed")

    original = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        with env():
            _raises(lambda: chat_json("S", "Q", sleep=lambda s: None), "연결 실패")
    finally:
        urllib.request.urlopen = original


# --- 재시도 ([검토16]) ---

def _sequence(*responses):
    """호출할 때마다 responses를 차례로 돌려주고 호출 횟수를 센다. 예외 객체는 던진다."""
    calls = []

    def fake(url, headers, body, timeout):
        calls.append(1)
        r = responses[min(len(calls), len(responses)) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    fake.calls = calls
    return fake


def test_blank_response_is_retried_and_tokens_are_summed():
    fake = _sequence(_ok("   "), _ok('{"reply": "안녕하세요", "used": []}'))
    sleeps = []
    with env():
        res = chat_json("S", "Q", post=fake, sleep=sleeps.append)
    assert len(fake.calls) == 2 and res["attempts"] == 2 and res["data"]["reply"] == "안녕하세요"
    assert res["usage"]["prompt_tokens"] == 20 and res["usage"]["completion_tokens"] == 10  # 버린 시도의 토큰도 센다
    assert sleeps == []  # 빈 응답은 기다리지 않고 바로 다시 보낸다


def test_success_on_first_try_has_one_attempt():
    fake = _sequence(_ok('{"reply": "ok"}'))
    with env():
        res = chat_json("S", "Q", post=fake)
    assert len(fake.calls) == 1 and res["attempts"] == 1


def test_gives_up_after_retries_and_reports_attempts():
    fake = _sequence(_ok(""))
    with env():
        try:
            chat_json("S", "Q", post=fake)
        except LLMError as e:
            assert "비어 있습니다" in str(e) and "재시도 1회 후에도 실패" in str(e), str(e)
            assert e.attempts == 2 and e.usage["prompt_tokens"] == 20
            assert len(fake.calls) == 2
            return
    raise AssertionError("LLMError가 발생하지 않음")


def test_retries_setting_controls_attempts():
    for retries, expected in (("0", 1), ("3", 4)):
        fake = _sequence(_ok(""))
        with env(LLM_RETRIES=retries):
            try:
                chat_json("S", "Q", post=fake)
            except LLMError:
                pass
        assert len(fake.calls) == expected, (retries, len(fake.calls))
    with env(LLM_RETRIES="9"):
        _raises(lambda: chat_json("S", "Q", post=_sequence(_ok("{}"))), "LLM_RETRIES")
    with env(LLM_RETRIES="abc"):
        _raises(lambda: chat_json("S", "Q", post=_sequence(_ok("{}"))), "숫자")


def test_truncated_and_bad_structure_are_not_retried():
    for bad in (_ok('{"reply": "잘린', finish="length"), {"unexpected": 1}):
        fake = _sequence(bad)
        with env():
            try:
                chat_json("S", "Q", post=fake)
            except LLMError:
                pass
        assert len(fake.calls) == 1, bad


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _with_urlopen(fn, scripted):
    """urllib의 urlopen을 scripted(호출마다 하나씩 소비하는 목록)로 바꿔서 fn을 실행한다. 호출 횟수를 돌려준다."""
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(1)
        item = scripted[min(len(calls), len(scripted)) - 1]
        if isinstance(item, Exception):
            raise item
        return _FakeResp(item)

    original = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        fn()
    finally:
        urllib.request.urlopen = original
    return len(calls)


def _http_error(code, text="x"):
    return urllib.error.HTTPError("https://example.invalid", code, "err", {}, io.BytesIO(text.encode("utf-8")))


def test_server_busy_is_retried_with_wait():
    sleeps, out = [], {}

    def run():
        with env():
            out["res"] = chat_json("S", "Q", sleep=sleeps.append)

    n = _with_urlopen(run, [_http_error(503, "overloaded"), _ok('{"reply": "ok"}')])
    assert n == 2 and out["res"]["attempts"] == 2 and sleeps == [1.0]


def test_auth_balance_and_bad_request_are_not_retried():
    for code in (400, 401, 402, 422):
        def run():
            with env():
                _raises(lambda: chat_json("S", "Q", sleep=lambda s: None), f"HTTP {code}")

        n = _with_urlopen(run, [_http_error(code, "nope")])
        assert n == 1, (code, n)


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print("FAIL", name, "->", repr(e))
    print(f"실패 {failed}건")
    sys.exit(1 if failed else 0)
