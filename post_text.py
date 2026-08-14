"""릴스 글(캡션) · 해시태그 만들기.

**여기 값들은 업종을 탄다.** 만든 사람이 강사라 기본값이 교육·강의 계정
기준이다. 업종이 다르면 .env 에서 바꿔야 남의 업종 태그가 안 붙는다:

    REELS_DEFAULT_TAGS   주제를 못 잡았을 때 붙는 기본 해시태그
    REELS_CTA            글 마지막 문장 (여러 개는 | 로 나눈다. 하나를 고른다)
    REELS_TAG_RULES      키워드 → 해시태그 사전 파일 (tag_rules.txt)
    REELS_CAPTION_POOL   자막 후보 문구 파일 (caption_pool.txt)

기본 자막 문구는 아이들 수업 현장 말투다. 카페·공방이면 caption_pool.txt 를
두어 통째로 갈아끼운다. 자막을 직접 쓸 거면 사진 폴더의 captions.txt 가 우선이다.

@ai.co.lab (수현쌤) 계정의 실제 릴스 글을 보고 톤을 맞췄다:
  - 훅 한 줄 먼저, 그 다음 빈 줄
  - 존댓말 구어체 ("~했어요", "~더라고요")
  - 짧은 줄로 자주 개행. 긴 문단 안 씀
  - 이모지는 절제해서 몇 개만 (🤖 📌 😃)
  - CTA 로 마무리 (댓글/하트/DM 유도)
  - 해시태그는 한글 주제 태그 5개 내외. #instagood #추천 같은 범용 태그는 안 씀
"""

from __future__ import annotations

import random
import re
from pathlib import Path

import config as cfg

# 주제별 해시태그. 폴더 이름/자막에 키워드가 있으면 붙는다.
# 실제 계정(교육·강의)에서 쓰던 태그다. 업종이 다르면 tags.txt 로 갈아끼운다.
BUILTIN_TOPIC_TAGS = {
    "반도체": ["#반도체교육", "#반도체", "#진로교육"],
    "로봇": ["#로봇코딩", "#휴머노이드", "#피지컬ai"],
    "알파미니": ["#알파미니", "#로봇코딩", "#인공지능"],
    "코딩": ["#코딩교육", "#소프트웨어교육", "#블록코딩"],
    "ai": ["#인공지능", "#AI교육", "#생성형AI"],
    "인공지능": ["#인공지능", "#AI교육"],
    "수업": ["#수업나눔", "#교실현장"],
    "늘봄": ["#늘봄", "#방과후"],
    "초등": ["#초등", "#초등수업"],
    "영상": ["#AI영상제작", "#생성형AI"],
    "sora": ["#Sora", "#AI영상제작"],
    "미드저니": ["#미드저니", "#AI이미지"],
}

def load_topic_tags() -> dict[str, list[str]]:
    """키워드 → 해시태그 사전.

    tags.txt 가 있으면 그것만 쓴다 (내장 교육 사전을 **대체**한다).
    업종이 다른 사람이 내장 사전 위에 얹는 방식이면 #코딩교육 이 계속
    따라붙어서, 갈아끼우는 쪽이 맞다.

        형식:  키워드 = #태그1 #태그2
        예:    원두 = #스페셜티커피 #홈카페
    """
    f = cfg.TAGS_FILE
    if not f.exists():
        return BUILTIN_TOPIC_TAGS
    table: dict[str, list[str]] = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, vals = line.split("=", 1)
        tags = [t if t.startswith("#") else f"#{t}" for t in vals.split()]
        if key.strip() and tags:
            table[key.strip().lower()] = tags
    return table or BUILTIN_TOPIC_TAGS


# 주제를 못 잡았을 때 쓰는 기본값 / 글 마지막 CTA — 둘 다 .env 로 바꾼다
DEFAULT_TAGS = cfg.DEFAULT_TAGS
CTAS = cfg.CTA_LIST


def _match_tags(*sources: str) -> list[str]:
    low = " ".join(sources).lower()
    tags: list[str] = []
    for key, vals in load_topic_tags().items():
        if key in low:
            for v in vals:
                if v not in tags:
                    tags.append(v)
    return tags


