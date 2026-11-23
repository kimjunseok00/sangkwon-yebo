# 상권예보 (가칭)

서울 상권 × 외식 업종별로 **"다음 해에 폐업이 몰릴 위험"**을 예측하고, 그 예측이 과거에 얼마나 맞았는지 **성적을 공개**하는 서비스.

- 사용자: 예비 창업자 ("이 동네에 치킨집 차리면 버틸 수 있을까?")
- 돈 내는 사람(가설): 소상공인 대출 금융기관 (대출 심사·부실 관리)
- 차별점: 무료 공공 지표(서울시 창업위험도 등)는 과거를 요약한다. 우리는 다음 해를 예측하고, 과거 기록으로 맞혀 본 성적을 공개한다.

발표: 2026-12-21(월). 일정은 `docs/ISSUES.md`.

## 실행

Python 3.11 이상.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
pytest
streamlit run app.py             # 실제 데이터가 없으면 가상 데이터로 뜬다
python -m experiments.backtest --synthetic   # 가상 데이터로 실험 코드 점검
```

실제 데이터로 돌리기:

```bash
# 1) docs/DATA_SOURCES.md의 파일을 data/raw/에 받는다
python -m ingest.seoul --inspect data/raw/<파일>.csv      # 열 이름 확인
python scripts_build_dataset.py --stores data/raw/store_*.csv --sales data/raw/sales_*.csv
python -m experiments.backtest --data data/processed/dataset.csv
```

## 폴더와 담당

| 경로 | 내용 | 담당 | 상태 |
|---|---|---|---|
| `core/` | 설정, 열 이름 약속, Gemini 호출 | 팀장 | 완료 |
| `ingest/seoul.py` | 서울시 CSV 읽기, 좌표 변환 | 팀원 A (좌표는 B) | 읽기 완료, 열 이름 확인 필요 |
| `features/build.py` | 연 단위 집계, 특징, 정답 | 팀장 (특징 추가는 A) | 완료 |
| `models/` | 기준선 2개, 예측 모델 | 기준선 팀장 / 모델 개선 A | 첫 모델 완료 |
| `experiments/` | 과거 맞히기 실험, 통과 판정, 가상 데이터 | 팀장 | 완료 |
| `engine/` | Gemini 위험 이유 설명 | 팀원 A | 가짜만 완료 |
| `app.py`, `ui/` | 화면, 지도, 비교, 보고서 | 팀원 B | 최소 화면 |
| `docs/` | 데이터 출처, 형식, 실험 계획, 이슈 | 팀장 | 완료 |

## 작업 규칙

1. `main`에 직접 올리지 않는다. 이슈마다 브랜치를 만들고 PR로 합친다.
2. 자기 담당 경로만 수정한다.
3. `.env`, API 키, `data/raw`, `data/processed`는 올리지 않는다.
4. PR 설명에 "무엇을 어떻게 확인했는지"를 한 줄 쓴다. PR 전에 `pytest` 통과.
5. **실험 기준(`core/config.py`)은 결과를 보고 바꾸지 않는다.** 바꿔야 하면 이유를 `docs/EXPERIMENTS.md`에 먼저 적는다.

## AI 코딩 도구

- Claude Code, Codex 등 저장소를 읽는 도구: `AGENTS.md`(Claude Code는 `CLAUDE.md`)를 자동으로 읽는다.
- Claude·ChatGPT 채팅 화면: `AGENTS.md`와 `docs/DATA_FORMAT.md`를 먼저 붙여 넣고, 자기 이슈 본문을 이어서 붙인다.
