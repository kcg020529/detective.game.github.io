import sys
from _server import frontend_url
from playwright.sync_api import sync_playwright

# J03 change 3: 가입+역할 선택, 새 수사 역할 제한, 채팅 행 짝 맞추기 (Mock, 8010)
URL = frontend_url()
errors, results = [], []


def check(name, ok, extra=""):
    results.append(("OK " if ok else "FAIL ") + name + (f" | {extra}" if extra else ""))
    print(results[-1], flush=True)


def to_signup(pg):
    pg.wait_for_selector("#start-button:not([hidden])", timeout=30000)
    pg.click("#start-button")
    pg.click("#signup-link")
    pg.wait_for_selector("#signup-pw-confirm-field:not([hidden])", timeout=3000)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1280, "height": 960})
    pg.on("pageerror", lambda e: errors.append(f"pageerror {e}"))
    pg.on("console", lambda m: m.type == "error" and errors.append(f"console {m.text}"))
    pg.goto(URL)
    to_signup(pg)

    # 비밀번호 확인 불일치 → 앞단에서 막음
    pg.fill("#login-id", "newbie")
    pg.fill("#login-pw", "pw1")
    pg.fill("#signup-pw-confirm", "pw2")
    pg.click("#login-submit")
    check("pw confirm mismatch", "일치" in pg.inner_text("#signup-pw-confirm-error") and pg.locator("#role-view:not([hidden])").count() == 0)

    # 역할 화면 → 뒤로 → 아이디·비밀번호·확인 유지
    pg.fill("#signup-pw-confirm", "pw1")
    pg.click("#login-submit")
    pg.wait_for_selector("#role-view:not([hidden])", timeout=3000)
    check("signup role screen: all 3 selectable", pg.locator("#role-view input[name=role]:disabled").count() == 0)
    pg.click("#role-back")
    check("back keeps id, pw, confirm", pg.locator("#signup-pw-confirm-field:not([hidden])").count() == 1 and pg.input_value("#login-id") == "newbie" and pg.input_value("#login-pw") == "pw1" and pg.input_value("#signup-pw-confirm") == "pw1")

    # std로 가입 → 정문 (확인 칸 다시 안 채워도 됨)
    pg.click("#login-submit")
    pg.wait_for_selector("#role-view:not([hidden])", timeout=3000)
    pg.check("input[name=role][value=std]", force=True)
    pg.click("#role-view [type=submit]")
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)
    check("signup → lobby", "newbie" in pg.inner_text("#lobby-user"), pg.inner_text("#lobby-user"))

    # 새 수사: 3개 모두 열림, 가입 역할 std 미리 선택
    pg.click("#menu-new")
    pg.wait_for_selector("#role-view:not([hidden])", timeout=3000)
    dis = pg.evaluate("[...document.querySelectorAll('#role-view input[name=role]')].map(i => [i.value, i.disabled, i.checked])")
    check("new game: all open, signup role std preselected", dis == [["prof", False, False], ["grad", False, False], ["std", False, True]], str(dis))
    check("no lock text", "계정 역할이 아닙니다" not in pg.inner_text("#role-view"))
    pg.locator("input[name=role][value=prof]").locator("xpath=ancestor::label").click(force=True)
    check("prof can be picked", pg.is_checked("input[name=role][value=prof]"))
    pg.click("#role-view [type=submit]")
    pg.wait_for_selector("[data-slot='0']", timeout=8000)
    pg.wait_for_timeout(1000)
    pg.click("[data-slot='0']")
    pg.wait_for_selector("[data-desktop]", timeout=15000)
    pg.wait_for_timeout(1500)
    check("std account made prof save", "교수" in pg.inner_text(".c-task-status"), pg.inner_text(".c-task-status").replace(chr(10), " "))
    b.close()

    # 중복 아이디 409, 짝 나뉜 페이지
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1280, "height": 960})
    pg.on("pageerror", lambda e: errors.append(f"pageerror {e}"))
    pg.on("console", lambda m: m.type == "error" and "favicon" not in m.text and errors.append(f"console {m.text}"))
    pg.goto(URL)
    pg.wait_for_selector("#start-button:not([hidden])", timeout=30000)
    pg.click("#start-button")
    pg.fill("#login-id", "researcher01")
    pg.fill("#login-pw", "x")
    pg.click("#login-submit")
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)
    pg.evaluate("Api.mockControl.setRoles([])")
    pg.click("#menu-new")
    pg.wait_for_selector("#role-view:not([hidden])", timeout=3000)
    check("empty roles → all 3 allowed", pg.locator("#role-view input[name=role]:disabled").count() == 0)
    pg.click("#role-back")

    # 홀수 행 페이지: 첫 페이지가 ai 행으로 시작해도 이전 페이지 뒤 짝이 맞아야 함
    # (YB-4 대화: 기존 + 질문만 하나 남긴 뒤 짝 11개 → 22행+1, 첫 페이지 20행은 ai로 시작)
    pg.click("#menu-continue")
    pg.wait_for_selector("[data-slot='0']", timeout=8000)
    pg.wait_for_timeout(1000)
    pg.click("[data-slot='0']")
    pg.wait_for_selector("[data-desktop]", timeout=15000)
    pg.wait_for_timeout(1500)
    pg.click("[data-start]")
    pg.click("[data-action=exit]")
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)
    pg.evaluate("Api.mockControl.seedChats('YB-4', 11)")
    total = pg.evaluate("Api.listSaves().then(r => r.saves[0].save_id).then(id => Api.listChats(id, 'YB-4')).then(r => [r.messages[0].sender, r.has_more])")
    pg.click("#menu-continue")
    pg.wait_for_selector("[data-slot='0']", timeout=8000)
    pg.wait_for_timeout(1000)
    pg.click("[data-slot='0']")
    pg.wait_for_selector("[data-desktop]", timeout=15000)
    pg.wait_for_timeout(1500)
    pg.click("[data-open=messenger]")
    pg.click("[data-yb='3']")
    pg.wait_for_timeout(800)
    while pg.locator("[data-load-older]").count():
        n = pg.locator("[data-chat-log] .c-bubble").count()
        pg.click("[data-load-older]")
        pg.wait_for_function(f"document.querySelectorAll('[data-chat-log] .c-bubble').length >= {n}", timeout=5000)
        pg.wait_for_timeout(500)
    texts = pg.locator("[data-chat-log] .c-bubble").all_inner_texts()
    check("first page starts with", True, str(total))
    check("pairs joined across pages, no 응답 없음", texts and not any("응답 없음" in t for t in texts) and sum("테스트 질문" in t for t in texts) == 11, f"{len(texts)} bubbles")
    b.close()

print("errors:", errors)

failed = any(item.startswith("FAIL ") for item in results) or bool(errors)
sys.exit(1 if failed else 0)
