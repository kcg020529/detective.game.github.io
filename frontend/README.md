# frontend

캐치 용범 게임 웹 화면. 빌드 없는 정적 HTML/CSS/JS.

## 실행

```bash
cd frontend
python -m http.server 8000 --bind 127.0.0.1
# http://127.0.0.1:8000/
```

`index.html`을 파일로 바로 열면 이미지·글꼴이 안 불러와질 수 있어서 서버로 띄워야 함.
`?skip=1`을 붙이면 로그인 없이 조사 화면으로 바로 이동 (개발용).

## 파일

| 파일 | 내용 |
|---|---|
| `index.html` | 화면 구조 |
| `style.css` | 시작·로그인·정문·역할 선택 화면 스타일 |
| `app.js` | 픽셀 연구소 그림, 시작·로그인·정문·역할 선택, 저장 슬롯 예시(`saves`), 조사 화면 연결 |
| `play/c.js`, `play/c.css` | 단말기 진입(출입증 선택)과 조사 화면(바탕화면, 메신저, 기록 보관함, 단서 수첩, 지목) |
| `play/data.js` | 캐릭터·화면 문구와 Mock 모드용 예시 데이터 |
| `play/api.js` | 서버 API 호출과 응답 검사. API 주소가 없으면 같은 형식의 Mock으로 동작 |
| `play/map.js` | 지도 앱 (연구동 손그림 지도) |
| `config.js` | API 주소 자리. 정적 실행은 비워 두고(Mock), Compose·Kubernetes의 nginx가 `/api/v1`로 채워 줌 |
| `play/pixel.js` | 픽셀 초상 그리기 |
| `assets/` | 숨은 기능용 캐릭터 이미지 |

외부 라이브러리: Pretendard 글꼴, html2canvas 1.4.1 (출입증 판독 뒤 전환 효과용). 둘 다 CDN에서 불러옴.

## 현재 상태

- 서버 연결됨: 회원가입·로그인, Save, Day 진행, 메모, 채팅, 최종 지목·판정서 (J03~J08)
- `python -m http.server`나 GitHub Pages처럼 API 주소가 없으면 Mock 모드. Mock 판정은 데모 값이며 실제 정답이 아님
- 전체를 서버와 함께 실행: `infrastructure/docker/README.md` (http://127.0.0.1:8080)
- 진행 기록: `parts/J-frontend/PLAN.md`, `parts/J-frontend/RESULT.md`
