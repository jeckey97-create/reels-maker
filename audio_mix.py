"""배경음악 합성 — 완성된 영상에 음악을 얹는다.

인코딩이 끝난 mp4 를 받아서 배경음악을 섞은 새 mp4 를 만든다. 비디오는
재인코딩하지 않고 그대로 복사하므로 빠르고 화질 손실이 없다.

원칙:
  · 음악 파일이 없으면 **에러를 내지 않는다.** 원본을 그대로 내보낸다.
  · 영상에 원래 음성이 있으면 그 음성은 유지하고 음악만 작게 깐다.
  · 인스타 음원 라이브러리는 API 로 접근할 수 없다. 여기서 쓰는 건
    사용자가 assets/music/ 에 직접 넣은 로컬 파일뿐이다.
    저작권 음원을 구워 넣으면 인스타가 자동 음소거하거나 삭제한다.
"""

from __future__ import annotations

import random
import shutil
import subprocess
from pathlib import Path

import config as cfg

_SILENT_HINT = "anullsrc"


class AudioMixError(RuntimeError):
    pass


def ffmpeg_available() -> tuple[bool, str]:
    """ffmpeg 가 실제로 실행되는지 확인. (가능여부, 안내문)"""
    try:
        proc = subprocess.run([cfg.FFMPEG, "-version"], capture_output=True, text=True)
        if proc.returncode == 0:
            return True, proc.stdout.splitlines()[0]
    except FileNotFoundError:
        pass
    return False, (
        "ffmpeg 를 찾지 못했다. 아래 명령으로 설치해라 (자동으로 설치하지 않는다):\n"
        "    winget install --id Gyan.FFmpeg\n"
        "설치 후에도 안 잡히면 .env 에 REELS_FFMPEG=<ffmpeg.exe 전체경로> 를 넣어라."
    )


