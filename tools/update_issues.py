"""깃허브 이슈를 docs/ISSUES.md에 맞춘다. 이슈 번호 = 깃허브 이슈 번호.

11/23 번호 정리
  예전에는 제목 앞에 우리 번호(#0~#23)를 붙였는데, 깃허브 번호와 어긋나 PR 링크가 엉뚱한 이슈에 걸렸다.
  이제 docs/ISSUES.md의 '## #번호'는 깃허브 번호이고, 깃허브 이슈 제목에서는 번호를 뗀다
  (깃허브가 제목 옆에 번호를 따로 보여 준다).

실행 (저장소 폴더에서):
  python3 tools/update_issues.py --dry-run               # 할 일만 출력
  python3 tools/update_issues.py --rename --sync-body    # 제목 번호 떼기 + 본문을 새 번호로 맞추기

- 다시 돌려도 안전하다(이미 맞는 것은 그대로).
- 새 이슈는 이 스크립트로 만들지 않는다. 깃허브에서 먼저 만들고 받은 번호로 ISSUES.md에 추가한 뒤 PLAN에 넣는다.
"""

# Mac 기본 Python 3.9에서도 'X | None' 같은 타입 표기가 오류 나지 않게 한다
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from create_issues import LABELS, LEAD, REPO, A, B, parse_issues  # noqa: E402

# 깃허브 번호 → (담당자, 라벨). 11/23 기준.
PLAN: dict[int, tuple[list[str], list[str]]] = {
    1: ([LEAD], ["lead"]),
    2: ([B], ["data"]),
    3: ([LEAD], ["lead"]),
    4: ([A], ["ui"]),
    5: ([A], ["model"]),
    6: ([B], ["ui"]),
    7: ([LEAD], ["lead"]),
    8: ([A], ["model", "추가목표"]),
    9: ([B], ["ui"]),
    10: ([], ["ui"]),  # #22로 대체되어 닫힘. 담당자 넣지 않음
    11: ([LEAD, A], ["lead"]),
    12: ([A, B], ["ui"]),
    13: ([LEAD], ["lead"]),
    14: ([LEAD, A, B], ["lead"]),
    16: ([B], ["ui", "추가목표"]),
    17: ([A], ["model", "추가목표"]),
    18: ([B], ["data"]),
    19: ([LEAD], ["lead"]),
    20: ([LEAD], ["data", "lead"]),
    21: ([B], ["data"]),
    22: ([A], ["api"]),
    23: ([LEAD], ["lead"]),
    24: ([LEAD], ["lead"]),
    25: ([LEAD], ["lead"]),
}

EXTRA_LABELS = {
    "추가목표": ("bbbbbb", "핵심이 끝났을 때만 진행"),
    "api": ("ff7f0e", "금융기관용 예측 API"),
}


def old_to_new(old: int) -> int:
    """11/23 이전 제목 번호 → 깃허브 번호. 깃허브 15번은 PR이라 #14부터 두 칸 밀렸다."""
    return old + 1 if old <= 13 else old + 2


def run(args: list[str], dry: bool) -> subprocess.CompletedProcess | None:
    if dry:
        print("  [dry-run] gh", " ".join(a if len(a) < 70 else a[:67] + "..." for a in args))
        return None
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  실패: gh {' '.join(args[:3])} ... → {r.stderr.strip()}")
    return r


def github_issues() -> dict[int, dict]:
    """깃허브 이슈(PR 제외) 번호 → {title, state}."""
    r = subprocess.run(
        ["gh", "issue", "list", "--repo", REPO, "--state", "all", "--limit", "200",
         "--json", "number,title,state"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.exit(f"이슈 목록을 읽지 못했습니다: {r.stderr}")
    return {i["number"]: i for i in json.loads(r.stdout)}


def check_title(number: int, title: str) -> str:
    """제목 상태: 'ok'(번호 없음), 'old'(예전 번호가 붙었고 이 이슈가 맞음), 'mismatch'(다른 이슈로 보임)."""
    m = re.match(r"^#(\d+)\s", title)
    if not m:
        return "ok"
    return "old" if old_to_new(int(m.group(1))) == number else "mismatch"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rename", action="store_true", help="제목 앞의 예전 번호(#N)를 떼고 ISSUES.md 제목으로 맞춘다")
    parser.add_argument("--sync-body", action="store_true", help="본문을 ISSUES.md 내용으로 덮어쓴다")
    opts = parser.parse_args()
    dry = opts.dry_run

    md = (Path(__file__).resolve().parent.parent / "docs" / "ISSUES.md").read_text(encoding="utf-8")
    sections = parse_issues(md)
    missing_doc = set(PLAN) - set(sections)
    if missing_doc:
        sys.exit(f"ISSUES.md에서 찾지 못한 번호: {sorted(missing_doc)}")

    print("1) 라벨")
    for name, (color, desc) in {**LABELS, **EXTRA_LABELS}.items():
        run(["label", "create", name, "--repo", REPO, "--color", color, "--description", desc, "--force"], dry)

    gh = github_issues()
    print(f"2) 깃허브 이슈 {len(gh)}개 확인")
    targets = []
    for num in sorted(PLAN):
        if num not in gh:
            print(f"  #{num}: 깃허브에 없음 → 깃허브에서 먼저 만드세요. 건너뜀")
            continue
        status = check_title(num, gh[num]["title"])
        if status == "mismatch":
            print(f"  #{num}: 제목 '{gh[num]['title']}'이 이 번호와 맞지 않음 → 건드리지 않음. 확인 필요")
            continue
        targets.append(num)

    if opts.rename:
        print("3) 제목 맞추기")
        for num in targets:
            want = sections[num][0]
            if gh[num]["title"] != want:
                r = run(["issue", "edit", str(num), "--repo", REPO, "--title", want], dry)
                if r is not None and r.returncode == 0:
                    print(f"  #{num}: '{gh[num]['title']}' → '{want}'")

    print("4) 담당자·라벨 맞추기")
    for num in targets:
        people, labels = PLAN[num]
        args = ["issue", "edit", str(num), "--repo", REPO, "--add-label", ",".join(labels)]
        if people and gh[num]["state"] == "OPEN":
            args += ["--add-assignee", ",".join(people)]
        r = run(args, dry)
        if r is not None and r.returncode == 0:
            print(f"  #{num}: {', '.join(people) or '-'} / {', '.join(labels)}")

    if opts.sync_body:
        print("5) 본문 맞추기")
        for num in targets:
            with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
                f.write(sections[num][1])
                body_path = f.name
            r = run(["issue", "edit", str(num), "--repo", REPO, "--body-file", body_path], dry)
            Path(body_path).unlink(missing_ok=True)
            if r is not None and r.returncode == 0:
                print(f"  #{num}: 본문 갱신")

    print("\n완료. 깃허브 Issues 목록에서 제목과 번호를 한 번 확인하세요.")


if __name__ == "__main__":
    main()
