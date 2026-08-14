"""배경음악을 직접 합성한다. 밝고 가사 없는 곡을 만든다.

인스타 인기 음원은 API 로 못 쓰고, 무료 음원 사이트는 라이선스 조건(출처 표기,
상업적 사용 제한)을 하나하나 확인해야 한다. 그냥 만들면 그 걱정이 사라진다.
여기서 나온 파일은 저작권자가 없으니 수업 홍보에 그대로 써도 된다.

사용법:
    py make_music.py                          # assets/music/background.mp3
    py make_music.py --seconds 45
    py make_music.py --bpm 124 --key A       # 더 빠르고 다른 조로
    py make_music.py --out assets/music/밝은곡2.mp3

ffmpeg 가 있어야 mp3 로 저장된다. 없으면 wav 로 저장한다 (프로그램은 wav 도 읽는다).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:
    print("[!] numpy 가 필요하다:  py -m pip install numpy")
    sys.exit(1)


SR = 44100

# 밝게 들리는 진행. I - V - vi - IV.
# 도수로 적어두면 --key 로 조를 바꿔도 그대로 따라온다.
PROGRESSION = [
    (0, "maj"),    # I
    (7, "maj"),    # V
    (9, "min"),    # vi
    (5, "maj"),    # IV
]

CHORD_TONES = {"maj": (0, 4, 7), "min": (0, 3, 7)}

# 4마디 멜로디. 마디마다 4분음표 4개, None 은 쉼표.
# 으뜸음(도)에서 몇 반음 위인지로 적는다.
MELODY = [
    [16, 14, 12, 14],
    [11, 14, 19, None],
    [9, 12, 16, 14],
    [12, 9, 5, 7],
]

KEYS = {"C": 60, "C#": 61, "D": 62, "D#": 63, "E": 64, "F": 65,
        "F#": 66, "G": 67, "G#": 68, "A": 69, "A#": 70, "B": 71}


def hz(midi: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69.0) / 12.0)


def _env(n: int, attack: float, decay: float, sustain: float, release: float) -> np.ndarray:
    """ADSR. 길이 n 샘플. 클릭 소리를 막으려고 항상 0 에서 시작해 0 으로 끝난다."""
    a = max(1, int(attack * SR))
    d = max(1, int(decay * SR))
    r = max(1, int(release * SR))
    s = max(0, n - a - d - r)
    return np.concatenate([
        np.linspace(0.0, 1.0, a),
        np.linspace(1.0, sustain, d),
        np.full(s, sustain),
        np.linspace(sustain, 0.0, r),
    ])[:n]


def pluck(midi: float, dur: float, gain: float = 1.0) -> np.ndarray:
    """뜯는 소리. 배음이 빠르게 빠져서 통통 튄다."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(midi)
    out = np.zeros(n)
    # 배음을 쌓되 위로 갈수록 작고 빨리 죽는다. 실제 현악기가 그렇다.
    for k, amp in enumerate([1.0, 0.5, 0.28, 0.14, 0.07], start=1):
        if f * k > SR / 2:
            break
        out += amp * np.sin(2 * np.pi * f * k * t) * np.exp(-t * (3.5 + k * 1.6))
    return out * _env(n, 0.004, 0.05, 0.35, 0.12) * gain


def pad(midis: list[float], dur: float, gain: float = 1.0) -> np.ndarray:
    """길게 깔리는 화음. 천천히 차오르고 천천히 빠진다."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for m in midis:
        f = hz(m)
        # 아주 살짝 어긋난 두 음을 겹치면 두껍게 들린다 (디튠).
        for det in (-0.08, 0.08):
            fd = hz(m + det)
            out += np.sin(2 * np.pi * fd * t)
            out += 0.3 * np.sin(2 * np.pi * fd * 2 * t)
        out += 0.12 * np.sin(2 * np.pi * f * 3 * t)
    out /= max(1, len(midis) * 2)
    return out * _env(n, dur * 0.25, dur * 0.1, 0.85, dur * 0.3) * gain


def bass(midi: float, dur: float, gain: float = 1.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(midi)
    out = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 2 * t)
    # 살짝 찌그러뜨리면 작은 스피커에서도 저음이 들린다.
    out = np.tanh(out * 1.4)
    return out * _env(n, 0.008, 0.08, 0.7, 0.1) * gain


def bell(midi: float, dur: float, gain: float = 1.0) -> np.ndarray:
    """멜로디용. 종소리에 가깝게 맑은 배음만 남긴다."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(midi)
    out = (np.sin(2 * np.pi * f * t) * np.exp(-t * 1.6)
           + 0.4 * np.sin(2 * np.pi * f * 2.01 * t) * np.exp(-t * 2.6)
           + 0.15 * np.sin(2 * np.pi * f * 3.02 * t) * np.exp(-t * 4.0))
    return out * _env(n, 0.006, 0.06, 0.5, 0.2) * gain


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """1차 저역통과. cutoff 위쪽을 부드럽게 깎는다."""
    a = 1.0 - np.exp(-2.0 * np.pi * cutoff / SR)
    out = np.empty_like(x)
    prev = 0.0
    for i, v in enumerate(x):
        prev += a * (v - prev)
        out[i] = prev
    return out


