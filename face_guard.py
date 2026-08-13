"""초상권 안전장치 — 얼굴 감지 · 블러 처리.

수업 사진에는 학생 얼굴이 들어간다. 공개 계정에 올라가면 되돌리기 어려우므로
사진 선별 단계에서 먼저 거른다.

판정 기준은 **"누구인지 알아볼 수 있느냐"** 다. 얼굴이 찍혔다는 사실 자체가
아니라 식별 가능성이 문제이므로, 두 가지를 같이 본다.

    1) 크기   ratio = 얼굴 폭 / 사진 폭
              작게 찍힌 얼굴은 확대해도 특정이 어렵다.
    2) 정면도 yaw = |코 x - 두 눈 중점 x| / 눈 사이 거리
              0 에 가까우면 정면, 크면 옆모습이다. 옆모습은 식별이 어렵다.

    식별 가능 = ratio >= FACE_ABSOLUTE_MAX_RATIO                    (각도 무관)
             또는 (ratio >= FACE_MAX_RATIO 그리고 yaw < FACE_PROFILE_YAW)

    크기 상한을 따로 둔 이유: 옆모습이어도 얼굴이 화면에서 충분히 크면
    누구인지 알아볼 수 있다. 실제로 정면도 1.72 짜리 옆모습이 8.9% 크기로
    찍혀 통과했는데 식별 가능한 수준이었다.

얼굴마다 따로 판정한다. 한 사진에 옆모습 큰 얼굴과 정면 작은 얼굴이 섞일 수
있어서, 사진 전체를 하나로 뭉뚱그리면 안 된다.

정책 (config.FACE_POLICY):
    "exclude"  얼굴이 식별되는 사진을 후보에서 뺀다 (기본)
    "blur"     빼는 대신 얼굴을 모자이크 처리해서 쓴다
    "off"      검사하지 않는다 (동의를 이미 받은 사진만 쓸 때)

수동 확인이 항상 우선한다. 사진 폴더 안에 `ok/` 하위폴더를 두면 거기 있는
사진은 검사 없이 통과한다 — 네가 직접 "이건 써도 된다"고 표시한 것이다.

모델: assets/models/face_detection_yunet_2023mar.onnx (OpenCV opencv_zoo, YuNet)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

import config as cfg

_DETECTOR = None
_TRIED = False


@dataclass
class Face:
    box: tuple[int, int, int, int]   # 원본 좌표계 (x, y, w, h)
    ratio: float                     # 얼굴 폭 / 사진 폭
    yaw: float                       # 0=정면, 클수록 옆모습

    def identifiable(self) -> bool:
        """식별 가능한가.

        두 경우다:
          1) 크게 찍힌 정면 얼굴
          2) 옆모습이어도 아주 크게 찍힌 얼굴 — 각도와 무관하게 알아볼 수 있다
        """
        if self.ratio >= cfg.FACE_ABSOLUTE_MAX_RATIO:
            return True
        return self.ratio >= cfg.FACE_MAX_RATIO and self.yaw < cfg.FACE_PROFILE_YAW


@dataclass
class FaceInfo:
    faces: list = None            # Face 목록
    available: bool = True        # 감지기를 못 쓰면 False

    @property
    def count(self) -> int:
        return len(self.faces or [])

    @property
    def max_ratio(self) -> float:
        return max((f.ratio for f in (self.faces or [])), default=0.0)

    def risky(self) -> list:
        """식별 가능한 얼굴만."""
        return [f for f in (self.faces or []) if f.identifiable()]

    def identifiable(self) -> bool:
        return bool(self.risky())

    @property
    def boxes(self) -> list:
        """블러 대상 = 식별 가능한 얼굴만. 옆모습은 안 가린다."""
        return [f.box for f in self.risky()]


def detector():
    """YuNet 감지기. 모델이나 opencv 가 없으면 None."""
    global _DETECTOR, _TRIED
    if _TRIED:
        return _DETECTOR
    _TRIED = True
    try:
        import cv2  # type: ignore

        if not cfg.FACE_MODEL.exists():
            return None
        _DETECTOR = cv2.FaceDetectorYN_create(str(cfg.FACE_MODEL), "", (320, 320), 0.6, 0.3, 5000)
    except Exception:
        _DETECTOR = None
    return _DETECTOR


def detect(path: Path, work_long_edge: int = 960) -> FaceInfo:
    """사진에서 얼굴을 찾는다. 좌표는 원본 해상도로 환산해서 돌려준다."""
    det = detector()
    if det is None:
        return FaceInfo(available=False)

    try:
        import cv2  # type: ignore
        import numpy as np

        full = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        ow = full.width
        small = full.copy()
        small.thumbnail((work_long_edge, work_long_edge))
        arr = cv2.cvtColor(np.array(small), cv2.COLOR_RGB2BGR)
        h, w = arr.shape[:2]
        det.setInputSize((w, h))
        _, faces = det.detect(arr)
    except Exception:
        return FaceInfo(available=False)

    if faces is None or len(faces) == 0:
        return FaceInfo(faces=[])

    scale = ow / w
    out: list[Face] = []
    for f in faces:
        # 랜드마크: 오른눈(4,5) 왼눈(6,7) 코(8,9) 입꼬리(10~13)
        rex, lex, nx = float(f[4]), float(f[6]), float(f[8])
        eye_mid = (rex + lex) / 2.0
        eye_d = abs(lex - rex)
        yaw = abs(nx - eye_mid) / eye_d if eye_d > 1e-6 else 0.0
        out.append(Face(
            box=(int(f[0] * scale), int(f[1] * scale),
                 int(f[2] * scale), int(f[3] * scale)),
            ratio=float(f[2]) / w,
            yaw=yaw,
        ))
    return FaceInfo(faces=out)


def blur_faces(img: Image.Image, boxes: list[tuple[int, int, int, int]],
               pad: float = 0.25) -> Image.Image:
    """얼굴 영역을 강하게 흐린다. 박스보다 조금 넓게 잡아 머리·턱까지 덮는다."""
    if not boxes:
        return img
    out = img.copy()
    for (x, y, w, h) in boxes:
        px, py = int(w * pad), int(h * pad)
        x0 = max(0, x - px)
        y0 = max(0, y - py)
        x1 = min(out.width, x + w + px)
        y1 = min(out.height, y + h + py)
        if x1 <= x0 or y1 <= y0:
            continue
        region = out.crop((x0, y0, x1, y1))
        radius = max(8, int(min(x1 - x0, y1 - y0) / 4))
        out.paste(region.filter(ImageFilter.GaussianBlur(radius)), (x0, y0))
    return out


# 잘라낸 뒤에도 이만큼은 남아야 한다 (원본 면적 대비).
# 낮게 잡으면 얼굴을 지우려고 사람 머리를 잘라내서 몸통만 남은 사진이 나온다.
# "가장자리에 살짝 걸친 얼굴만 쳐낸다" 는 뜻이 되도록 높게 잡는다.
MIN_CROP_AREA = 0.75
# 위쪽을 잘라내면 머리가 날아간다. 세로 방향은 훨씬 보수적으로 본다.
MIN_CROP_AREA_VERTICAL = 0.85


def crop_out_faces(size: tuple[int, int], risky_boxes: list,
                   keep_boxes: list | None = None) -> tuple[int, int, int, int] | None:
    """식별 얼굴을 잘라내는 크롭 영역을 찾는다.

    얼굴이 가장자리에 있으면 그쪽을 잘라내서 사진을 살릴 수 있다. 네 방향
    각각에 대해 "이 방향에서 얼마나 잘라내야 문제 얼굴이 전부 빠지는가" 를
    계산하고, 면적이 가장 많이 남는 방향을 고른다.

    반환: (x0, y0, x1, y1) 또는 None(잘라도 안 되는 경우).
    잘린 뒤 남는 면적이 원본의 MIN_CROP_AREA 미만이면 포기한다.
    """
    if not risky_boxes:
        return None
    W, H = size
    best = None

    # 오른쪽을 잘라낸다 → 문제 얼굴들의 가장 왼쪽 경계까지만 남긴다
    x1 = min(b[0] for b in risky_boxes)
    candidates = [(0, 0, x1, H)]
    # 왼쪽을 잘라낸다
    x0 = max(b[0] + b[2] for b in risky_boxes)
    candidates.append((x0, 0, W, H))
    # 아래를 잘라낸다
    y1 = min(b[1] for b in risky_boxes)
    candidates.append((0, 0, W, y1))
    # 위를 잘라낸다
    y0 = max(b[1] + b[3] for b in risky_boxes)
    candidates.append((0, y0, W, H))

    total = W * H
    for idx, (cx0, cy0, cx1, cy1) in enumerate(candidates):
        cw, ch = cx1 - cx0, cy1 - cy0
        if cw <= 0 or ch <= 0:
            continue
        area = cw * ch
        vertical = idx >= 2      # 0,1=좌우 / 2,3=상하
        floor = MIN_CROP_AREA_VERTICAL if vertical else MIN_CROP_AREA
        if area / total < floor:
            continue
        # 남겨야 할 얼굴(작거나 옆모습)이 잘려나가면 감점
        kept = 0
        for b in (keep_boxes or []):
            bx = b[0] + b[2] / 2
            by = b[1] + b[3] / 2
            if cx0 <= bx <= cx1 and cy0 <= by <= cy1:
                kept += 1
        score = area / total + kept * 0.05
        if best is None or score > best[0]:
            best = (score, (cx0, cy0, cx1, cy1))

    return best[1] if best else None


def consent_dir(folder: Path) -> Path:
    """네가 직접 승인한 사진을 두는 곳."""
    return folder / "ok"


def is_consented(path: Path, folder: Path) -> bool:
    """ok/ 안에 있는 사진이면 검사 없이 통과."""
    try:
        return consent_dir(folder) in path.parents
    except Exception:
        return False