def build_hashtags(folder_name: str, captions: list[str] | None = None,
                   extra: list[str] | None = None, limit: int = 6,
                   info: dict | None = None) -> list[str]:
    """한글 주제 태그 위주로 5~6개. 인스타는 30개까지 되지만 이 계정은 적게 쓴다."""
    tags: list[str] = []
    for t in (extra or []):
        t = t if t.startswith("#") else f"#{t}"
        if t not in tags:
            tags.append(t)

    # info.txt 값은 통째로 하나의 태그가 된다. 단어별로 쪼개면
    # "반도체 교구 & 코딩 수업" 이 #반도체 #교구 #코딩 #수업 이 돼서 쓸모없어진다.
    for key in ("주제", "교구", "도구", "장소", "기관"):
        val = (info or {}).get(key)
        if not val:
            continue
        for chunk in val.replace("&", "·").split("·"):
            # 해시태그에는 한글·영문·숫자·밑줄만 유효하다. 가운뎃점 같은 게
            # 섞이면 인스타가 거기서 태그를 끊어버린다.
            cleaned = re.sub(r"[^0-9A-Za-z가-힣_]", "", chunk)
            t = "#" + cleaned
            if len(t) > 2 and t not in tags:
                tags.append(t)

    for t in _match_tags(folder_name, " ".join(captions or []), *(info or {}).values()):
        if t not in tags:
            tags.append(t)

    if not tags:
        tags = list(DEFAULT_TAGS)
    return tags[:limit]


def build_caption(folder_name: str, captions: list[str],
                  extra_tags: list[str] | None = None,
                  info: dict | None = None) -> str:
    """자막을 재료로 릴스 본문 + 해시태그를 만든다.

    구조: 훅 / 빈 줄 / 본문(짧은 줄) / 빈 줄 / CTA / 빈 줄 / 해시태그
    """
    lines = [c.strip() for c in captions if c.strip()]

    if lines:
        hook = lines[0]
        body = lines[1:]
    else:
        hook = folder_name
        body = []

    parts = [hook, ""]
    if body:
        parts.extend(body)
        parts.append("")
    parts.append(random.choice(CTAS))
    parts.append("")
    parts.append(" ".join(build_hashtags(folder_name, captions, extra_tags, info=info)))
    return "\n".join(parts)


# 기본 톤은 **홍보**다. 자막은 궁금하게만 만드는 게 아니라 무엇인지
# 알려주는 역할이다. "맞혀보세요" 같은 퀴즈형은 쓰지 않는다.
#
# 원칙:
#   · 첫 컷에서 **어디서 무엇을 했는지** 밝힌다. 이게 홍보의 핵심이다.
#   · 중간은 무엇을 어떻게 하는지 구체적으로.
#   · 마지막은 다음으로 이어지게 닫는다.
#   · @ai.co.lab 톤 — 존댓말 구어체, 짧게.
#
# 장소·주제 같은 정보는 사진 폴더의 info.txt 에서 읽는다:
#   장소 = 하이닉스 연수원
#   주제 = 반도체 교구 & 코딩 수업
#   대상 = 초등 3~6학년
#   교구 = 반도체 교구


def read_info(folder: Path) -> dict:
    """사진 폴더의 info.txt 를 읽는다. `키 = 값` 한 줄에 하나."""
    f = folder / "info.txt"
    if not f.exists():
        return {}
    info: dict[str, str] = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k and v:
            info[k] = v
    return info


def _compact(text: str) -> str:
    """자막용으로 줄인다. & 는 가운뎃점으로, 군더더기 제거."""
    return (text.replace(" & ", "·").replace("&", "·")
                .replace(" 수업", " 수업").strip())


