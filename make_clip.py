"""화면 녹화본 → 9:16 릴스. **진짜 녹화가 제일 생생하다.**

`make_screen.py` 는 작업 화면을 그려서 재현한다. 이건 반대로, 실제로 녹화한
파일에서 좋은 구간만 잘라 릴스 규격으로 만든다.

    py make_clip.py 녹화.mp4 --from 1:20 --to 1:50
    py make_clip.py 녹화.mp4 --from 90 --to 118 --focus left
    py make_clip.py 녹화.mp4 --from 0:10 --to 0:40 --label "AI 가 코드 쓰는 중"

PC 화면은 가로(16:9)라 세로로 그냥 넣으면 글자가 깨알같이 작아진다.
그래서 **화면의 일부만 잘라낸다.** 어디를 남길지 `--focus` 로 정한다.

    left    왼쪽 (터미널이 왼쪽에 있을 때)
    center  가운데 (기본)
    right   오른쪽

윈도우 녹화는 `Win + G` 로 한다. 30초 안팎이 좋고, 오류가 한 번 나는 구간이
있으면 그게 제일 좋은 장면이다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import approve
import config as cfg

FONTS = ["C:/Windows/Fonts/malgunbd.ttf",
         "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf"]


def seconds(text: str) -> float:
    """`1:20` 이나 `80` 을 초로."""
    text = text.strip()
    if ":" in text:
        parts = [float(p) for p in text.split(":")]
        out = 0.0
        for p in parts:
            out = out * 60 + p
        return out
    return float(text)


def probe_size(path: Path) -> tuple[int, int]:
    r = subprocess.run([cfg.FFPROBE, "-v", "error", "-select_streams", "v",
                        "-show_entries", "stream=width,height",
                        "-of", "csv=p=0:s=x", str(path)],
                       capture_output=True, text=True, check=True)
    w, h = r.stdout.strip().split("\n")[0].split("x")
    return int(w), int(h)


def build(src: Path, start: float, end: float, focus: str, label: str) -> Path:
    if end <= start:
        raise SystemExit("[!] --to 가 --from 보다 뒤여야 한다.")
    dur = end - start
    if dur > 90:
        print(f"[!] {dur:.0f}초는 길다. 릴스는 30초 안팎이 낫다.")

    w, h = probe_size(src)
    print(f"[i] 원본 {w}x{h} / {dur:.1f}초 를 자른다")

    # 9:16 로 잘라낼 폭. 원본이 세로면 그대로 쓴다.
    crop_w = min(w, int(h * 9 / 16))
    x = {"left": 0, "right": w - crop_w}.get(focus, (w - crop_w) // 2)
    chain = (f"crop={crop_w}:{h}:{x}:0,"
             f"scale={cfg.WIDTH}:{cfg.HEIGHT}:force_original_aspect_ratio=decrease,"
             f"pad={cfg.WIDTH}:{cfg.HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
             f"fps={cfg.FPS},format=yuv420p")

    if label:
        fontfile = next((f for f in FONTS if Path(f).exists()), None)
        if fontfile:
            safe = label.replace(":", "\\:").replace("'", "")
            chain += (f",drawtext=fontfile='{fontfile}':text='{safe}':"
                      f"fontcolor=white:fontsize=64:borderw=4:bordercolor=black:"
                      f"x=(w-text_w)/2:y=h*0.80")
        else:
            print("[i] 한글 글꼴을 못 찾아 자막은 넣지 않는다")

    cfg.ensure_dirs()
    out = cfg.OUT_DIR / f"{src.stem}-clip.mp4"
    subprocess.run([
        cfg.FFMPEG, "-y", "-ss", f"{start}", "-t", f"{dur}", "-i", str(src),
        "-vf", chain, "-c:v", "libx264", "-preset", "medium",
        "-b:v", f"{cfg.VIDEO_BITRATE_K}k",
        "-c:a", "aac", "-ac", "2", str(out),
    ], check=True, capture_output=True)
    print(f"[+] 완성: {out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="화면 녹화본 → 9:16 릴스")
    ap.add_argument("video")
    ap.add_argument("--from", dest="start", required=True, help="시작 (1:20 또는 80)")
    ap.add_argument("--to", dest="end", required=True, help="끝")
    ap.add_argument("--focus", default="center", choices=["left", "center", "right"])
    ap.add_argument("--label", default="", help="아래쪽 자막 한 줄")
    args = ap.parse_args()

    src = Path(args.video).resolve()
    if not src.exists():
        print(f"[!] 영상이 없다: {src}")
        return 2

    out = build(src, seconds(args.start), seconds(args.end), args.focus, args.label)
    approve.register_pending(src.parent / src.stem, out)
    print(f"[i] 승인 대기에 넣었다. 확인: py approve.py --show \"{src.stem}\"")
    print("[i] 소리가 들어 있으면 그대로 올라간다. 필요 없으면 인스타에서 음소거해라.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
