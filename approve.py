"""승인 대기 릴스 확인 · 게시.

make_reel.py / watch_folder.py 는 영상을 만들기만 하고 게시하지 않는다.
만들어진 릴스는 승인 대기 상태로 state.json 에 쌓이고, 게시는 여기서 사람이
확인한 뒤에 한다.

수업 사진에는 학생 얼굴이 들어가므로 사람 검토 단계를 없애면 안 된다.

사용법:
    py approve.py                    # 대기 중인 릴스 목록
    py approve.py --show 7.22        # 영상 경로와 글 전문 보기
    py approve.py --publish 7.22     # 승인하고 게시
    py approve.py --reject 7.22      # 올리지 않기로 하고 목록에서 뺀다
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import config as cfg
import graph_api
import preview

PENDING = "pending"
KIND_NAME = {"reel": "릴스", "image": "피드 사진", "carousel": "캐러셀"}
PUBLISHED = "published"
REJECTED = "rejected"
SKIPPED = "skipped"   # 기준을 통과한 사진이 모자라 만들지 못한 폴더


def load_state() -> dict:
    if cfg.STATE_FILE.exists():
        try:
            return json.loads(cfg.STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    cfg.STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def entry_key(folder: Path) -> str:
    """state.json 에서 폴더 하나를 가리키는 키."""
    return str(folder)


def register_pending(folder: Path, video: Path, fingerprint: str = "",
                     state: dict | None = None, kind: str = "reel",
                     files: list[str] | None = None) -> dict:
    """만들어진 릴스를 승인 대기 목록에 넣는다.

    make_reel.py 와 watch_folder.py 가 **둘 다** 여기를 거쳐야 한다.
    한쪽만 등록하면 그 경로로 만든 사람은 approve.py 에서
    "승인 대기 중인 릴스가 없다" 만 보게 된다.
    """
    state = load_state() if state is None else state
    key = entry_key(folder)
    prev = state.get(key, {})
    was = prev.get("status")
    # 한 폴더는 대기 항목 하나만 갖는다. 릴스를 만들고 캐러셀을 또 만들면
    # 앞의 것이 밀려난다. 조용히 사라지면 "만들었는데 없다" 가 되므로 알린다.
    if was == PENDING and prev.get("kind", "reel") != kind:
        print(f"[i] 이 폴더로 만든 {KIND_NAME.get(prev.get('kind','reel'))}"
              f"(이)가 대기 중이었다. {KIND_NAME.get(kind)}(으)로 바꾼다.")
    state[key] = {
        "fingerprint": fingerprint,
        "video": str(video),      # 릴스면 mp4, 피드면 첫 사진
        "kind": kind,             # reel / image / carousel
        "files": files or [str(video)],
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": PENDING,
    }
    save_state(state)
    if was == PUBLISHED:
        print("[i] 전에 게시한 폴더다. 영상을 새로 만들었으니 다시 승인 대기로 둔다.")
    return state


def register_failure(folder: Path, error: str, fingerprint: str = "",
                     state: dict | None = None) -> dict:
    """만들지 못한 폴더를 기록한다 (사진 부족 등)."""
    state = load_state() if state is None else state
    state[entry_key(folder)] = {
        "fingerprint": fingerprint,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": SKIPPED,
        "error": error,
    }
    save_state(state)
    return state


def mark_published(folder: Path, media_id: str, state: dict | None = None) -> dict:
    """게시가 끝난 폴더를 게시 완료로 바꾼다.

    make_reel.py --publish 로 바로 올린 경우, 이걸 안 하면 이미 올라간 릴스가
    approve.py 목록에 계속 대기로 남는다.
    """
    state = load_state() if state is None else state
    rec = state.get(entry_key(folder))
    if rec is None:
        return state
    rec["status"] = PUBLISHED
    rec["media_id"] = media_id
    save_state(state)
    return state


def _entries(state: dict, status: str) -> list[tuple[str, dict]]:
    return [(k, v) for k, v in state.items() if v.get("status") == status]


def _find(state: dict, name: str) -> tuple[str, dict] | None:
    for key, rec in state.items():
        if Path(key).name == name or key == name:
            return key, rec
    return None


def cmd_list(state: dict) -> int:
    pending = _entries(state, PENDING)
    if not pending:
        print("[i] 승인 대기 중인 릴스가 없다.")
        return 0
    print(f"[i] 승인 대기 {len(pending)}개:\n")
    for key, rec in pending:
        print(f"  {Path(key).name}   [{KIND_NAME.get(rec.get('kind', 'reel'), '릴스')}]")
        print(f"    파일: {rec.get('video')}")
        n = len(rec.get("files") or [])
        if n > 1:
            print(f"    사진 {n}장")
        print(f"    만든 시각: {rec.get('at')}")
        print()
    print("확인:  py approve.py --show <이름>")
    print("게시:  py approve.py --publish <이름>")
    return 0


def cmd_show(state: dict, name: str) -> int:
    hit = _find(state, name)
    if not hit:
        print(f"[!] '{name}' 을 찾지 못했다.")
        return 2
    key, rec = hit
    kind = rec.get("kind", "reel")
    print(f"[i] {Path(key).name}  [{KIND_NAME.get(kind, '릴스')}]  ({rec.get('status')})")
    vid = Path(rec.get("video", ""))

    if kind == "reel":
        print(f"    영상: {vid}")
        sheet = vid.with_name(vid.stem + "-preview.jpg")
        if not sheet.exists():
            sheet = preview.contact_sheet(vid) or sheet
        if sheet.exists():
            print(f"    미리보기 이미지: {sheet}")
            print("    (영상이 안 보이는 환경이면 이 이미지로 확인해라)")
        txt = vid.with_suffix(".txt")
    else:
        for i, f in enumerate(rec.get("files") or [], 1):
            print(f"    {i}. {f}")
        txt = vid.with_name(Path(key).name + "-post.txt")

    if txt.exists():
        print("\n--- 게시글 ---")
        print(txt.read_text(encoding="utf-8"))
    print("\n사진을 직접 확인해라. 학생 얼굴이 들어갔다면 동의 범위를 먼저 따져야 한다.")
    return 0


def cmd_publish(state: dict, name: str) -> int:
    hit = _find(state, name)
    if not hit:
        print(f"[!] '{name}' 을 찾지 못했다.")
        return 2
    key, rec = hit
    if rec.get("status") != PENDING:
        print(f"[!] 상태가 '{rec.get('status')}' 라 게시할 수 없다.")
        return 2

    kind = rec.get("kind", "reel")
    paths = [Path(p) for p in (rec.get("files") or [rec.get("video", "")])]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"[!] 파일이 없다: {missing[0]}")
        return 2

    if not cfg.PUBLIC_VIDEO_BASE:
        print("[!] .env 의 REELS_PUBLIC_BASE 가 비어 있다. "
              "Graph API 는 공개 URL 로만 파일을 받는다. serve.py 를 먼저 켜라.")
        return 2
    if not graph_api.configured():
        print("[!] .env 의 IG_USER_ID / IG_ACCESS_TOKEN 이 비어 있다.")
        return 2

    base = cfg.PUBLIC_VIDEO_BASE.rstrip("/")
    urls = [f"{base}/{p.name}" for p in paths]

    if kind == "reel":
        caption = paths[0].with_suffix(".txt").read_text(encoding="utf-8")
        media_id = graph_api.publish_reel(urls[0], caption, dry_run=False)
    else:
        # 피드 글은 <폴더이름>-post.txt 에 있다
        txt = paths[0].with_name(Path(key).name + "-post.txt")
        caption = txt.read_text(encoding="utf-8")
        if kind == "carousel":
            media_id = graph_api.publish_carousel(urls, caption, dry_run=False)
        else:
            media_id = graph_api.publish_image(urls[0], caption, dry_run=False)
    rec["status"] = PUBLISHED
    rec["media_id"] = media_id
    save_state(state)
    print(f"[+] 게시 완료: {Path(key).name}")
    return 0


def cmd_reject(state: dict, name: str) -> int:
    hit = _find(state, name)
    if not hit:
        print(f"[!] '{name}' 을 찾지 못했다.")
        return 2
    key, rec = hit
    rec["status"] = REJECTED
    save_state(state)
    print(f"[i] '{Path(key).name}' 을 올리지 않기로 했다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="승인 대기 릴스 확인·게시")
    ap.add_argument("--show", metavar="이름")
    ap.add_argument("--publish", metavar="이름")
    ap.add_argument("--reject", metavar="이름")
    args = ap.parse_args()

    state = load_state()
    if args.show:
        return cmd_show(state, args.show)
    if args.publish:
        return cmd_publish(state, args.publish)
    if args.reject:
        return cmd_reject(state, args.reject)
    return cmd_list(state)


if __name__ == "__main__":
    sys.exit(main())
