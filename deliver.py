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


PHONE_STEPS = {
    "reel": [
        "1) 위 영상을 드라이브 앱에서 저장",
        "2) 인스타 → 릴스 → 그 영상 선택",
        "3) 음악 붙이기 (인기 음원 권장)",
        "4) 이 글 복사해서 붙여넣기",
        "5) 게시",
    ],
    "photo": [
        "1) 위 사진들을 드라이브 앱에서 저장",
        "2) 인스타 → 새 게시물 → 그 사진들 선택 (여러 장이면 순서대로)",
        "3) 이 글 복사해서 붙여넣기",
        "4) 게시",
    ],
}


def deliver(files: list[Path], caption: str, dest_dir: Path, name: str,
            kind: str = "reel") -> tuple[list[Path], Path]:
    """완성물과 글을 dest_dir 에 보기 좋은 이름으로 복사한다.

    **종류를 반드시 봐야 한다.** 캐러셀·피드 사진까지 `_릴스_이름.mp4` 로
    복사하면 알맹이는 JPG 인데 확장자만 mp4 인 파일이 만들어진다.
    휴대폰에서 열리지 않고, 왜 안 되는지도 알 수 없다.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []

    if kind == "reel":
        dst = dest_dir / f"_릴스_{files[0].stem}.mp4"
        shutil.copy2(files[0], dst)
        copied.append(dst)
    else:
        for i, src in enumerate(files, 1):
            # 원래 확장자를 지킨다. 사진은 사진으로 가야 한다.
            suffix = f"-{i}" if len(files) > 1 else ""
            dst = dest_dir / f"_사진_{name}{suffix}{src.suffix}"
            shutil.copy2(src, dst)
            copied.append(dst)

    steps = PHONE_STEPS["reel" if kind == "reel" else "photo"]
    out_text = dest_dir / f"_게시글_{name}.txt"
    out_text.write_text("\n".join([
        caption.rstrip(), "", "-" * 30, "휴대폰에서 할 일", *steps,
    ]), encoding="utf-8")
    return copied, out_text


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
        print("[i] 보낼 것이 없다. 먼저 만들어라: py make_reel.py <폴더>")
        return 0

    for key, rec in targets:
        name = Path(key).name
        kind = rec.get("kind", "reel")
        files = [Path(f) for f in (rec.get("files") or [rec.get("video", "")])]
        missing = [f for f in files if not f.exists()]
        if not files or missing:
            print(f"[!] 파일이 없다: {missing[0] if missing else name}")
            continue
        if kind == "reel" and files[0].suffix.lower() != ".mp4":
            print(f"[!] {name}: 릴스로 등록돼 있는데 영상 파일이 아니다 ({files[0].name}). 건너뛴다.")
            continue

        # 글 파일 위치가 릴스와 피드가 다르다 (approve.py 와 같은 규칙)
        cap = (files[0].with_suffix(".txt") if kind == "reel"
               else files[0].with_name(name + "-post.txt"))
        text = cap.read_text(encoding="utf-8") if cap.exists() else ""

        dest = Path(args.to) if args.to else Path(key)
        copied, t = deliver(files, text, dest, name, kind)
        print(f"[+] {name}  [{approve.KIND_NAME.get(kind, '릴스')}]")
        for c in copied:
            print(f"    {'영상' if kind == 'reel' else '사진'}: {c}")
        print(f"    글  : {t}")

    print()
    print("휴대폰에서: 드라이브 앱에서 저장 → 인스타에 올리기 → 글 붙여넣기 → 게시")
    print("(자세한 순서는 폴더에 만들어진 _게시글_*.txt 아래쪽에 적어뒀다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
