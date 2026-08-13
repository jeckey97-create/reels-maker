"""배경음악 합성 CLI.

사용법:
    py mix_cli.py out/sample-reel.mp4
    py mix_cli.py <영상> --music assets/music/background.mp3
    py mix_cli.py <영상> --volume 0.25 --fade-out 3 --no-loop
    py mix_cli.py <영상> -o out/final.mp4
    py mix_cli.py --check          # ffmpeg 설치 확인만

음원이 없으면 에러 없이 원본을 그대로 내보낸다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import audio_mix
import config as cfg


def main() -> int:
    ap = argparse.ArgumentParser(description="릴스 영상에 배경음악 합성")
    ap.add_argument("video", nargs="?", help="입력 영상 (mp4)")
    ap.add_argument("--music", help=f"음원 파일. 없으면 {cfg.MUSIC_DIR} 에서 고른다")
    ap.add_argument("--volume", type=float, help=f"배경음악 볼륨 (기본 {cfg.MUSIC_VOLUME})")
    ap.add_argument("--original-volume", type=float,
                    help=f"원본 음성 볼륨 (기본 {cfg.ORIGINAL_AUDIO_VOLUME})")
    ap.add_argument("--fade-out", type=float,
                    help=f"끝부분 페이드아웃 초 (기본 {cfg.FADE_OUT_SECONDS})")
    loop = ap.add_mutually_exclusive_group()
    loop.add_argument("--loop", dest="loop", action="store_true", help="음악이 짧으면 반복")
    loop.add_argument("--no-loop", dest="loop", action="store_false", help="반복하지 않음")
    ap.set_defaults(loop=None)
    ap.add_argument("-o", "--out", help="출력 경로 (기본 <입력>-music.mp4)")
    ap.add_argument("--check", action="store_true", help="ffmpeg 설치 확인만 하고 종료")
    args = ap.parse_args()

    ok, info = audio_mix.ffmpeg_available()
    if args.check:
        print(f"[+] {info}" if ok else f"[!] {info}")
        print(f"[i] 음원 폴더: {cfg.MUSIC_DIR}")
        found = audio_mix.pick_music()
        print(f"[i] 쓸 음원: {found if found else '없음 (원본 그대로 나간다)'}")
        return 0 if ok else 1
    if not ok:
        print(f"[!] {info}")
        return 1

    if not args.video:
        ap.error("영상 경로가 필요하다 (또는 --check)")

    try:
        out = audio_mix.mix_audio(
            Path(args.video),
            Path(args.music) if args.music else None,
            music_volume=args.volume,
            original_volume=args.original_volume,
            fade_out_seconds=args.fade_out,
            loop_music=args.loop,
            out=Path(args.out) if args.out else None,
        )
    except audio_mix.AudioMixError as e:
        print(f"[!] {e}")
        return 1

    print(f"[i] 결과: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
