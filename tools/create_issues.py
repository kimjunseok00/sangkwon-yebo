"""⚠️ 11/23 실행 완료. 다시 실행하지 않는다(이슈가 중복으로 생기고, 아래 PLAN은 예전 번호 체계다).
이후 이슈 관리는 tools/update_issues.py로 한다. 이 파일은 공용 함수(parse_issues)와 상수 때문에 남겨 둔다.

(원래 설명) docs/ISSUES.md를 읽어 깃허브에 라벨·마일스톤·이슈를 한 번에 만든다.

준비: GitHub CLI(gh) 설치 후 `gh auth login`으로 로그인.
실행:
  python tools/create_issues.py --dry-run   # 만들 내용만 출력 (먼저 확인)
  python tools/create_issues.py             # 실제로 생성

다시 실행하면 이슈가 중복으로 생기므로 한 번만 실행한다.
담당자가 아직 초대를 수락하지 않았으면 그 이슈는 담당자 없이 만들고 목록을 알려 준다.
"""

# Mac 기본 Python 3.9에서도 'X | None' 같은 타입 표기가 오류 나지 않게 한다
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = "kimjunseok00/sangkwon-yebo"
LEAD, A, B = "kimjunseok00", "acme31", "chochohyun"  # 김준석(팀장), 이민준(발표), 주초현

# (제목에 붙일 마감일, 마감 시각 UTC). 각 주 일요일 23:59 KST
MILESTONES = {
    "1주차": "2026-11-29T14:59:59Z",
    "2주차": "2026-12-06T14:59:59Z",
    "3주차": "2026-12-13T14:59:59Z",
    "4주차": "2026-12-20T14:59:59Z",
}

LABELS = {
    "data": ("1f77b4", "데이터 받기·정리"),
    "model": ("9467bd", "예측 모델·설명"),
    "ui": ("2ca02c", "화면·지도·보고서"),
    "lead": ("d62728", "팀장: 실험·판정·발표"),
}

# 이슈 번호 → (마일스톤, 담당자, 라벨)
PLAN = {
    0: ("1주차", [LEAD], ["lead"]),
    1: ("1주차", [B], ["data"]),  # 11/23 acme31 → chochohyun
    2: ("1주차", [LEAD], ["lead"]),
    3: ("1주차", [A], ["ui"]),  # 11/23 주초현 → 이민준
    4: ("2주차", [A], ["model"]),
    5: ("2주차", [B], ["ui"]),
    6: ("2주차", [LEAD], ["lead"]),
    7: ("3주차", [A], ["model"]),
    8: ("3주차", [B], ["ui"]),
    9: ("3주차", [B, LEAD], ["ui"]),
    10: ("4주차", [LEAD, A], ["lead"]),  # 이민준 발표 담당
    11: ("4주차", [A, B], ["ui"]),
    12: ("4주차", [LEAD], ["lead"]),
    13: ("4주차", [LEAD, A, B], ["lead"]),
}


def parse_issues(md: str) -> dict[int, tuple[str, str]]:
    """'## #번호 제목' 단위로 나눠 {번호: (제목, 본문)}을 만든다."""
    parts = re.split(r"^## #(\d+) (.+)$", md, flags=re.M)
    issues = {}
    for i in range(1, len(parts), 3):
        num, title, body = int(parts[i]), parts[i + 1].strip(), parts[i + 2]
        body = body.split("\n---")[0].strip()  # 다음 구분선 전까지
        issues[num] = (title, body)
    return issues


def gh(args: list[str], dry: bool) -> subprocess.CompletedProcess | None:
    if dry:
        print("  [dry-run] gh", " ".join(a if len(a) < 60 else a[:57] + "..." for a in args))
        return None
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    dry = args.dry_run

    md = (Path(__file__).resolve().parent.parent / "docs" / "ISSUES.md").read_text(encoding="utf-8")
    issues = parse_issues(md)
    missing = set(PLAN) - set(issues)
    if missing:
        sys.exit(f"ISSUES.md에서 찾지 못한 이슈 번호: {sorted(missing)}")

    print("1) 라벨")
    for name, (color, desc) in LABELS.items():
        gh(["label", "create", name, "--repo", REPO, "--color", color, "--description", desc, "--force"], dry)

    print("2) 마일스톤")
    for title, due in MILESTONES.items():
        r = gh(["api", f"repos/{REPO}/milestones", "-f", f"title={title}", "-f", f"due_on={due}"], dry)
        if r is not None and r.returncode != 0 and "already_exists" not in r.stderr:
            sys.exit(f"마일스톤 '{title}' 생성 실패: {r.stderr}")

    print("3) 이슈 (번호 순서대로)")
    no_assignee = []
    for num in sorted(PLAN):
        milestone, assignees, labels = PLAN[num]
        title, body = issues[num]
        full_title = f"#{num} {title}"
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(body)
            body_path = f.name
        base = ["issue", "create", "--repo", REPO, "--title", full_title, "--body-file", body_path,
                "--milestone", milestone] + sum((["--label", lab] for lab in labels), [])
        with_assignee = base + sum((["--assignee", a] for a in assignees), [])
        r = gh(with_assignee, dry)
        if r is not None and r.returncode != 0:
            # 초대를 아직 수락하지 않은 담당자가 있으면 실패하므로, 담당자 없이 다시 만든다
            r = gh(base, dry)
            if r.returncode != 0:
                sys.exit(f"{full_title} 생성 실패: {r.stderr}")
            no_assignee.append((full_title, assignees))
        if r is not None:
            print(f"  만듦: {full_title} → {r.stdout.strip()}")
        Path(body_path).unlink(missing_ok=True)

    if no_assignee:
        print("\n담당자 없이 만든 이슈(초대 수락 후 깃허브에서 직접 지정):")
        for t, a in no_assignee:
            print(f"  {t}: {', '.join(a)}")
    print("\n완료")


if __name__ == "__main__":
    main()
