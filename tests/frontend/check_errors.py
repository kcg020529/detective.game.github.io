import sys
import tempfile
from pathlib import Path
from _server import frontend_url
from playwright.sync_api import sync_playwright

# J03 3단계: 오류 코드별 화면·기다림 표시 확인 (Mock, 8010)
URL = frontend_url()
errors, results = [], []

# 요청 ID 확인용: sendChat·advanceDay 인자 기록
SPY = """(() => {
window.__calls = [];
for (const name of ['sendChat', 'advanceDay', 'submitAccusation']) {
  const orig = Api[name];
  Api[name] = (...args) => { __calls.push([name, ...args]); return orig(...args); };
}
})()"""


def check(name, ok, extra=""):
    results.append(("OK " if ok else "FAIL ") + name + (f" | {extra}" if extra else ""))
    print(results[-1], flush=True)


def fail_next(pg, code):
    pg.evaluate(f"Api.mockControl.failNext('{code}')")


def login(pg):
    pg.wait_for_selector("#start-button:not([hidden])", timeout=30000)
    pg.click("#start-button")
    pg.fill("#login-id", "researcher01")
    pg.fill("#login-pw", "x")
    pg.click("#login-submit")
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)


def open_session(pg):
    pg.click("#menu-continue")
    pg.wait_for_selector("[data-slot='0']", timeout=8000)
    pg.wait_for_timeout(1000)


def enter(pg, slot=0):
    pg.click(f"[data-slot='{slot}']")
    pg.wait_for_selector("[data-desktop]", timeout=15000)
    pg.wait_for_timeout(1500)


def last_bubble(pg):
    return pg.inner_text("[data-chat-log] .c-bubble:last-child")


