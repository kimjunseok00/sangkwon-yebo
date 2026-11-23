"""이미 만든 이슈에 담당자를 다시 넣고, 추가 이슈(#14~#23)를 만든다. 다시 돌려도 중복이 생기지 않는다.

11/23 2차: 전국판(#18, #19), 금융기관용 API(#20), CI(#21), 자동 갱신(#22), 사업 질문 대비(#23) 추가.
#7에 추가목표 라벨, #9는 #20으로 대체하며 닫는다.

실행 (저장소 폴더에서):
  python3 tools/update_issues.py --dry-run   # 할 일만 출력
  python3 tools/update_issues.py

- 기존 이슈는 제목 앞의 '#번호 '로 찾는다. 담당자 추가는 이미 지정된 사람이 있어도 안전하다.
- 같은 제목의 이슈가 이미 있으면 새로 만들지 않고 담당자만 맞춘다.
"""

# Mac 기본 Python 3.9에서도 'X | None' 같은 타입 표기가 오류 나지 않게 한다
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from create_issues import LABELS, LEAD, PLAN, REPO, A, B, parse_issues  # noqa: E402

NEW_PLAN = {
    14: ("3주차", [B], ["ui", "추가목표"]),
    15: ("3주차", [A], ["model", "추가목표"]),
    16: ("1주차", [B], ["data"]),  # 11/23 #1과 함께 chochohyun
    17: ("3주차", [LEAD], ["lead"]),
    18: ("1주차", [LEAD], ["data", "lead"]),  # 전국판 판정 11/27
    19: ("2주차", [B], ["data"]),  # #18 통과 시에만
    20: ("3주차", [A], ["api"]),  # 금융기관용 API (#9 대체)
    21: ("1주차", [LEAD], ["lead"]),  # CI
    22: ("3주차", [LEAD], ["lead"]),  # 자동 갱신, #20 끝났을 때만
    23: ("2주차", [LEAD], ["lead"]),  # 사업 질문 대비, 이용 조건
}
# 기존 이슈에 라벨 추가
ADD_LABELS = {7: ["추가목표"]}
# 닫을 이슈: 번호 → (새 제목, 닫을 때 남길 댓글)
CLOSE = {
    9: ("#9 금융기관용 보고서 → #20으로 대체",
        "11/23 결정: 금융기관은 화면 보고서보다 심사 시스템이 직접 부르는 API를 쓰므로 #20 금융기관용 예측 API로 대체합니다."),
}
# 담당이 바뀐 이슈: 예전 담당자를 뺀다 (11/23 #1·#16 acme31 → chochohyun)
REMOVE = {1: [A], 16: [A], 3: [B]}  # 11/23 #3 주초현 → 이민준

EXTRA_LABELS = {
    "추가목표": ("bbbbbb", "핵심이 끝났을 때만 진행"),
    "api": ("ff7f0e", "금융기관용 예측 API"),
}


def run(args: list[str], dry: bool, read_only: bool = False) -> subprocess.CompletedProcess | None:
    if dry and not read_only:
        print("  [dry-run] gh", " ".join(a if len(a) < 60 else a[:57] + "..." for a in args))
        return None
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  실패: gh {' '.join(args[:3])} ... → {r.stderr.strip()}")
    return r


