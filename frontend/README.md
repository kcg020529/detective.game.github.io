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
| `play/data.js` | 캐릭터·대화·단서·기록 파일 예시 데이터 (임시값) |
| `play/pixel.js` | 픽셀 초상 그리기 |
| `assets/` | 숨은 기능용 캐릭터 이미지 |

외부 라이브러리: Pretendard 글꼴, html2canvas 1.4.1 (출입증 판독 뒤 전환 효과용). 둘 다 CDN에서 불러옴.

## 현재 상태

- 모든 데이터는 Mock. 로그인·저장·채팅 답변 모두 서버 연결 없음 (J03에서 연결)
- 진행 기록: `parts/J-frontend/PLAN.md`, `parts/J-frontend/RESULT.md` (J01, J02)
