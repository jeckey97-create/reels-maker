"""사진 선별 — 어떤 사진을 릴스에 넣을지 정하는 기준.

수업 사진 수십 장을 그냥 파일명 순으로 뽑으면 흔들린 사진, 연사로 찍은
똑같은 컷, 어두운 컷이 그대로 들어간다. 그래서 아래 기준으로 거르고 점수를 매긴다.

**초상권이 첫 번째 기준이다.** 화질이 아무리 좋아도 학생 얼굴이 식별되는
사진은 쓰지 않는다. 공개 계정에 한 번 올라가면 되돌리기 어렵다.

── 0순위: 수동 승인 ──────────────────────────────────
  사진 폴더 안에 `ok/` 하위폴더가 있으면 **거기 있는 사진만** 후보가 된다.
  네가 직접 고른 것이므로 얼굴 검사를 하지 않는다.

── 하드 필터 (아예 제외) ─────────────────────────────
  · 얼굴 식별        — 크게 찍힌 **정면** 얼굴. 옆모습은 식별이 어려워 통과시킨다.
                       (크기 4% 이상 + 정면도 0.35 미만)
                       정책이 blur 면 제외 대신 그 얼굴만 모자이크 처리한다
  · 흔들린 사진      — 라플라시안 분산이 낮으면 초점이 안 맞은 것
  · 노출 실패        — 너무 어둡거나 하얗게 날아간 것
  · 해상도 미달      — 세로 1920 을 채우지 못하는 것
  · 중복             — 이미 뽑은 사진과 거의 같은 것 (연사 컷)

── 점수 (높을수록 먼저 뽑힘) ────────────────────────
  · 선명도    최대 35점 — 릴스는 화면이 작아서 흔들림이 특히 눈에 띈다
  · 노출      최대 25점 — 중간 밝기에 가까울수록 높다
  · 세로 사진 최대 20점 — 9:16 에 크롭해도 안 잘린다
  · 색 다양성 최대 20점 — 밋밋한 벽/책상만 찍힌 컷을 뒤로 민다

  · 얼굴 없음 최대 25점 — 뒷모습·손·화면·결과물 위주로 뽑히게 하는 가산점.
                          얼굴이 작을수록 높고, 아예 없으면 만점.

  얼굴에 **가산점이 아니라 감점**을 주는 게 핵심이다. 예전 배점은 얼굴이 큰
  사진을 우대해서 정확히 반대로 동작했다.

── 마지막 배치: 장면 슬롯 ───────────────────────────
  화질 좋은 사진을 모아둔다고 릴스가 되지 않는다. 이야기가 있어야 한다.
  그래서 점수순으로 자르지 않고 scene.py 가 정한 슬롯을 채운다.

      전체샷 → 실습샷 → 협동샷 → 교구샷

  각 슬롯에서 최고점 1장씩 뽑고, 남는 자리는 아직 안 쓴 유형을 우선해 채운다.
  마지막에 촬영 시간순으로 정렬해서 수업 흐름이 순서대로 담기게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, ImageStat

import config as cfg
import face_guard
import scene as scene_mod

# --- 임계값 -------------------------------------------------------------
BLUR_MIN = 45.0        # 라플라시안 분산이 이보다 낮으면 흔들린 것으로 본다
BRIGHT_MIN = 40        # 0~255. 이보다 어두우면 제외
BRIGHT_MAX = 225       # 이보다 밝으면 날아간 것
MIN_LONG_EDGE = 1200   # 긴 변이 이보다 짧으면 화질 부족
DUP_HASH_DIST = 6      # aHash 해밍거리가 이 이하면 같은 사진 취급

@dataclass
class Shot:
    path: Path
    sharpness: float = 0.0
    brightness: float = 0.0
    portrait: bool = False
    colorfulness: float = 0.0
    faces: int = 0
    face_ratio: float = 0.0
    face_boxes: list = field(default_factory=list)
    consented: bool = False
    scene: object = None
    needs_blur: bool = False
    crop_box: tuple | None = None
    ahash: int = 0
    taken: float = 0.0
    score: float = 0.0
    rejected: str = ""
    reasons: list[str] = field(default_factory=list)


def _load_small(path: Path, size: int = 480) -> Image.Image:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((size, size))
    return img


def _sharpness(gray: Image.Image) -> float:
    """라플라시안 필터를 먹인 뒤 분산. 높을수록 선명하다."""
    lap = gray.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1))
    return ImageStat.Stat(lap).stddev[0] ** 2


def _colorfulness(img: Image.Image) -> float:
    stat = ImageStat.Stat(img)
    return sum(stat.stddev) / 3.0


def _ahash(gray: Image.Image) -> int:
    small = gray.resize((8, 8), Image.LANCZOS)
    pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p >= avg:
            bits |= 1 << i
    return bits


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def measure(path: Path, folder: Path | None = None,
            tags: dict | None = None) -> Shot:
    shot = Shot(path=path)
    shot.consented = bool(folder and face_guard.is_consented(path, folder))
    try:
        full = ImageOps.exif_transpose(Image.open(path))
        w, h = full.size
        shot.portrait = h >= w
        if max(w, h) < MIN_LONG_EDGE:
            shot.rejected = f"해상도 부족 ({w}x{h})"
            return shot
        img = _load_small(path)
    except Exception as e:
        shot.rejected = f"열기 실패 ({e})"
        return shot

    gray = img.convert("L")
    shot.sharpness = _sharpness(gray)
    shot.brightness = ImageStat.Stat(gray).mean[0]
    shot.colorfulness = _colorfulness(img)
    shot.ahash = _ahash(gray)
    try:
        shot.taken = path.stat().st_mtime
    except OSError:
        shot.taken = 0.0

    if shot.sharpness < BLUR_MIN:
        shot.rejected = f"흔들림 (선명도 {shot.sharpness:.0f})"
    elif shot.brightness < BRIGHT_MIN:
        shot.rejected = f"너무 어두움 (밝기 {shot.brightness:.0f})"
    elif shot.brightness > BRIGHT_MAX:
        shot.rejected = f"노출 날아감 (밝기 {shot.brightness:.0f})"
    if shot.rejected:
        return shot

    # 초상권 검사 — 승인 폴더(ok/) 사진은 건너뛴다
    if not shot.consented and cfg.FACE_POLICY != "off":
        info = face_guard.detect(path)
        if not info.available:
            # 여기서 통과시키면 안 된다. 얼굴을 못 거른 채 올라가는 것보다
            # 아무것도 안 만드는 쪽이 낫다. 대신 원인을 정확히 알려준다.
            shot.rejected = ("얼굴 감지기를 쓸 수 없다 — py setup_check.py 로 "
                             "모델과 opencv 를 확인해라")
            return shot
        shot.faces = info.count
        shot.face_ratio = info.max_ratio
        shot.face_boxes = info.boxes or []
        shot.scene = scene_mod.classify(path, info, tags)
        risky = info.risky()
        if risky:
            # 문제 얼굴이 가장자리에 있으면 잘라내서 살릴 수 있다
            from PIL import Image as _I
            try:
                _im = ImageOps.exif_transpose(_I.open(path))
                box = face_guard.crop_out_faces(
                    _im.size, [f.box for f in risky],
                    [f.box for f in info.faces if f not in risky])
            except Exception:
                box = None
            if box is not None and cfg.FACE_CROP:
                shot.crop_box = box
                risky = []
            elif cfg.FACE_POLICY == "blur":
                shot.needs_blur = True
            else:
                shot.rejected = (f"정면 얼굴 식별됨 ({len(risky)}명, "
                                 f"최대 {max(f.ratio for f in risky):.1%})")
    return shot


def score(shot: Shot) -> float:
    """0~100. 위 문서의 배점 그대로."""
    s = 0.0
    s += min(35.0, shot.sharpness / 400.0 * 35.0)          # 선명도
    s += max(0.0, 25.0 - abs(shot.brightness - 128) / 128 * 25.0)  # 노출
    s += 20.0 if shot.portrait else 0.0                     # 세로
    s += min(20.0, shot.colorfulness / 70.0 * 20.0)         # 색 다양성
    # 얼굴은 감점 대상이다. 없으면 만점, 클수록 0 에 가깝다.
    if shot.faces == 0:
        s += 25.0
    else:
        s += max(0.0, 25.0 * (1.0 - shot.face_ratio / max(cfg.FACE_MAX_RATIO, 1e-6)))
    return s


def choose(photos: list[Path], want: int, verbose: bool = True,
           folder: Path | None = None) -> list[Shot]:
    """기준에 따라 want 장을 고른다. 반환은 촬영 시간순."""
    tags = scene_mod.read_shot_tags(folder) if folder else {}
    if tags:
        print(f"[선별] shots.txt 에서 {len(tags)}개 유형 지정을 읽었다.")
    shots = [measure(p, folder, tags) for p in photos]
    for s in shots:
        s.score = score(s)

    ok = [s for s in shots if not s.rejected]
    dropped = [s for s in shots if s.rejected]

    if verbose:
        print(f"[선별] 후보 {len(shots)}장 → 통과 {len(ok)}장, 제외 {len(dropped)}장")
        for s in dropped[:8]:
            print(f"    - {s.path.name}: {s.rejected}")
        if len(dropped) > 8:
            print(f"    - … 외 {len(dropped)-8}장")

    if not ok:
        faced = [s for s in dropped if "얼굴" in s.rejected]
        if faced:
            print()
            print(f"[!] 쓸 수 있는 사진이 없다. {len(faced)}장이 얼굴 식별로 걸렸다.")
            print("    선택지:")
            print("      1) 사진 폴더에 ok/ 를 만들고 써도 되는 사진만 넣기 (동의받은 것)")
            print("      2) .env 에 REELS_FACE_POLICY=blur — 얼굴을 모자이크 처리해서 사용")
            print("      3) 얼굴이 안 나온 사진(뒷모습·손·화면·결과물)을 폴더에 추가")
        return []

    # 연사 중복부터 걷어낸다
    ok.sort(key=lambda s: -s.score)
    deduped: list[Shot] = []
    for cand in ok:
        if all(_hamming(cand.ahash, p.ahash) > DUP_HASH_DIST for p in deduped):
            deduped.append(cand)

    # 장면 슬롯을 채우는 방식으로 고른다 (전체샷 → 실습 → 협동 → 교구)
    for sh in deduped:
        if sh.scene is None:
            sh.scene = scene_mod.Scene()
    picked = scene_mod.compose(deduped, want)
    if verbose:
        print("[선별] 최종 선택:")
        for s in picked:
            bits = [f"점수 {s.score:.0f}", f"선명도 {s.sharpness:.0f}"]
            if s.consented:
                bits.append("승인됨(ok/)")
            elif s.faces:
                bits.append(f"얼굴 {s.faces}명 {s.face_ratio:.1%}" + (" →블러" if s.needs_blur else ""))
            else:
                bits.append("얼굴 없음")
            bits.append("세로" if s.portrait else "가로")
            label = scene_mod.LABELS.get(getattr(s.scene, "kind", ""), "?")
            if getattr(s.scene, "manual", False):
                label += "(지정)"
            print(f"    + [{label}] {s.path.name}  ({', '.join(bits)})")
    return picked
