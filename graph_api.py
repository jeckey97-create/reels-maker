"""Instagram Graph API 로 릴스 게시.

전제 (네가 한 번 해둬야 하는 것):
  1. 인스타 계정을 비즈니스 또는 크리에이터로 전환
  2. 페이스북 페이지와 연결
  3. Meta 앱 등록 → instagram_business_content_publish 권한
  4. 장기 액세스 토큰 발급 → .env 의 IG_ACCESS_TOKEN
  5. IG 유저 ID → .env 의 IG_USER_ID

중요: Graph API 는 **공개 URL** 로 영상을 가져간다. 로컬 파일 경로는 안 된다.
      out/ 를 어딘가에 올려서 https:// 로 접근 가능하게 만들어야 한다.

주의: 인스타 음원 라이브러리(인기 음원)는 API 로 붙일 수 없다. 앱 전용 기능이다.
      음악이 필요하면 영상에 미리 구워 넣어야 하고, 저작권 음원을 구우면
      자동 음소거되거나 삭제될 수 있다. music/ 에는 로열티프리 음원만 넣어라.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
import json

import config as cfg


class GraphError(RuntimeError):
    pass


def _post(path: str, params: dict) -> dict:
    url = f"https://graph.instagram.com/{cfg.GRAPH_VERSION}/{path}"
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise GraphError(f"{path} 실패 {e.code}: {e.read().decode()[:400]}") from e


def _get(path: str, params: dict) -> dict:
    url = f"https://graph.instagram.com/{cfg.GRAPH_VERSION}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise GraphError(f"{path} 실패 {e.code}: {e.read().decode()[:400]}") from e


_USER_ID_CACHE: str | None = None


def resolve_user_id() -> str:
    """IG 사용자 ID. .env 에 없으면 토큰으로 조회한다.

    토큰만 있으면 사용자 ID 는 /me 로 얻을 수 있다. 옮겨 적을 값을 하나로
    줄이면 오타로 막힐 일도 준다.
    """
    global _USER_ID_CACHE
    if cfg.IG_USER_ID:
        return cfg.IG_USER_ID
    if _USER_ID_CACHE:
        return _USER_ID_CACHE
    if not cfg.IG_ACCESS_TOKEN:
        raise GraphError(".env 에 IG_ACCESS_TOKEN 이 없다")
    data = _get("me", {"fields": "id", "access_token": cfg.IG_ACCESS_TOKEN})
    uid = data.get("id")
    if not uid:
        raise GraphError(f"사용자 ID 를 얻지 못했다: {data}")
    _USER_ID_CACHE = uid
    return uid


def configured() -> bool:
    """토큰만 있으면 된다. 사용자 ID 는 토큰으로 조회한다."""
    return bool(cfg.IG_ACCESS_TOKEN)


def create_container(video_url: str, caption: str) -> str:
    """릴스 컨테이너 생성 → container id."""
    res = _post(
        f"{resolve_user_id()}/media",
        {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": cfg.IG_ACCESS_TOKEN,
        },
    )
    cid = res.get("id")
    if not cid:
        raise GraphError(f"컨테이너 id 가 없다: {res}")
    return cid


def create_image_container(image_url: str, caption: str) -> str:
    """피드 사진 1장 컨테이너.

    사진은 media_type 을 생략하면 IMAGE 로 처리된다. 명시해도 되지만
    구버전 API 에서 거부하는 경우가 있어 넣지 않는다.
    """
    res = _post(
        f"{resolve_user_id()}/media",
        {
            "image_url": image_url,
            "caption": caption,
            "access_token": cfg.IG_ACCESS_TOKEN,
        },
    )
    cid = res.get("id")
    if not cid:
        raise GraphError(f"컨테이너 id 가 없다: {res}")
    return cid


def create_carousel_item(image_url: str) -> str:
    """캐러셀에 들어갈 사진 한 장. 글은 붙이지 않는다 (묶음에 붙는다)."""
    res = _post(
        f"{resolve_user_id()}/media",
        {
            "image_url": image_url,
            "is_carousel_item": "true",
            "access_token": cfg.IG_ACCESS_TOKEN,
        },
    )
    cid = res.get("id")
    if not cid:
        raise GraphError(f"캐러셀 항목 id 가 없다: {res}")
    return cid


def create_carousel_container(children: list[str], caption: str) -> str:
    """사진 컨테이너들을 하나의 캐러셀로 묶는다."""
    res = _post(
        f"{resolve_user_id()}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption,
            "access_token": cfg.IG_ACCESS_TOKEN,
        },
    )
    cid = res.get("id")
    if not cid:
        raise GraphError(f"캐러셀 컨테이너 id 가 없다: {res}")
    return cid


def wait_ready(container_id: str, timeout: int = 300) -> None:
    """인스타가 영상을 다 받고 처리할 때까지 기다린다."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = _get(container_id, {"fields": "status_code,status", "access_token": cfg.IG_ACCESS_TOKEN})
        code = res.get("status_code")
        if code == "FINISHED":
            return
        # 사진은 만들어지자마자 준비된 상태라 status_code 를 안 주기도 한다.
        # 영상만 처리 시간이 걸린다. 값이 없으면 기다릴 이유가 없다.
        if code is None:
            return
        if code in ("ERROR", "EXPIRED"):
            raise GraphError(f"컨테이너 처리 실패: {res}")
        time.sleep(5)
    raise GraphError("컨테이너 처리 시간 초과")


