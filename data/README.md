# 시나리오 데이터 원본

게임·테스트 콘텐츠 원본은 이 폴더에서 관리한다. MariaDB 테이블 정의와 적재용 SQL은 `database/schemas/`에서 관리한다.

```text
data/
├── README.md
├── game-data/
│   ├── README.md
│   ├── characters/
│   │   └── personas/
│   ├── map/
│   └── experiments/
│       ├── day_01/
│       ├── day_02/
│       ├── day_03/
│       ├── day_04/
│       ├── day_05/
│       └── day_06/
└── test-data/
    ├── README.md
    └── records.json
```

각 Day 폴더에는 `setup.json`, `actions.json`, `dialogues.json`, `thoughts.json`, `results.json`, `incidents.json`을 둔다. 현재 setup.json은 매일 5건씩, Day 1 results.json은 5건, actions.json은 회차별 12·9·10·11·13건으로 총 55건, Day 1 incidents.json은 벽 끼임 2건, dialogues.json은 회차별 3·4·5·4·3건으로 총 19건, thoughts.json은 회차별 6건씩 총 30건을 작성했다. 나머지 빈 배열은 미작성 상태이며 해당 날짜에 사건이 없다는 확정 설정으로 해석하지 않는다.

캐릭터 설정은 추후 `characters/characters.json`, 페르소나는 `characters/personas/ai_01.md` 등의 파일에 작성한다. 지도는 `map/map.json`과 `map/map.png`에 작성할 예정이며 현재는 디렉터리만 준비했다.
