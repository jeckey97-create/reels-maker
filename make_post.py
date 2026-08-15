"""사진 폴더 → 인스타 피드 게시물 (사진 1장 또는 캐러셀).

릴스(make_reel.py)와 같은 사진 선별·초상권 검사·글 생성을 그대로 쓴다.
다른 것은 영상을 만들지 않고 사진을 그대로 올린다는 점뿐이다.

사용법:
    py make_post.py "G:\\내 드라이브\\릴스\\7월수업"              # 캐러셀 (기본)
    py make_post.py <폴더> --one                                 # 사진 1장만
    py make_post.py <폴더> --count 4                             # 장수 지정
    py make_post.py <폴더> --publish                             # 실제 게시

릴스와 마찬가지로 **--publish 를 붙이기 전에는 게시되지 않는다.**
만들어진 게시물은 승인 대기 목록에 올라가고, approve.py 로 확인한 뒤 올린다.
"""

from __future__ import annotations

import argparse
import sys
import urllib.parse
from pathlib import Path

import approve
import config as cfg
import graph_api
import images
import make_reel
import photo_select
import post_text


def build(folder: Path, count: int) -> tuple[list[Path], str]:
    """사진을 골라 피드 규격으로 저장하고 글을 만든다."""
    cfg.ensure_dirs()

    shots = make_reel.pick_photos(folder, count)
    if not shots:
        raise make_reel.NotEnoughPhotos("쓸 수 있는 사진이 없다.")
    if count > 1 and len(shots) < 2:
        raise make_reel.NotEnoughPhotos(
            f"캐러셀은 2장 이상 필요한데 {len(shots)}장뿐이다. "
            "--one 으로 한 장만 올리거나 사진을 더 넣어라.")

    out_files: list[Path] = []
    for i, sh in enumerate(shots, 1):
        boxes = sh.face_boxes if sh.needs_blur else None
        if boxes:
            print(f"[i] 얼굴 블러 처리: {sh.path.name} ({len(boxes)}곳)")
        if sh.crop_box:
            print(f"[i] 얼굴 잘라내기: {sh.path.name} → {sh.crop_box}")
        dst = cfg.OUT_DIR / f"{folder.name}-{i}.jpg"
        images.prepare_feed_photo(sh.path, dst, boxes, sh.crop_box)
        out_files.append(dst)
        print(f"[+] 사진 {i}: {dst.name}  ({cfg.FEED_WIDTH}x{cfg.FEED_HEIGHT})")

    info = post_text.read_info(folder)
    if info:
        print("[i] info.txt: " + ", ".join(f"{k}={v}" for k, v in info.items()))

    # 글은 릴스와 같은 방식으로 만든다. 자막용 문구를 본문 재료로 쓴다.
    caps = list(post_text.read_captions(folder))
    if not caps:
        kinds = [getattr(sh.scene, "kind", "other") for sh in shots]
        caps = post_text.build_story_captions(kinds, seed=folder.name, info=info)
    # 글에 쓰는 문장은 **올라가는 사진 수만큼**만 쓴다. 릴스는 자막이 컷마다
    # 얹히지만 피드는 글이 전부라, --one 으로 한 장 올리는데 captions.txt 의
    # 네 줄이 다 들어가면 사진과 글이 안 맞는다. 첫 줄(훅)은 항상 남긴다.
    if len(caps) > len(out_files):
        caps = caps[:max(1, len(out_files))]
    override_cap, extra_tags = post_text.read_overrides(folder)
    caption = override_cap or post_text.build_caption(
        folder.name, caps, extra_tags, info)

    txt = cfg.OUT_DIR / f"{folder.name}-post.txt"
    txt.write_text(caption, encoding="utf-8")
    print(f"[+] 글 저장: {txt}")
    return out_files, caption


def main() -> int:
    ap = argparse.ArgumentParser(description="사진 폴더로 인스타 피드 게시물 만들기")
    ap.add_argument("folder", help="사진이 있는 폴더")
    ap.add_argument("--one", action="store_true", help="사진 1장짜리 게시물")
    ap.add_argument("--count", type=int, default=None,
                    help=f"캐러셀에 넣을 사진 수 (기본 {cfg.CAROUSEL_MAX}, 최대 10)")
    ap.add_argument("--publish", action="store_true",
                    help="실제로 게시 (기본은 dry-run)")
    ap.add_argument("--base-url", default="",
                    help="사진을 올려둔 공개 주소. 없으면 .env 의 REELS_PUBLIC_BASE")
    args = ap.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        print(f"[!] 폴더가 없다: {folder}")
        return 2
    folder = folder.resolve()

    count = 1 if args.one else min(args.count or cfg.CAROUSEL_MAX, 10)

    try:
        files, caption = build(folder, count)
    except make_reel.NotEnoughPhotos as e:
        print(f"[!] {e}")
        return 1

    kind = "image" if len(files) == 1 else "carousel"
    approve.register_pending(folder, files[0], images.folder_fingerprint(folder),
                             kind=kind, files=[str(f) for f in files])
    print(f"[i] 승인 대기에 넣었다 ({kind}). "
          f"확인: py approve.py --show \"{folder.name}\"")

    base = args.base_url or cfg.PUBLIC_VIDEO_BASE
    if args.publish and not base:
        print("[!] 게시하려면 공개 URL 이 필요하다. serve.py 를 켜거나 --base-url 을 줘라.")
        return 2
    # 한글 파일명은 인코딩해서 보낸다 (approve.py 의 같은 처리 참고)
    urls = [f"{base.rstrip('/')}/{urllib.parse.quote(f.name)}" for f in files] if base else \
           ["(공개 URL 없음)"] * len(files)

    if kind == "image":
        mid = graph_api.publish_image(urls[0], caption, dry_run=not args.publish)
    else:
        mid = graph_api.publish_carousel(urls, caption, dry_run=not args.publish)
    if args.publish and mid:
        approve.mark_published(folder, mid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
