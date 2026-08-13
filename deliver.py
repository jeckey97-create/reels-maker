"""완성된 릴스를 휴대폰에서 바로 쓸 수 있는 곳으로 보낸다.

인스타는 외부에서 초안(draft)을 만들 수 없다. Graph API 로 올리면 그 즉시
게시되고, 인기 음원은 앱 안에서만 붙는다. 그래서 "올려두고 나중에 음악 붙여
게시" 구조가 인스타에 없다.

대신 사람이 해야 하는 마지막 단계를 최소로 줄인다. 영상과 글을 구글 드라이브
폴더에 넣어두면 휴대폰 드라이브 앱에서 바로 받아 인스타에 올릴 수 있다.

휴대폰에서 남는 일:
    1. 드라이브 앱에서 영상 저장
    2. 인스타 → 릴스 → 그 영상 선택
    3. 음악 붙이기
    4. 글 붙여넣기 (같은 폴더의 _게시글.txt)
    5. 게시
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import approve
import config as cfg


def deliver(video: Path, caption: str, dest_dir: Path) -> tuple[Path, Path]:
    """영상과 글을 dest_dir 에 보기 좋은 이름으로 복사한다."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = video.stem

    out_video = dest_dir / f"_릴스_{stem}.mp4"
    shutil.copy2(video, out_video)

    out_text = dest_dir / f"_게시글_{stem}.txt"
    steps = [
        caption.rstrip(),
        "",
        "-" * 30,
        "휴대폰에서 할 일",
        "1) 위 영상을 드라이브 앱에서 저장",
        "2) 인스타 → 릴스 → 그 영상 선택",
        "3) 음악 붙이기 (인기 음원 권장)",
        "4) 이 글 복사해서 붙여넣기",
        "5) 게시",
    ]
    out_text.write_text("\n".join(steps), encoding="utf-8")
    return out_video, out_text


def main() -> int:
    ap = argparse.ArgumentParser(description="완성된 릴스를 드라이브로 보내기")
    ap.add_argument("name", nargs="?", help="릴스 이름 (없으면 승인 대기 전부)")
    ap.add_argument("--to", help="보낼 폴더 (기본: 원본 사진 폴더)")
    args = ap.parse_args()

    state = approve.load_state()
    targets = []
    for key, rec in state.items():
        if rec.get("status") != approve.PENDING:
            continue
        if args.name and Path(key).name != args.name:
            continue
        targets.append((key, rec))

    if not targets:
        print("[i] 보낼 릴스가 없다. 먼저 만들어라: py watch_folder.py --once")
        return 0

    for key, rec in targets:
        video = Path(rec.get("video", ""))
        if not video.exists():
            print(f"[!] 영상이 없다: {video}")
            continue
        caption = video.with_suffix(".txt")
        text = caption.read_text(encoding="utf-8") if caption.exists() else ""
        dest = Path(args.to) if args.to else Path(key)
        v, t = deliver(video, text, dest)
        print(f"[+] {Path(key).name}")
        print(f"    영상: {v}")
        print(f"    글  : {t}")

    print()
    print("휴대폰에서: 드라이브 앱 → 영상 저장 → 인스타 릴스 → 음악 → 글 붙여넣기 → 게시")
    return 0


if __name__ == "__main__":
    sys.exit(main())
