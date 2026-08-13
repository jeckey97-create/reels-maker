"""사진 목록 읽기 · 9:16 크롭 · 자막 얹기 (Pillow)."""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

import config as cfg
import face_guard


def list_images(folder: Path) -> list[Path]:
    """폴더의 이미지를 파일명 순으로 반환. 하위 폴더는 보지 않는다.

    `_` 로 시작하는 파일은 건너뛴다. 우리가 만들어 넣은 _미리보기.jpg 를
    다음 실행에서 원본 사진으로 다시 집어드는 걸 막기 위해서다.
    """
    if not folder.exists():
        return []
    return sorted(
        (p for p in folder.iterdir()
         if p.is_file()
         and p.suffix.lower() in cfg.IMAGE_EXTS
         and not p.name.startswith("_")),
        key=lambda p: p.name,
    )


def folder_fingerprint(folder: Path) -> str:
    """폴더의 이미지 구성이 바뀌었는지 판단할 지문.

    make_reel.py 와 watch_folder.py 가 같은 값을 써야 승인 대기 목록에서
    같은 폴더를 같은 항목으로 인식한다.
    """
    return "|".join(f"{p.name}:{p.stat().st_size}" for p in list_images(folder))


def load_upright(path: Path) -> Image.Image:
    """EXIF 회전을 적용해서 연다. 폰 사진은 이게 없으면 눕는다."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def crop_to_feed(img: Image.Image) -> Image.Image:
    """피드용 4:5 로 중앙 크롭. 위쪽을 조금 더 남긴다 (사람 얼굴이 위에 온다)."""
    return ImageOps.fit(
        img, (cfg.FEED_WIDTH, cfg.FEED_HEIGHT), method=Image.LANCZOS,
        centering=(0.5, 0.4),
    )


def prepare_feed_photo(src: Path, dst: Path,
                       blur_boxes: list | None = None,
                       crop_box: tuple | None = None) -> Path:
    """사진 1장 → 피드용 JPG.

    릴스와 달리 자막을 태우지 않는다. 피드는 글이 사진 아래에 따로 붙어서
    사진 위에 글자를 얹으면 오히려 지저분해진다.

    초상권 처리(잘라내기·모자이크)는 릴스와 똑같이 적용한다.
    """
    img = load_upright(src)
    if crop_box:
        img = img.crop(crop_box)
    if blur_boxes:
        img = face_guard.blur_faces(img, blur_boxes)
    dst.parent.mkdir(parents=True, exist_ok=True)
    crop_to_feed(img).convert("RGB").save(dst, "JPEG", quality=cfg.FEED_QUALITY)
    return dst


def crop_to_reel(img: Image.Image) -> Image.Image:
    """9:16 으로 꽉 차게 중앙 크롭한다 (레터박스 없음)."""
    return ImageOps.fit(
        img, (cfg.WIDTH, cfg.HEIGHT), method=Image.LANCZOS, centering=(0.5, 0.4)
    )


# 맑은 고딕에 글리프가 없는 구간. 그대로 그리면 □ 로 나온다.
_EMOJI_RANGES = [
    (0x1F000, 0x1FAFF),   # 그림문자 전반 (😃 🤖 등)
    (0x2600, 0x27BF),     # 기타 기호·딩뱃 (☀ ✂ ➜)
    (0x2B00, 0x2BFF),     # 화살표·도형
    (0xFE00, 0xFE0F),     # 변형 선택자
    (0x1F1E6, 0x1F1FF),   # 국기
    (0x200D, 0x200D),     # ZWJ (이모지 결합용)
]


def _drop_unsupported(text: str, font: ImageFont.FreeTypeFont) -> str:
    """폰트에 글리프가 없는 문자를 뺀다.

    맑은 고딕에는 이모지가 없어서 그대로 그리면 □ 로 나온다. 영상 자막에서만
    빼고, 인스타 글 본문의 이모지는 건드리지 않는다.
    """
    out = []
    for ch in text:
        if ch in ("\n", " "):
            out.append(ch)
            continue
        if any(lo <= ord(ch) <= hi for lo, hi in _EMOJI_RANGES):
            continue
        out.append(ch)
    # 이모지를 빼면서 생긴 이중 공백·꼬리 공백을 정리한다
    return " ".join("".join(out).split())


def _wrap(text: str, chars: int | None = None) -> list[str]:
    """한글은 단어 경계가 애매해서 글자 수로 자른다."""
    width = chars or cfg.CAPTION_MAX_CHARS_PER_LINE
    lines: list[str] = []
    for para in text.splitlines():
        para = para.strip()
        if not para:
            continue
        lines.extend(textwrap.wrap(para, width=width) or [para])
    return lines


def draw_caption(img: Image.Image, text: str) -> Image.Image:
    """하단에 반투명 검은 박스 + 흰 글씨. 자동 줄바꿈."""
    if not text.strip():
        return img

    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.truetype(str(cfg.FONT_PATH), cfg.FONT_SIZE)

    lines = _wrap(_drop_unsupported(text, font))
    if not lines:
        return img.convert("RGB")
    line_h = int(cfg.FONT_SIZE * 1.35)
    block_h = line_h * len(lines)
    pad = 32

    widths = [draw.textlength(ln, font=font) for ln in lines]
    box_w = int(max(widths)) + pad * 2
    box_w = min(box_w, cfg.WIDTH - 60)
    box_x0 = (cfg.WIDTH - box_w) // 2
    box_y1 = cfg.HEIGHT - cfg.CAPTION_MARGIN_BOTTOM
    box_y0 = box_y1 - block_h - pad * 2

    draw.rounded_rectangle(
        [box_x0, box_y0, box_x0 + box_w, box_y1],
        radius=24,
        fill=(0, 0, 0, cfg.CAPTION_BOX_ALPHA),
    )

    y = box_y0 + pad
    for ln, w in zip(lines, widths):
        draw.text(((cfg.WIDTH - w) / 2, y), ln, font=font, fill=(255, 255, 255, 255))
        y += line_h

    return Image.alpha_composite(img, overlay).convert("RGB")


def photo_only(img: Image.Image) -> Image.Image:
    """자막 없이 사진만 크롭한다. box 는 화면 전체, band 는 띠 아래 크기.

    켄번스는 이 사진에만 걸린다. 자막까지 같이 확대하면 글자가 잘려나간다.
    """
    photo_h = cfg.HEIGHT if cfg.CAPTION_STYLE != "band" else cfg.HEIGHT - cfg.BAND_HEIGHT
    return ImageOps.fit(
        img, (cfg.WIDTH, photo_h), method=Image.LANCZOS, centering=(0.5, 0.4)
    )


# 이어진 같은 기호는 한 덩어리로 본다. "^^" 가 "중^" / "^" 로 쪼개지면 흉하다.
_STICKY = set("^~!?.ㅋㅎ…")


def _tokens(para: str) -> list[str]:
    """줄바꿈 단위. 이어진 이모티콘 기호는 묶어서 하나로 취급한다."""
    out: list[str] = []
    i = 0
    while i < len(para):
        ch = para[i]
        if ch in _STICKY:
            j = i
            while j < len(para) and para[j] in _STICKY:
                j += 1
            out.append(para[i:j])
            i = j
        else:
            out.append(ch)
            i += 1
    return out


def _wrap_px(text: str, font, max_w: float) -> list[str]:
    """실제 픽셀 폭으로 줄바꿈한다. 글자 수로 자르면 폰트 크기에 따라 어긋난다."""
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    out: list[str] = []
    for para in text.splitlines():
        para = para.strip()
        if not para:
            continue
        line = ""
        for tok in _tokens(para):
            trial = line + tok
            if probe.textlength(trial, font=font) <= max_w or not line:
                line = trial
            else:
                out.append(line.strip())
                line = "" if tok == " " else tok
        if line.strip():
            out.append(line.strip())

    # 마지막 줄이 이모티콘만 남았으면 앞줄에 붙인다.
    # "…중" / "^^" 처럼 기호만 한 줄 차지하면 흉하다. 박스가 조금 넓어지는 건
    # 감수한다 (화면 폭 안에서만).
    hard_max = cfg.WIDTH - 80
    if len(out) >= 2 and all(c in _STICKY for c in out[-1]):
        merged = out[-2] + out[-1]
        if probe.textlength(merged, font=font) <= hard_max:
            out = out[:-2] + [merged]
    return out


def _fit_lines(text: str, limit_h: int):
    """자막을 최대 CAPTION_MAX_LINES 줄에 맞춘다. (font, lines, line_h) 반환.

    **글자 크기는 절대 줄이지 않는다.** 크기가 들쭉날쭉하면 컷마다 자막이
    커졌다 작아졌다 해서 보기 나쁘다. 대신 넘치는 글자를 잘라낸다.

    96px 기준 한 줄에 한글 9자, 두 줄이면 18자가 한계다. 잘림이 생기면
    caption_budget_exceeded 가 True 로 돌아오므로 호출부에서 경고할 수 있다.
    """
    max_w = cfg.WIDTH * cfg.CAPTION_MAX_WIDTH_RATIO
    font = ImageFont.truetype(str(cfg.FONT_PATH), cfg.FONT_SIZE)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    line_h = int(cfg.FONT_SIZE * 1.35)

    # 줄바꿈은 무시하고 통째로 감는다. 96px 에서는 한 줄에 9자뿐이라
    # 의미 단위로 끊어봐야 어차피 다시 감기기 때문이다.
    flat = " ".join(_drop_unsupported(text, font).split())
    lines = _wrap_px(flat, font, max_w)

    over = len(lines) > cfg.CAPTION_MAX_LINES
    if over:
        lines = lines[:cfg.CAPTION_MAX_LINES]
        last = lines[-1]
        while last and probe.textlength(last + "…", font=font) > max_w:
            last = last[:-1]
        lines[-1] = last + "…"

    _fit_lines.exceeded = over
    return font, lines, line_h


_fit_lines.exceeded = False


def caption_char_budget() -> int:
    """현재 글자 크기에서 자막에 들어가는 한글 글자 수 (대략)."""
    font = ImageFont.truetype(str(cfg.FONT_PATH), cfg.FONT_SIZE)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    max_w = cfg.WIDTH * cfg.CAPTION_MAX_WIDTH_RATIO
    n = 0
    while probe.textlength("가" * (n + 1), font=font) <= max_w:
        n += 1
    return n * cfg.CAPTION_MAX_LINES


def caption_layer(text: str) -> Image.Image:
    """자막 오버레이 (1080x1920 RGBA). 영상에서 **움직이지 않는다.**

    사진만 켄번스로 움직이고 자막은 그 위에 고정으로 얹힌다. 합쳐서 켄번스를
    걸면 글자가 확대되면서 가장자리가 잘려나간다.

    box  — 사진 위 반투명 둥근 박스. 인스타 UI 를 피해 위쪽 20% 지점에 놓는다.
    band — 상단 검은 띠.
    """
    if cfg.CAPTION_STYLE != "band":
        return _caption_layer_box(text)
    return _caption_layer_band(text)


def _caption_layer_box(text: str) -> Image.Image:
    """사진 위 반투명 박스. 배경이 밝아도 읽히도록 테두리를 같이 그린다."""
    canvas = Image.new("RGBA", (cfg.WIDTH, cfg.HEIGHT), (0, 0, 0, 0))
    if not text.strip():
        return canvas

    draw = ImageDraw.Draw(canvas)
    top = int(cfg.HEIGHT * cfg.CAPTION_TOP_RATIO)
    # 인스타 하단 UI 가 가리는 구간 전까지만 쓴다
    limit_h = int(cfg.HEIGHT * 0.75) - top
    font, lines, line_h = _fit_lines(text, limit_h)
    if not lines:
        return canvas

    pad = 30
    widths = [draw.textlength(ln, font=font) for ln in lines]
    box_w = min(int(max(widths)) + pad * 2, cfg.WIDTH - 60)
    box_h = line_h * len(lines) + pad * 2
    x0 = (cfg.WIDTH - box_w) // 2
    draw.rounded_rectangle([x0, top, x0 + box_w, top + box_h],
                           radius=28, fill=(0, 0, 0, cfg.CAPTION_BOX_ALPHA))

    y = top + pad
    for ln, w in zip(lines, widths):
        x = (cfg.WIDTH - w) / 2
        # 얇은 검은 테두리를 둘러 밝은 배경에서도 글자가 뜨게 한다
        draw.text((x, y), ln, font=font, fill=(255, 255, 255, 255),
                  stroke_width=3, stroke_fill=(0, 0, 0, 210))
        y += line_h
    return canvas


def _caption_layer_band(text: str) -> Image.Image:
    band_h = cfg.BAND_HEIGHT
    canvas = Image.new("RGBA", (cfg.WIDTH, cfg.HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, cfg.WIDTH, band_h], fill=(0, 0, 0, 255))

    if not text.strip():
        return canvas


    # 띠 안에 들어갈 때까지 글자를 줄인다. 안 그러면 긴 자막이 사진 위로
    # 흘러나온다. 대부분은 기본 크기로 들어가고, 넘칠 때만 작아진다.
    bottom_margin = 40
    size = cfg.FONT_SIZE
    while True:
        font = ImageFont.truetype(str(cfg.FONT_PATH), size)
        chars = max(6, int(cfg.CAPTION_MAX_CHARS_PER_LINE * cfg.FONT_SIZE / size))
        lines = _wrap(_drop_unsupported(text, font), chars)
        line_h = int(size * 1.35)
        if cfg.BAND_TEXT_TOP + line_h * len(lines) + bottom_margin <= band_h:
            break
        if size <= 56:
            break
        size -= 8

    if not lines:
        return canvas

    # 항상 같은 높이에서 시작한다. 중앙 정렬하면 줄 수에 따라 자막이 위아래로
    # 튀어서 컷이 넘어갈 때 거슬린다.
    y = cfg.BAND_TEXT_TOP
    for ln in lines:
        w = draw.textlength(ln, font=font)
        draw.text(((cfg.WIDTH - w) / 2, y), ln, font=font, fill=(255, 255, 255, 255))
        y += line_h

    return canvas


def prepare_frame(src: Path, caption: str, dst: Path,
                  blur_boxes: list | None = None,
                  crop_box: tuple | None = None) -> tuple[Path, Path | None]:
    """사진 1장 → (사진 PNG, 자막 오버레이 PNG).

    band 스타일에서는 둘을 나눠 돌려준다. 켄번스는 사진에만 걸고 자막은
    고정으로 얹기 위해서다. box 스타일은 예전처럼 한 장으로 합친다.

    crop_box 가 있으면 먼저 잘라낸다 (식별 얼굴 제거용).
    blur_boxes 가 있으면 그 영역(얼굴)을 모자이크 처리한다.
    """
    img = load_upright(src)
    if crop_box:
        img = img.crop(crop_box)
    if blur_boxes:
        img = face_guard.blur_faces(img, blur_boxes)

    dst.parent.mkdir(parents=True, exist_ok=True)
    photo_only(img).save(dst, "PNG")
    cap_path = dst.with_name(dst.stem + "-cap.png")
    caption_layer(caption).save(cap_path, "PNG")
    return dst, cap_path
