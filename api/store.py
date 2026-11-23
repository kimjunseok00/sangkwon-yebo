"""API용 결과 읽기. 실제 구현은 core/published.py(화면과 공용)에 있다.

예전 import 경로(api.store)를 쓰는 코드가 깨지지 않게 이름만 다시 내보낸다.
"""

from core.published import Dataset, load_all, load_dataset

__all__ = ["Dataset", "load_all", "load_dataset"]
