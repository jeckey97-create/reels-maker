# reels-maker

사진 폴더를 지정하면 **인스타그램 릴스를 만들어 자동으로 올려주는 프로그램**입니다.

수업 사진으로 홍보용 릴스를 만들려고 만들었습니다. 사진을 고르고, 9:16 영상으로
엮고, 자막과 해시태그를 붙여서, 사람이 한 번 확인한 뒤 게시합니다.

```
사진 폴더  →  사진 선별  →  영상 또는 사진  →  글·해시태그  →  사람 확인  →  게시
```

**릴스(9:16 영상)** 와 **피드 사진·캐러셀** 을 둘 다 만들 수 있습니다.

---

## 이런 걸 신경 썼습니다

**초상권** — 수업 사진에는 학생 얼굴이 들어갑니다. 얼굴 크기와 정면도로
"알아볼 수 있는가" 를 판정해 자동으로 걸러냅니다. 얼굴 검사를 할 수 없는
상태면 **사진을 통과시키지 않고 멈춥니다.** 못 거른 채 올라가는 것보다
아무것도 안 만드는 편이 낫기 때문입니다.

**사람 확인** — 만들어진 릴스는 승인 대기 목록에 쌓입니다. `--publish` 를
직접 붙이기 전에는 절대 게시되지 않습니다.

**토큰** — 액세스 토큰은 `.env` 에만 두고 코드에 쓰지 않습니다. 화면이나
오류 메시지에도 토큰을 출력하지 않습니다.

---

## 설치

**필요한 것**: 윈도우 PC, Python 3.11 이상, ffmpeg,
인스타그램 **프로페셔널 계정**, Meta 앱 액세스 토큰

```powershell
git clone https://github.com/jeckey97-create/reels-maker C:\reels
cd C:\reels

py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

winget install --id Gyan.FFmpeg
```

