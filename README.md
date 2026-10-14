# Shorts Studio 0.2.13

YouTube Shorts/TikTok URL 또는 원본 파일 → 자동 다운로드 → 9:16 H.264 MP4 → 모든 오디오 제거. 최종 실행 대상은 Windows 로컬 설치형 앱입니다.

## 현재 상태

- 제공된 프로젝트의 `sources/`가 비어 있고 연결 대화에도 MVP 소스/첨부가 없어, 기존 0.1 코드 직접 검토는 하지 못했습니다.
- 사용자 설명과 대화에서 확인한 MVP 기능을 바탕으로 독립 프로젝트를 재구성했습니다. 기존 소스 확보 시 비교·이관합니다.
- 구현: Core Engine, Windows 로컬 브라우저 작업 UI, 기존 Tkinter/선택 Streamlit 개발 UI, CLI, Provider adapter, LocalSource.
- 새 기본 UI는 한 화면에서 소스, 9:16 설정, 문자 제거, AI 분석·대본 편집, TTS 합성, 상품 후보, YouTube metadata·업로드, 단계별 결과를 관리합니다. API 설정은 화면 내 drawer에 모았고 비밀 값은 Windows Credential Manager에 저장합니다. 앱은 `127.0.0.1`에만 로컬 서버를 열며 URL과 파일 업로드를 지원합니다.
- URL 소싱 구현: YouTube 개별 영상/Shorts, TikTok 개별 영상/공유 단축 URL. yt-dlp로 다운로드 후 Core Engine에 전달합니다.
- YouTube 후보 검색: 앱의 `YouTube API 설정`에서 API key를 저장한 뒤 `YouTube 영상 찾기`에서 Creative Commons 및 4분 미만 후보를 검색하고 사용자가 선택할 수 있습니다. API key는 Windows Credential Manager에 보관하며, 선택된 후보의 제목·채널·URL·라이선스는 출력 옆 `.source.json`에 기록합니다. 사용 전 원본 페이지에서 이용 조건과 필요한 attribution을 확인하세요.
- 구현: AI frame 분석, 한국어 대본 생성, TTS·SRT·자막 합성, YouTube 후보 검색 및 YouTube OAuth 업로드 adapter/CLI.
- 구현: 작업별 진행 기록, 앱 재시작 후 중단 작업 감지와 재실행, YouTube OAuth 업로드 Desktop UI.
- Coupang Partners 상품 검색 API adapter, HMAC-SHA256 인증, Windows Credential Manager key 저장, API 후보 선택 및 JSON 후보 입력을 구현했습니다. 앱은 시간당 10회 검색 한도를 로컬에서 보수적으로 적용합니다. 실제 계정 연결은 Partners 최종 승인과 API key가 필요하며 별도 검증 항목입니다.
- TikTok 직접 영상 URL 입력과 승인된 Commercial Content API의 EEA 광고 keyword search를 지원합니다. API 결과는 광고 참고용이고 Shorts 재사용 권리를 부여하지 않습니다. 일반 organic video keyword search는 제공 API가 없어 미지원입니다. Research API는 상업용 데이터 검색에 사용하지 않습니다 ([Commercial Content API](https://developers.tiktok.com/products/commercial-content-api), [Research API eligibility](https://developers.tiktok.com/products/research-api/)).
- Windows app 및 문자 제거 worker의 PyInstaller 배포본을 생성하고, frozen worker의 합성 영상 처리까지 확인했습니다. `scripts/package-windows.ps1`은 Inno Setup이 있으면 설치 EXE를, 없으면 사용자별 설치·제거 스크립트를 포함한 `ShortsStudio-Portable.zip`을 생성합니다.
- 설치/제거와 clean Windows PC 테스트는 별도 수동 검증이 필요합니다. installer 산출물은 `build/package-dist`에 생성되며 Git에는 포함하지 않습니다.

## Windows 시작

Python 3.11 이상(권장 3.12, 설치 시 Tcl/Tk 포함), Git, FFmpeg와 ffprobe가 필요합니다.
FFmpeg는 PATH에 등록하거나 `FFMPEG_BINARY`, `FFPROBE_BINARY` 환경변수에 각 실행 파일 경로를 지정합니다.

```powershell
# 이 README가 있는 shorts-studio 폴더에서 실행
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Windows 배포 패키지는 개발 PC에서 `powershell -ExecutionPolicy Bypass -File .\scripts\package-windows.ps1`로 생성합니다. Inno Setup 6이 설치되어 있으면 `build/installer`에 설치 EXE를 만들고, 없으면 `build/package-dist/ShortsStudio-Portable.zip`을 만듭니다. ZIP을 압축 해제한 뒤 `Install-ShortsStudio.ps1`을 실행하면 `%LOCALAPPDATA%\Programs\ShortsStudio`에 설치되고 시작 메뉴 바로가기가 생성됩니다. 제거 바로가기에서 앱을 삭제하며 OCR model cache와 작업 기록은 보존합니다.

FFmpeg 설치가 필요한 경우 [Windows builds](https://www.gyan.dev/ffmpeg/builds/)에서 Essentials ZIP을 받아 압축을 풉니다.
해당 `bin` 폴더의 실행 파일 두 개를 아래처럼 지정하면 시스템 PATH 수정 없이 실행됩니다.

```powershell
$env:FFMPEG_BINARY = 'C:\ffmpeg\bin\ffmpeg.exe'
$env:FFPROBE_BINARY = 'C:\ffmpeg\bin\ffprobe.exe'
.\.venv\Scripts\python.exe -m shorts_studio.ui.desktop
```

`Start.cmd` 또는 시작 메뉴에서 앱을 실행하면 기본 브라우저에 Shorts Studio 작업 화면이 열립니다. URL 입력 또는 영상 파일 업로드 → 저장 위치 선택 → 여백/Crop 선택 → 문자 제거 시작. 기본 720×1280, CRF 23, CPU threads 2.
환경 준비 후 `Start.cmd`를 더블클릭해도 실행됩니다. 현재 PC의 `.tools/ffmpeg/`에 준비된 FFmpeg는 시작 스크립트가 자동 인식합니다.
기존 결과 파일은 덮어쓰지 않습니다. 저장 위치는 hard link를 지원하는 로컬 NTFS 디스크를 사용합니다.

YouTube 업로드는 선택 기능입니다. `pip install -e ".[upload]"`로 Google client를 설치하고 Google Cloud Console에서 YouTube Data API v3를 활성화한 OAuth Desktop client JSON을 준비합니다. 첫 실행은 브라우저 OAuth 승인 후 기본 `private`로 업로드하고 refresh token은 `%LOCALAPPDATA%\ShortsStudio\tokens` 아래에 저장됩니다. metadata JSON 예시는 다음과 같습니다.

```json
{
  "title": "제목",
  "description": "설명",
  "tags": ["shorts", "제품"],
  "privacy_status": "private"
}
```

```powershell
.\.venv\Scripts\shorts-upload.exe .\data\shorts.mp4 .\metadata.json --client-secrets 'C:\secrets\client_secret.json'
```

새 Google API 프로젝트의 검증 상태에 따라 업로드 영상이 비공개로 제한될 수 있습니다. 공개 전환은 API 프로젝트 승인 및 채널 권한을 별도 확인합니다.

후보 검색은 YouTube Data API v3 key가 필요합니다. 앱에서 `YouTube API 설정`을 열고 key를 입력해 저장한 다음 `YouTube 영상 찾기`를 누릅니다. 후보는 자동 다운로드하지 않으며, 후보를 선택한 뒤 `제작 시작`을 눌러야 다운로드와 필수 문자 제거가 진행됩니다. 출처 정보는 결과 MP4 옆에 `.source.json`으로 남습니다.

Coupang 상품 검색은 정상 활동으로 최종 승인된 Partners 계정의 Access Key/Secret Key가 필요합니다. 웹 작업 화면은 대본의 product keyword로 상품을 최대 10개 자동 검색하고 이미지·상품명·가격·검색 순위·배송 표시를 비교할 수 있게 보여줍니다. 후보 선택 시 상품/제휴 URL을 대본에 연결하고 YouTube 제목·설명·태그를 자동 작성하며 제휴 고지를 포함합니다. 판매량과 리뷰 수는 API 응답에 제공되는 경우만 표시하고 누락 시 `API 미제공`으로 표시합니다. key는 Windows Credential Manager에 저장됩니다. 앱의 로컬 호출 기록은 Search 제한인 시간당 10회를 넘지 않도록 보수적으로 검색을 막으며, 다른 앱에서 발생한 호출은 이 기록에 포함되지 않습니다. 발급 조건과 기능은 [공식 Partners guide](https://partners.coupangcdn.com/partners-guide/partners-guide-20250714121952.pdf)를 확인하세요.

```powershell
# CLI: 실제 원본 파일 경로로 변경
.\.venv\Scripts\python.exe -m shorts_studio.cli 'C:\Videos\input.mp4' 'C:\Videos\shorts.mp4' --mode pad
# 1080×1920
.\.venv\Scripts\python.exe -m shorts_studio.cli 'C:\Videos\input.mp4' 'C:\Videos\shorts-hd.mp4' --mode crop --hd
# 기존 MVP 방식의 개발 UI
.\.venv\Scripts\python.exe -m streamlit run src/shorts_studio/ui/web.py
# 테스트
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 프로젝트 구조

```text
src/shorts_studio/
  core/          FFmpeg 실행, 검증, 진행률, 취소
  ui/            web_app.py + static/ (기본 로컬 웹 UI), desktop.py (구형 UI), web.py (Streamlit 개발 UI)
  providers/     AI 분석 계약, Provider 설정 및 secret 조회
  sourcing/      LocalSource, URL 검증, yt-dlp 다운로드 worker
  pipeline.py    URL/파일 → 다운로드 → Core 변환 연결
  narration/     한국어 TTS 계약
  subtitles/     Caption 및 정렬 계약
  products/      provider 독립 상품 모델, 키워드 ranking 및 CLI
  upload/        YouTube OAuth 업로드 adapter/CLI
  cli.py         자동화용 CLI
tests/           실제 합성 영상 변환 및 오류/취소 테스트
.devcontainer/   GitHub Codespaces 개발 환경
.github/         push/PR 테스트
scripts/         Windows 설치 준비 및 실행
```

Core에는 UI나 AI SDK 의존성이 없습니다. UI 교체/설치 패키징 시 동일 Engine을 호출합니다.

## GitHub 연결: 최초 한 번

1. 기존 GitHub 저장소가 있으면 HTTPS 또는 SSH clone URL을 사용합니다. 새 저장소가 필요하면 [새 저장소 만들기](https://github.com/new)에서 빈 `shorts-studio` 저장소를 생성합니다. 기존 저장소에 다른 프로젝트나 별도 초기 commit이 있으면 먼저 병합 상태를 확인하고 push를 진행합니다.
2. `YOUR_REPOSITORY_URL`을 실제 URL로 바꾸고, `YOUR_NAME`과 `YOUR_GITHUB_NOREPLY_EMAIL`에 GitHub 계정 정보를 넣습니다. 인증은 Git Credential Manager 또는 SSH를 사용하고, 토큰을 코드나 채팅에 붙여 넣지 않습니다.

```powershell
git config user.name 'YOUR_NAME'
git config user.email 'YOUR_GITHUB_NOREPLY_EMAIL'
git add -A
git commit -m "Build Shorts Studio MVP"
git remote add origin YOUR_REPOSITORY_URL
git push -u origin main
```

현재 workspace에는 initial commit과 remote가 없습니다. 저장소 URL을 정한 뒤 위 명령을 최초 한 번 실행하세요. 이후 다른 PC/Codespaces에서는 clone, 작업 전 `git pull --ff-only`, 작업 후 commit/push를 수행합니다. Signed Release 업데이트 설정과 asset 게시 절차는 [docs/UPDATES.md](docs/UPDATES.md)를 참고합니다.

이미 초기 commit이 있으면 commit 명령은 생략합니다. 이미 remote가 있으면 `git remote -v`로 먼저 확인합니다.

## Android / PC에서 개발 이어가기

GitHub 저장소 → Code → Codespaces → Create codespace on main. `.devcontainer`가 Python과 FFmpeg를 준비합니다.
Android는 Chrome의 데스크톱 사이트 모드가 편리하며, 작은 화면/키보드 제약이 있습니다. 모바일 편집 환경은 직접 검증하지 않았습니다.

```bash
# Codespaces terminal: 필요할 때만 개발 UI 실행
python -m streamlit run src/shorts_studio/ui/web.py --server.address 0.0.0.0
python -m unittest discover -s tests -v
git add .
git commit -m "Describe change"
git push
```

Ports의 8501에서 Open in Browser를 선택합니다. 포트 공개 범위는 Private로 유지합니다.
이곳은 개발 환경입니다. 최종 영상 처리/사용자 데이터는 Windows 로컬 앱에서 처리하는 설계를 유지합니다.
Codespaces 사용량에 따라 비용이 발생할 수 있으므로 작업 후 Stop합니다.
다른 PC에서는 clone 후 setup, 이후 작업 시작 전 `git pull --ff-only`, 종료 전 commit/push를 수행합니다.
원본 영상/결과/키/가상환경은 Git에 포함하지 않으며 기기 간 자동으로 이동하지 않습니다.
GitHub의 Codespaces 안내: https://docs.github.com/en/codespaces/quickstart

## 설정과 자원 관리

`config.example.toml`은 예시이며, Desktop 설정 화면에서 Provider를 등록할 수 있습니다. 현재 영상 변환에는 AI API가 필요하지 않습니다.
설정 파일에는 Provider/model/base_url/key_name만 보관합니다. Windows Desktop의 AI Provider 설정 화면은 key를 Windows Credential Manager에 저장하며, API key는 환경변수 또는 자격 증명 저장소에서 조회합니다. 영상 분석은 `openai-compatible` Chat Completions endpoint를 사용합니다. 한국어 대본 생성은 별도 **한국어 대본 · Gemini** 설정에서 Gemini API key와 model을 등록하고 연결을 확인합니다. 기본 선택은 `gemini-3.8-flash`이며 현재 모델 선택 항목은 `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`입니다. Key는 Windows Credential Manager에 저장합니다. Google AI Studio에서 API key를 만든 뒤 설정 화면에 입력하세요. 대본 생성과 연결 확인은 Gemini API를 호출하며 사용량/quota가 적용됩니다. 각 설정 탭은 입력값 안내를 제공합니다. 영상 분석 Provider 설정과 대본용 Gemini 설정은 서로 독립적입니다.

```powershell
# AI 분석을 명시적으로 실행할 때만 작은 frame sample을 설정한 Provider로 전송합니다.
.\.venv\Scripts\python.exe -m shorts_studio.providers.cli 'C:\Videos\input.mp4'
```

분석 요청은 최대 8장의 512px frame과 timestamp만 전송하며, 전체 영상 파일은 Provider에 보내지 않습니다. 실제 사용에는 Provider 과금·보존 정책을 확인하세요. 제작 pipeline 자체는 AI 분석을 자동 호출하지 않습니다.

```powershell
# 분석 결과 JSON을 바탕으로 Gemini API가 한국어 대본 초안을 생성합니다.
.\.venv\Scripts\python.exe -m shorts_studio.narration.cli '.\data\analysis.json' --duration 30 --tone friendly --output '.\data\script.json'
```

대본의 segment는 TTS 전에 편집할 수 있는 문장 단위이며, 실제 음성 길이와 자막 timestamp는 TTS 단계에서 생성합니다.

**한국어 TTS**는 Windows Heami 음성을 로컬에서 사용해 API Key와 인터넷 연결이 필요 없습니다. MSIX 설치본과 Windows 한국어 음성이 필요합니다. 반드시 Shorts Studio가 만든 문자 제거 결과(옆에 `.report.json`이 있는 MP4)를 사용하세요.

```powershell
# 한국어 음성과 segment 단위 burn-in 자막을 문자 제거 영상에 합성합니다.
.\.venv\Scripts\python.exe -m shorts_studio.narration.render_cli '.\data\shorts.mp4' '.\data\script.json' '.\data\final.mp4'
```

최종 출력에는 AAC narration, 화면 자막, `.srt`, `.voice.wav`, `.narration.json`이 포함됩니다. 대본 음성이 원본 영상보다 길면 잘라내지 않고 길이를 줄이라는 오류를 냅니다.

- Desktop은 영상 전체를 Python 메모리에 읽지 않고 FFmpeg에 파일 경로를 전달합니다.
- 디코더/필터/인코더 threads를 제한하고, FFmpeg 로그는 최근 32행만 보관합니다.
- Streamlit은 업로드/다운로드 데이터를 메모리에 보관하므로 큰 영상은 Desktop을 사용합니다.
- 실행 전에 입력 파일 크기의 보수적 배수와 최소 여유 공간을 기준으로 출력 드라이브를 점검합니다. 실제 인코딩 크기는 장면·codec에 따라 달라 추정치는 보장값이 아니며, 검사 후 디스크가 소진되는 상황도 발생할 수 있습니다.
- 무음은 음성뿐 아니라 음악/효과음을 포함한 모든 audio stream 제거를 뜻합니다.
- 실행 인자를 배열로 전달하고 shell을 사용하지 않습니다. 원본은 읽기 전용으로 처리하고, 실패/취소된 출력은 폐기합니다.
- 강제 종료 후 남은 임시 폴더는 작업 기록에 연결된 출력 위치를 다음 시작 시 확인해 12시간 이상 된 Shorts Studio marker 보유 폴더만 정리합니다. 일반적인 실패·취소 폴더는 즉시 제거됩니다.
- FFmpeg filter 기준: https://www.ffmpeg.org/ffmpeg-filters.html

## 개발·검증 진행

구현 순서와 현재 상태, 자동 테스트·사용자 수동 검증 분류는 [docs/ROADMAP.md](docs/ROADMAP.md) 및 [docs/VALIDATION.md](docs/VALIDATION.md)를 기준으로 관리합니다. 서명 검증 기반 GitHub Release 업데이트 구현 및 설정 UI를 포함합니다. 사용 방법과 Release asset 서명은 [docs/UPDATES.md](docs/UPDATES.md)를 참고하세요. 실제 저장소·서명키·Release 설정, 외부 계정 연동, clean Windows PC 검증은 수동 테스트 항목입니다. 일반 TikTok organic video keyword search는 제공 API 범위 밖이며, 승인된 Commercial Content API의 EEA 광고 참고 검색만 지원합니다. 광고 미디어의 재사용 권리는 별도 확인해야 합니다.

한국어 TTS는 외부 API 대신 Windows Heami 로컬 음성을 사용합니다. 음성 합성에는 package identity가 필요하므로 MSIX 패키지로 실행해야 합니다. 빌드·서명·설치 안내는 [docs/WINDOWS-MSIX.md](docs/WINDOWS-MSIX.md)를 참고하세요.

## URL 다운로드 사용

기존 설치는 `scripts/setup.ps1`을 다시 실행하면 yt-dlp가 추가됩니다. 현재 PC에는 설치를 진행했습니다.
Desktop 기본 입력 방식은 URL입니다. 다운로드한 원본은 임시 폴더에서만 사용하고, 완료/실패/취소 후 삭제합니다. 결과 MP4만 지정 위치에 남깁니다.

- 지원 입력: YouTube Shorts/watch/youtu.be, TikTok @계정/video 및 vm/vt/t 공유 링크.
- 단일 영상만 처리하며 playlist/채널 URL은 거부합니다.
- 기본 제한: 영상 10분, 다운로드 500 MB, 전체 다운로드 15분, 네트워크 timeout 20초, 재시도 2회.
- 해상도는 가로/세로 최대 1920의 단일 video stream 우선. 원본 audio를 별도 다운로드·병합하지 않습니다.
- Desktop의 취소는 다운로드와 변환 모두에 적용됩니다. Streamlit에는 현재 별도 취소 버튼이 없습니다.
- 로그인/비공개/지역 제한/사이트 차단 영상은 실패할 수 있으며 오류를 표시합니다. 브라우저 쿠키 자동 수집은 하지 않습니다.
- 플랫폼 변경으로 다운로드 오류가 생기면 가상환경에서 `python -m pip install -U "yt-dlp[default]"`로 업데이트할 수 있습니다.
- YouTube JS challenge 처리를 위해 Node.js 22+ 또는 Deno가 필요할 수 있습니다. PATH에서 자동 탐색하며 Node 경로는 `SHORTS_JS_RUNTIME`으로 지정할 수 있습니다. 현재 개발 PC에서는 기존 Node를 사용합니다. 다른 Windows PC에도 런타임 설치가 필요하며, 설치형 배포에는 함께 포함할 예정입니다.
- 다운로드가 필요한 외부 사이트 접근은 URL 제작 실행 시에만 발생합니다.

```powershell
.\.venv\Scripts\python.exe -m shorts_studio.cli 'https://www.youtube.com/shorts/VIDEO_ID' '.\data\shorts.mp4' --url
```

`VIDEO_ID`를 실제 영상 ID로 바꿉니다. 다운로드 구현 기준: [yt-dlp](https://github.com/yt-dlp/yt-dlp), [JS runtime 안내](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

## 필수 영상 문자 제거

모든 제작 경로에서 **전체 화면 문자 제거가 필수 적용**됩니다. UI에서 끄거나 API 호출 인자로 건너뛸 수 없습니다. 영문·한글·중국어 등 언어 필터 없이 매 프레임 전체 화면을 CRAFT로 탐지합니다. 줄 전체 사각형 대신 CRAFT의 픽셀 단위 문자 점수 지도로 획 주변만 마스킹하며, 문장을 읽는 recognition 모델은 사용하지 않습니다.

최초 설치 시 `scripts/setup.ps1`이 프로젝트 전용 가상환경에 EasyOCR/PyTorch/OpenCV를 설치하고 `.tools/models`에 탐지 모델을 받습니다. 이후 로컬에서 실행되며, 제작 시 모델을 자동 다운로드하지 않습니다. 모델이 없으면 오류로 알려주며 문자 제거를 몰래 건너뛰지 않습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Streamlit/CLI는 같은 PowerShell에서 다음 경로를 지정합니다.

```powershell
$env:SHORTS_MODEL_DIR = (Resolve-Path .tools/models).Path
.\.venv\Scripts\python.exe -m shorts_studio.cli 'C:\Videos\input.mp4' 'C:\Videos\clean.mp4'
```

처리 순서: URL 다운로드/파일 입력 → 9:16·30 FPS 무음 영상 준비 → 매 프레임 문자 탐지 → 큰 문자 마스크는 주변 crop에 LaMa 복원, 작은 마스크는 OpenCV Telea 복원 → MP4 저장. 프레임 전체를 디스크 이미지로 풀지 않고 한 프레임씩 순차 처리합니다. CRAFT 탐지 canvas는 기본 960px이며 `SHORTS_TEXT_CANVAS=640`은 빠른 처리, `1280`은 작은 문자를 더 잘 찾는 고비용 설정입니다. OCR은 PyTorch CPU threads 2개, FFmpeg 인코딩은 threads 2개로 제한합니다. CPU에서는 일반 변환보다 상당히 느립니다. 최초 setup은 CRAFT 모델과 LaMa 모델(약 92.6 MB)을 내려받으며, 최대 문자 처리 시간은 2시간입니다.

> 품질 개선: 사용자 제공 비교(111.mp4 원본 / 22.mp4 제거본)에서 자막은 지워졌지만 커튼 주름이 끊겼습니다. 픽셀 단위 CRAFT 마스크와 큰 영역용 LaMa crop 복원을 추가해 배경 전체 축소와 큰 Telea 번짐을 피합니다. 원본은 그대로 보존하며, 손가락과 자막이 겹치는 경계 등은 실제 영상에서 확인해야 합니다.

출력 옆에 `이름.preview.jpg`(첫 탐지 프레임의 원본/탐지 영역/결과)와 `이름.report.json`(처리 프레임 수)이 생깁니다. 탐지 문자가 없으면 비교 이미지는 생성하지 않습니다. Desktop의 **문자 제거 비교 보기** 또는 Streamlit 미리보기로 확인합니다.

모든 문자를 *탐지·제거 대상으로* 하지만 100% 제거를 보장하지 않습니다. 작은 글자, 흐린/기울어진/장식 글자는 누락될 수 있습니다. 간판·상품 포장·로고 내부 문자도 탐지되면 제거됩니다. LaMa와 Telea 모두 단일 프레임 영상 복원이며 시간 방향 정보를 사용하지 않으므로, 움직이는 배경·손과 글자가 겹친 장면에서는 흔적이나 프레임 간 깜빡임이 생길 수 있습니다. 원래 가려진 배경을 완벽히 복구한다고 보장하지 않습니다. 결과 preview와 report를 검토하고 원본을 보존하세요.

기술 기준: [EasyOCR 탐지 API](https://jaided.ai/easyocr/documentation/), [OpenCV inpainting](https://docs.opencv.org/3.4.18/d7/d8b/group__photo__inpaint.html).
