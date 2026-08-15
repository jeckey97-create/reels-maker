"""공개 URL 만들기 — 인스타가 영상을 받아갈 주소를 연다.

Graph API 는 로컬 파일을 못 받는다. https:// 로 접근 가능한 주소에서만
영상을 가져간다. 계정 가입이나 클라우드 설정 없이 그 주소를 만드는 게 이 스크립트다.

    out/ 폴더를 로컬 웹서버로 열고
    → cloudflared 로 그 서버에 https 주소를 붙이고
    → 주소를 .env 의 REELS_PUBLIC_BASE 에 써준다

사용법:
    py serve.py              # 주소 만들고 계속 띄워둔다 (Ctrl+C 로 종료)
    py serve.py --port 8899

주의: 이 주소가 열려 있는 동안 out/ 폴더의 파일은 **인터넷에 공개된다.**
게시가 끝나면 Ctrl+C 로 닫아라. 주소는 실행할 때마다 새로 바뀐다.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import re
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

import config as cfg

# 파일로 리다이렉트하면 print 가 버퍼에 갇혀 주소가 안 보인다.
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# api.trycloudflare.com 은 **터널 주소가 아니다.** cloudflared 가 터널을
# 요청할 때 쓰는 서버라, 터널 생성이 실패한 오류 로그에도 이 주소가 찍힌다.
# 그걸 주소로 잡으면 "성공했다" 고 해놓고 게시에서 405 가 난다.
TUNNEL_URL_RE = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")

# 만든 주소로 실제 파일이 받아지는지 확인할 때 쓰는 임시 파일
PROBE_NAME = "_serve_check.txt"


def find_cloudflared() -> str | None:
    found = shutil.which("cloudflared")
    if found:
        return found
    import glob
    # winget 은 PATH 에 안 넣어주는 경우가 많다. 알려진 설치 위치를 훑는다.
    pats = [
        os.path.expandvars(r"%ProgramFiles(x86)%\cloudflared\cloudflared.exe"),
        os.path.expandvars(r"%ProgramFiles%\cloudflared\cloudflared.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Cloudflare.cloudflared*\*.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe"),
    ]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def _drain(proc: subprocess.Popen) -> None:
    """cloudflared 출력을 계속 읽어 버린다.

    안 읽으면 파이프가 차서 터널이 멈춘다. 주소를 찾은 뒤에도 계속 필요하다.
    """
    try:
        for _ in proc.stdout or []:
            pass
    except Exception:
        pass


def start_file_server(port: int) -> socketserver.TCPServer:
    """out/ 을 정적으로 서빙한다. mp4 는 video/mp4 로 나가야 인스타가 받는다."""
    cfg.OUT_DIR.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                               directory=str(cfg.OUT_DIR))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def start_tunnel(exe: str, port: int, timeout: int = 60) -> tuple[subprocess.Popen, str | None]:
    """cloudflared 로 https 주소를 연다. 계정 없이 임시 주소를 준다."""
    proc = subprocess.Popen(
        [exe, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    url = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            if proc.poll() is not None:
                break
            continue
        m = TUNNEL_URL_RE.search(line)
        if m:
            url = m.group(0)
            break
    return proc, url


def verify_tunnel(base_url: str, timeout: int = 40) -> bool:
    """그 주소로 **우리 파일이 실제로 받아지는지** 확인한다.

    주소 모양만 보고 넘어가면 안 된다. 정규식이 엉뚱한 주소를 잡거나 터널이
    아직 안 붙었는데 주소만 먼저 찍히는 경우가 있고, 그러면 8장까지 가서야
    "공개 주소로 파일을 받을 수 없다" 로 드러난다. 여기서 걸러야 한다.
    """
    import urllib.request

    token = f"reels-maker {time.time()}"
    probe = cfg.OUT_DIR / PROBE_NAME
    probe.write_text(token, encoding="utf-8")
    url = f"{base_url.rstrip('/')}/{PROBE_NAME}"
    deadline = time.time() + timeout
    last = ""
    try:
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=10) as r:
                    if r.status == 200 and r.read().decode("utf-8", "replace") == token:
                        return True
                    last = f"HTTP {r.status}"
            except Exception as e:      # 터널이 붙는 데 몇 초 걸린다
                last = str(e)
            time.sleep(2)
    finally:
        probe.unlink(missing_ok=True)
    print(f"    (마지막 응답: {last})")
    return False


def write_env(base_url: str) -> None:
    """.env 의 REELS_PUBLIC_BASE 를 갱신한다."""
    env = cfg.BASE_DIR / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    out, done = [], False
    for ln in lines:
        if ln.strip().startswith("REELS_PUBLIC_BASE="):
            out.append(f"REELS_PUBLIC_BASE={base_url}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"REELS_PUBLIC_BASE={base_url}")
    env.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="인스타가 영상을 받아갈 공개 URL 열기")
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args()

    exe = find_cloudflared()
    if not exe:
        print("[!] cloudflared 를 찾지 못했다. 아래로 설치해라 (자동 설치하지 않는다):")
        print("      winget install --id Cloudflare.cloudflared")
        print("    설치 후 새 터미널에서 다시 실행해라.")
        return 1

    httpd = start_file_server(args.port)
    print(f"[i] out/ 을 http://127.0.0.1:{args.port} 로 열었다")

    print("[i] 공개 주소를 만드는 중… (10~30초)")
    proc, url = start_tunnel(exe, args.port)
    if not url:
        print("[!] 공개 주소를 못 만들었다. 인터넷 연결을 확인하고 다시 실행해라.")
        print("    회사·학교 네트워크에서 cloudflare 가 막혀 있는 경우가 있다.")
        proc.terminate()
        httpd.shutdown()
        return 1

    # 주소가 나왔다고 끝이 아니다. 실제로 파일이 받아지는지 확인하고 저장한다.
    threading.Thread(target=_drain, args=(proc,), daemon=True).start()
    print("[i] 주소가 살아 있는지 확인하는 중…")
    if not verify_tunnel(url):
        print()
        print(f"[!] 주소는 만들어졌는데({url}) 그 주소로 파일이 안 받아진다.")
        print("    .env 에 저장하지 않았다. 이대로 게시하면 실패한다.")
        print("    이 창을 닫고 다시 실행해봐라. 계속 그러면 인터넷 환경 문제다.")
        proc.terminate()
        httpd.shutdown()
        return 1

    write_env(url)
    print()
    print("=" * 56)
    print(f"  공개 주소: {url}")
    print("=" * 56)
    print("  .env 의 REELS_PUBLIC_BASE 에 자동으로 저장했다.")
    print()
    print("  이 창을 켜둔 채로 다른 창에서 게시해라:")
    print("      py approve.py --publish <이름>")
    print()
    print("  게시가 끝나면 이 창에서 Ctrl+C 로 닫아라.")
    print("  (닫으면 주소가 사라진다. out/ 이 인터넷에 열려 있으니 오래 두지 마라.)")
    print()

    try:
        while proc.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[i] 닫는 중…")
    finally:
        proc.terminate()
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
