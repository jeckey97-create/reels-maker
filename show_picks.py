"""고른 사진 · 뺀 사진을 **그림으로** 펼쳐 보여준다.

터미널 출력만으로는 파일 이름밖에 안 보인다. 어떤 사진이 뽑혔는지 눈으로
보려면(그리고 화면 녹화에 담으려면) 사진 자체가 화면에 떠야 한다.

    py show_picks.py "C:\\사진\\8월수업"          # 두 장을 만들고 바로 띄운다
    py show_picks.py "C:\\사진\\8월수업" --no-open  # 만들기만

만들어지는 것 (out/):
    <폴더>-뽑힘.jpg   골라낸 사진 + 점수·이유
    <폴더>-제외.jpg   빠진 사진 + 빠진 이유 (흐리게 처리)

게시하지 않는다. 영상도 만들지 않는다. **보여주기만 한다.**
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

import config as cfg
import images
import photo_select

COLS = 4
THUMB = 380
PAD = 26
CAP_H = 86
BG = (18, 20, 24)
TITLE_H = 130


def _font(size: int, bold: bool = False):
    names = ([str(cfg.FONT_PATH), "C:/Windows/Fonts/malgunbd.ttf",
              "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf"] if bold else
             ["C:/Windows/Fonts/malgun.ttf",
              "/usr/share/fonts/truetype/nanum/NanumSquareR.ttf"])
    for n in names:
        if Path(n).exists():
            try:
                return ImageFont.truetype(n, size)
            except OSError:
                pass
    return ImageFont.load_default()


def sheet(items: list[tuple[Path, str, tuple]], title: str,
          dim: bool = False) -> Image.Image:
    """사진 + 한 줄 설명을 격자로 붙인다. dim 이면 흐리게 (뺀 사진)."""
    cols = min(COLS, max(1, len(items)))
    rows = (len(items) + cols - 1) // cols
    cell_w, cell_h = THUMB + PAD, THUMB + CAP_H + PAD
    img = Image.new("RGB", (cols * cell_w + PAD, TITLE_H + rows * cell_h + PAD), BG)
    d = ImageDraw.Draw(img)
    d.text((PAD + 6, 42), title, font=_font(52, True), fill=(240, 244, 250))

    for i, (path, caption, color) in enumerate(items):
        x = PAD + (i % cols) * cell_w
        y = TITLE_H + (i // cols) * cell_h
        try:
            th = images.load_upright(path).convert("RGB")
        except Exception:
            continue
        th.thumbnail((THUMB, THUMB))
        if dim:
            th = ImageEnhance.Brightness(ImageEnhance.Color(th).enhance(0.25)).enhance(0.55)
        box_x = x + (THUMB - th.width) // 2
        img.paste(th, (box_x, y + (THUMB - th.height) // 2))
        d.rectangle([x, y, x + THUMB, y + THUMB], outline=(60, 66, 74), width=2)

        d.text((x + 4, y + THUMB + 10), path.name[:26], font=_font(26), fill=(150, 156, 164))
        d.text((x + 4, y + THUMB + 46), caption[:30], font=_font(30, True), fill=color)
    return img


def build(folder: Path, want: int) -> list[Path]:
    cfg.ensure_dirs()
    photos = images.list_images(folder)
    if not photos:
        raise SystemExit(f"[!] 사진이 없다: {folder}")

    print(f"[i] {folder.name} — 사진 {len(photos)}장을 살펴본다")
    shots = [photo_select.measure(p, folder) for p in photos]
    for s in shots:
        s.score = photo_select.score(s)
    picked = photo_select.choose(photos, want, verbose=True, folder=folder)
    picked_names = {p.path.name for p in picked}

    good = [(s.path,
             f"{s.score:.0f}점 · " + ("얼굴 없음" if not s.faces else f"얼굴 {s.faces}명"),
             (120, 230, 180))
            for s in shots if s.path.name in picked_names]
    bad = [(s.path, photo_select._reason_text(s.rejected) if s.rejected
            else f"{s.score:.0f}점 · 자리 부족", (255, 140, 130) if s.rejected else (170, 175, 182))
           for s in shots if s.path.name not in picked_names]

    out: list[Path] = []
    if good:
        p = cfg.OUT_DIR / f"{folder.name}-뽑힘.jpg"
        sheet(good, f"골라낸 사진 {len(good)}장 — 이게 릴스에 들어갑니다").save(p, quality=92)
        print(f"[+] {p}")
        out.append(p)
    if bad:
        p = cfg.OUT_DIR / f"{folder.name}-제외.jpg"
        sheet(bad, f"빠진 사진 {len(bad)}장 — 이유도 같이", dim=True).save(p, quality=92)
        print(f"[+] {p}")
        out.append(p)
    return out


def open_file(path: Path) -> None:
    """기본 뷰어로 띄운다. 화면 녹화에 담으려면 이게 있어야 한다."""
    try:
        if os.name == "nt":
            os.startfile(str(path))            # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:
        print(f"[i] 자동으로 못 띄웠다 ({e}). 직접 열어라: {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="고른 사진·뺀 사진을 그림으로 보여준다")
    ap.add_argument("folder")
    ap.add_argument("--want", type=int, default=cfg.MAX_PHOTOS, help="고를 장수")
    ap.add_argument("--no-open", action="store_true", help="띄우지 않고 만들기만")
    args = ap.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"[!] 폴더가 없다: {folder}")
        return 2

    made = build(folder, args.want)
    if not args.no_open:
        for p in made:
            open_file(p)
    print("\n[i] 게시하지 않았다. 보여주기만 한 것이다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
