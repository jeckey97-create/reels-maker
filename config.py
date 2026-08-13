"""릴스 생성기 설정.

경로·규격을 한 곳에 모아둔다. 값은 .env 로 덮어쓸 수 있다.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str) -> str:
    return os.getenv(key, default).strip() or default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, "").strip() or default)
    except ValueError:
        return default


# --- 경로 ---------------------------------------------------------------
# 감시할 사진 폴더. 여기에 사진을 올리면 릴스가 만들어진다.
WATCH_DIR = Path(_env("REELS_WATCH_DIR", r"G:\내 드라이브\릴스"))
# 결과물
OUT_DIR = BASE_DIR / "out"
# 로열티프리 음원을 넣어두는 곳 (mp3/m4a/wav)
MUSIC_DIR = Path(_env("REELS_MUSIC_DIR", str(BASE_DIR / "assets" / "music")))
# 기본으로 쓸 음원 파일. 없으면 MUSIC_DIR 에서 아무거나 고른다.
MUSIC_FILE = Path(_env("REELS_MUSIC_FILE", str(MUSIC_DIR / "background.mp3")))
# 처리 이력 — 같은 사진으로 두 번 만들지 않기 위해
STATE_FILE = BASE_DIR / "state.json"

WORK_DIR = BASE_DIR / ".work"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".ogg"}

# --- 영상 규격 (PLAN.md) ------------------------------------------------
WIDTH = 1080
HEIGHT = 1920

# --- 피드 사진 · 캐러셀 -------------------------------------------------
# 인스타 피드는 1:1 / 4:5 / 1.91:1 을 받는다. 4:5 가 화면을 가장 많이
# 차지해서 눈에 잘 띈다. 정사각형으로 하려면 1080 으로 바꾼다.
FEED_WIDTH = _env_int("REELS_FEED_WIDTH", 1080)
FEED_HEIGHT = _env_int("REELS_FEED_HEIGHT", 1350)
# 캐러셀에 넣을 사진 수. 인스타 상한은 10장이다.
CAROUSEL_MAX = _env_int("REELS_CAROUSEL_MAX", 6)
# 피드 사진 JPEG 품질
FEED_QUALITY = _env_int("REELS_FEED_QUALITY", 90)
FPS = 30
# 사진당 노출 시간(초). 전환 시간은 여기서 겹친다.
# 자막 길이에 따라 컷마다 다르게 잡는다 — 긴 훅은 읽을 시간이 필요하고
# 짧은 자막은 금방 넘어가도 된다. 아래 값으로 계산한다.
SECONDS_PER_PHOTO = _env_int("REELS_SECONDS_PER_PHOTO", 3)   # 자막이 없을 때 기본값
CUT_BASE_SECONDS = float(_env("REELS_CUT_BASE", "1.4"))      # 사진 자체를 보는 시간
CUT_SECONDS_PER_CHAR = float(_env("REELS_CUT_PER_CHAR", "0.085"))  # 글자당 읽는 시간
CUT_MIN_SECONDS = float(_env("REELS_CUT_MIN", "2.0"))
CUT_MAX_SECONDS = float(_env("REELS_CUT_MAX", "4.0"))
CROSSFADE = 0.5
MIN_PHOTOS = 3
MAX_PHOTOS = 4  # 3초 × 4장 ≈ 10초
# 인스타 권장 영상 비트레이트(kbps). 최소 3500, 권장 5000~10000.
VIDEO_BITRATE_K = _env_int("REELS_VIDEO_BITRATE_K", 6000)
# 켄번스 확대율 (1.0 = 없음)
ZOOM_END = 1.12

# --- 자막 ---------------------------------------------------------------
FONT_PATH = Path(_env("REELS_FONT", r"C:\Windows\Fonts\malgunbd.ttf"))
FONT_SIZE = _env_int("REELS_FONT_SIZE", 84)          # 96 에서 조금 줄임
CAPTION_MAX_CHARS_PER_LINE = _env_int("REELS_CAPTION_CHARS", 11)  # 글자가 커진 만큼 줄임

# "box"  = 사진이 화면을 꽉 채우고 그 위에 반투명 박스 자막 (기본값)
# "band" = 상단 검은 띠 + 흰 글씨
#
# box 를 기본으로 둔 이유: 릴스는 전체화면으로 보므로 검은 띠가 화면의 20% 를
# 먹으면 손해다. 계정 조회수 상위 2개(2173/1444)도 사진이 꽉 찬 방식이었다.
CAPTION_STYLE = _env("REELS_CAPTION_STYLE", "box")

# box 스타일 자막 블록이 시작하는 높이 (화면 비율).
# 인스타 상단 UI 가 약 8~10% 를 쓴다. 그 바로 아래에 붙여 최대한 위로 올린다.
# 아래로 내리면 사진 가운데를 가려서 답답해 보인다.
CAPTION_TOP_RATIO = float(_env("REELS_CAPTION_TOP", "0.16"))
# 자막 최대 줄 수. 넘치면 글자를 줄이고, 그래도 안 되면 잘라낸다.
# 릴스는 화면이 작아서 3줄만 돼도 사진을 절반쯤 가린다.
CAPTION_MAX_LINES = _env_int("REELS_CAPTION_MAX_LINES", 2)
# 자막 블록의 최대 가로 폭 (화면 대비)
CAPTION_MAX_WIDTH_RATIO = float(_env("REELS_CAPTION_MAX_WIDTH", "0.86"))
CAPTION_FONT_MIN = _env_int("REELS_FONT_MIN", 54)

# band 스타일: 위쪽 검은 띠 높이
BAND_HEIGHT = _env_int("REELS_BAND_HEIGHT", 380)
# 띠 안에서 글자가 시작하는 높이. 세로 중앙 정렬을 하면 1줄/2줄 자막의 위치가
# 서로 달라 컷마다 튄다. 고정값으로 두어 항상 같은 자리에서 시작하게 한다.
BAND_TEXT_TOP = _env_int("REELS_BAND_TEXT_TOP", 70)
# box 스타일: 아래에서 띄우는 거리 / 박스 투명도
CAPTION_MARGIN_BOTTOM = 320
CAPTION_BOX_ALPHA = 150

# --- 초상권 안전장치 (face_guard.py) ------------------------------------
# 얼굴 폭 / 사진 폭 이 이 값 이상이면 개인이 특정된다고 본다.
FACE_MAX_RATIO = float(_env("REELS_FACE_MAX_RATIO", "0.04"))
# 각도와 무관한 크기 상한. 옆모습이어도 이보다 크게 찍히면 알아볼 수 있다.
FACE_ABSOLUTE_MAX_RATIO = float(_env("REELS_FACE_ABSOLUTE_MAX_RATIO", "0.07"))
# 정면도(코가 두 눈 중점에서 벗어난 정도). 이보다 크면 옆모습으로 보고 통과시킨다.
# 실측: 정면 0.01~0.24 / 옆모습 0.54~3.15
# 0.54 짜리(거의 정면)가 통과해버려서 1.0 으로 올렸다.
FACE_PROFILE_YAW = float(_env("REELS_FACE_PROFILE_YAW", "1.0"))
# exclude = 식별되는 얼굴이 있으면 후보에서 뺀다 (기본)
# blur    = 빼는 대신 얼굴을 모자이크 처리해서 쓴다
# off     = 검사 안 함 (동의받은 사진만 쓸 때)
FACE_POLICY = _env("REELS_FACE_POLICY", "exclude").lower()
# 문제 얼굴이 가장자리에 있으면 잘라내서 사진을 살린다
FACE_CROP = _env("REELS_FACE_CROP", "true").lower() not in ("0", "false", "no")
FACE_MODEL = Path(_env("REELS_FACE_MODEL",
                       str(BASE_DIR / "assets" / "models" / "face_detection_yunet_2023mar.onnx")))

# --- 배경음악 (audio_mix.py) --------------------------------------------
# 저작권 문제 없는 음원만 assets/music/ 에 넣어라. 인스타 음원 라이브러리는
# API 로 접근할 수 없고, 저작권 음원을 구우면 자동 음소거되거나 삭제된다.
MUSIC_VOLUME = float(_env("REELS_MUSIC_VOLUME", "0.15"))
ORIGINAL_AUDIO_VOLUME = float(_env("REELS_ORIGINAL_AUDIO_VOLUME", "1.0"))
FADE_OUT_SECONDS = float(_env("REELS_FADE_OUT_SECONDS", "2"))
LOOP_MUSIC = _env("REELS_LOOP_MUSIC", "true").lower() not in ("0", "false", "no")

# --- 인스타 게시 --------------------------------------------------------
IG_USER_ID = _env("IG_USER_ID", "")
IG_ACCESS_TOKEN = _env("IG_ACCESS_TOKEN", "")
GRAPH_VERSION = _env("GRAPH_VERSION", "v21.0")
# 영상은 공개 URL 이어야 Graph API 가 가져갈 수 있다.
PUBLIC_VIDEO_BASE = _env("REELS_PUBLIC_BASE", "")


def ensure_dirs() -> None:
    for d in (OUT_DIR, MUSIC_DIR, WORK_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _find_ffmpeg(name: str) -> str:
    """winget 으로 깐 ffmpeg 가 PATH 에 없는 경우가 흔해서 직접 찾는다."""
    import glob
    import shutil

    found = shutil.which(name)
    if found:
        return found
    patterns = [
        os.path.expandvars(
            rf"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\{name}.exe"
        ),
        rf"C:\ProgramData\chocolatey\bin\{name}.exe",
        rf"C:\ffmpeg\bin\{name}.exe",
    ]
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return name  # 못 찾으면 이름 그대로 (실행 시 에러로 드러난다)


FFMPEG = _env("REELS_FFMPEG", "") or _find_ffmpeg("ffmpeg")
FFPROBE = _env("REELS_FFPROBE", "") or _find_ffmpeg("ffprobe")
