"""음원을 분석해서 영상에 어울리는 것을 고른다.

`audio_mix.pick_music()` 은 폴더에서 **랜덤으로** 골랐다. 이 모듈은 대신 음원을 실제로
분석해서(BPM·에너지·음색) 영상의 컷 리듬과 맞는 것을 고른다.

분석 결과는 `music_index.json` 에 캐시한다. 음원이 바뀌지 않으면 다시 분석하지 않는다
(librosa 로드가 트랙당 몇 초 걸린다).

사용법:
    py music_pick.py --list                    # 음원 폴더를 분석해서 표로 보여준다
    py music_pick.py --for out/제주.mp4 --cuts 4   # 이 영상에 뭘 깔지 고른다

주의: 이 모듈은 소리를 듣고 판단하지 않는다. 측정값으로 고를 뿐이다.
최종 확인은 사람이 들어보고 해야 한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config as cfg

INDEX_PATH = cfg.BASE_DIR / "music_index.json"

# 컷 하나가 이 정도 길이일 때 어울리는 BPM 대역.
# 컷이 짧으면 빠른 곡, 길면 느린 곡이 붙어야 리듬이 맞는다.
BPM_FOR_CUT_SECONDS = [
    (1.5, 120, 180),   # 아주 빠른 컷
    (2.5, 100, 140),
    (3.5, 80, 120),
    (99.0, 60, 100),   # 느긋한 컷
]


def _bpm_target(cut_seconds: float) -> tuple[int, int]:
    for upto, lo, hi in BPM_FOR_CUT_SECONDS:
        if cut_seconds <= upto:
            return lo, hi
    return 60, 100


def analyze(path: Path) -> dict:
    """음원 하나를 분석한다. librosa 가 없으면 예외."""
    import librosa
    import numpy as np

    # 앞 90초만 본다. 전체를 읽으면 느리고, 배경음악 판단에는 충분하다.
    y, sr = librosa.load(str(path), mono=True, duration=90)
    if y.size == 0:
        raise ValueError("빈 오디오")

    tempo = librosa.beat.beat_track(y=y, sr=sr)[0]
    bpm = float(tempo[0] if hasattr(tempo, "__len__") else tempo)
    rms = float(np.mean(librosa.feature.rms(y=y)))
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))

    return {
        "bpm": round(bpm, 1),
        "energy": round(rms, 4),          # 클수록 크고 꽉 찬 소리
        "brightness": round(centroid, 1),  # 높을수록 밝고 날카로운 음색
        "duration": round(librosa.get_duration(path=str(path)), 1),
    }


def mood_of(f: dict) -> str:
    """측정값을 사람 말로 옮긴다. 어디까지나 수치 기반 추정이다."""
    speed = "빠름" if f["bpm"] >= 120 else "보통" if f["bpm"] >= 90 else "느림"
    power = "강함" if f["energy"] >= 0.12 else "보통" if f["energy"] >= 0.05 else "잔잔함"
    tone = "밝음" if f["brightness"] >= 2600 else "중간" if f["brightness"] >= 1500 else "어두움"
    return f"{speed}·{power}·{tone}"


def _stamp(p: Path) -> str:
    st = p.stat()
    return f"{st.st_size}:{int(st.st_mtime)}"


def load_index() -> dict:
    if not INDEX_PATH.exists():
        return {}
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def tracks_in(music_dir: Path | None = None) -> list[Path]:
    music_dir = music_dir or cfg.MUSIC_DIR
    if not music_dir.exists():
        return []
    return sorted(p for p in music_dir.iterdir()
                  if p.is_file() and p.suffix.lower() in cfg.AUDIO_EXTS)


def build_index(music_dir: Path | None = None, verbose: bool = True) -> dict:
    """폴더의 음원을 분석한다. 이미 분석했고 파일이 안 바뀌었으면 건너뛴다."""
    index = load_index()
    changed = False
    for p in tracks_in(music_dir):
        key = p.name
        if index.get(key, {}).get("stamp") == _stamp(p):
            continue
        if verbose:
            print(f"[분석] {p.name} ...")
        try:
            f = analyze(p)
        except Exception as e:
            if verbose:
                print(f"  [!] 실패: {e}")
            continue
        f["stamp"] = _stamp(p)
        index[key] = f
        changed = True
    if changed:
        INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def score(f: dict, video_seconds: float, cut_seconds: float) -> tuple[float, str]:
    """높을수록 잘 어울린다. 왜 그렇게 봤는지도 같이 돌려준다."""
    lo, hi = _bpm_target(cut_seconds)
    bpm = f["bpm"]
    if lo <= bpm <= hi:
        bpm_score, why_bpm = 1.0, f"BPM {bpm:.0f} — 컷 {cut_seconds:.1f}초에 맞음"
    else:
        off = (lo - bpm) if bpm < lo else (bpm - hi)
        bpm_score = max(0.0, 1.0 - off / 60)
        why_bpm = f"BPM {bpm:.0f} — 목표 {lo}~{hi} 에서 {off:.0f} 벗어남"

    # 영상보다 길면 반복 없이 쓸 수 있다.
    if f["duration"] >= video_seconds:
        len_score, why_len = 1.0, "길이 충분"
    else:
        len_score = max(0.0, f["duration"] / max(video_seconds, 0.1))
        why_len = f"{f['duration']:.0f}초라 반복 필요"

    # 배경음악이라 너무 센 곡은 자막·나레이션을 덮는다.
    energy = f["energy"]
    energy_score = 1.0 if energy <= 0.15 else max(0.0, 1.0 - (energy - 0.15) * 4)
    why_energy = "배경으로 적당" if energy_score >= 0.9 else "소리가 센 편"

    total = bpm_score * 0.5 + len_score * 0.3 + energy_score * 0.2
    return total, f"{why_bpm} / {why_len} / {why_energy}"


def pick_for(video_seconds: float, cuts: int = 4,
             music_dir: Path | None = None, verbose: bool = False) -> Path | None:
    """영상 길이와 컷 수를 보고 가장 어울리는 음원을 고른다. 없으면 None."""
    files = tracks_in(music_dir)
    if not files:
        return None
    index = build_index(music_dir, verbose=verbose)
    cut_seconds = video_seconds / max(cuts, 1)

    ranked = []
    for p in files:
        f = index.get(p.name)
        if not f:
            continue
        s, why = score(f, video_seconds, cut_seconds)
        ranked.append((s, p, why))
    if not ranked:
        return None
    ranked.sort(key=lambda r: -r[0])
    if verbose:
        for s, p, why in ranked:
            print(f"  {s:.2f}  {p.name} — {why}")
    return ranked[0][1]


def main() -> int:
    ap = argparse.ArgumentParser(description="음원 분석·선택")
    ap.add_argument("--list", action="store_true", help="음원 폴더를 분석해서 보여준다")
    ap.add_argument("--for", dest="video", help="이 영상에 어울리는 음원을 고른다")
    ap.add_argument("--cuts", type=int, default=4, help="영상의 컷 수")
    ap.add_argument("--dir", help="음원 폴더 (기본: assets/music)")
    args = ap.parse_args()

    music_dir = Path(args.dir) if args.dir else None
    files = tracks_in(music_dir)
    if not files:
        print(f"[!] 음원이 없다: {music_dir or cfg.MUSIC_DIR}")
        return 1

    if args.list or not args.video:
        index = build_index(music_dir)
        print(f"\n{'파일':<34}{'BPM':>7}{'에너지':>9}{'음색':>9}{'길이':>8}  느낌")
        print("-" * 86)
        for p in files:
            f = index.get(p.name)
            if not f:
                print(f"{p.name:<34}  (분석 실패)")
                continue
            print(f"{p.name:<34}{f['bpm']:>7.0f}{f['energy']:>9.3f}"
                  f"{f['brightness']:>9.0f}{f['duration']:>7.0f}초  {mood_of(f)}")
        print("\n※ 측정값 기반 추정이다. 실제로 어울리는지는 들어보고 판단해라.")
        return 0

    import audio_mix
    seconds = audio_mix.duration_of(Path(args.video))
    if seconds <= 0:
        print(f"[!] 영상 길이를 못 읽었다: {args.video}")
        return 1
    print(f"[i] 영상 {seconds:.1f}초 / 컷 {args.cuts}개 "
          f"→ 컷당 {seconds / max(args.cuts, 1):.1f}초")
    best = pick_for(seconds, args.cuts, music_dir, verbose=True)
    print(f"\n[+] 고른 음원: {best.name if best else '없음'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
