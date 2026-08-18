"""대본 한 장 → 카드형 릴스. **사진이 없어도 만든다.**

수업 사진으로 만드는 릴스(`make_reel.py`)와 쓰임이 다르다. 이건 정보·후기·
공지처럼 **할 말이 있을 때** 쓴다. 화면을 전부 같은 규격으로 그리므로
비율이 튀지 않고, 글자가 크게 들어가 무음으로도 읽힌다.

    py make_cards.py 대본.txt                 # 카드 그리고 영상까지
    py make_cards.py 대본.txt --sec 1.8       # 카드당 시간
    py make_cards.py 대본.txt --no-video      # 카드(png)만

## 대본 형식 — `---` 로 카드를 나눈다

    kicker: 왜 만들었냐면          작은 라벨 (선택)
    title: 프로그램은 / 만들었는데  큰 제목. `/` 로 줄바꿈
    note: 설정이 복잡해서 / 남한테 알려줄 수가 없었어요
    ---
    title: 숫자로 보면
    big: 4,121줄 = 원고 / 98쪽 = A4      숫자 = 설명
    ---
    title: 제일 오래 막힌 곳
    term: 개발자 역할 권한 부족 / 원인이 안 나와요     검은 창 (오류 느낌)
    note: 이 오류 하나에 이틀을 썼어요

첫 카드가 **훅**이고 마지막 카드가 **CTA** 다. 그 둘은 더 오래 머문다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import approve
import config as cfg

W, H = 1080, 1920
BG = (13, 17, 23)
PANEL = (22, 27, 34)
LINE = (48, 54, 61)
TEXT = (230, 237, 243)
DIM = (139, 148, 158)
ACCENT = (86, 211, 173)
WARN = (255, 123, 114)

BOLD = ["C:/Windows/Fonts/malgunbd.ttf",
        "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf"]
REGULAR = ["C:/Windows/Fonts/malgun.ttf",
           "/usr/share/fonts/truetype/nanum/NanumSquareR.ttf"]
MONO = ["C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicCoding.ttf"]

HANDLE = "@ai.co.lab"


def font(kind: list[str], size: int):
    for p in kind:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def parse(path: Path) -> list[dict]:
    """대본을 카드 목록으로. `---` 가 카드 구분, `키: 값` 이 한 줄."""
    cards: list[dict] = []
    cur: dict = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        if line.startswith("---"):
            if cur:
                cards.append(cur)
            cur = {}
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key and val:
            cur[key] = [v.strip() for v in val.split("/") if v.strip()]
    if cur:
        cards.append(cur)
    return cards


def draw_card(card: dict, idx: int, total: int) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = 420

    if "kicker" in card:
        d.text((90, y), card["kicker"][0], font=font(REGULAR, 46), fill=ACCENT)
        y += 96

    for line in card.get("title", []):
        d.text((90, y), line, font=font(BOLD, 92), fill=TEXT)
        y += 116
    y += 40

    if "big" in card:
        for item in card["big"]:
            num, _, label = item.partition("=")
            d.text((90, y), num.strip(), font=font(BOLD, 128), fill=ACCENT)
            y += 148
            if label.strip():
                d.text((90, y), label.strip(), font=font(REGULAR, 46), fill=DIM)
                y += 76
            y += 24

    if "term" in card:
        rows = card["term"]
        pad, lh = 40, 62
        h = pad * 2 + lh * len(rows)
        d.rounded_rectangle([70, y, W - 70, y + h], 18, fill=PANEL,
                            outline=LINE, width=2)
        for i, row in enumerate(rows):
            d.text((110, y + pad + i * lh), row, font=font(MONO, 40), fill=WARN)
        y += h + 50

    for line in card.get("note", []):
        d.text((90, y), line, font=font(REGULAR, 54), fill=DIM)
        y += 76

    # 아래쪽 — 계정과 진행 막대. 비워두면 허전하고, 인스타 UI 가 가리는 자리다.
    d.text((90, 1560), HANDLE, font=font(REGULAR, 44), fill=DIM)
    d.rounded_rectangle([90, 1650, W - 90, 1658], 4, fill=LINE)
    d.rounded_rectangle([90, 1650, 90 + int((W - 180) * (idx + 1) / total), 1658],
                        4, fill=ACCENT)
    return img


def build(script: Path, sec: float, hold: float, make_video: bool) -> Path | None:
    cards = parse(script)
    if len(cards) < 2:
        raise SystemExit(f"[!] 카드가 {len(cards)}장뿐이다. `---` 로 나눠 2장 이상 써라.")
    cfg.ensure_dirs()

    name = script.stem
    out_dir = cfg.OUT_DIR / f"cards-{name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.png"):
        f.unlink()

    for i, card in enumerate(cards):
        p = out_dir / f"{i:02d}.png"
        draw_card(card, i, len(cards)).save(p)
        head = (card.get("title") or card.get("note") or ["(제목 없음)"])[0]
        print(f"  {i+1:2}/{len(cards)}  {head[:28]}")

    total = hold * 2 + sec * (len(cards) - 2)
    print(f"[i] 카드 {len(cards)}장 / 약 {total:.1f}초 → {out_dir}")
    if not make_video:
        return None

    # 영상은 make_fast.py 가 만든다. 같은 일을 두 번 짜지 않는다.
    subprocess.run([sys.executable, str(Path(__file__).parent / "make_fast.py"),
                    str(out_dir), "--sec", str(sec), "--hold", str(hold)],
                   check=True)
    return cfg.OUT_DIR / f"{out_dir.name}-fast.mp4"


def main() -> int:
    ap = argparse.ArgumentParser(description="대본 → 카드형 릴스")
    ap.add_argument("script", help="대본 파일 (.txt/.md)")
    ap.add_argument("--sec", type=float, default=1.6, help="카드당 초")
    ap.add_argument("--hold", type=float, default=2.4, help="첫 장·끝 장 초")
    ap.add_argument("--no-video", action="store_true", help="카드만 만들고 끝")
    args = ap.parse_args()

    script = Path(args.script).resolve()
    if not script.exists():
        print(f"[!] 대본이 없다: {script}")
        return 2

    out = build(script, args.sec, args.hold, not args.no_video)
    if out:
        print(f"[+] {out}")
        print("[i] 확인:  py approve.py --show \"cards-" + script.stem + "\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
