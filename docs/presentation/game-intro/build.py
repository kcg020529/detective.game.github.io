"""Build the game-introduction presentation. No network or model calls."""
import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
base_template = (HERE.parent / 'design-v1/template.html').read_text(encoding='utf-8')
head = base_template.split('<main class="deck">')[0]
head = head.replace('캐치 용범 · 발표 디자인 초안', '캐치 용범 · 게임 소개 및 시연')
head = head.replace('게임 프론트 기반 / 16:9 / 6개 레이아웃', 'AI 추리 게임 / 게임 소개 및 시연')
map_css = (ROOT / 'frontend/play/c.css').read_text(encoding='utf-8')
map_css = map_css[map_css.index('.c-map {'):]
head = head.replace('</style>', map_css + '\n' + (HERE / 'extra.css').read_text(encoding='utf-8') + '\n</style>')
footer = base_template[base_template.index('<footer class="controls">'):base_template.index('<script>')]
footer = footer.replace('01 / 06', '01 / 09')
navigation = base_template[base_template.index('const pages='):base_template.rindex('</script>')]
navigation = navigation.replace("+' / 06'", "+' / '+String(pages.length).padStart(2,'0')")
navigation = navigation.replace('show(5)', 'show(pages.length-1)')
initialization = r'''
const drawPortrait=(cv,yb,i)=>{cv.width=32;cv.height=32;cv.setAttribute('aria-hidden','true');window.Play.pixel.drawYb(cv.getContext('2d'),{x:16,y:17,frame:0},yb.color,i)};
window.Play.data.ybs.forEach((yb,i)=>{
 const item=document.createElement('div');item.className='character';const portrait=document.createElement('canvas');drawPortrait(portrait,yb,i);item.append(portrait,document.createTextNode(yb.id));document.getElementById('characters').append(item);
 const button=document.createElement('button');button.type='button';button.className='yb-choice'+(i===2?' selected':'');button.setAttribute('aria-label',yb.id+' 선택');button.setAttribute('aria-pressed',String(i===2));const face=document.createElement('canvas');drawPortrait(face,yb,i);button.append(face,document.createTextNode(yb.id));button.onclick=()=>{document.querySelectorAll('.yb-choice').forEach(x=>{x.classList.remove('selected');x.setAttribute('aria-pressed','false')});button.classList.add('selected');button.setAttribute('aria-pressed','true');document.getElementById('preview-ai').textContent=yb.id};document.getElementById('preview-ybs').append(button);
});
const mapRoot=document.getElementById('game-map');mapRoot.innerHTML=window.Play.map.markup();window.Play.map.bind(mapRoot);
'''
map_script = (ROOT / 'frontend/play/map.js').read_text(encoding='utf-8')
template = head + '<main class="deck">' + (HERE / 'content.html').read_text(encoding='utf-8') + '</main>\n' + footer + '<script>\n/* GAME_ART */\n' + map_script + '\n' + initialization + '\n' + navigation + '</script></body></html>'
source = (ROOT / 'frontend/app.js').read_text(encoding='utf-8')
scene = source[source.index('const S = 8;'):source.index('// 조사 화면 바탕화면용:')]
scene = scene.replace('img.src = `./assets/${name}.png`;', "img.src = sprites[name];")
sprites = {name: 'data:image/png;base64,' + base64.b64encode((ROOT / f'frontend/assets/{name}.png').read_bytes()).decode() for name in ('chiigawa', 'hachigare', 'gugagi')}
scene = '(function(){const canvas=document.getElementById("lab");const ctx=canvas.getContext("2d");const reduceMotion=true;const sprites=' + json.dumps(sprites) + ';\n' + scene
scene += '\nfor(const r of Object.values(rooms))r.lightAt=0;for(const b of bots)b.shownAt=0;showLabels=false;drawScene(7000,0);})();'
pixel = (ROOT / 'frontend/play/pixel.js').read_text(encoding='utf-8')
data = (ROOT / 'frontend/play/data.js').read_text(encoding='utf-8')
html = template.replace('/* GAME_ART */', data+'\n'+pixel+'\n'+scene)
(HERE / 'index.html').write_text(html, encoding='utf-8')
print('Built', HERE / 'index.html')
