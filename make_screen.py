"""작업 화면 릴스 — 코드가 쳐지고, 문서가 써지고, 캡처가 꽂히는 영상.

"AI 가 이런 걸 만들고 있다" 를 보여줄 때 쓴다. 사진도 녹화본도 없이
대본 하나로 만든다.

    py make_screen.py 대본/작업화면.txt

**실제 화면 녹화가 아니라 재현이다.** 코드·문장은 진짜를 넣되, 타이핑되는
모습은 그린 것이다. 생동감이 필요하면 진짜 녹화를 하고 `make_clip.py` 로
잘라라. 둘을 이어 붙이면 제일 좋다 (앞은 녹화, 뒤는 정리 화면).

## 대본 형식

    title: reels-maker — photo_select.py     위쪽 터미널 창 제목
    doc: 전자책 원고 — 01-계정-준비.md        아래쪽 문서 창 제목
    shot: ebook/images/캡처-32.png            문서에 꽂을 그림 (선택)

    --- code ---
    # 여기에 화면에 쳐질 코드
    if not shot.consented:

    --- doc ---
    1.3 인스타그램과 페이스북을 연결하기
    (첫 줄이 문서 제목으로 굵게 나온다)

    --- build ---
    > py build.py
    [+] 만들었다

    --- caption ---
    코드를 씁니다
    그걸 책으로 옮깁니다
    화면 캡처를 넣습니다
    한 권으로 묶습니다
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import approve
import config as cfg

W, H = 1080, 1920
FPS = 15
BG = (13, 17, 23)
TERM_BG = (22, 27, 34)
PAPER = (250, 250, 248)
LINE = (48, 54, 61)
TEXT = (230, 237, 243)
DIM = (139, 148, 158)
ACCENT = (86, 211, 173)
KEYWORD = (255, 166, 87)
COMMENT = (110, 168, 254)

BOLD = ["C:/Windows/Fonts/malgunbd.ttf",
        "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf"]
REGULAR = ["C:/Windows/Fonts/malgun.ttf",
           "/usr/share/fonts/truetype/nanum/NanumSquareR.ttf"]
MONO = ["C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicCoding.ttf"]

DEFAULT_CAPTIONS = ["코드를 씁니다", "글로 옮깁니다", "화면을 넣습니다", "완성"]


def font(kind: list[str], size: int):
    for p in kind:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def parse(path: Path) -> dict:
    """대본 → {title, doc, shot, code[], doc_lines[], build[], captions[]}"""
    out: dict = {"title": "터미널", "doc": "문서", "shot": None,
                 "code": [], "doc_lines": [], "build": [], "captions": []}
    section = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        st = line.strip()
        if st.startswith("---") and st.endswith("---"):
            section = st.strip("- ").strip().lower()
            continue
        if section is None:
            if st.startswith("#") or not st or ":" not in st:
                continue
            k, v = st.split(":", 1)
            k, v = k.strip().lower(), v.strip()
            if k in ("title", "doc"):
                out[k] = v
            elif k == "shot":
                out["shot"] = v
            continue
        if section == "code":
            out["code"].append(line)
        elif section == "doc":
            out["doc_lines"].append(line)
        elif section == "build":
            out["build"].append(line)
        elif section == "caption" and st:
            out["captions"].append(st)
    while out["code"] and not out["code"][-1].strip():
        out["code"].pop()
    while out["doc_lines"] and not out["doc_lines"][-1].strip():
        out["doc_lines"].pop()
    return out


def _color_for(line: str):
    s = line.strip()
    if s.startswith("#"):
        return COMMENT
    if '"' in s or "'" in s:
        return KEYWORD
    return TEXT


def chrome(d, box, title, fill, ink):
    x0, y0, x1, y1 = box
    d.rounded_rectangle([x0, y0, x1, y1], 20, fill=fill, outline=LINE, width=2)
    d.rounded_rectangle([x0, y0, x1, y0 + 66], 20, fill=(38, 43, 52))
    d.rectangle([x0, y0 + 46, x1, y0 + 66], fill=(38, 43, 52))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([x0 + 26 + i * 34, y0 + 24, x0 + 42 + i * 34, y0 + 40], fill=c)
    d.text((x0 + 150, y0 + 16), title[:34], font=font(REGULAR, 34), fill=ink)


def typed(lines: list[str], chars: int) -> list[str]:
    out, left = [], chars
    for text in lines:
        if left <= 0:
            break
        out.append(text[:left])
        left -= max(len(text), 1)
    return out


def draw(sc: dict, code_n: int, doc_n: int, shot_y: int | None,
         build_n: int, caption: str) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    chrome(d, (50, 150, W - 50, 900), sc["title"], TERM_BG, DIM)
    f = font(MONO, 34)
    y = 240
    for line in typed(sc["code"], code_n)[:12]:
        d.text((90, y), line, font=f, fill=_color_for(line))
        y += 52

    chrome(d, (50, 960, W - 50, 1740), sc["doc"], PAPER, (60, 60, 60))
    y = 1060
    for i, line in enumerate(typed(sc["doc_lines"], doc_n)[:8]):
        if i == 0:
            d.text((90, y), line, font=font(BOLD, 44), fill=(32, 34, 38))
            y += 76
        else:
            d.text((90, y), line, font=font(REGULAR, 36), fill=(70, 72, 78))
            y += 56

    if shot_y is not None and sc.get("shot_img"):
        shot = sc["shot_img"]
        room = 1740 - shot_y - 30
        sc_ = min((W - 420) / shot.width, room / shot.height)
        th = shot.resize((int(shot.width * sc_), int(shot.height * sc_)),
                         Image.LANCZOS)
        img.paste(th, ((W - th.width) // 2, shot_y))
        d.rectangle([(W - th.width) // 2 - 2, shot_y - 2,
                     (W + th.width) // 2 + 2, shot_y + th.height + 2],
                    outline=(190, 190, 190), width=3)

    if build_n and sc["build"]:
        d.rounded_rectangle([70, 620, W - 70, 880], 16, fill=(15, 19, 25),
                            outline=ACCENT, width=2)
        for i, line in enumerate(sc["build"][:build_n][:4]):
            color = ACCENT if line.strip().startswith((">", "$")) else TEXT
            d.text((110, 650 + i * 54), line[:40], font=font(MONO, 34), fill=color)

    if caption:
        fc = font(BOLD, 58)
        x = (W - d.textlength(caption, font=fc)) / 2
        for dx in (-3, 0, 3):
            for dy in (-3, 0, 3):
                if dx or dy:
                    d.text((x + dx, 1800 + dy), caption, font=fc, fill=(0, 0, 0))
        d.text((x, 1800), caption, font=fc, fill=(255, 255, 255))
    return img


def build(script: Path) -> Path:
    sc = parse(script)
    if not sc["code"] and not sc["doc_lines"]:
        raise SystemExit("[!] 대본에 --- code --- 나 --- doc --- 이 없다.")

    if sc["shot"]:
        p = (script.parent / sc["shot"]).resolve()
        if not p.exists():
            p = (Path(__file__).parent / sc["shot"]).resolve()
        sc["shot_img"] = Image.open(p).convert("RGB") if p.exists() else None
        if sc["shot_img"] is None:
            print(f"[!] 그림을 못 찾았다: {sc['shot']} — 없이 만든다")

    caps = sc["captions"] or DEFAULT_CAPTIONS
    while len(caps) < 4:
        caps.append(caps[-1])

    cfg.ensure_dirs()
    work = cfg.WORK_DIR / f"screen-{script.stem}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    code_total = sum(len(c) or 1 for c in sc["code"])
    doc_total = sum(len(c) or 1 for c in sc["doc_lines"])
    n = 0

    def emit(img, frames):
        nonlocal n
        for _ in range(frames):
            img.save(work / f"{n:05d}.jpg", quality=92)
            n += 1

    steps = 60
    for i in range(steps + 1):
        emit(draw(sc, int(code_total * i / steps), 0, None, 0, caps[0]), 1)
    emit(draw(sc, code_total, 0, None, 0, caps[0]), 15)

    steps = 70
    for i in range(steps + 1):
        emit(draw(sc, code_total, int(doc_total * i / steps), None, 0, caps[1]), 1)
    emit(draw(sc, code_total, doc_total, None, 0, caps[1]), 12)

    if sc.get("shot_img"):
        for i in range(20):
            emit(draw(sc, code_total, doc_total,
                      1320 + int(120 * i / 19), 0, caps[2]), 1)
        emit(draw(sc, code_total, doc_total, 1440, 0, caps[2]), 12)
    shot_y = 1440 if sc.get("shot_img") else None

    for r in range(1, len(sc["build"][:4]) + 1):
        emit(draw(sc, code_total, doc_total, shot_y, r, caps[3]), 12)
    emit(draw(sc, code_total, doc_total, shot_y, len(sc["build"][:4]), caps[3]), 30)

    out = cfg.OUT_DIR / f"{script.stem}-화면.mp4"
    subprocess.run([
        cfg.FFMPEG, "-y", "-framerate", str(FPS), "-i", str(work / "%05d.jpg"),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-shortest", "-vf", "fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium",
        "-b:v", f"{cfg.VIDEO_BITRATE_K}k", "-c:a", "aac", str(out),
    ], check=True, capture_output=True)
    print(f"[+] 완성: {out}  ({n / FPS:.1f}초)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="작업 화면 릴스 (재현)")
    ap.add_argument("script")
    args = ap.parse_args()
    script = Path(args.script).resolve()
    if not script.exists():
        print(f"[!] 대본이 없다: {script}")
        return 2
    out = build(script)
    approve.register_pending(script.parent / script.stem, out)
    print(f"[i] 승인 대기에 넣었다. 확인: py approve.py --show \"{script.stem}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