def _highpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """저역통과로 걸러낸 나머지가 고역통과다."""
    return x - _lowpass(x, cutoff)


def _bandpass(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """노이즈를 그냥 쓰면 치익 소리만 남는다. 필요한 대역만 남긴다."""
    return _lowpass(_highpass(x, lo), hi)


def kick(gain: float = 1.0) -> np.ndarray:
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    # 높은 음에서 낮은 음으로 떨어지는 게 킥 소리의 정체다.
    f = 118.0 * np.exp(-t * 26.0) + 46.0
    out = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9.0)
    return out * gain


def hat(gain: float = 1.0) -> np.ndarray:
    n = int(0.05 * SR)
    rng = np.random.default_rng(7)
    # 5~11kHz 만 남긴다. 위를 안 깎으면 영상 전체가 치익거린다.
    noise = _bandpass(rng.standard_normal(n), 5000.0, 11000.0)
    t = np.arange(n) / SR
    return noise * np.exp(-t * 70.0) * gain


def clap(gain: float = 1.0) -> np.ndarray:
    n = int(0.18 * SR)
    rng = np.random.default_rng(11)
    noise = _bandpass(rng.standard_normal(n), 1200.0, 5000.0)
    t = np.arange(n) / SR
    env = np.exp(-t * 22.0)
    # 짧은 소리를 몇 번 겹치면 여러 명이 치는 것처럼 들린다.
    for delay, amp in ((0.010, 0.7), (0.020, 0.5)):
        d = int(delay * SR)
        env[d:] += np.exp(-t[:-d] * 22.0) * amp
    return noise * env * gain


def _add(buf: np.ndarray, sound: np.ndarray, at: float) -> None:
    """buf 의 at 초 지점에 sound 를 얹는다. 끝을 넘으면 잘라 넣는다."""
    i = int(at * SR)
    if i >= len(buf):
        return
    end = min(len(buf), i + len(sound))
    buf[i:end] += sound[:end - i]


def _delay(sig: np.ndarray, seconds: float, feedback: float, mix: float) -> np.ndarray:
    """되울림. 공간이 있는 것처럼 들리게 한다."""
    d = int(seconds * SR)
    if d <= 0 or d >= len(sig):
        return sig
    echo = np.zeros_like(sig)
    tap = sig.copy()
    for _ in range(4):
        tap = np.concatenate([np.zeros(d), tap[:-d]]) * feedback
        echo += tap
    return sig + echo * mix


