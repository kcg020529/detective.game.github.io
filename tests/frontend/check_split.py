import sys
from _server import frontend_url
from playwright.sync_api import sync_playwright

# J03 change 3: 페이지 경계에서 나뉜 질문/답 짝, 답 없는 질문 → '응답 없음'
URL = frontend_url()
PATCH = """(() => {
const r = (id, sender, content, type) => ({ message_id: id, ai_id: 'YB-5', sender, content, response_type: type, created_at: '2026-10-16 12:00:00' });
const o = Api.listChats;
Api.listChats = (saveId, aiId, before) => aiId !== 'YB-5' ? o(saveId, aiId, before)
  : Promise.resolve(before == null
    ? { messages: [r(5, 'ai', 'A10', 'normal'), r(6, 'user', 'Q11', null), r(7, 'ai', 'A11', 'partial')], has_more: true }
    : { messages: [r(1, 'user', 'Q8', null), r(2, 'user', 'Q9', null), r(3, 'ai', 'A9', 'normal'), r(4, 'user', 'Q10', null)], has_more: false });
})()"""
res, errors = [], []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1280, "height": 960})
    pg.on("pageerror", lambda e: errors.append(f"pageerror {e}"))
    pg.on("console", lambda m: m.type == "error" and "favicon" not in m.text and errors.append(f"console {m.text}"))
    pg.goto(URL + "?skip=1")
    pg.wait_for_selector("[data-desktop]", timeout=15000)
    pg.evaluate(PATCH)
    # 처음 불러오기는 진입 때 끝났으니 정문 왕복 없이: 메신저 다시 열기 전에 다시 진입
    pg.click("[data-start]"); pg.click("[data-action=exit]")
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)
    pg.click("#menu-continue"); pg.wait_for_selector("[data-slot='0']", timeout=8000); pg.wait_for_timeout(1000)
    pg.click("[data-slot='0']"); pg.wait_for_selector("[data-desktop]", timeout=15000); pg.wait_for_timeout(1500)
    pg.click("[data-open=messenger]"); pg.click("[data-yb='4']"); pg.wait_for_timeout(600)
    before = pg.locator("[data-chat-log] .c-bubble").all_inner_texts()
    res.append(("first page", before))
    pg.click("[data-load-older]"); pg.wait_for_timeout(800)
    after = pg.locator("[data-chat-log] .c-bubble").all_inner_texts()
    res.append(("after older", after))
    b.close()
for k, v in res:
    print(k, [t.replace("\n", " | ") for t in v])

print("errors:", errors)
sys.exit(1 if errors else 0)
