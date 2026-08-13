"""사진 폴더를 감시하다가 새 사진이 들어오면 릴스를 만든다.

폴링 방식이다. 구글 드라이브 스트리밍 폴더는 OS 파일 이벤트가 잘 안 올라와서
watchdog 보다 폴링이 안정적이다.

사용법:
    py watch_folder.py                       # 30초마다 확인
    py watch_folder.py --interval 60
    py watch_folder.py --once                # 한 바퀴만 돌고 종료

영상만 만들고 게시는 하지 않는다. 게시는 approve.py 로 사람이 확인한 뒤에 한다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import config as cfg
import approve
import images
import make_reel


load_state = approve.load_state
save_state = approve.save_state


# 지문 계산은 make_reel.py 와 공유한다 (images.py). 둘이 다르면 같은 폴더가
# 승인 대기 목록에 두 번 들어간다.
fingerprint = images.folder_fingerprint


def scan_once(watch_dir: Path, state: dict) -> int:
    """감시 폴더 아래 각 하위 폴더를 하나의 릴스 단위로 본다.

    하위 폴더가 없으면 감시 폴더 자체를 하나의 단위로 취급한다.
    """
    subdirs = [d for d in watch_dir.iterdir() if d.is_dir()] if watch_dir.exists() else []
    targets = subdirs or ([watch_dir] if watch_dir.exists() else [])

    made = 0
    for folder in targets:
        photos = images.list_images(folder)
        if len(photos) < cfg.MIN_PHOTOS:
            continue
        fp = fingerprint(folder)
        key = approve.entry_key(folder)
        if state.get(key, {}).get("fingerprint") == fp:
            continue  # 이미 처리했고 바뀐 게 없다

        print(f"\n[i] 새 사진 감지: {folder}  ({len(photos)}장)")
        try:
            out, caption = make_reel.make(folder, captions=None, use_music=True)
        except Exception as e:
            print(f"[!] 실패: {folder} — {e}")
            # 실패도 기록해둔다. 안 그러면 스캔할 때마다 얼굴 감지를 다시 돌린다.
            # 사진이 바뀌면 지문이 달라져서 자동으로 재시도된다.
            approve.register_failure(folder, str(e), fp, state)
            continue

        approve.register_pending(folder, out, fp, state)
        print(f"[i] 승인 대기에 넣었다. 확인: py approve.py --show \"{folder.name}\"")
        made += 1

    return made


def main() -> int:
    ap = argparse.ArgumentParser(description="사진 폴더 감시 → 릴스 자동 생성")
    ap.add_argument("--dir", default=str(cfg.WATCH_DIR), help="감시할 폴더")
    ap.add_argument("--interval", type=int, default=30, help="확인 주기(초)")
    ap.add_argument("--once", action="store_true", help="한 바퀴만 돌고 종료")
    args = ap.parse_args()

    watch_dir = Path(args.dir)
    cfg.ensure_dirs()
    print(f"[i] 감시 폴더: {watch_dir}")
    print("[i] 영상만 만든다. 게시는 approve.py 로 사람이 확인한 뒤에 한다.")
    if not watch_dir.exists():
        print(f"[!] 폴더가 없다: {watch_dir}  — .env 의 REELS_WATCH_DIR 를 확인해라")
        return 2

    state = load_state()
    if args.once:
        n = scan_once(watch_dir, state)
        print(f"[i] {n}개 처리")
        return 0

    print(f"[i] {args.interval}초마다 확인한다. Ctrl+C 로 종료.")
    try:
        while True:
            scan_once(watch_dir, state)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[i] 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
