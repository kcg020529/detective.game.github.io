"""Build the HTML presentation prototype using existing game artwork. No network."""
import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
source = (ROOT / 'frontend/app.js').read_text(encoding='utf-8')
scene = source[source.index('const S = 8;'):source.index('// 조사 화면 바탕화면용:')]
scene = scene.replace('img.src = `./assets/${name}.png`;', "img.src = sprites[name];")
sprites = {name: 'data:image/png;base64,' + base64.b64encode((ROOT / f'frontend/assets/{name}.png').read_bytes()).decode() for name in ('chiigawa', 'hachigare', 'gugagi')}
scene = '(function(){const canvas=document.getElementById("lab");const ctx=canvas.getContext("2d");const reduceMotion=true;const sprites=' + json.dumps(sprites) + ';\n' + scene
scene += '\nfor(const r of Object.values(rooms))r.lightAt=0;for(const b of bots)b.shownAt=0;showLabels=false;drawScene(7000,0);})();'
pixel = (ROOT / 'frontend/play/pixel.js').read_text(encoding='utf-8')
data = (ROOT / 'frontend/play/data.js').read_text(encoding='utf-8')
html = (HERE / 'template.html').read_text(encoding='utf-8').replace('/* GAME_ART */', data+'\n'+pixel+'\n'+scene)
(HERE / 'index.html').write_text(html, encoding='utf-8')
print('Built', HERE / 'index.html')