def _probe(path: Path, stream: str, entries: str) -> str:
    proc = subprocess.run(
        [cfg.FFPROBE, "-v", "error", "-select_streams", stream,
         "-show_entries", entries, "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return (proc.stdout or "").strip()


def duration_of(path: Path) -> float:
    try:
        return float(_probe(path, "v:0", "format=duration") or 0.0)
    except ValueError:
        return 0.0


def has_audio(path: Path) -> bool:
    """영상에 오디오 스트림이 있는지."""
    return bool(_probe(path, "a:0", "stream=codec_type"))


def has_real_audio(path: Path) -> bool:
    """무음 트랙만 있는 게 아니라 실제 소리가 있는지 대략 판단.

    build_reel 이 넣는 anullsrc 무음 트랙은 '원래 음성'이 아니므로
    그 위에 음악을 얹을 때 섞을 필요가 없다. 볼륨 최대값으로 판별한다.
    """
    if not has_audio(path):
        return False
    # volumedetect 결과는 info 레벨로 stderr 에 나온다. -v error 로 막으면 안 된다.
    proc = subprocess.run(
        [cfg.FFMPEG, "-hide_banner", "-v", "info", "-i", str(path), "-af", "volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    for line in (proc.stderr or "").splitlines():
        if "max_volume" in line:
            try:
                return float(line.split("max_volume:")[1].replace("dB", "").strip()) > -90.0
            except (IndexError, ValueError):
                return True
    return True


def pick_music(music_dir: Path | None = None, *,
               video_seconds: float | None = None,
               cuts: int | None = None) -> Path | None:
    """쓸 음원을 고른다.

    지정된 파일 → (영상 정보를 주면) 어울리는 것 → 폴더에서 랜덤 → 없으면 None.

    영상 길이와 컷 수를 주면 `music_pick` 이 BPM·길이·에너지를 재서 고른다.
    librosa 가 없거나 분석이 실패하면 조용히 랜덤으로 돌아간다 — 음악 때문에
    영상 생성 자체가 막히면 안 되기 때문이다.
    """
    if cfg.MUSIC_FILE.exists() and cfg.MUSIC_FILE.is_file():
        return cfg.MUSIC_FILE
    music_dir = music_dir or cfg.MUSIC_DIR
    if not music_dir.exists():
        return None
    tracks = sorted(
        p for p in music_dir.iterdir()
        if p.is_file() and p.suffix.lower() in cfg.AUDIO_EXTS
    )
    if not tracks:
        return None

    if video_seconds and video_seconds > 0:
        try:
            import music_pick

            best = music_pick.pick_for(video_seconds, cuts or 4, music_dir)
            if best:
                return best
        except Exception as e:
            print(f"[i] 음원 분석을 건너뛴다 ({e}). 랜덤으로 고른다.")

    return random.choice(tracks)


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
        raise AudioMixError(f"ffmpeg 실패 (코드 {proc.returncode}):\n{tail}")


def mix_audio(
    video: Path,
    music: Path | None = None,
    *,
    music_volume: float | None = None,
    original_volume: float | None = None,
    fade_out_seconds: float | None = None,
    loop_music: bool | None = None,
    out: Path | None = None,
    cuts: int | None = None,
    verbose: bool = True,
) -> Path:
    """영상에 배경음악을 합성한다.

    music 이 None 이거나 파일이 없으면 원본을 그대로 내보낸다 (에러 없음).
    반환값은 결과 파일 경로.
    """
    video = Path(video)
    if not video.exists():
        raise AudioMixError(f"영상이 없다: {video}")

    ok, hint = ffmpeg_available()
    if not ok:
        raise AudioMixError(hint)

    music_volume = cfg.MUSIC_VOLUME if music_volume is None else music_volume
    original_volume = cfg.ORIGINAL_AUDIO_VOLUME if original_volume is None else original_volume
    fade_out_seconds = cfg.FADE_OUT_SECONDS if fade_out_seconds is None else fade_out_seconds
    loop_music = cfg.LOOP_MUSIC if loop_music is None else loop_music

    if music is None:
        # 어울리는 음원을 고르려면 영상 길이가 먼저 필요하다.
        music = pick_music(video_seconds=duration_of(video), cuts=cuts)
    music = Path(music) if music else None

    out = Path(out) if out else video.with_name(video.stem + "-music.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    # --- 음악이 없으면 원본 그대로 -------------------------------------
    if music is None or not music.exists():
        if verbose:
            where = music if music else cfg.MUSIC_DIR
            print(f"[i] 음원이 없다 ({where}). 원본 영상을 그대로 쓴다.")
        if out.resolve() != video.resolve():
            shutil.copy2(video, out)
        return out

    dur = duration_of(video)
    if dur <= 0:
        raise AudioMixError(f"영상 길이를 읽지 못했다: {video}")

    keep_original = has_real_audio(video) and original_volume > 0
    fade = max(0.0, min(fade_out_seconds, dur))
    fade_start = max(0.0, dur - fade)

    if verbose:
        print(f"[i] 배경음악: {music.name}")
        print(f"    영상 {dur:.1f}초 / 음악 볼륨 {music_volume} / 페이드아웃 {fade:.1f}초")
        print(f"    원본 음성: {'유지 (볼륨 ' + str(original_volume) + ')' if keep_original else '없음'}")
        print(f"    반복: {'켬' if loop_music else '끔'}")

    # --- 음악 트랙 필터 -------------------------------------------------
    # 길면 atrim 으로 자르고, 짧으면 aloop 로 반복한 뒤 자른다.
    music_chain = []
    if loop_music:
        # aloop 는 샘플 단위. -1 은 무한 반복이고 뒤에서 atrim 으로 끊는다.
        music_chain.append("aloop=loop=-1:size=2e9")
    music_chain.append(f"atrim=0:{dur:.3f}")
    music_chain.append("asetpts=PTS-STARTPTS")
    # 반복을 끄면 음악이 영상보다 짧게 끝나 오디오 트랙이 중간에 사라진다.
    # 무음으로 채워 트랙이 영상 전체를 덮게 한다.
    music_chain.append(f"apad=whole_dur={dur:.3f}")
    music_chain.append(f"volume={music_volume}")
    if fade > 0:
        music_chain.append(f"afade=t=out:st={fade_start:.3f}:d={fade:.3f}")
    music_chain.append("aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo")

    args: list[str] = [cfg.FFMPEG, "-y", "-i", str(video), "-i", str(music)]

    if keep_original:
        filter_complex = (
            f"[0:a]volume={original_volume},"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[orig];"
            f"[1:a]{','.join(music_chain)}[bg];"
            "[orig][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
        )
    else:
        filter_complex = f"[1:a]{','.join(music_chain)}[aout]"

    # ffmpeg 는 읽고 있는 파일에 그대로 쓸 수 없다. 제자리 갱신이면 임시로 뺐다가 바꾼다.
    in_place = out.resolve() == video.resolve()
    target = out.with_name(out.stem + ".mixtmp.mp4") if in_place else out

    args += [
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",          # 비디오 재인코딩 없음
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-t", f"{dur:.3f}",
        "-movflags", "+faststart",
        str(target),
    ]

    _run(args)
    if in_place:
        target.replace(out)
    if verbose:
        print(f"[+] 합성 완료: {out}")
    return out
