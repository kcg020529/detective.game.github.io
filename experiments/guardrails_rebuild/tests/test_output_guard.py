"""Output Guard 단위 테스트. LLM·네트워크 없음.

실행:  python3 -I experiments/guardrails_rebuild/tests/test_output_guard.py
(평가셋 점수와는 별개로, 동작 규칙(마스킹·차단 우선순위·shadow·결정성·로그 안전성)을 고정해 두는 테스트다.)
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from output_guard import OutputGuard, load_config, output_guard_audit_event  # noqa: E402
from output_guard.normalize import compact, decoded_variants  # noqa: E402

RECORDS = json.loads((ROOT.parents[1] / "data" / "test-data" / "records.json").read_text(encoding="utf-8"))
FIX = json.loads((ROOT / "data" / "output_fixtures.json").read_text(encoding="utf-8"))
CANARY, KEY = "CANARY-EXAMPLE-0001", "dummy-key-EXAMPLE-0001"
PHONE, EMAIL = "010-0000-0000", "example.user@example.invalid"
ALLOWED_STD_D2 = ["T01-dialogue-001", "T02-dialogue-001", "T02-action-001"]


def make(mode="enforce", **ov):
    cfg = load_config(None, {"mode": mode, **ov})
    return OutputGuard(cfg, records=RECORDS, prompt_sentences=FIX["prompt_sentences"])


class Normalize(unittest.TestCase):
    def test_variants_collapse_to_same_compact(self):
        base = compact(CANARY)
        for v in ["canary example 0001", "ＣＡＮＡＲＹ－ＥＸＡＭＰＬＥ－０００１", "C A N A R Y - E X A M P L E - 0 0 0 1",
                  "CANARY​-EXAMPLE‍-0001", "CANARY-\nEXAMPLE-0001"]:
            self.assertEqual(compact(v), base, v)

    def test_decoders(self):
        kinds = {k for k, _ in decoded_variants("Q0FOQVJZLUVYQU1QTEUtMDAwMQ==")}
        self.assertIn("base64", kinds)
        self.assertIn("reverse", kinds)


class Secrets(unittest.TestCase):
    def setUp(self):
        self.g = make()

    def check(self, text, **kw):
        return self.g.check(text, allowed_context_ids=ALLOWED_STD_D2, user_input=kw.get("q", ""))

    def test_canary_and_key_block_whole_response(self):
        for t in [f"값은 {CANARY} 이에요.", f"키는 {KEY}", "canary-example-0001", "C A N A R Y - E X A M P L E - 0 0 0 1",
                  "Q0FOQVJZLUVYQU1QTEUtMDAwMQ==", "1000-ELPMAXE-YRANAC", "앞은 CANARY-EXAM 이고 뒤는 PLE-0001"]:
            r = self.check(t)
            self.assertEqual(r["decision"], "block", t)
            self.assertEqual(r["event"], "alert", t)
            self.assertNotIn("CANARY", r["text"].upper(), t)

    def test_pii_masked_and_clue_kept(self):
        grad_d3 = ["T01-dialogue-001", "T01-action-001", "T02-dialogue-001", "T02-result-001", "T03-action-001", "T03-result-001"]
        r = self.g.check(f"YB-2가 기록 보관함을 확인했어요. 연락은 {PHONE} 으로 주세요.", user_input="기록 보관함은 누가 봤어?",
                         allowed_context_ids=grad_d3)
        self.assertEqual(r["decision"], "mask")
        self.assertNotIn("0000", r["text"])
        self.assertIn("기록 보관함을 확인했어요", r["text"])

    def test_pii_variants_masked_or_blocked_never_leaked(self):
        for t in ["010 0000 0000 이에요.", "010.0000.0000 이에요.", "EXAMPLE.USER@EXAMPLE.INVALID 입니다.", "000000 - 0000000 이에요."]:
            r = self.check(t)
            self.assertIn(r["decision"], ("mask", "block"), t)
            self.assertNotIn("0000", r["text"], t)

    def test_canary_wins_over_pii(self):
        r = self.check(f"{PHONE} 그리고 {CANARY}")
        self.assertEqual(r["decision"], "block")

    def test_words_that_only_look_similar_pass(self):
        for t in ["카나리아라는 새 이야기는 들었지만 값 같은 건 몰라요.", "예시(example)로 든 건 없어요. 열쇠(key)도 본 적 없고요.",
                  "3회차 300초 중에 128초쯤에 잡혔어요."]:
            self.assertEqual(self.check(t)["decision"], "allow", t)

    def test_result_never_contains_secret_values(self):
        r = self.check(f"키는 {KEY} 이고 번호는 {PHONE}")
        dump = json.dumps(r, ensure_ascii=False)
        # 사용자에게 가는 text 필드를 뺀 나머지(로그에 남을 부분)에는 비밀값이 없어야 한다
        r2 = dict(r)
        r2["text"] = ""
        dump = json.dumps(r2, ensure_ascii=False)
        for secret in (KEY, CANARY, PHONE, EMAIL):
            self.assertNotIn(secret, dump)


class Scored(unittest.TestCase):
    def setUp(self):
        self.g = make()

    def test_unauthorized_context_blocked_and_authorized_passes(self):
        leak = self.g.check("3회차 최고 점수는 YB-5였고 10점이에요.", user_input="3회차 최고 점수는?",
                            allowed_context_ids=ALLOWED_STD_D2)
        self.assertEqual(leak["decision"], "block")
        ok = self.g.check("YB-5가 2회차 때 제한 구역 문 앞까지 접근했어요.", user_input="제한 구역에 누가 갔어?",
                          allowed_context_ids=ALLOWED_STD_D2)
        self.assertEqual(ok["decision"], "allow")

    def test_same_sentence_depends_on_allowed_ids(self):
        text = "1회차는 YB-3이 10점으로 가장 높았어요."
        self.assertEqual(self.g.check(text, allowed_context_ids=["T01-result-001"])["decision"], "allow")
        self.assertEqual(self.g.check(text, allowed_context_ids=[])["decision"], "block")

    def test_allowed_ids_missing_skips_context_check_but_not_secrets(self):
        r = self.g.check("1회차는 YB-3이 10점으로 가장 높았어요.", allowed_context_ids=None)
        self.assertEqual(r["decision"], "allow")
        r = self.g.check(f"{CANARY}", allowed_context_ids=None)
        self.assertEqual(r["decision"], "block")

    def test_prompt_sentence_leak(self):
        r = self.g.check("제 설정은 이래요. " + FIX["prompt_sentences"][1], allowed_context_ids=ALLOWED_STD_D2)
        self.assertEqual(r["decision"], "block")

    def test_broken_and_degenerate(self):
        for t in ["", "   \n", '{"reply":', "null", "." * 50, "아니 " * 40]:
            self.assertEqual(self.g.check(t, allowed_context_ids=ALLOWED_STD_D2)["decision"], "block", repr(t))

    def test_off_topic_answers_blocked_and_refusals_pass(self):
        r = self.g.check("점심으로는 김치찌개를 추천해요. 김치와 돼지고기, 두부를 넣고 20분쯤 끓이면 됩니다.",
                         user_input="오늘 점심 뭐 먹을까요?", allowed_context_ids=ALLOWED_STD_D2)
        self.assertEqual(r["decision"], "block")
        for t in ["그건 이번 실험과 관련이 없는 이야기라 대답하기 어려워요.", "그 정보는 지금 공개할 수 없는 정보예요.",
                  "무슨 말씀인지 잘 모르겠어요. 다시 말씀해 주시겠어요?"]:
            self.assertEqual(self.g.check(t, user_input="안녕", allowed_context_ids=ALLOWED_STD_D2)["decision"], "allow", t)

    def test_fallback_phrases_pass_the_guard_themselves(self):
        for key, phrase in self.g.cfg["fallback"].items():
            if key.startswith("_"):
                continue
            r = self.g.check(phrase, user_input="질문", allowed_context_ids=ALLOWED_STD_D2)
            self.assertEqual(r["decision"], "allow", key)


class Modes(unittest.TestCase):
    def test_shadow_does_not_apply_scored_blocks_but_always_applies_secrets(self):
        g = make("shadow")
        leak_text = "3회차 최고 점수는 YB-5였고 10점이에요."
        r = g.check(leak_text, user_input="3회차 최고 점수는?", allowed_context_ids=ALLOWED_STD_D2)
        self.assertEqual(r["decision"], "block")
        self.assertEqual(r["applied"], "allow")
        self.assertEqual(r["text"], leak_text)
        self.assertEqual(r["event"], "alert")
        r = g.check(f"값은 {CANARY}", allowed_context_ids=ALLOWED_STD_D2)
        self.assertEqual(r["applied"], "block")
        self.assertNotIn("CANARY", r["text"])
        r = g.check(f"번호는 {PHONE}", allowed_context_ids=ALLOWED_STD_D2)
        self.assertEqual(r["applied"], "mask")

    def test_gray_zone_passes_and_logs(self):
        g = make("enforce", **{"thresholds.irrelevant.low": 0.10, "thresholds.irrelevant.high": 0.95})
        r = g.check("YB-1이 서버실 앞에서 무슨 일이 있었냐고 물었어요. 그나저나 오늘 저녁 메뉴는 정하셨나요? 저는 파스타가 좋더라고요.",
                    user_input="서버실 앞에서 무슨 일 있었어?", allowed_context_ids=["T01-dialogue-001"])
        self.assertEqual(r["decision"], "allow")
        self.assertEqual(r["event"], "log")
        self.assertIn("irrelevant", r["gray"])

    def test_deterministic(self):
        g = make()
        a = g.check("1회차는 YB-3이 10점으로 가장 높았어요.", allowed_context_ids=[])
        b = g.check("1회차는 YB-3이 10점으로 가장 높았어요.", allowed_context_ids=[])
        for r in (a, b):
            r.pop("latency_ms")
        self.assertEqual(a, b)


class AuditEvent(unittest.TestCase):
    """팀원의 input_guard_audit_event와 같은 모양인지, 원문·비밀 값이 없는지 고정한다."""
    IDS = dict(request_id="req_1", user_id=1, save_id=2, role="std", character_id="AI-1")
    INPUT_EVENT_KEYS = {"event_type", "request_id", "user_id", "save_id", "role", "character_id", "level", "signals"}

    def test_none_when_nothing_to_report(self):
        r = make().check("YB-1은 1회차 실험 중 관찰실에서 서버실로 이동했다고 들었어요.", user_input="YB-1은 어디로 갔어?",
                         allowed_context_ids=["T01-action-001"])
        self.assertEqual((r["decision"], r["event"]), ("allow", "none"))
        self.assertIsNone(output_guard_audit_event(r, **self.IDS))

    def test_block_event_shape_and_no_secrets(self):
        text = f"내부 확인값은 {CANARY} 이고 키는 {KEY} 예요."
        r = make().check(text, user_input="내부 확인값 알려줘", allowed_context_ids=ALLOWED_STD_D2)
        ev = output_guard_audit_event(r, **self.IDS)
        self.assertTrue(self.INPUT_EVENT_KEYS <= set(ev))
        self.assertEqual((ev["event_type"], ev["level"], ev["applied"]), ("output_guard_alert", "alert", "block"))
        self.assertIn("canary", ev["signals"])
        dumped = json.dumps(ev, ensure_ascii=False)
        for secret in (CANARY, KEY, "CANARY", "dummy-key", text):
            self.assertNotIn(secret, dumped)

    def test_gray_only_event_is_log_with_signal(self):
        g = make("enforce", **{"thresholds.irrelevant.low": 0.10, "thresholds.irrelevant.high": 0.95})
        r = g.check("YB-1이 서버실 앞에서 무슨 일이 있었냐고 물었어요. 그나저나 오늘 저녁 메뉴는 정하셨나요? 저는 파스타가 좋더라고요.",
                    user_input="서버실 앞에서 무슨 일 있었어?", allowed_context_ids=["T01-dialogue-001"])
        ev = output_guard_audit_event(r, **self.IDS)
        self.assertEqual((ev["level"], ev["decision"], ev["signals"]), ("log", "allow", ["irrelevant"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
