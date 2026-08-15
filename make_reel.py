"""사진 폴더 → 릴스 mp4 (+ 글·해시태그).

사용법:
    py make_reel.py "G:\\내 드라이브\\릴스"
    py make_reel.py <폴더> --captions "첫 컷" "둘째 컷" "셋째 컷"
    py make_reel.py <폴더> --no-music
    py make_reel.py <폴더> --publish       # 실제 게시 (기본은 dry-run)
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

import approve
import audio_mix
import config as cfg
import graph_api
import images
import photo_select
import post_text
import preview
import video


class NotEnoughPhotos(RuntimeError):
    """기준을 통과한 사진이 모자랄 때."""


def pick_photos(folder: Path, limit: int):
    """photo_select.py 의 기준으로 고른다. Shot 목록을 그대로 돌려준다.

    ok/ 하위폴더가 있으면 거기 있는 사진만 후보로 쓴다 (수동 승인).
    """
    consent = folder / "ok"
    source = consent if consent.is_dir() and images.list_images(consent) else folder
    if source is consent:
        print(f"[i] 승인 폴더를 쓴다: {consent}")
    photos = images.list_images(source)
    if not photos:
        return []
    return photo_select.choose(photos, limit, folder=folder)


def make(folder: Path, captions: list[str] | None, use_music: bool,
         out_name: str | None = None) -> tuple[Path, str]:
    cfg.ensure_dirs()

    shots = pick_photos(folder, cfg.MAX_PHOTOS)
    if len(shots) < cfg.MIN_PHOTOS:
        # SystemExit 는 Exception 이 아니라 호출부의 예외 처리를 빠져나간다.
        # 감시 루프가 폴더 하나 때문에 멈추면 안 되므로 평범한 예외를 쓴다.
        raise NotEnoughPhotos(
            f"쓸 수 있는 사진이 {len(shots)}장뿐이다. 최소 {cfg.MIN_PHOTOS}장 필요.")

    caps = list(captions or post_text.read_captions(folder))
    if not captions and caps:
        print(f"[i] captions.txt 에서 자막 {len(caps)}줄을 읽었다.")
    info = post_text.read_info(folder)
    if info:
        print(f"[i] info.txt: " + ", ".join(f"{k}={v}" for k, v in info.items()))
    if not caps:
        kinds = [getattr(sh.scene, "kind", "other") for sh in shots]
        caps = post_text.build_story_captions(kinds, seed=folder.name, info=info)
        print("[i] 장면 순서에 맞춰 자막을 만들었다 (captions.txt 로 덮어쓸 수 있다).")
    caps += [""] * (len(shots) - len(caps))

    budget = images.caption_char_budget()
    for c in caps:
        if len("".join(c.split())) > budget:
            print(f"[!] 자막이 {budget}자를 넘어 잘린다: {c!r}")
            print(f"    글자 크기는 고정이라 줄일 수 없다. captions.txt 나 info.txt 의 훅을 짧게 써라.")

    work = cfg.WORK_DIR / folder.name
    # 이전 실행에서 남은 프레임을 지운다. 컷 수가 줄어들면 옛 프레임이 남아
    # 결과를 확인할 때 헷갈린다.
    if work.exists():
        for old in work.glob("frame*.png"):
            old.unlink(missing_ok=True)
    frames = []
    for i, (sh, c) in enumerate(zip(shots, caps)):
        boxes = sh.face_boxes if sh.needs_blur else None
        if boxes:
            print(f"[i] 얼굴 블러 처리: {sh.path.name} ({len(boxes)}곳)")
        if sh.crop_box:
            print(f"[i] 얼굴 잘라내기: {sh.path.name} → {sh.crop_box}")
        frames.append(images.prepare_frame(
            sh.path, c, work / f"frame{i:02d}.png", boxes, sh.crop_box))


    out = cfg.OUT_DIR / (out_name or f"{folder.name}.mp4")
    video.build_reel(frames, out, captions=caps)
    print(f"[+] 영상 완성: {out}  ({video.probe_duration(out):.1f}초)")

    # 배경음악은 인코딩이 끝난 뒤에 얹는다. 음원이 없으면 그대로 넘어간다.
    if use_music:
        audio_mix.mix_audio(out, out=out, cuts=len(caps))

    sheet = preview.contact_sheet(out, durations=[video.cut_duration(c) for c in caps])
    if sheet:
        print(f"[+] 미리보기 이미지: {sheet}")
        # 휴대폰에서는 영상 미리보기가 안 되는 경우가 많다. 사진 폴더에도 넣어두면
        # 구글 드라이브 앱으로 바로 확인할 수 있다.
        try:
            import shutil
            drive_copy = folder / "_미리보기.jpg"
            shutil.copy2(sheet, drive_copy)
            print(f"[+] 드라이브에도 저장: {drive_copy}")
        except Exception as e:
            print(f"[i] 드라이브 복사 실패 (무시함): {e}")

    override_cap, extra_tags = post_text.read_overrides(folder)
    caption = override_cap or post_text.build_caption(folder.name, caps, extra_tags, info)

    (out.with_suffix(".txt")).write_text(caption, encoding="utf-8")
    print(f"[+] 글 저장: {out.with_suffix('.txt')}")
    return out, caption


def main() -> int:
    ap = argparse.ArgumentParser(description="사진 폴더로 릴스 만들기")
    ap.add_argument("folder", help="사진이 있는 폴더")
    ap.add_argument("--captions", nargs="*", default=None, help="사진별 자막")
    ap.add_argument("--no-music", action="store_true", help="무음으로 만든다")
    ap.add_argument("--publish", action="store_true", help="실제로 인스타에 게시 (기본은 dry-run)")
    ap.add_argument("--video-url", default="", help="게시에 쓸 공개 영상 URL")
    args = ap.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        print(f"[!] 폴더가 없다: {folder}")
        return 2
    # watch_folder.py 와 같은 키로 기록되도록 경로를 펴둔다.
    # 상대 경로로 실행해도 승인 대기 목록에 같은 항목으로 들어간다.
    folder = folder.resolve()

    try:
        out, caption = make(folder, args.captions, use_music=not args.no_music)
    except NotEnoughPhotos as e:
        print(f"[!] {e}")
        return 1

    # 승인 대기 목록에 올린다. 이게 빠지면 approve.py 에서 안 보인다.
    approve.register_pending(folder, out, images.folder_fingerprint(folder))
    print(f"[i] 승인 대기에 넣었다. 확인: py approve.py --show \"{folder.name}\"")

    # 한글 파일명은 인코딩해서 보낸다 (approve.py 의 같은 처리 참고)
    video_url = args.video_url or (
        f"{cfg.PUBLIC_VIDEO_BASE.rstrip('/')}/{urllib.parse.quote(out.name)}"
        if cfg.PUBLIC_VIDEO_BASE else ""
    )
    if args.publish and not video_url:
        print("[!] 게시하려면 공개 URL 이 필요하다. --video-url 또는 .env 의 REELS_PUBLIC_BASE 를 채워라.")
        return 2

    media_id = graph_api.publish_reel(
        video_url or "(공개 URL 없음)", caption, dry_run=not args.publish)
    if args.publish and media_id:
        approve.mark_published(folder, media_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
