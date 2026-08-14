"""장면 분류 — 이 사진이 어떤 컷인가.

릴스는 화질 좋은 사진 4장을 모아둔 게 아니라 **이야기**여야 한다. 그래서
사진을 화질 점수로만 뽑지 않고, 필요한 장면 슬롯을 먼저 정하고 거기에 맞는
사진을 찾는다.

슬롯 (구성 순서 = 이야기 순서):
    result    결과물    — 만들어진 것·화면·완성품. **첫 화면으로 가장 강하다**
    wide      전체샷    — 어떤 자리인지 보여준다. 사람이 모여 있으면 더 좋다
    practice  활동샷    — 뭘 하고 있는지. 손이 움직이는 장면
    collab    함께샷    — 두세 명이 같이 있는 장면. 없을 수도 있다
    tool      도구샷    — 도구·장비·재료를 쓰는 장면. 있을 때만

(이름은 수업 사진에서 출발했지만 판별은 얼굴 배치와 밝기로만 한다. 카페든
공방이든 "전체 → 활동 → 함께 → 도구" 라는 순서는 그대로 쓸 만하다.)

자동으로 판별되는 것과 아닌 것:
    · result 는 얼굴이 하나도 없는 사진이면 자동으로 잡힌다 (화면·작품·교구).
    · wide / collab / closeup 은 **얼굴 배치**로 구분된다 (개수·크기·퍼짐).
    · practice / tool 은 물체를 알아봐야 해서 얼굴 감지기만으로는 안 된다.
      사진 폴더에 `shots.txt` 를 두면 사진별 유형을 직접 지정할 수 있다.

shots.txt 형식 (한 줄에 하나, `파일명 = 유형`):
    20260722_101456.jpg = practice
    20260722_103543.jpg = tool
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

RESULT = "result"
WIDE = "wide"
PRACTICE = "practice"
COLLAB = "collab"
TOOL = "tool"
CLOSEUP = "closeup"
OTHER = "other"

# 이야기 순서대로. 앞에 있을수록 먼저 배치된다.
#
# 결과물을 맨 앞에 둔 이유: 계정에서 조회수가 높았던 릴스(2173/1444)는 모두
# 만들어진 결과물 화면이 첫 화면을 채웠다. 반대로 뒷모습·현수막으로 시작한
# 것들은 하위였다. 릴스는 첫 1~2초에 넘길지 말지가 갈린다.
SLOT_ORDER = [RESULT, WIDE, PRACTICE, COLLAB, TOOL]

LABELS = {
    RESULT: "결과물",
    WIDE: "전체샷",
    PRACTICE: "활동샷",
    COLLAB: "함께샷",
    TOOL: "도구샷",
    CLOSEUP: "클로즈업",
    OTHER: "기타",
}

# --- 판별 임계값 (실측 기반) --------------------------------------------
# 전체샷: 얼굴이 많고 작게 흩어져 있다  (실측 10명 / 평균 2.6~2.9% / 퍼짐 0.74)
WIDE_MIN_FACES = 5
WIDE_MAX_AVG_RATIO = 0.045
# 함께샷: 두세 명이 가까이 붙어 있다     (실측 4명 / 퍼짐 0.37)
COLLAB_MAX_FACES = 4
COLLAB_MAX_SPREAD = 0.55


@dataclass
class Scene:
    kind: str = OTHER
    density: float = 0.0     # 밀집도 점수. 높을수록 사람이 붙어 있다
    faces: int = 0
    spread: float = 0.0
    manual: bool = False     # shots.txt 로 지정된 것인가


def read_shot_tags(folder: Path) -> dict[str, str]:
    """shots.txt 를 읽어 {파일명: 유형} 으로 돌려준다."""
    f = folder / "shots.txt"
    if not f.exists():
        return {}
    tags: dict[str, str] = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, kind = line.split("=", 1)
        kind = kind.strip().lower()
        if kind in LABELS:
            tags[name.strip()] = kind
    return tags


def classify(path: Path, face_info, tags: dict[str, str] | None = None) -> Scene:
    """얼굴 배치로 장면을 분류한다. shots.txt 지정이 있으면 그게 우선."""
    tags = tags or {}
    faces = list(getattr(face_info, "faces", None) or [])

    scene = Scene(faces=len(faces))

    if not faces:
        # 얼굴이 없으면 화면·작품·교구 클로즈업일 가능성이 높다. 이런 컷이
        # 릴스 첫 화면으로 가장 강하다. shots.txt 로 다르게 지정할 수 있다.
        scene.kind = tags.get(path.name, RESULT)
        scene.manual = path.name in tags
        return scene

    try:
        w = ImageOps.exif_transpose(Image.open(path)).width
    except Exception:
        w = 1

    centers = [f.box[0] + f.box[2] / 2 for f in faces]
    scene.spread = (max(centers) - min(centers)) / w if len(faces) > 1 else 0.0
    avg_ratio = statistics.mean(f.ratio for f in faces)

    # 밀집도: 얼굴 수가 많고 좁게 모여 있을수록 높다
    if len(faces) > 1 and scene.spread > 0:
        scene.density = len(faces) / (scene.spread * 10)
    else:
        scene.density = 0.0

    if path.name in tags:
        scene.kind = tags[path.name]
        scene.manual = True
        return scene

    if len(faces) >= WIDE_MIN_FACES and avg_ratio < WIDE_MAX_AVG_RATIO:
        scene.kind = WIDE
    elif 2 <= len(faces) <= COLLAB_MAX_FACES and scene.spread <= COLLAB_MAX_SPREAD:
        scene.kind = COLLAB
    elif len(faces) == 1:
        scene.kind = CLOSEUP
    else:
        scene.kind = OTHER
    return scene


def compose(shots: list, want: int) -> list:
    """슬롯을 채우는 방식으로 고른다. shots 는 Shot 목록 (scene 속성 필요).

    1) 이야기 순서대로 슬롯을 하나씩 채운다 (해당 유형 중 최고점)
    2) 남는 자리는 점수순으로 채우되 같은 유형이 몰리지 않게 한다
    3) 마지막에 촬영 시간순으로 정렬한다
    """
    picked: list = []
    used: set = set()

    def best_of(kind: str):
        cands = [s for s in shots if s not in picked and s.scene.kind == kind]
        if not cands:
            return None
        # 전체샷은 밀집도가 높은 쪽을 우선한다
        if kind == WIDE:  # noqa: SIM108
            return max(cands, key=lambda s: (s.scene.density, s.score))
        return max(cands, key=lambda s: s.score)

    for kind in SLOT_ORDER:
        if len(picked) >= want:
            break
        s = best_of(kind)
        if s is not None:
            picked.append(s)
            used.add(kind)

    # 남는 자리 — 아직 안 쓴 유형을 먼저, 그다음 점수순
    rest = sorted(
        (s for s in shots if s not in picked),
        key=lambda s: (s.scene.kind in used, -s.score),
    )
    for s in rest:
        if len(picked) >= want:
            break
        picked.append(s)

    # 결과물 컷은 **맨 앞에 고정**한다. 나머지는 촬영 시간순으로 놓아 수업
    # 흐름이 보이게 한다. 전부 시간순으로 정렬하면 나중에 찍힌 결과물이
    # 뒤로 밀려서 첫 화면에 두려던 의미가 사라진다.
    head = [s for s in picked if s.scene.kind == RESULT][:1]
    tail = [s for s in picked if s not in head]
    tail.sort(key=lambda s: s.taken)
    return head + tail