**얼굴 감지 모델**을 받아 `assets\models\` 에 넣습니다 (약 230KB).

```
https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
```

`.env.example` 을 `.env` 로 복사하고 토큰을 채웁니다.

```
IG_ACCESS_TOKEN=발급받은_토큰
```

준비가 됐는지 확인합니다.

```powershell
.venv\Scripts\python.exe setup_check.py
```

전부 `[ OK ]` 면 됩니다.

---

## 쓰는 법

**1. 사진 폴더를 만들고 사진을 넣습니다** (최소 3장, 20~30장 권장)

원하면 `info.txt` 를 같이 넣어 수업 정보를 적습니다.

```
장소 = 하이닉스 연수원
주제 = 반도체·코딩 수업
대상 = 초등 3~6학년
교구 = 반도체 교구
훅 = 초등학생이 만든다고?
```

자막을 직접 쓰려면 `captions.txt` 에 한 줄에 한 컷씩 적습니다.

**2. 릴스나 게시물을 만듭니다**

```powershell
.venv\Scripts\python.exe make_reel.py "C:\reels\사진\7월수업"    # 릴스 (9:16 영상)
.venv\Scripts\python.exe make_post.py "C:\reels\사진\7월수업"    # 캐러셀 (사진 여러 장)
.venv\Scripts\python.exe make_post.py "C:\reels\사진\7월수업" --one   # 사진 1장
```

`out\` 에 결과물과 게시글이 만들어지고, 승인 대기 목록에 올라갑니다.

| 만드는 것 | 규격 | 자막 |
| --- | --- | --- |
| 릴스 | 1080×1920 (9:16) | 사진 위에 얹습니다 |
| 피드 사진·캐러셀 | 1080×1350 (4:5) | 글에만 넣습니다 |

캐러셀은 기본 6장이고 `--count` 로 바꿉니다 (인스타 상한 10장).

> **한 폴더는 대기 항목을 하나만 가집니다.** 같은 폴더로 릴스를 만든 뒤
> 캐러셀을 만들면 앞의 것이 밀려납니다. 둘 다 올리시려면 하나를 게시한 뒤
> 다른 것을 만드세요.

**3. 영상을 인터넷에 잠깐 엽니다**

인스타그램은 파일을 받아가는 게 아니라 **주소로 가지러 옵니다.**

```powershell
.venv\Scripts\python.exe serve.py
```

주소가 `.env` 에 자동으로 저장됩니다. **게시가 끝나면 `Ctrl+C` 로 닫으세요.**

**4. 확인하고 게시합니다**

```powershell
.venv\Scripts\python.exe approve.py                    # 대기 목록
.venv\Scripts\python.exe approve.py --show "7월수업"    # 내용 확인
.venv\Scripts\python.exe approve.py --publish "7월수업" # 게시
```

---

## 파일 구성

| 파일 | 하는 일 |
| --- | --- |
| `make_reel.py` | 사진 폴더 하나를 릴스로 |
| `make_post.py` | 사진 폴더 하나를 피드 사진·캐러셀로 |
| `watch_folder.py` | 여러 폴더를 감시하며 자동 생성 |
| `approve.py` | 승인 대기 목록 확인·게시 |
| `serve.py` | 영상을 임시 공개 주소로 여는 것 |
| `photo_select.py` | 사진 선별 (선명도·노출·중복) |
| `face_guard.py` | 초상권 안전장치 (YuNet) |
| `scene.py` | 장면 분류 (전체샷·실습·협동) |
| `images.py` | 9:16 크롭·자막 |
| `video.py` | ffmpeg 인코딩 (켄번스·크로스페이드) |
| `audio_mix.py` | 배경음악 합성 |
| `post_text.py` | 자막·게시글·해시태그 |
| `graph_api.py` | Instagram Graph API 게시 |
| `refresh_token.py` | 토큰 갱신 (60일마다) |
| `setup_check.py` | 설치 상태 진단 |
| `deliver.py` | 휴대폰으로 직접 올릴 때 파일 전달 |
| `config.py` | 설정값 (`.env` 로 덮어쓰기) |

---

## 조절하기

`.env` 에 넣으면 바뀝니다.

```
REELS_FONT_SIZE=84            자막 크기
REELS_CAPTION_TOP=0.16        자막 위치 (0.10=위 / 0.30=아래)
REELS_CAPTION_MAX_LINES=2     자막 최대 줄 수
REELS_CUT_MIN=2.0             컷 최소 길이(초)
REELS_CUT_MAX=4.0             컷 최대 길이(초)
REELS_MAX_PHOTOS=4            릴스에 쓸 최대 사진 수
REELS_CAROUSEL_MAX=6          캐러셀 사진 수 (최대 10)
REELS_FEED_WIDTH=1080         피드 사진 가로
REELS_FEED_HEIGHT=1350        피드 사진 세로 (1080 이면 정사각형)
REELS_FACE_POLICY=exclude     exclude=제외 / blur=모자이크 / off=검사 안 함
```

---

## 알아두실 것

**인스타그램 인기 음원은 API 로 붙일 수 없습니다.** Meta 가 막아뒀습니다.
자동 게시하면 무음이거나 직접 준비한 로열티프리 음원만 들어갑니다.
인기 음원을 쓰시려면 `deliver.py` 로 파일을 받아 휴대폰에서 올리세요.

**액세스 토큰은 60일마다 만료됩니다.** 50일쯤에 `refresh_token.py` 를 돌리면
그날부터 다시 60일이 됩니다. 만료된 뒤에는 갱신이 안 되고 재발급해야 합니다.

**게시 자동화는 되고, 상호작용 자동화는 하지 마세요.** 자동 좋아요·팔로우·
무차별 댓글은 Meta 정책 위반이고 계정 정지 사유입니다. 이 프로그램은 게시만
합니다.

**본인 계정, 본인이 만든 앱에만 쓰세요.**

---

## 라이선스

MIT
