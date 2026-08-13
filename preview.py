"""릴스 미리보기 이미지 만들기.

휴대폰에서 승인할 때 영상이 재생 안 되는 환경이 있어서, 영상 대신 볼 수 있는
정지 이미지를 만든다. 컷마다 한 프레임씩 뽑아 가로로 이어붙인 컨택트 시트다.

이미지는 어디서든 보이니까 승인 판단(어떤 사진이 들어갔나, 자막이 맞나,
올리면 안 될 얼굴이 있나)은 이걸로 충분히 할 수 있다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

import config as cfg


def _grab(video: Path, at: float, dst: Path) -> Path | None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [cfg.FFMPEG, "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", str(video),
         "-frames:v", "1", str(dst)],
        capture_output=True, text=True,
    )
    return dst if proc.returncode == 0 and dst.exists() else None


def contact_sheet(video: Path, dst: Path | None = None, thumb_w: int = 320,
                  durations: list | None = None) -> Path | None:
    """영상에서 컷마다 한 장씩 뽑아 가로로 이어붙인 이미지를 만든다.

    durations 를 주면 그 컷 경계를 그대로 쓴다. 컷 길이가 자막에 따라 달라지므로
    이걸 안 주면 전환 구간을 집어서 두 사진이 겹친 프레임이 나온다.
    """
    if not video.exists():
        return None

    from video import probe_duration

    dur = probe_duration(video)
    if dur <= 0:
        return None

    work = cfg.WORK_DIR / "preview" / video.stem
    times: list[float] = []
    if durations:
        # 각 컷의 한가운데. 전환(크로스페이드) 구간을 피한다.
        start = 0.0
        for d in durations:
            times.append(min(dur - 0.15, start + d / 2))
            start += d - cfg.CROSSFADE
    else:
        n = min(max(1, round(dur / 3)), cfg.MAX_PHOTOS)
        times = [min(dur - 0.15, (i + 0.4) * (dur / n)) for i in range(n)]

    frames: list[Image.Image] = []
    for i, at in enumerate(times):
        got = _grab(video, at, work / f"f{i}.png")
        if got:
            frames.append(Image.open(got))
    if not frames:
        return None

    h = int(cfg.HEIGHT / cfg.WIDTH * thumb_w)
    frames = [f.resize((thumb_w, h), Image.LANCZOS) for f in frames]

    gap = 10
    sheet = Image.new("RGB", (thumb_w * len(frames) + gap * (len(frames) - 1), h), (255, 255, 255))
    for i, f in enumerate(frames):
        sheet.paste(f, (i * (thumb_w + gap), 0))

    dst = dst or video.with_name(video.stem + "-preview.jpg")
    sheet.save(dst, "JPEG", quality=85)
    return dst