# 첫 컷에 붙일 궁금증 한 줄. info.txt 의 `훅 = ...` 으로 직접 쓸 수 있다.
#
# 계정 데이터 근거: 조회수 상위 릴스는 전부 첫 화면에 궁금증이 있었다.
#   2173회 "오늘도 고민중~~~"        1444회 "코딩은 자신있는데....."
#    786회 "생각보다 쉽지 않았던 이유"
# 반대로 하위는 사실만 진술했다.
#    67회 "자료구조 3일차 시작!"      81회 "제주대 코딩테스트 런케이션"
CURIOSITY = [
    "생각보다 쉽지 않았던 이유",
    "예상 못한 반응이 나왔어요",
    "이게 진짜 되네요^^",
    "반응이 달랐던 이유",
]


def _visible_len(text: str) -> int:
    """공백을 뺀 실제 글자 수. 자막 예산 계산용."""
    return len("".join(text.split()))


def caption_budget() -> int:
    """자막 한 컷에 들어가는 글자 수. images 가 폰트로 계산해준다."""
    try:
        import images
        return images.caption_char_budget()
    except Exception:
        return 18


def _hook(info: dict) -> str:
    """첫 컷 — 정보 + 궁금증 두 줄.

    홍보이므로 무슨 수업인지는 밝히되, 사실만 적으면 넘겨진다. 계정에서
    조회수가 높았던 릴스는 전부 첫 화면에 궁금증이 한 줄 더 있었다.
    """
    place = info.get("장소")
    topic = _compact(info.get("주제", "")) or None
    target = info.get("대상")
    hook_line = info.get("훅") or info.get("hook")
    # 자막은 2줄(약 18자)이 상한이다. 글자 크기는 고정이라 넘치면 잘린다.
    # 장소·주제를 다 넣으면 훅이 밀려나므로, 안 들어가면 짧은 쪽부터 버린다.
    # 버려진 정보는 피드 글과 해시태그에 그대로 들어간다.
    base = None
    if place and topic:
        base = f"{place} {topic}"
    elif topic and target:
        base = f"{target} {topic}"
    elif topic:
        base = topic
    elif place:
        base = f"{place} 수업"
    else:
        base = "오늘 수업 기록"

    # 궁금증을 붙인다. 직접 쓴 게 있으면 그걸 쓴다.
    tail = hook_line or random.Random(base).choice(CURIOSITY)

    # 예산 안에 맞춘다. 궁금증(tail)이 조회수를 끌므로 이걸 우선 남기고
    # 앞의 정보를 줄인다: 장소+주제 → 주제 → 없음.
    budget = caption_budget()
    for cand in (f"{base} {tail}", f"{topic or base} {tail}", tail):
        if _visible_len(cand) <= budget:
            return cand
    return tail


def load_caption_pool() -> dict[str, list[str]]:
    """자막 후보 문구. caption_pool.txt 가 있으면 그 유형만 갈아끼운다.

        형식:  유형 = 문구 | 문구 | 문구
        유형:  result wide practice collab tool closeup other ending

    기본값은 아이들 수업 말투라 업종이 다르면 그대로 쓸 수 없다.
    적어둔 유형만 바뀌고, 안 적은 유형은 기본값이 남는다.
    """
    if not cfg.CAPTION_POOL_FILE.exists():
        return {}
    table: dict[str, list[str]] = {}
    for line in cfg.CAPTION_POOL_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        kind, vals = line.split("=", 1)
        lines = [v.strip() for v in vals.split("|") if v.strip()]
        if kind.strip() and lines:
            table[kind.strip().lower()] = lines
    return table


