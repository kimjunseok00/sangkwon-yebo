# 상권예보 (가칭)

지역 × 외식 업종별로 **"다음 해에 폐업이 몰릴 위험"**을 예측하고, 그 예측이 과거에 얼마나 맞았는지 **성적을 공개**하는 서비스.

- **전국판(제품)**: 행정안전부 인허가 데이터로 전국 시군구 × 업종. 서울 밖은 이런 예측 도구가 거의 없다
- **서울판(검증판)**: 서울시 상권분석서비스로 상권 단위. 정밀한 데이터에서 방법이 통하는지 먼저 증명
- **금융기관용 API**: 대출 심사 시스템이 직접 부르는 `GET /v1/risk`. 모든 응답에 과거 성적과 주의 문구 포함

- 사용자: 예비 창업자 ("이 동네에 치킨집 차리면 버틸 수 있을까?")
- 돈 내는 사람(가설): 소상공인 대출 금융기관 (대출 심사·부실 관리)
- 차별점: 무료 공공 지표(서울시 창업위험도 등)는 과거를 요약하고 서울만 다룬다. 우리는 다음 해를 예측하고, 과거 기록으로 맞혀 본 성적을 공개하며, 전국을 다룬다.

```
공공데이터(서울 상권, 전국 인허가) → 분기 패널(같은 형식) → 특징·정답 → 연도별 과거 맞히기 시험(누설 방지)
   → 성적표 + 최신 위험 점수(experiments.publish) → 화면(Streamlit) / 금융기관용 API(FastAPI)
   ↑ GitHub Actions: PR마다 테스트(CI), 분기마다 자동 갱신(#22)
```

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

# 전국판 (인허가 데이터)
python -m ingest.localdata data/raw/localdata_food.csv --inspect   # 열 이름·품질 확인(#18)
python -m ingest.localdata data/raw/localdata_food.csv              # national_dataset.csv
python -m experiments.backtest --data data/processed/national_dataset.csv
```

API 띄우기:

```bash
python -m experiments.publish --synthetic --name seoul   # 실제 데이터는 --data ... 
# .env에 API_KEYS=demo-key 추가
uvicorn api.main:app --reload    # http://127.0.0.1:8000/docs 에서 키 넣고 직접 호출
```

## 팀

| 이름 | 깃허브 | 역할 |
|---|---|---|
| 김준석 | kimjunseok00 | 팀장: 실험·판정, 전국판 판정, CI·자동 갱신, 발표 자료, 외부 의견 |
| 이민준 | acme31 | 성적표 화면, 모델 개선, 금융기관용 API, **발표자** (Gemini 설명은 추가목표) |
| 주초현 | chochohyun | 데이터 받기·정리(서울·전국), 지도, 후보지 비교, 배포 |

## 폴더와 담당

| 경로 | 내용 | 담당 | 상태 |
|---|---|---|---|
| `core/` | 설정, 열 이름 약속, Gemini 호출 | 팀장 | 완료 |
| `ingest/seoul.py`, `scripts_build_dataset.py` | 서울시 CSV 읽기, 좌표 변환, dataset 만들기 | 주초현 | 읽기 완료, 열 이름 확인 필요 |
| `ingest/localdata.py` | 전국 인허가 → 서울판과 같은 분기 패널 | 주초현 (열 이름·업태 표는 팀장 #18) | 변환 완료, 열 이름 확인 필요 |
| `api/` | 금융기관용 API (키 확인, 호출 기록, 자동 문서) | 이민준 | 뼈대 완료 |
| `.github/workflows/` | PR마다 자동 테스트 | 팀장 | 완료 |
| `features/build.py` | 연 단위 집계, 특징, 정답 | 팀장 (특징 추가는 이민준) | 완료 |
| `models/` | 기준선 2개, 예측 모델 | 기준선 팀장 / 모델 개선 이민준 | 첫 모델 완료 |
| `experiments/` | 과거 맞히기 실험, 통과 판정, 서비스용 결과(publish), 서울-전국 교차 확인 | 팀장 | 완료 |
| `engine/` | Gemini 위험 이유 설명 | 이민준 | 가짜만 완료 |
| `app.py`, `ui/` | 화면, 지도, 비교, 보고서 (성적표 `ui/scorecard.py`는 이민준) | 주초현 | 최소 화면 |
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