def ask_idle(pg):
    pg.wait_for_function("!document.querySelector('[data-ask]').disabled", timeout=10000)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1280, "height": 960})
    pg.on("pageerror", lambda e: errors.append(f"pageerror {e}"))
    pg.on("console", lambda m: m.type == "error" and "favicon" not in m.text and errors.append(f"console {m.text}"))
    pg.goto(URL)
    login(pg)

    # Mock: 숫자 id, 같은 재시도 ID는 한 번만 반영
    ids = pg.evaluate("Api.listSaves().then(r => r.saves.map(s => typeof s.save_id))")
    check("mock save_id numeric", ids and all(t == "number" for t in ids), str(ids))
    dedupe = pg.evaluate("""(async () => {
      const id = (await Api.listSaves()).saves[1].save_id;
      const a = await Api.advanceDay(id, 'same-1'); const b2 = await Api.advanceDay(id, 'same-1');
      const s = await Api.getSave(id); return [a.game_state.current_day, b2.game_state.current_day, s.day];
    })()""")
    check("mock advanceDay dedupe by client_request_id", dedupe[0] == dedupe[1] == dedupe[2] == 2, str(dedupe))

    # 출입증 판독 중 401 → 로그인, 진입 화면 처리기 정리, 재로그인 정상
    open_session(pg)
    fail_next(pg, "AUTH_REQUIRED")
    pg.click("[data-slot='0']")
    pg.wait_for_selector("#login-view:not([hidden])", timeout=10000)
    check("401 during badge read → login", "만료" in pg.inner_text("#login-message"))
    for key in ["ArrowRight", "ArrowLeft", "Escape"]:
        pg.keyboard.press(key)
    pg.wait_for_timeout(500)
    check("401 entry screen cleaned", pg.evaluate("document.querySelector('.play-c').hidden") and pg.locator("#login-view:not([hidden])").count() == 1 and pg.input_value("#login-id") == "researcher01")
    pg.fill("#login-pw", "x")
    pg.click("#login-submit")
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)
    open_session(pg)

    # 출입증: 403 → 리더기 빨간 문구, 다시 누르면 진입
    fail_next(pg, "ACCESS_DENIED")
    pg.click("[data-slot='0']")
    pg.wait_for_timeout(4500)
    check("403 on session stays", pg.locator("[data-desktop]").count() == 0, pg.inner_text("[data-reader-status]") if pg.locator("[data-reader-status]").count() else "")
    # 출입증: 판독 뒤 Save 불러오기 지연 → '기록 불러오는 중…'
    pg.evaluate("(() => { const o = Api.getSave; Api.getSave = (...a) => new Promise(r => setTimeout(r, 1500)).then(() => o(...a)); window.__restoreGetSave = () => { Api.getSave = o; }; })()")
    pg.click("[data-slot='0']")
    pg.wait_for_function("document.body.innerText.includes('기록 불러오는 중')", timeout=8000)
    check("session waiting text", True)
    pg.wait_for_selector("[data-desktop]", timeout=15000)
    pg.evaluate("__restoreGetSave()")
    pg.wait_for_timeout(1500)
    pg.evaluate(SPY)

    pg.click("[data-open=messenger]")
    pg.wait_for_selector("[data-ask='0']")

    # 기다림: 300ms 뒤 '…'
    pg.evaluate("Api.mockControl.delayNext(1500)")
    pg.click("[data-ask='0']")
    pg.wait_for_timeout(120)
    early = last_bubble(pg)
    pg.wait_for_timeout(400)
    late = last_bubble(pg)
    check("pending label", "응답 대기" in early, early.split("\n")[1])
    check("pending hidden <300ms, shown after", "…" not in early.split("\n")[-1] and "…" in late, f"{early!r} / {late!r}")
    ask_idle(pg)

    # 503 → 말풍선 유지 + 다시 보내기 (같은 요청 ID)
    fail_next(pg, "SERVICE_UNAVAILABLE")
    pg.click("[data-ask='1']")
    pg.wait_for_selector("[data-retry-chat]", timeout=5000)
    check("503 bubble kept with retry", "응답 실패" in last_bubble(pg))
    check("503 failed bubble no '…'", "…" not in last_bubble(pg) and pg.locator("[data-chat-log] .c-bubble:last-child .c-caret").count() == 0, last_bubble(pg).replace("\n", " "))
    pg.click("[data-retry-chat]")
    ask_idle(pg)
    calls = pg.evaluate("__calls.filter(c => c[0] === 'sendChat').slice(-2).map(c => c[4])")
    check("503 retry same client_request_id", len(calls) == 2 and calls[0] == calls[1] and calls[0], str(calls))
    check("503 retry answered", "YB-4" in last_bubble(pg) or "████" in last_bubble(pg), last_bubble(pg)[:40])

    # 422 → 입력창에 글자 복원 + 입력창 위 오류
    fail_next(pg, "VALIDATION_ERROR")
    pg.fill("[data-compose]", "아무 질문")
    pg.click("[data-send]")
    pg.wait_for_timeout(800)
    check("422 compose restored", pg.input_value("[data-compose]") == "아무 질문")
    check("422 inline error", len(pg.inner_text("[data-chat-error]")) > 0, pg.inner_text("[data-chat-error]"))
    pg.fill("[data-compose]", "")

    # 연결 끊김 → 띠 + 다시 시도 → 띠 사라짐
    fail_next(pg, "NETWORK_ERROR")
    pg.click("[data-ask='2']")
    pg.wait_for_selector("[data-connection]:not([hidden])", timeout=5000)
    check("network banner shown", True, pg.inner_text("[data-connection]"))
    check("network bubble retry", pg.locator("[data-retry-chat]").count() >= 1)
    pg.click("[data-retry-connection]")
    pg.wait_for_selector("[data-connection]", state="hidden", timeout=5000)
    check("network banner cleared", True)
    pg.wait_for_timeout(1000)

    pg.evaluate("Api.mockControl.seedChats('YB-1', 60)")  # 아래 재진입 뒤 '이전 대화 더 보기' 오류 확인용

    # Day: 503 → 확인 창 복귀, 재시도 같은 ID / 409 → 최신 상태
    pg.click("[data-day-next]")
    fail_next(pg, "SERVICE_UNAVAILABLE")
    pg.click("[data-day-confirm]")
    pg.wait_for_timeout(800)
    check("day 503 dialog back", pg.locator("[data-day-dialog]:not([hidden])").count() == 1)
    pg.click("[data-day-confirm]")
    pg.wait_for_selector("[data-day-curtain]", state="hidden", timeout=8000)
    pg.wait_for_timeout(2500)
    ids = pg.evaluate("__calls.filter(c => c[0] === 'advanceDay').slice(-2).map(c => c[2])")
    check("day 503 retry same client_request_id", len(ids) == 2 and ids[0] == ids[1] and ids[0] is not None, str(ids))
    day_before = pg.inner_text(".c-task-status")
    pg.click("[data-day-next]")
    fail_next(pg, "STATE_CONFLICT")
    pg.click("[data-day-confirm]")
    pg.wait_for_timeout(1500)
    check("day 409 synced", "최신 상태" in pg.inner_text("[data-toast]") and pg.inner_text(".c-task-status").split("·")[0] == day_before.split("·")[0], pg.inner_text("[data-toast]"))

    # 첫 로드 실패 → '다시 시도' 버튼 (정문 → 재진입 시 YB-1 listChats 한 번 실패)
    pg.click("[data-start]")
    pg.click("[data-action=exit]")
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)
    pg.evaluate("(() => { const o = Api.listChats; Api.listChats = (s, c, bf) => { if (c !== 'YB-1') return o(s, c, bf); Api.listChats = o; return Promise.reject(new Api.ApiError(503, 'SERVICE_UNAVAILABLE', Api.messageFor('SERVICE_UNAVAILABLE'))); }; })()")
    open_session(pg)
    enter(pg)
    pg.click("[data-open=messenger]")
    pg.click("[data-yb='0']")
    check("initial load failed retry", pg.locator("[data-chat-log] [data-retry-load]").count() == 1)
    pg.click("[data-chat-log] [data-retry-load]")
    pg.wait_for_timeout(1200)
    check("initial load retry ok", pg.locator("[data-retry-load]").count() == 0)

    # 이전 대화 더 보기: 지연 → '불러오는 중…', 503 → 버튼 복귀
    pg.click("[data-open=messenger]")
    pg.click("[data-yb='0']")
    pg.wait_for_selector("[data-load-older]", timeout=5000)
    pg.evaluate("Api.mockControl.delayNext(1200)")
    pg.click("[data-load-older]")
    pg.wait_for_timeout(500)
    check("load older waiting text", "불러오는 중" in pg.inner_text("[data-load-older]"))
    pg.wait_for_timeout(1200)
    fail_next(pg, "SERVICE_UNAVAILABLE")
    pg.click("[data-load-older]")
    pg.wait_for_timeout(900)
    check("load older 503 → button back", pg.locator("[data-load-older]:not([disabled])").count() == 1 and "이전 대화" in pg.inner_text("[data-load-older]"), pg.inner_text("[data-toast]"))

    # 401 → 로그인 화면 + 안내, 아이디 유지, 재로그인 → 정문
    pg.click("[data-open=messenger]")
    fail_next(pg, "AUTH_REQUIRED")
    pg.click("[data-ask='3']")
    pg.wait_for_selector("#login-view:not([hidden])", timeout=5000)
    check("401 to login", "만료" in pg.inner_text("#login-message"), pg.inner_text("#login-message"))
    check("401 id kept", pg.input_value("#login-id") == "researcher01", repr(pg.input_value("#login-id")))
    check("401 play unmounted", pg.locator("[data-desktop]").count() == 0)
    pg.fill("#login-pw", "x")
    pg.click("#login-submit")
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)
    check("relogin to gate", True)
    pg.screenshot(path=str(Path(tempfile.gettempdir()) / "prism-j04-j03-errors-end.png"))
    b.close()

print("errors:", errors)

print("errors:", errors)
failed = any(item.startswith("FAIL ") for item in results) or bool(errors)
sys.exit(1 if failed else 0)
