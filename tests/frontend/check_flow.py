import sys
import tempfile
from pathlib import Path
from _server import frontend_url
from playwright.sync_api import sync_playwright

# J03 1·2단계: Mock Api 경유 전체 흐름 확인 (8010)
URL = frontend_url()
errors, results = [], []


def check(name, ok, extra=""):
    results.append(("OK " if ok else "FAIL ") + name + (f" | {extra}" if extra else ""))


def login(pg, fail=None):
    pg.wait_for_selector("#start-button:not([hidden])", timeout=30000)
    pg.click("#start-button")
    pg.fill("#login-id", "researcher01")
    pg.fill("#login-pw", "x")
    if fail:
        pg.evaluate(f"Api.mockControl.failNext('{fail}')")
    pg.click("#login-submit")


def enter_slot(pg, slot, opened=False):
    if not opened:
        pg.click("#menu-continue")
    pg.wait_for_selector(f"[data-slot='{slot}']", timeout=8000)
    pg.wait_for_timeout(1000)
    pg.click(f"[data-slot='{slot}']")
    pg.wait_for_selector("[data-desktop]", timeout=15000)
    pg.wait_for_timeout(1500)


def to_gate(pg):
    pg.click("[data-start]")
    pg.click("[data-action=exit]")
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1280, "height": 960})
    pg.on("pageerror", lambda e: errors.append(f"pageerror {e}"))
    pg.on("console", lambda m: m.type == "error" and errors.append(f"console {m.text}"))
    pg.on("response", lambda r: r.status >= 400 and errors.append(f"{r.status} {r.url}"))
    pg.goto(URL)
    check("Api mode mock", pg.evaluate("Api.mode") == "mock")
    label_rows = pg.evaluate("""(() => {
      const now = performance.now();
      const saved = bots.slice(0, 2).map(({ x, shownAt }) => ({ x, shownAt }));
      const draws = [];
      const fillText = ctx.fillText;
      bots[0].x = bots[1].x = 30;
      bots[0].shownAt = bots[1].shownAt = now - 500;
      ctx.fillText = function (value, x, y, ...rest) {
        if (String(value).startsWith('YB-')) draws.push(y);
        return fillText.call(this, value, x, y, ...rest);
      };
      try { drawBotLabels(now); }
      finally {
        ctx.fillText = fillText;
        bots.slice(0, 2).forEach((bot, i) => Object.assign(bot, saved[i]));
      }
      return draws.length === 2 && Math.abs(draws[1] - draws[0]) === 3 * S;
    })()""")
    check("nearby bot labels use separate rows", label_rows)

    # 로그인 실패 → 메시지
    login(pg, fail="SERVICE_UNAVAILABLE")
    pg.wait_for_function("document.querySelector('#login-message').textContent.length > 0", timeout=5000)
    check("login error message", True, pg.inner_text("#login-message"))
    pg.evaluate("""(() => {
      const listSaves = Api.listSaves;
      Api.listSaves = async (...args) => {
        const result = await listSaves(...args);
        const save = result.saves.find(Boolean);
        if (save) save.last_played_at = '2026-10-25 16:00:00';
        return result;
      };
    })()""")
    pg.click("#login-submit")
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)
    check("lobby continue info", "Day 2" in pg.inner_text("#continue-info") and "단서" not in pg.inner_text("#continue-info"), pg.inner_text("#continue-info"))

    # 이어하기 슬롯 1 (grad Day 2)
    pg.click("#menu-continue")
    pg.wait_for_selector("[data-slot='0']", timeout=8000)
    check("UTC save date displayed in KST", "10월 26일" in pg.inner_text("[data-slot='0']"), pg.inner_text("[data-slot='0']").replace("\n", " "))
    enter_slot(pg, 0, opened=True)
    check("desktop status", True, pg.inner_text(".c-task-status").replace("\n", " "))

    # 메신저: 대기 "…" → 타자 → 단서
    pg.click("[data-open=messenger]")
    pg.wait_for_selector("[data-ask='0']")
    pg.evaluate("Api.mockControl.delayNext(1000)")
    pg.click("[data-ask='0']")
    pg.wait_for_timeout(60)
    check("pending label", "응답 대기" in pg.inner_text("[data-chat-log] .c-bubble:last-child"))
    pg.wait_for_timeout(300)  # 3단계: '…'는 300ms 뒤부터
    pending = pg.inner_text("[data-chat-log] .c-bubble:last-child .c-answer-text")
    check("pending bubble", pending.strip() == "…", repr(pending))
    check("buttons disabled while pending", pg.locator("[data-ask][disabled]").count() == 4)
    pg.wait_for_function("!document.querySelector('[data-ask]').disabled", timeout=10000)
    check("reply typed", "관찰실" in pg.inner_text("[data-chat-log] .c-bubble:last-child"))
    check("no clue UI", "단서" not in pg.inner_text("[data-toast]") and "단서" not in pg.inner_text("[data-desktop]"), pg.inner_text("[data-toast]"))

    # 채팅 오류(403) → 말풍선 제거, 버튼 복귀 (503 재시도는 check_errors.py)
    before = pg.locator("[data-chat-log] .c-bubble").count()
    pg.evaluate("Api.mockControl.failNext('ACCESS_DENIED')")
    pg.click("[data-ask='1']")
    pg.wait_for_timeout(700)
    check("chat error rollback", pg.locator("[data-chat-log] .c-bubble").count() == before and pg.locator("[data-ask][disabled]").count() == 0, pg.inner_text("[data-toast]"))

    # 자유 질문
    pg.fill("[data-compose]", "서버실 기록 봤어?")
    pg.click("[data-send]")
    pg.wait_for_function("!document.querySelector('[data-ask]').disabled", timeout=10000)
    check("free question", pg.locator("[data-chat-log] .c-bubble").count() == before + 1)

    # 기록 보관함 삭제 확인
    check("archive removed", pg.locator("[data-open=archive]").count() == 0 and "기록 보관함" not in pg.inner_text("[data-desktop]"))

    # 메모 디바운스 저장
    pg.click("[data-open=notebook]")
    pg.fill("[data-memo]", "YB-2 수상함")
    pg.wait_for_timeout(1500)
    clue_count_before = pg.locator("[data-notebook-body] li").count()

    # Day 진행 2 → 6
    for _ in range(4):
        pg.click("[data-day-next]")
        pg.click("[data-day-confirm]")
        pg.wait_for_selector("[data-day-curtain]", state="visible", timeout=5000)
        pg.wait_for_selector("[data-day-curtain]", state="hidden", timeout=8000)
    check("day 6", "6" in pg.inner_text(".c-task-status"), pg.inner_text(".c-task-status").replace("\n", " "))
    check("day button off at 6", pg.locator("[data-day-next]:not([disabled]):visible").count() == 0)

    # 지목 YB-2 → 판정서
    pg.click("[data-open=accuse]")
    pg.click("[data-suspect='1']")
    pg.click("[data-submit-accuse]")
    pg.click("[data-accuse-confirm]")
    pg.wait_for_selector("[data-verdict]", timeout=8000)
    pg.wait_for_timeout(3000)
    check("verdict hit", "적중" in pg.inner_text("[data-verdict-stamp]"))
    check("verdict evidence", True, pg.inner_text(".c-verdict-list").replace("\n", " "))
    pg.screenshot(path=str(Path(tempfile.gettempdir()) / "prism-j04-j03-verdict.png"))
    pg.click("[data-verdict-back]")

    # 정문 → 다시 이어하기: 메모·지목 유지 (+ YB-3 대화 45개 심어 두고 이전 대화 더 보기 확인)
    pg.evaluate("Api.mockControl.seedChats('YB-3', 45)")
    to_gate(pg)
    check("lobby after day6", "Day 6" in pg.inner_text("#continue-info"), pg.inner_text("#continue-info"))
    enter_slot(pg, 0)
    pg.click("[data-open=notebook]")
    check("memo persisted", pg.input_value("[data-memo]") == "YB-2 수상함")
    pg.click("[data-open=accuse]")
    check("accusation persisted", pg.locator("[data-verdict-open]").count() == 1)

    # 이전 대화 더 보기: 20개씩, 스크롤 위치 유지
    pg.click("[data-open=messenger]")
    pg.click("[data-yb='2']")
    pg.wait_for_selector("[data-load-older]", timeout=5000)
    n1 = pg.locator("[data-chat-log] .c-bubble").count()
    first_q = pg.inner_text("[data-chat-log] .c-bubble >> nth=0")
    pg.click("[data-load-older]")
    pg.wait_for_function(f"document.querySelectorAll('[data-chat-log] .c-bubble').length > {n1}", timeout=5000)
    n2 = pg.locator("[data-chat-log] .c-bubble").count()
    log_box = pg.locator("[data-chat-log]").bounding_box()
    old_first = pg.locator("[data-chat-log] .c-bubble").nth(n2 - n1).bounding_box()
    check("load older page 10→20 pairs", n1 == 10 and n2 == 20, f"{n1}->{n2}")
    check("scroll kept on old first message", log_box["y"] - 5 <= old_first["y"] <= log_box["y"] + log_box["height"], f"log y={log_box['y']:.0f} h={log_box['height']:.0f} old-first y={old_first['y']:.0f}")
    check("old first message same", pg.inner_text(f"[data-chat-log] .c-bubble >> nth={n2 - n1}") == first_q)
    while pg.locator("[data-load-older]").count():
        n = pg.locator("[data-chat-log] .c-bubble").count()
        pg.click("[data-load-older]")
        pg.wait_for_function(f"document.querySelectorAll('[data-chat-log] .c-bubble').length > {n}", timeout=5000)
    texts = pg.locator("[data-chat-log] .c-bubble").all_inner_texts()
    check("all 45 seeded pairs, no 응답 없음", len(texts) == 45 and not any("응답 없음" in t for t in texts), str(len(texts)))

    # 새 수사 prof → 빈 슬롯 3
    to_gate(pg)
    pg.click("#menu-new")
    pg.check("input[name=role][value=prof]", force=True)
    pg.click("#role-view [type=submit]")
    pg.wait_for_selector("[data-slot='2']", timeout=8000)
    pg.wait_for_timeout(1000)
    pg.click("[data-slot='2']")
    pg.wait_for_selector("[data-desktop]", timeout=15000)
    pg.wait_for_timeout(1500)
    check("new prof save", "교수" in pg.inner_text(".c-task-status"), pg.inner_text(".c-task-status").replace("\n", " "))

    # 로그아웃 → 다시 로그인: Save 3개 유지
    to_gate(pg)
    pg.click("#logout")
    login(pg)
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)
    pg.click("#menu-continue")
    pg.wait_for_selector("[data-slot='2']", timeout=8000)
    pg.wait_for_timeout(800)
    check("3 saves after relogin", pg.locator(".c-session-card.is-empty").count() == 0)

    # ?skip=1
    pg.goto(URL + "?skip=1")
    pg.wait_for_selector("[data-desktop]", timeout=15000)
    check("skip=1 desktop", True, pg.inner_text(".c-task-status").replace("\n", " "))
    b.close()

print("\n".join(results))
print("errors:", errors)

failed = any(item.startswith("FAIL ") for item in results) or bool(errors)
sys.exit(1 if failed else 0)