def existing_issues() -> dict[int, int]:
    """'#번호 ' 로 시작하는 기존 이슈 → 깃허브 이슈 번호."""
    r = subprocess.run(
        ["gh", "issue", "list", "--repo", REPO, "--state", "all", "--limit", "200", "--json", "number,title"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.exit(f"이슈 목록을 읽지 못했습니다: {r.stderr}")
    found = {}
    for item in json.loads(r.stdout):
        head = item["title"].split(" ", 1)[0]
        if head.startswith("#") and head[1:].isdigit():
            found[int(head[1:])] = item["number"]
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sync-body", action="store_true",
                        help="기존 이슈 본문을 ISSUES.md 내용으로 덮어쓴다(깃허브에서 직접 고친 본문은 사라짐)")
    opts = parser.parse_args()
    dry = opts.dry_run

    md = (Path(__file__).resolve().parent.parent / "docs" / "ISSUES.md").read_text(encoding="utf-8")
    sections = parse_issues(md)
    all_plan = {**PLAN, **NEW_PLAN}
    missing = set(all_plan) - set(sections)
    if missing:
        sys.exit(f"ISSUES.md에서 찾지 못한 이슈 번호: {sorted(missing)}")

    print("1) 라벨")
    for name, (color, desc) in {**LABELS, **EXTRA_LABELS}.items():
        run(["label", "create", name, "--repo", REPO, "--color", color, "--description", desc, "--force"], dry)

    found = existing_issues()
    print(f"2) 기존 이슈 {len(found)}개 확인: {sorted(found)}")

    print("3) 없는 이슈 만들기")
    for num in sorted(all_plan):
        if num in found:
            continue
        milestone, _, labels = all_plan[num]
        title, body = sections[num]
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(body)
            body_path = f.name
        r = run(["issue", "create", "--repo", REPO, "--title", f"#{num} {title}", "--body-file", body_path,
                 "--milestone", milestone] + sum((["--label", lab] for lab in labels), []), dry)
        Path(body_path).unlink(missing_ok=True)
        if r is not None and r.returncode == 0:
            print(f"  만듦: #{num} → {r.stdout.strip()}")
    if not dry:
        found = existing_issues()

    print("4) 담당자 맞추기")
    for num in sorted(all_plan):
        if num in CLOSE:
            continue  # 닫을 이슈는 담당자를 다시 넣지 않는다
        if num not in found:
            print(f"  #{num}: 이슈가 없어 건너뜀" + (" (dry-run에서는 정상)" if dry else ""))
            continue
        assignees = all_plan[num][1]
        r = run(["issue", "edit", str(found[num]), "--repo", REPO, "--add-assignee", ",".join(assignees)], dry)
        if r is not None and r.returncode == 0:
            print(f"  #{num}: {', '.join(assignees)}")
    print("5) 바뀐 담당 정리")
    for num, people in REMOVE.items():
        if num in found:
            r = run(["issue", "edit", str(found[num]), "--repo", REPO, "--remove-assignee", ",".join(people)], dry)
            if r is not None and r.returncode == 0:
                print(f"  #{num}: {', '.join(people)} 제외")
    print("6) 라벨 추가")
    for num, labels in ADD_LABELS.items():
        if num in found:
            r = run(["issue", "edit", str(found[num]), "--repo", REPO, "--add-label", ",".join(labels)], dry)
            if r is not None and r.returncode == 0:
                print(f"  #{num}: +{', '.join(labels)}")
    print("7) 대체된 이슈 닫기")
    for num, (title, comment) in CLOSE.items():
        if num not in found:
            continue
        run(["issue", "edit", str(found[num]), "--repo", REPO, "--title", title], dry)
        r = run(["issue", "close", str(found[num]), "--repo", REPO, "--comment", comment], dry)
        if r is not None and r.returncode == 0:
            print(f"  #{num}: 닫음")
        elif r is not None and "already closed" in (r.stderr or ""):
            print(f"  #{num}: 이미 닫혀 있음")
    if opts.sync_body:
        print("8) 본문 맞추기")
        for num in sorted(all_plan):
            if num not in found:
                continue
            with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
                f.write(sections[num][1])
                body_path = f.name
            r = run(["issue", "edit", str(found[num]), "--repo", REPO, "--body-file", body_path], dry)
            Path(body_path).unlink(missing_ok=True)
            if r is not None and r.returncode == 0:
                print(f"  #{num}: 본문 갱신")
    print("\n완료. 깃허브 Issues에서 담당자 칸을 한 번 확인하세요.")


if __name__ == "__main__":
    main()