def publish(container_id: str) -> str:
    res = _post(
        f"{resolve_user_id()}/media_publish",
        {"creation_id": container_id, "access_token": cfg.IG_ACCESS_TOKEN},
    )
    mid = res.get("id")
    if not mid:
        raise GraphError(f"게시 실패: {res}")
    return mid


def publish_image(image_url: str, caption: str, dry_run: bool = True) -> str | None:
    """피드 사진 1장 게시."""
    if dry_run:
        print("[dry-run] 실제로 게시하지 않는다.")
        print(f"  image_url: {image_url}")
        print(f"  caption:\n{caption}")
        return None
    if not configured():
        raise GraphError(".env 에 IG_USER_ID / IG_ACCESS_TOKEN 이 없다")
    cid = create_image_container(image_url, caption)
    print(f"[i] 컨테이너 {cid} 생성")
    wait_ready(cid)
    mid = publish(cid)
    print(f"[+] 게시 완료: media id {mid}")
    return mid


def publish_carousel(image_urls: list[str], caption: str,
                     dry_run: bool = True) -> str | None:
    """캐러셀(사진 여러 장) 게시. 인스타 상한은 10장이다."""
    if not 2 <= len(image_urls) <= 10:
        raise GraphError(f"캐러셀은 2~10장이어야 한다 (지금 {len(image_urls)}장)")
    if dry_run:
        print("[dry-run] 실제로 게시하지 않는다.")
        for i, u in enumerate(image_urls, 1):
            print(f"  {i}. {u}")
        print(f"  caption:\n{caption}")
        return None
    if not configured():
        raise GraphError(".env 에 IG_USER_ID / IG_ACCESS_TOKEN 이 없다")

    children = []
    for i, url in enumerate(image_urls, 1):
        children.append(create_carousel_item(url))
        print(f"[i] {i}/{len(image_urls)}장 올림")
    cid = create_carousel_container(children, caption)
    print(f"[i] 캐러셀 컨테이너 {cid} 생성, 처리 대기 중…")
    wait_ready(cid)
    mid = publish(cid)
    print(f"[+] 게시 완료: media id {mid}")
    return mid


def publish_reel(video_url: str, caption: str, dry_run: bool = True) -> str | None:
    """릴스 게시. dry_run 이면 실제로 올리지 않고 무엇을 올릴지만 보여준다."""
    if dry_run:
        print("[dry-run] 실제로 게시하지 않는다.")
        print(f"  video_url: {video_url}")
        print(f"  caption:\n{caption}")
        return None
    if not configured():
        raise GraphError(".env 에 IG_USER_ID / IG_ACCESS_TOKEN 이 없다")
    cid = create_container(video_url, caption)
    print(f"[i] 컨테이너 {cid} 생성, 처리 대기 중…")
    wait_ready(cid)
    mid = publish(cid)
    print(f"[+] 게시 완료: media id {mid}")
    return mid