def compose(seconds: float, bpm: float, root: int) -> np.ndarray:
    beat = 60.0 / bpm
    bar = beat * 4
    bars = max(4, int(round(seconds / bar)))
    total = bars * bar
    n = int(total * SR) + SR  # 마지막 소리가 잘리지 않게 1초 여유

    ch_pluck = np.zeros(n)
    ch_pad = np.zeros(n)
    ch_bass = np.zeros(n)
    ch_lead = np.zeros(n)
    ch_drum = np.zeros(n)

    # 구간을 나눠 악기를 넣고 뺀다. 60초 내내 똑같으면 지겹다.
    def section(b: int) -> str:
        r = b / bars
        if r < 0.14:
            return "intro"      # 패드 + 아르페지오
        if r < 0.28:
            return "build"      # + 베이스, 하이햇
        if 0.57 <= r < 0.71:
            return "break"      # 드럼 빼고 숨 고르기
        if r >= 0.93:
            return "outro"
        return "main"           # 전부

    for b in range(bars):
        t0 = b * bar
        sec = section(b)
        degree, quality = PROGRESSION[b % len(PROGRESSION)]
        chord_root = root + degree
        tones = [chord_root + i for i in CHORD_TONES[quality]]

        # --- 패드: 마디 전체를 채운다 ---
        _add(ch_pad, pad(tones, bar * 1.02, 0.62), t0)

        # --- 아르페지오: 16분음표로 화음 음을 오르내린다 ---
        if sec != "outro":
            up = tones + [chord_root + 12, tones[1] + 12]
            order = up + up[-2:0:-1]
            for i in range(16):
                m = order[i % len(order)]
                vel = 0.34 if i % 4 == 0 else 0.22
                _add(ch_pluck, pluck(m + 12, beat * 0.55, vel), t0 + i * beat / 4)

        # --- 베이스: 마디 첫 박과 셋째 박 ---
        if sec in ("build", "main", "outro"):
            _add(ch_bass, bass(chord_root - 24, beat * 1.6, 0.85), t0)
            _add(ch_bass, bass(chord_root - 24, beat * 1.4, 0.62), t0 + beat * 2)

        # --- 멜로디 ---
        if sec in ("main", "break", "outro"):
            for i, step in enumerate(MELODY[b % len(MELODY)]):
                if step is None:
                    continue
                _add(ch_lead, bell(root + step + 12, beat * 0.95, 0.42), t0 + i * beat)

        # --- 드럼 ---
        if sec in ("build", "main"):
            for i in range(8):
                if sec == "main" or i % 2 == 0:
                    _add(ch_drum, hat(0.045 if i % 2 else 0.075), t0 + i * beat / 2)
        if sec == "main":
            for i in (0, 2):
                _add(ch_drum, kick(1.0), t0 + i * beat)
            _add(ch_drum, kick(0.7), t0 + beat * 2.5)
            for i in (1, 3):
                _add(ch_drum, clap(0.16), t0 + i * beat)

    # 되울림은 통통 튀는 소리에만. 베이스와 드럼에 걸면 지저분해진다.
    ch_pluck = _delay(ch_pluck, beat * 0.75, 0.32, 0.22)
    ch_lead = _delay(ch_lead, beat * 0.5, 0.28, 0.26)

    # 좌우로 조금씩 벌린다. 가운데에 다 몰리면 답답하다.
    left = ch_pad * 0.95 + ch_pluck * 1.05 + ch_bass + ch_lead * 0.85 + ch_drum
    right = ch_pad * 1.05 + ch_pluck * 0.85 + ch_bass + ch_lead * 1.05 + ch_drum

    stereo = np.stack([left, right], axis=1)
    stereo = np.tanh(stereo * 0.8)          # 튀는 부분만 부드럽게 눌러준다
    peak = np.max(np.abs(stereo)) or 1.0
    # mp3 로 굽는 과정에서 파형이 조금 부풀기 때문에 최대치까지 채우지 않는다.
    stereo = stereo / peak * 0.72

    # 시작과 끝을 부드럽게. 영상에 깔았을 때 툭 끊기지 않는다.
    fade = int(min(1.5, total * 0.05) * SR)
    stereo[:fade] *= np.linspace(0, 1, fade)[:, None]
    stereo[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return stereo


def write_wav(stereo: np.ndarray, path: Path) -> None:
    data = (np.clip(stereo, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def find_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="밝고 가사 없는 배경음악 만들기")
    ap.add_argument("--out", default="assets/music/background.mp3", help="저장할 파일")
    ap.add_argument("--seconds", type=float, default=60.0, help="길이(초)")
    ap.add_argument("--bpm", type=float, default=112.0, help="빠르기")
    ap.add_argument("--key", default="C", help=f"조 ({'/'.join(KEYS)})")
    args = ap.parse_args()

    if args.key not in KEYS:
        print(f"[!] 모르는 조: {args.key}  (쓸 수 있는 것: {', '.join(KEYS)})")
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"[i] {args.key} 조 / {args.bpm:.0f} BPM / {args.seconds:.0f}초 로 만든다.")
    stereo = compose(args.seconds, args.bpm, KEYS[args.key])

    if out.suffix.lower() == ".wav":
        write_wav(stereo, out)
        print(f"[+] 만들었다: {out}")
        return 0

    ffmpeg = find_ffmpeg()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_wav = Path(tmp) / "raw.wav"
        write_wav(stereo, tmp_wav)
        if not ffmpeg:
            fallback = out.with_suffix(".wav")
            shutil.copy2(tmp_wav, fallback)
            print(f"[!] ffmpeg 가 없어 wav 로 저장했다: {fallback}")
            print("    프로그램은 wav 도 읽으니 그대로 써도 된다.")
            return 0
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(tmp_wav),
             "-codec:a", "libmp3lame", "-b:a", "192k", str(out)],
            check=True,
        )

    size = out.stat().st_size / 1024
    print(f"[+] 만들었다: {out}  ({size:.0f}KB)")
    print(f"[i] 볼륨은 .env 의 REELS_MUSIC_VOLUME 으로 조절한다 (지금 기본 0.15).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