def _line_for(kind: str, info: dict, rnd) -> str:
    """중간 컷 — **그 자리의 반응과 감정**을 적는다.

    @ai.co.lab 실제 자막을 보고 맞춘 톤이다:
        "둘이 동시에 외침!"  "알파미니 방구 뽕~~~~!!"
        "안 먹었어요...."     "오늘도 고민중~~~"

    특징: 관찰한 것을 그대로 옮긴 듯한 구어체. 물결(~~~)·느낌표·^^ 를 쓴다.
    말끝을 흐리는 `....` 은 쓰지 않는다 — 수업은 밝은 자리인데 어조가 반대로
    가서 사진과 안 맞는다. "다음에 더 좋은 걸로" 같은 격식체도 안 쓴다.
    """
    tool = info.get("교구") or info.get("도구")
    pools = {
        "result": [
            "이걸 아이들이 만들었어요!",
            "완성작 나왔습니다~",
            "직접 만든 결과물^^",
        ],
        "wide": [
            "다 모였어요~",
            "시작 전부터 신났음!",
            "자리 꽉 찼습니다~",
        ],
        "practice": [
            "다들 화면만 봐요^^",
            "집중 모드 돌입!",
            "손이 먼저 나감ㅋㅋ",
            "여기서부터 조용해짐~~~",
            f"{tool} 붙잡고 씨름 중~~~" if tool else "붙잡고 씨름 중~~~",
        ],
        "collab": [
            "둘이 동시에 외침!",
            "이거 어떻게 하냐고 난리~~~",
            "옆자리랑 같이 보는 중^^",
            "같이 하니까 금방 됨!",
            "머리 맞대고 고민중~~~",
        ],
        "tool": [
            "됐다고 소리 지름ㅋㅋ",
            "움직이니까 다 몰려옴!",
            "이게 진짜 되네~~~",
            f"{tool} 드디어 성공!" if tool else "드디어 성공!",
        ],
        "closeup": [
            "이 표정이 다 했다^^",
            "진지함 그 자체~~~",
        ],
        "other": [
            "이런 것도 합니다~",
            "계속 이어집니다~~~",
        ],
    }
    pools.update(load_caption_pool())   # 업종에 맞게 갈아끼운 것이 있으면 그것
    return rnd.choice(pools.get(kind, pools["other"]))


# 마지막 컷 자막. CTA 도, 격식 있는 마무리도 넣지 않는다. 마지막까지
# 아이들 반응으로 닫는다.
# 말끝을 흐리는 `....` 은 쓰지 않는다. 수업은 밝은 자리인데 어조가 반대로 간다.
# 밝게 닫는 `^^` `!` `ㅋㅋ` 를 쓴다.
ENDINGS = [
    "끝나고도 안 가려고 함ㅋㅋ",
    "다음 시간 언제냐고 물어봄!",
    "오늘 제일 신났던 순간^^",
    "다음 시간도 이렇게^^",
]


def build_story_captions(kinds: list[str], seed: str = "",
                         info: dict | None = None) -> list[str]:
    """장면 유형 순서 + 수업 정보로 자막을 만든다.

    첫 컷은 어디서 무슨 수업인지, 중간은 활동, 마지막은 마무리.
    같은 폴더면 같은 결과가 나오도록 폴더 이름으로 시드를 고정한다.
    """
    info = info or {}
    rnd = random.Random(seed or "reels")
    if not kinds:
        return []

    out = [_hook(info)]
    used = {out[0]}
    for kind in kinds[1:-1]:
        for _ in range(6):
            line = _line_for(kind, info, rnd)
            if line not in used:
                break
        used.add(line)
        out.append(line)
    if len(kinds) > 1:
        out.append(rnd.choice(load_caption_pool().get("ending") or ENDINGS))
    return out


def read_captions(folder: Path) -> list[str]:
    """사진 폴더의 captions.txt 를 읽는다. 한 줄에 컷 하나씩.

    자동 모드(watch_folder)에서 자막을 넣는 유일한 방법이다. 없으면 자막 없이
    만들어진다.
    """
    f = folder / "captions.txt"
    if not f.exists():
        return []
    lines = [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def read_overrides(folder: Path) -> tuple[str | None, list[str]]:
    """사진 폴더에 caption.txt / tags.txt 가 있으면 그걸 우선한다."""
    caption = None
    cap_file = folder / "caption.txt"
    if cap_file.exists():
        caption = cap_file.read_text(encoding="utf-8").strip() or None

    tags: list[str] = []
    tag_file = folder / "tags.txt"
    if tag_file.exists():
        raw = tag_file.read_text(encoding="utf-8")
        tags = [t.strip() for t in raw.replace(",", " ").split() if t.strip()]
    return caption, tags
