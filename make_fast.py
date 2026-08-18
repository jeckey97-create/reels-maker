"""빠른 컷 릴스 — 과정을 촥촥 넘겨 보여주는 15초짜리.

make_reel.py 는 **사진 3~4장을 천천히** 보여준다 (컷당 2~4초, 확대 효과).
이건 반대다. **화면 캡처 수십 장을 0.5초씩** 넘겨 과정 전체를 압축한다.
"이거 만드는 데 이런 걸 다 거쳤다" 를 보여주는 용도다.

    py make_fast.py <폴더>              # 0.5초씩
    py make_fast.py <폴더> --sec 0.4    # 더 빠르게
    py make_fast.py <폴더> --hold 2     # 첫 컷과 끝 컷만 길게 (초)

make_reel.py 와 다른 점:
    · 사진을 고르지 않는다. **폴더에 있는 순서 그대로 전부** 쓴다.
      화면 캡처는 흔들림·밝기로 거르면 안 되고, 비슷하다고 빼도 안 된다.
    · 확대(켄번스)와 크로스페이드가 없다. 0.5초 컷에서는 어지럽기만 하다.
    · 가로 화면을 세로에 맞춘다. 잘라내지 않고 **흐린 배경 위에 얹는다.**
      명령창이나 웹 화면은 잘라내면 무슨 화면인지 알 수 없게 된다.

폴더에 둘 수 있는 것:
    순서.txt    한 줄에 파일명 하나. 이 순서대로 쓴다 (없으면 파일명 순)
    labels.txt  `파일명 = 자막` — 그 컷에만 자막이 뜬다
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import approve
import config as cfg
import images


def fit_vertical(src: Path, dst: Path, label: str = "") -> Path:
    """가로 화면을 9:16 에 맞춘다. 잘라내는 대신 흐린 배경 위에 얹는다."""
    img = images.load_upright(src).convert("RGB")
    W, H = cfg.WIDTH, cfg.HEIGHT

    # 배경 — 같은 그림을 꽉 채워 자르고 흐리게. 검은 여백보다 훨씬 낫다.
    scale = max(W / img.width, H / img.height)
    bg = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1),
                    Image.LANCZOS)
    left = (bg.width - W) // 2
    top = (bg.height - H) // 2
    canvas = bg.crop((left, top, left + W, top + H)).filter(
        ImageFilter.GaussianBlur(28))
    canvas = Image.blend(canvas, Image.new("RGB", (W, H), (10, 12, 18)), 0.35)

    # 본체 — 가로폭을 거의 꽉 채운다. 화면 글자가 읽혀야 의미가 있다.
    fit = min((W - 60) / img.width, (H - 420) / img.height)
    body = img.resize((int(img.width * fit), int(img.height * fit)), Image.LANCZOS)
    canvas.paste(body, ((W - body.width) // 2, (H - body.height) // 2))

    if label:
        canvas = _draw_label(canvas, label)
    canvas.save(dst, quality=95)
    return dst


def _draw_label(img: Image.Image, text: str) -> Image.Image:
    """아래쪽에 한 줄 자막. 컷이 짧으니 짧게 한 줄만."""
    d = ImageDraw.Draw(img)
    size = 76
    try:
        font = ImageFont.truetype(str(cfg.FONT_PATH), size)
    except OSError:
        font = ImageFont.load_default()
    text = images._drop_unsupported(text, font)
    w = d.textbbox((0, 0), text, font=font)[2]
    x, y = (cfg.WIDTH - w) // 2, int(cfg.HEIGHT * 0.80)
    # 배경이 어떤 색이든 읽히게 검은 테두리를 두른다
    for dx in (-3, 0, 3):
        for dy in (-3, 0, 3):
            if dx or dy:
                d.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
    d.text((x, y), text, font=font, fill=(255, 255, 255))
    return img


def read_order(folder: Path) -> list[Path]:
    order_file = folder / "순서.txt"
    if order_file.exists():
        out = []
        for line in order_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = folder / line
            if p.exists():
                out.append(p)
            else:
                print(f"[!] 순서.txt 에 적힌 파일이 없다: {line}")
        return out
    return images.list_images(folder)


def read_labels(folder: Path) -> dict[str, str]:
    f = folder / "labels.txt"
    if not f.exists():
        return {}
    out = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def build(folder: Path, sec: float, hold: float) -> Path:
    cfg.ensure_dirs()
    shots = read_order(folder)
    if len(shots) < 3:
        raise SystemExit(f"[!] 사진이 {len(shots)}장뿐이다. 3장 이상 넣어라.")
    labels = read_labels(folder)

    work = cfg.WORK_DIR / f"fast-{folder.name}"
    work.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[Path, float]] = []
    for i, src in enumerate(shots):
        dst = work / f"{i:03d}.jpg"
        fit_vertical(src, dst, labels.get(src.name, ""))
        # 첫 컷과 끝 컷은 길게 — 첫 컷은 훅을 읽어야 하고, 끝 컷은 CTA 다.
        d = hold if (i == 0 or i == len(shots) - 1) else sec
        frames.append((dst, d))
        print(f"  {i+1:2}/{len(shots)}  {src.name}  {d}초"
              + (f"  「{labels[src.name]}」" if src.name in labels else ""))

    total = sum(d for _, d in frames)
    print(f"[i] {len(frames)}컷 / 약 {total:.1f}초")

    # concat 목록 — 확대도 크로스페이드도 없다. 그냥 촥촥 넘긴다.
    lst = work / "list.txt"
    lines = []
    for p, d in frames:
        lines.append(f"file '{p.as_posix()}'")
        lines.append(f"duration {d}")
    lines.append(f"file '{frames[-1][0].as_posix()}'")   # 마지막 컷 고정용
    lst.write_text("\n".join(lines), encoding="utf-8")

    out = cfg.OUT_DIR / f"{folder.name}-fast.mp4"
    subprocess.run([
        cfg.FFMPEG, "-y",
        "-f", "concat", "-safe", "0", "-i", str(lst),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-shortest",
        "-vf", f"fps={cfg.FPS},format=yuv420p",
        "-c:v", "libx264", "-preset", "medium",
        "-b:v", f"{cfg.VIDEO_BITRATE_K}k", "-c:a", "aac",
        str(out),
    ], check=True, capture_output=True)
    print(f"[+] 완성: {out}  ({total:.1f}초)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="과정을 빠르게 넘기는 릴스")
    ap.add_argument("folder")
    ap.add_argument("--sec", type=float, default=0.5, help="컷당 초 (기본 0.5)")
    ap.add_argument("--hold", type=float, default=1.6,
                    help="첫 컷·끝 컷을 붙잡는 초 (기본 1.6)")
    args = ap.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"[!] 폴더가 없다: {folder}")
        return 2

    out = build(folder, args.sec, args.hold)
    approve.register_pending(folder, out, images.folder_fingerprint(folder))
    print(f"[i] 승인 대기에 넣었다. 확인: py approve.py --show \"{folder.name}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
