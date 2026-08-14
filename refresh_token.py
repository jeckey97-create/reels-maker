"""액세스 토큰 갱신.

인스타 장기 토큰은 60일이면 만료된다. 설정할 때는 잘 되다가 두 달 뒤에
"Invalid OAuth access token" 으로 막히는 게 이 때문이다.

이 스크립트는 토큰을 갱신하고 .env 를 자동으로 고쳐준다. 만료 **전에** 돌려야
한다 — 이미 만료됐으면 갱신이 안 되고 Meta 개발자 사이트에서 새로 받아야 한다.

    py refresh_token.py           # 갱신
    py refresh_token.py --check   # 남은 기간만 확인

한 달에 한 번쯤 돌리면 계속 유지된다.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import config as cfg


def _call(params: dict) -> tuple[int, dict]:
    url = (f"https://graph.instagram.com/refresh_access_token?"
           + urllib.parse.urlencode(params))
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


def write_env(token: str) -> None:
    env = cfg.BASE_DIR / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    out, done = [], False
    for ln in lines:
        if ln.strip().startswith("IG_ACCESS_TOKEN="):
            out.append(f"IG_ACCESS_TOKEN={token}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"IG_ACCESS_TOKEN={token}")
    env.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="인스타 액세스 토큰 갱신")
    ap.add_argument("--check", action="store_true", help="남은 기간만 확인")
    args = ap.parse_args()

    if not cfg.IG_ACCESS_TOKEN:
        print("[!] .env 에 IG_ACCESS_TOKEN 이 없다. 전자책 5장에서 토큰을 발급받아 .env 에 넣어라.")
        return 2

    code, data = _call({"grant_type": "ig_refresh_token",
                        "access_token": cfg.IG_ACCESS_TOKEN})
    if code != 200:
        msg = (data.get("error") or {}).get("message", "알 수 없는 오류")
        print(f"[!] 갱신 실패 (HTTP {code}): {msg}")
        print()
        print("    이미 만료됐으면 갱신이 안 된다. Meta 개발자 사이트에서 새로 발급받아라:")
        print("      https://developers.facebook.com/  →  내 앱  →  Instagram  →  Generate access token")
        print("    자세한 절차는 전자책 5장.")
        return 1

    expires = int(data.get("expires_in", 0))
    days = expires // 86400
    until = (datetime.now() + timedelta(seconds=expires)).strftime("%Y-%m-%d")

    if args.check:
        print(f"[i] 토큰 남은 기간: 약 {days}일 (~{until})")
        if days < 14:
            print("    곧 만료된다. --check 없이 실행해서 갱신해라.")
        return 0

    new_token = data.get("access_token")
    if not new_token:
        print("[!] 응답에 새 토큰이 없다.")
        return 1

    write_env(new_token)
    print(f"[+] 토큰을 갱신했다. 약 {days}일 유효 (~{until})")
    print(f"    .env 의 IG_ACCESS_TOKEN 을 새 값으로 바꿨다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
