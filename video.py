"""ffmpeg 인코딩: 켄번스 + 크로스페이드 + (선택) 배경음악.

정지 이미지 준비는 images.py(Pillow), 움직임·전환·인코딩은 여기(ffmpeg)가 맡는다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import config as cfg


class FFmpegError(RuntimeError):
    pass


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
        raise FFmpegError(f"ffmpeg 실패 (코드 {proc.returncode}):\n{tail}")


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        [cfg.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float((proc.stdout or "0").strip())
    except ValueError:
        return 0.0


def _kenburns_filter(idx: int, dur: float, out_w: int, out_h: int) -> str:
    """느린 확대. zoompan 은 프레임 단위라 d 를 fps 로 계산한다.

    확대 방향을 사진마다 바꿔서 단조롭지 않게 한다.
    """
    frames = int(dur * cfg.FPS)
    zoom_in = idx % 2 == 0
    if zoom_in:
        z = f"min(1+({cfg.ZOOM_END}-1)*on/{frames},{cfg.ZOOM_END})"
    else:
        z = f"max({cfg.ZOOM_END}-({cfg.ZOOM_END}-1)*on/{frames},1)"
    # 확대 중심을 살짝 움직여 팬 효과를 준다
    x = "iw/2-(iw/zoom/2)"
    y = "ih/2-(ih/zoom/2)" if idx % 4 < 2 else "ih/2-(ih/zoom/2)+ih*0.03*on/%d" % frames
    return (
        f"scale={out_w*2}:{out_h*2},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={out_w}x{out_h}:fps={cfg.FPS},"
        f"setsar=1"
    )


def cut_duration(caption: str) -> float:
    """자막 길이로 컷 노출 시간을 정한다.

    사진 보는 시간 + 글자 읽는 시간. 긴 훅은 길게, 짧은 자막은 짧게.
    너무 길면 지루하고 너무 짧으면 다 못 읽으므로 위아래를 자른다.
    """
    chars = len("".join((caption or "").split()))
    dur = cfg.CUT_BASE_SECONDS + chars * cfg.CUT_SECONDS_PER_CHAR
    return max(cfg.CUT_MIN_SECONDS, min(cfg.CUT_MAX_SECONDS, dur))


def build_reel(frames: list, out_path: Path, captions: list | None = None) -> Path:
    """프레임 목록 → 릴스 mp4 (무음).

    frames 항목은 (사진 PNG, 자막 오버레이 PNG 또는 None) 이다.
    자막 오버레이가 있으면 **켄번스는 사진에만 걸고 자막은 고정으로 얹는다.**
    합쳐진 한 장에 켄번스를 걸면 확대되면서 글자 가장자리가 잘려나간다.

    배경음악은 여기서 넣지 않는다. audio_mix.mix_audio() 로 따로 얹는다.
    """
    if not frames:
        raise ValueError("프레임이 없다")

    # (photo, caption) 형태로 정규화
    pairs = [(f, None) if isinstance(f, (str, Path)) else tuple(f) for f in frames]
    layered = pairs[0][1] is not None
    if layered and cfg.CAPTION_STYLE == "band":
        photo_h, pad_y = cfg.HEIGHT - cfg.BAND_HEIGHT, cfg.BAND_HEIGHT
    else:
        photo_h, pad_y = cfg.HEIGHT, 0

    # 컷마다 노출 시간이 다르다 (자막 길이 기준)
    if captions:
        durs = [cut_duration(c) for c in captions]
    else:
        durs = [float(cfg.SECONDS_PER_PHOTO)] * len(pairs)
    xf = min(cfg.CROSSFADE, min(durs) / 2)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    args: list[str] = [cfg.FFMPEG, "-y"]
    for (photo, _), d in zip(pairs, durs):
        args += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(photo)]
    if layered:
        for (_, cap), d in zip(pairs, durs):
            args += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(cap)]
    # 비디오만 있는 mp4 는 플레이어·미리보기에서 재생을 거부하는 경우가 많고
    # 인스타도 오디오 트랙이 있는 쪽을 선호한다. 무음이어도 트랙은 넣는다.
    args += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]

    n = len(pairs)
    parts: list[str] = []
    for i in range(n):
        kb = _kenburns_filter(i, durs[i], cfg.WIDTH, photo_h)
        if layered:
            # 사진만 움직인다 → 위쪽에 띠 자리를 비우고 → 자막을 고정으로 얹는다
            parts.append(
                f"[{i}:v]{kb},pad={cfg.WIDTH}:{cfg.HEIGHT}:0:{pad_y}:black[p{i}]"
            )
            parts.append(f"[{n+i}:v]format=rgba[c{i}]")
            parts.append(f"[p{i}][c{i}]overlay=0:0:format=auto[v{i}]")
        else:
            parts.append(f"[{i}:v]{kb}[v{i}]")

    # 크로스페이드로 이어붙인다. offset 은 누적 길이에서 전환시간을 뺀 지점.
    if n == 1:
        parts.append("[v0]null[vout]")
        total = durs[0]
    else:
        prev = "[v0]"
        total = durs[0]
        for i in range(1, n):
            offset = total - xf
            label = "[vout]" if i == n - 1 else f"[x{i}]"
            parts.append(
                f"{prev}[v{i}]xfade=transition=fade:duration={xf:.3f}:offset={offset:.3f}{label}"
            )
            prev = label
            total = total + durs[i] - xf

    filter_complex = ";".join(parts)
    maps = ["-map", "[vout]"]

    a_idx = n * 2 if layered else n  # anullsrc 는 이미지 입력들 뒤에 온다
    # 인스타 권장: AAC 48kHz. 44.1kHz 로 올리면 인스타가 리샘플하면서 한 번 더 손실난다.
    maps += ["-map", f"{a_idx}:a", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest"]

    args += [
        "-filter_complex", filter_complex,
        *maps,
        "-t", f"{total:.3f}",
        "-c:v", "libx264",
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-r", str(cfg.FPS),
        "-preset", "medium",
        # 인스타는 업로드본을 다시 압축한다. 원본 비트레이트가 낮으면 그만큼
        # 더 깎이므로 권장치(5000~10000kbps)를 목표로 잡는다.
        #
        # CRF 와 -b:v 를 같이 주면 x264 가 CRF 를 우선해서 목표 비트레이트를
        # 무시한다. 정지 사진은 압축이 잘 돼 CRF 만으로는 3000~4000kbps 대에
        # 머무르므로, 여기서는 CRF 를 빼고 평균 비트레이트 방식으로 간다.
        "-b:v", f"{cfg.VIDEO_BITRATE_K}k",
        "-maxrate", f"{int(cfg.VIDEO_BITRATE_K * 1.5)}k",
        "-bufsize", f"{cfg.VIDEO_BITRATE_K * 2}k",
        "-movflags", "+faststart",
        str(out_path),
    ]

    _run(args)
    return out_path
