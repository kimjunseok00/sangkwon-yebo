# AI 코딩 도구용 규칙 (상권예보)

이 저장소에서 코드를 작성하는 모든 AI 도구는 아래 규칙을 따른다.
작업 전 `docs/DATA_FORMAT.md`와 `core/schemas.py`를 먼저 읽는다.

## 프로젝트
- 지역×외식업종별 다음 해 폐업 위험을 예측하고 과거 성적을 공개한다.
  - 서울판(검증판): 서울시 상권분석서비스, 상권 단위
  - 전국판(제품): 행정안전부 지방행정 인허가 데이터(일반음식점), 시군구 단위. `ingest/localdata.py`가 서울판과 같은 분기 패널 형식으로 바꿔서 특징·실험 코드를 그대로 쓴다
  - 금융기관용 API(`api/`, FastAPI): 미리 계산한 점수를 조회만 한다
- Python 3.11 이상, pandas, scikit-learn, Streamlit, Plotly, FastAPI, Gemini(`google-genai`, 설명 문장에만 사용).
- 3명이 각자 AI 도구로 개발한 뒤 합친다. 열 이름과 경로 규칙이 가장 중요하다.

## 반드시 지킬 것
1. **열 이름은 `core/schemas.py`에 정의된 것만 쓴다.** 새 열이 필요하면 코드를 고치지 말고 사용자에게 알린다.
2. **미래 정보를 특징에 넣지 않는다.** 예측 기준 연도 t의 특징은 t년 말까지 알 수 있는 값만. `next_*` 열과 `risk_next`, `risk_threshold`는 절대 모델 입력에 넣지 않는다.
3. **실험 규칙을 바꾸지 않는다.** `core/config.py`의 RISK_QUANTILE, MIN_STORES, TEST_FEATURE_YEARS, TOP_FRACTION, GATE_* 값과 `experiments/backtest.py`의 분할 규칙, `models/baselines.py`는 팀장만 수정한다.
4. **기준선을 약하게 만들지 않는다.** 모델 성능을 높이려고 기준선을 고치는 것은 금지.
5. **LLM 호출은 `core/llm.py`의 `call_llm_json()`으로만.** 위험 점수 계산에 LLM을 쓰지 않는다. LLM은 이미 계산된 숫자를 설명하는 데만 쓴다.
6. **담당 경로 밖 파일을 수정하지 않는다.**
   - 이민준(acme31): `models/model.py`, `engine/`, `prompts/`, `ui/scorecard.py`, `api/`, `tests/test_model_*.py`, `tests/test_api*.py`
   - 주초현(chochohyun): `ingest/`(단 `ingest/localdata.py`의 열 이름·업태 표는 팀장 확인 후), `scripts_build_dataset.py`, `app.py`, `ui/`(scorecard.py 제외), `tests/test_ingest_*.py`, `tests/test_localdata*.py`, `tests/test_ui_*.py`
   - `core/`(`core/published.py` 포함), `features/`, `experiments/`(publish·crosscheck·make_all 포함), `models/baselines.py`, `docs/`, `.github/`, `AGENTS.md`, `requirements.txt`는 팀장만.
7. **라이브러리를 새로 추가하지 않는다.** 필요하면 이유와 함께 제안만 한다.
8. **API 키·비밀 값은 코드에 쓰지 않는다.** `.env`에서 `core/config.py`로 읽는다.
9. **데이터를 웹에서 크롤링하지 않는다.** 서울열린데이터광장, 공공데이터포털·LOCALDATA에서 받은 파일만 쓴다.
10. **API 응답에서 `track_record`(과거 성적)와 `caution`(주의 문구)을 빼지 않는다.** API는 `experiments.publish`가 만든 파일만 읽고, 요청마다 모델을 학습하지 않는다.
11. **API 키 원문을 기록·저장하지 않는다.** 호출 기록에는 해시 앞자리(`key_id`)만 남긴다.
12. **화면(`app.py`, `ui/`)과 API(`api/`)는 `published/` 결과만 읽는다.** 읽기는 `core/published.py`(`load_all`, `Dataset`)로 한다.
    화면에서 모델을 학습하거나 실험(`run_backtest`)을 다시 돌리지 않는다. 결과를 새로 만들 때는 `python -m experiments.make_all`.
    필요한 값이 `scores.csv`·`meta.json`에 없으면 화면에서 계산하지 말고 팀장에게 요청한다(`experiments/publish.py`에 추가).

## 화면 문구 규칙
- "망한다", "반드시", "성공 보장" 같은 단정 표현 금지. "위험이 높은 편", "과거 통계상" 등을 쓴다.
- 모든 예측 화면에 "과거 통계 기반 참고 정보이며 개별 점포의 성패를 보장하지 않습니다"를 표시한다.
- 성적표를 숨기지 않는다. 모델이 기준선보다 못한 해도 그대로 보여준다.
- 가상 데이터일 때는 화면 맨 위에 경고를 띄운다.

## 코드 스타일
- 타입 힌트, 공개 함수에 한국어 docstring(의도와 입출력), "왜"를 설명하는 한국어 주석.
- 예외를 삼키지 않는다. 결측을 0으로 채우지 않는다(폐업 0과 '데이터 없음'은 다르다).
- 확실하지 않은 라이브러리 사용법은 공식 문서를 확인하거나, 확인이 필요하다고 말한다.

## 작업을 마칠 때
- `pytest` 통과 확인. PR을 올리면 GitHub Actions가 같은 테스트를 자동으로 돌린다(빨간 X면 병합하지 않는다).
- 무엇을 바꿨고 어떻게 확인했는지 3줄 이내 요약(PR 설명).
