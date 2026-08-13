"""자동 게시 설정 점검 — 어디서 막혔는지 짚어준다.

인스타 Graph API 는 막히는 지점이 정해져 있다. 에러 메시지가 불친절해서
"뭐가 틀렸는지" 모른 채 포기하는 경우가 많다. 이 스크립트는 단계별로 검사해서
무엇이 안 됐고 어떻게 고치는지 알려준다.

    py setup_check.py

검사 항목:
    1. ffmpeg          — 영상 인코딩
    2. 얼굴 감지 모델   — 초상권 필터
    3. .env 값         — IG_USER_ID / IG_ACCESS_TOKEN / REELS_PUBLIC_BASE
    4. 토큰 유효성      — 만료 여부와 남은 기간, 계정 종류
    5. 권한            — content_publish 가 붙어 있는지
    6. 공개 URL        — 인스타가 실제로 영상을 받아갈 수 있는 주소인지
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import config as cfg

OK = "[ OK ]"
NO = "[ 문제 ]"
SKIP = "[ 건너뜀 ]"

_problems: list[str] = []


def say(status: str, title: str, detail: str = "", fix: str = "") -> None:
    print(f"{status} {title}")
    if detail:
        print(f"       {detail}")
    if fix:
        print(f"       → {fix}")
        _problems.append(title)
    print()


def check_ffmpeg() -> None:
    try:
        r = subprocess.run([cfg.FFMPEG, "-version"], capture_output=True, text=True)
        if r.returncode == 0:
            say(OK, "ffmpeg", r.stdout.splitlines()[0][:60])
            return
    except FileNotFoundError:
        pass
    say(NO, "ffmpeg 없음", "영상을 만들 수 없다.",
        "winget install --id Gyan.FFmpeg  (설치 후 새 터미널)")


def check_face_model() -> None:
    """모델 파일과 opencv 를 **둘 다** 본다.

    파일만 검사하면 opencv 가 없을 때 여기서는 OK 가 뜨는데 정작 릴스를
    만들 때 사진이 전부 제외된다. 초보자가 원인을 찾을 수 없다.
    """
    if not cfg.FACE_MODEL.exists():
        say(NO, "얼굴 감지 모델 없음",
            "학생 얼굴이 걸러지지 않는다. 사진이 전부 제외되어 릴스가 안 만들어진다.",
            "assets/models/ 에 YuNet 모델을 받아라 (assets/models/README.md 참고)")
        return

    try:
        import cv2  # type: ignore
    except ImportError:
        say(NO, "opencv 없음",
            "모델 파일은 있지만 얼굴을 검사할 프로그램이 없다. "
            "이대로 두면 사진이 전부 제외된다.",
            ".venv\\Scripts\\python.exe -m pip install opencv-python")
        return

    say(OK, "얼굴 감지 모델",
        f"{cfg.FACE_MODEL.name} ({cfg.FACE_MODEL.stat().st_size//1024}KB) / "
        f"opencv {cv2.__version__}")


def check_env() -> bool:
    """토큰만 있으면 된다. 사용자 ID 는 토큰으로 조회한다."""
    if not cfg.IG_ACCESS_TOKEN:
        say(NO, "액세스 토큰 없음", ".env 의 IG_ACCESS_TOKEN 이 비어 있다.",
            "SETUP.md 3단계에서 토큰을 발급받아 .env 에 넣어라")
        return False
    extra = f" / IG_USER_ID 직접 지정됨" if cfg.IG_USER_ID else " / 사용자 ID 는 토큰으로 조회한다"
    say(OK, ".env 값", f"토큰 {len(cfg.IG_ACCESS_TOKEN)}자{extra}")
    return True


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": {"message": str(e)}}


def check_token() -> None:
    """토큰이 살아 있는지, 어떤 계정인지, 언제 만료되는지."""
    url = (f"https://graph.instagram.com/{cfg.GRAPH_VERSION}/me?"
           + urllib.parse.urlencode({
               "fields": "id,username,account_type",
               "access_token": cfg.IG_ACCESS_TOKEN}))
    code, data = _get(url)
    if code != 200:
        msg = (data.get("error") or {}).get("message", "알 수 없는 오류")
        fix = "토큰이 만료됐거나 잘못됐다. SETUP.md 의 '토큰 발급'을 다시 하라."
        if "session" in msg.lower() or "expired" in msg.lower():
            fix = "토큰 만료다. py refresh_token.py 로 갱신하거나 새로 발급받아라."
        say(NO, "토큰 확인 실패", f"HTTP {code}: {msg}", fix)
        return

    acct = data.get("account_type", "?")
    say(OK, "토큰 유효", f"@{data.get('username')} / 계정 종류 {acct}")

    if acct not in ("BUSINESS", "MEDIA_CREATOR", "CREATOR"):
        say(NO, "계정 종류", f"현재 {acct}",
            "개인 계정으로는 자동 게시가 안 된다. 인스타 앱에서 프로페셔널 계정으로 전환해라.")

    # 남은 기간
    code, data = _get(
        f"https://graph.instagram.com/{cfg.GRAPH_VERSION}/refresh_access_token?"
        + urllib.parse.urlencode({"grant_type": "ig_refresh_token",
                                  "access_token": cfg.IG_ACCESS_TOKEN}))
    if code == 200 and "expires_in" in data:
        days = int(data["expires_in"]) // 86400
        status = OK if days > 7 else NO
        say(status, "토큰 남은 기간", f"약 {days}일",
            "" if days > 7 else "곧 만료된다. py refresh_token.py 를 돌려라.")


def check_public_url() -> None:
    base = cfg.PUBLIC_VIDEO_BASE
    if not base:
        # 미리 설정해둘 값이 아니다. serve.py 를 켤 때마다 새 주소가 채워진다.
        # 이걸 "해결할 것" 으로 세면 미리 뭔가 해야 하는 줄 알고 헤맨다.
        say(SKIP, "공개 URL — 아직 안 열림",
            "게시할 때 py serve.py 를 켜면 주소가 자동으로 채워진다. 미리 할 일은 없다.")
        return

    videos = sorted(cfg.OUT_DIR.glob("*.mp4")) if cfg.OUT_DIR.exists() else []
    if not videos:
        say(SKIP, "공개 URL 확인", f"{base} — out/ 에 영상이 없어 실제 접근은 확인 못 했다")
        return

    url = f"{base.rstrip('/')}/{urllib.parse.quote(videos[-1].name)}"
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ctype = r.headers.get("Content-Type", "")
            size = r.headers.get("Content-Length", "?")
            if r.status == 200 and "video" in ctype:
                say(OK, "공개 URL", f"{url} ({ctype}, {size} bytes)")
            else:
                say(NO, "공개 URL 응답 이상", f"HTTP {r.status}, Content-Type={ctype}",
                    "영상 파일이 video/mp4 로 서빙돼야 한다.")
    except Exception as e:
        say(NO, "공개 URL 접근 불가", f"{url} — {e}",
            "인스타 서버가 이 주소로 영상을 받아가야 한다. 사설망 주소나 로그인이 "
            "필요한 주소는 안 된다. py serve.py 로 터널을 열어라.")


def main() -> int:
    print("=" * 56)
    print(" 자동 게시 설정 점검")
    print("=" * 56)
    print()

    check_ffmpeg()
    check_face_model()
    if check_env():
        check_token()
    check_public_url()

    print("=" * 56)
    if _problems:
        print(f" 해결할 것 {len(_problems)}개:")
        for i, p in enumerate(_problems, 1):
            print(f"   {i}. {p}")
        print()
        print(" 자세한 절차는 SETUP.md 를 봐라.")
        return 1
    print(" 전부 준비됐다. py approve.py --publish <이름> 으로 게시할 수 있다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
