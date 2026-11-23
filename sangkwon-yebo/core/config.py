"""환경 설정과 실험 규칙을 한 곳에 둔다.

실험 결과에 영향을 주는 값(위험 기준, 최소 점포 수, 시험 연도)은 모두 여기서만 바꾼다.
값을 바꾸면 docs/EXPERIMENTS.md에 언제, 왜 바꿨는지 기록한다(결과를 보고 기준을 바꾸는 일을 막기 위함).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

# --- LLM (위험 이유 설명에만 사용) ---
USE_MOCK: bool = os.getenv("USE_MOCK", "1") == "1"
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# --- 정답(위험) 정의 ---
# 예측 기준 연도 t의 특징으로, 다음 해(t+1) 폐업률이 '같은 업종 안에서 상위 25%'인 칸을 위험(1)으로 본다.
# 업종 안에서 비교하는 이유: 업종마다 기본 폐업률이 달라, 서울 전체로 줄 세우면 업종만 맞혀도 점수가 나온다.
RISK_QUANTILE: float = 0.75

# 연평균 점포 수가 이보다 적은 칸은 폐업률이 1~2곳 폐업으로 크게 흔들리므로 학습·평가에서 뺀다.
MIN_STORES: int = 5

# --- 과거 맞히기 실험 ---
# '예측 기준 연도'. 2022년 특징으로 2023년을 맞히는 식이다.
# 2019년 데이터는 전년 대비 특징을 만들 수 없어 특징 연도는 2020년부터다.
TEST_FEATURE_YEARS: tuple[int, ...] = (2022, 2023, 2024)

# 위험 점수 상위 몇 %를 '경고'로 볼지. 정밀도·재현율 계산에 쓴다.
TOP_FRACTION: float = 0.10

# --- 11/26 통과 판정 규칙 (docs/EXPERIMENTS.md에도 같은 내용) ---
# 모델 AUC가 두 기준선 중 나은 쪽보다 이만큼 이상 높은 연도가 GATE_MIN_YEARS개 이상이면 통과.
GATE_MIN_AUC_GAIN: float = 0.02
GATE_MIN_YEARS: int = 2

RANDOM_SEED: int = 0
