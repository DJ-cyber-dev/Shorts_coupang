# 검증 기록

## Windows Portable ZIP 검증 (2026-10-14)

- 기존 0.2.13 app/Worker build에 로컬 FFmpeg와 검증된 CRAFT/LaMa 모델을 포함해 `build/package-dist/ShortsStudio-Portable.zip` 생성 (**733,587,341 bytes**).
- ZIP 8,247개 항목의 CRC 무결성 검사 통과. 앱 executable, 문자 제거 Worker, FFmpeg/FFprobe, 두 모델, LaMa license, per-user install/uninstall 및 update helper 존재 확인.
- SHA-256: `31CA9A30A637D639071820BDAAFCE110A12C09C008FB50865940EBFC97B15EE5`.
- Portable ZIP은 Core Engine 및 문자 제거 실행용입니다. Heami WinRT TTS는 package identity가 필요한 MSIX에서만 제공됨을 확인.
- Inno Setup이 이 PC에 없어 별도 Setup.exe는 생성하지 못함. Portable ZIP의 새 Windows 계정 추출·설치·실행·제거는 사용자 테스트 목록에 유지.

## 문자 제거 실제 다국어 모델 검증 (2026-10-14 11:46 KST)

- 실제 CRAFT 모델로 합성 영상의 `Hello WORLD`, `한글 문자 제거`, `中文文字测试`를 탐지. 세 언어 모두 글자 ink 픽셀 mask coverage **100%**.
- 같은 1-frame 영상을 필수 문자 제거 service로 처리: 1/1 frame 감지, LaMa 1 frame, `opencl-fp16`, report에 `text_removal_required=true` 기록. 출력 H.264 360×640, FFprobe 및 전체 FFmpeg decode PASS.
- 산출물: `build/manual-text-quality-20261014-114629/` 아래 input, multilingual source image, cleaned MP4, preview, report.
- 반복 실행마다 새 결과 폴더를 만들고 CP949 터미널에서도 중문 출력이 되도록 `tests/manual_text_quality.py` 보완. 이 합성 샘플은 언어별 검출 확인이며 다른 폰트·기울기·배경·실제 영상의 품질 평가는 사용자 검수 목록에 유지.
- 현재 전체 자동 회귀 재실행: **111 tests PASS, 1 Windows-only skip**. 저장소 내 FFmpeg/FFprobe 명시 경로로 Core Engine 통합 테스트도 실행.
- `ShortsStudioWorker.spec`의 torchvision native extension 경로가 개발 PC 절대 경로에 고정된 것을 찾아 현재 build environment의 설치 위치에서 동적으로 검색하도록 수정. active `.venv`에서 `_C_stable.pyd`·`image_stable.pyd` 검색, spec Python parse, 절대 사용자 경로 제거 확인.

## MSIX 0.2.13 Gemini 모델·연결 검증 (2026-10-14)

- 현재 Gemini stable text-generation 모델 4개 제공: `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`. 설치 UI에서 네 항목 표시, `gemini-3.6-flash` 선택 후 `gemini-3.8-flash`로 복구·저장 및 기존 Credential Manager key 보존 확인.
- 첫 실연결은 HTTP 503. Google은 이를 일시적 과부하/장애로 분류하고 지수형 backoff를 권장 ([API errors](https://ai.google.dev/gemini-api/docs/api-errors?hl=en), [retry guidance](https://ai.google.dev/gemini-api/docs/troubleshooting)). 최대 3회 재시도(1/2/4초 대기) 구현, 관련 테스트 2개 추가.
- 0.2.13 설치본에서 실제 Google Gemini API 연결 테스트 성공: `Gemini 연결에 성공했습니다. (gemini-3.8-flash)`. API key는 Credential Manager에 보관되고 화면·로그에 표시되지 않음.
- 설치 앱 상태: `text_removal.ready=true`, `local_only=true`, Heami TTS ready. 기존 API key 저장 상태와 4개 모델 목록 보존 확인.
- 전체 자동 회귀 테스트 **111 tests PASS, 1 Windows-only skip**. 저장소 외부 `%TEMP%`에서 실행해 release signing key 보안 검사도 통과. MSIX (601,557,392 bytes) 서명·검증 통과, warnings/errors 0, 설치 버전 0.2.13.0.
- 앱 executable은 Gemini retry 수정사항으로 재빌드. 변경되지 않은 검증된 0.2.12 text-removal worker와 CRAFT/LaMa 모델을 포함하고, 새 설치본에서 readiness를 확인.

## MSIX 0.2.11 문자 제거 재실행 (2026-10-14 10:10 KST)

- 설치 앱을 다시 실행한 뒤 동일한 원본 `C:\Users\user\Downloads\111.mp4` (1,355,711 bytes)를 업로드해 `C:\Users\user\Videos\ShortsStudio\retest-20261014-111.mp4`로 전체 재처리. 10:10:49 시작, 10:40:48 완료(약 30분), 오류 없음.
- `/api/status`: `text_removal.ready=true`; 206/206 frames text 감지, LaMa 13 / Telea 193, persistent mask 1,530 pixels, OpenCL FP16. 이전 0.2.11 full-run 결과와 출력 SHA-256이 동일해 재현성 확인.
- FFprobe에서 H.264 720×1280/30fps/6.8667초, video-only, 1,751,647 bytes 확인. FFmpeg 전체 디코드 PASS.
- 0.5/2.0/3.5/5.5초 비교에서 Korean captions와 `[광고]`, watermark가 제거되고 큰 기하 왜곡은 보이지 않음. 복원된 watermark 주변의 약한 smoothing은 남으며 연속 재생/flicker 검수 필요.
- 검증용 사본, report 및 비교 이미지: `build/review-artifacts/retest-111-output.mp4`, `retest-111-report.json`, `retest-111-comparison.jpg`. `WinError 5`는 이번 실행에서 재현되지 않음.

## MSIX 0.2.11 화면 이동 및 실제 문자 제거 재검증 (2026-10-14)

- 설치된 Shorts Studio 0.2.11.0을 재실행하고 `/api/status`에서 `text_removal.ready=true`, `local_only=true` 확인. 설치 경로에서 `ShortsStudioWorker.exe`를 정상 실행.
- 웹 화면 단계 버튼 02 문자 제거, 03 분석·대본, 04 음성·자막, 05 상품·게시를 눌러 각 대응 섹션으로 이동하는 것을 확인. URL/파일 입력 탭과 설정 상태도 화면에 표시됨.
- `111.mp4` 2초 샘플과 실제 전체 6.8667초 입력을 로컬 앱 API로 처리. 전체 작업은 206/206 frames에서 text 감지 후 완료, LaMa 13 / Telea 193, persistent small-text mask 1,530 pixels, backend `opencl-fp16`.
- 전체 출력은 H.264 720×1280/30fps/6.8667초, video-only, 1,751,647 bytes. FFprobe 형식 검사와 FFmpeg 전체 디코딩 PASS.
- 원본/결과의 0.5·2.0·3.5·5.5초 비교에서 Korean captions, `[광고]`, 저대비 영문 watermark 제거를 확인. 대표 frame에 큰 기하 왜곡은 보이지 않으나 watermark 복원부의 약한 smoothing은 연속 재생으로 추가 평가 필요.
- 전체 영상 처리 약 31분. Worker 메모리 사용량은 약 1.5 GB까지 관찰. 화면의 프레임 처리 진행률 표시는 계산 도중 갱신되며, 상태 API 응답도 높은 CPU 부하 시 지연될 수 있음.
- 비교 이미지: `build/review-artifacts/0.2.11-retest-111-full-frames.jpg`; watermark crop: `build/review-artifacts/0.2.11-retest-111-watermark-crops.jpg`; 전체 preview: `build/review-artifacts/0.2.11-retest-111-full-preview.jpg`; 처리 리포트: `build/review-artifacts/0.2.11-retest-111-full-report.json`.
- 2초 샘플 출력은 `build/review-artifacts/0.2.11-retest-111-2s-output.mp4`; 전체 출력은 `build/review-artifacts/0.2.11-retest-111-full-output.mp4`.
- 제한된 실행 권한으로 첫 자동 회귀 테스트를 시작했을 때 Python 임시 폴더 내부 생성·정리가 `PermissionError (WinError 5)`로 막혔음. 로컬 테스트 전용 임시 경로를 사용해 승인된 권한으로 재실행한 결과 **108 tests PASS, 1 Windows 전용 검사 skip**. 같은 테스트 결과는 `tests` 전체 모듈을 대상으로 함.
- JavaScript 문법 검사, PowerShell 패키지 스크립트 parse, `git diff --check`, 실제 MSIX 기능 및 미디어 디코딩도 별도로 통과.

## MSIX 0.2.9 실제 Heami TTS 통합 재검증 (2026-10-14)

- WinRT `DataReader.read_bytes`에 크기가 아닌 `bytearray` 버퍼를 전달해야 하는 호환성 수정 후 설치 MSIX 0.2.9.0에서 재검증.
- 단색 5초/720×1280 샘플 영상이 필수 문자 제거 단계를 거쳐 완료됨. 150 frames 검사, 글자 검출 0건, 오류 없이 output 생성.
- 문장 `테스트입니다.`를 Microsoft Heami로 실제 합성. PCM WAV 16 kHz/mono, speech duration 1.8초, SRT에 `00:00:00,000 --> 00:00:01,800` 기록.
- 최종 MP4에 H.264 720×1280/5초와 AAC 16 kHz/mono/4.992초 stream이 포함됨. FFmpeg 전체 디코딩 PASS.
- 샘플 Core Engine 처리부터 최종 렌더까지 약 13분 43초 소요(CPU). 모델 초기화와 샘플 처리 시간을 포함하므로 일반 작업 시간은 영상 길이·기기 성능에 따라 달라짐.
- 0.2.9 변경 포함 자동 회귀: 108 tests PASS, 1 Windows 전용 검사 skip. WinRT `DataReader` 버퍼 타입 회귀 테스트 포함.
- 실제 로컬 TTS 합성과 mux는 확인 완료. 자연스러운 발음·음량·자막 가독성은 사용자 대본으로 청취/화면 검수가 남음.

## MSIX 0.2.9 실제 문자 포함 영상 재검증 (2026-10-14)

- 사용자 원본 `111.mp4`의 첫 2초를 720×1280/30fps 샘플로 만들어 설치 앱에 입력. 원본 파일은 수정하지 않음.
- `WinError 5` 모델 경로 접근 오류 없이 문자 제거 완료. 60/60 frames에 문자 검출, LaMa 1 frame / Telea 59 frames, LaMa backend `opencl-fp16`, persistent mask 3,898 pixels.
- 0.5초 원본/결과 비교에서 Korean caption `공간 분리하려고`, `[광고]`, 영문 watermark 제거 확인. 배경·손·커튼의 큰 기하 왜곡은 보이지 않으며 복원 영역의 약한 smoothing은 확대 검수가 필요.
- 결과는 720×1280/30fps/2초 H.264 video-only이며 FFmpeg 전체 디코딩 PASS. 비교 이미지: `build/review-artifacts/0.2.9-111-text-trigger-comparison.jpg`.
- 처리 시간 약 11분. 2초 입력의 최초 CPU 모델 초기화와 60-frame 복원을 포함한 값이며, PC 사양 및 이후 모델 cache 상태에 따라 달라짐.
- 이번 짧은 영상 검증은 설치 앱의 권한 오류 재현에는 통과. 6.8667초 전체 영상의 모든 프레임/연속 재생 flicker는 기존 사용자 최종 검수 항목으로 남음.

## 로컬 TTS 및 MSIX 변경 (2026-10-13)

- Windows Heami 로컬 TTS provider의 mocked WAV 합성·무네트워크 동작, 무료 local 기본 설정 단위 테스트 추가.
- TTS 설정 UI에서 API key 필드를 제거하고 MSIX/Heami 준비 상태 표시로 전환.
- MSIX package/sign/install scripts와 `docs/WINDOWS-MSIX.md` 추가.
- 실기기 WinRT Heami 합성, 서명 및 설치는 Windows SDK·서명 인증서가 필요한 수동 검증.

2026-10-12 / Windows / Python 3.12.14 / FFmpeg 9.0.2 Essentials

- `python -m unittest discover -s tests -v`: 11 tests PASS, skip 없음.
- 실영상 테스트는 FFmpeg testsrc2와 sine으로 생성한 1초 입력을 사용.
- 320×180 + audio, 180×320 무음, 180×180 SAR 4:3 각각 pad/crop 변환.
- 출력 크기 180×320, SAR 1:1, audio stream 부재, 약 1초 길이 확인.
- 한글/공백 경로, 원본 bytes 보존, 진행률 완료 확인.
- 손상 파일/잘못된 filter 오류 시 출력과 임시 파일 미잔존 확인.
- 입력 옵션 검증, 기존 출력 보존, 실행 중 취소, timeout 확인.
- Provider disabled/env secret 및 평문 secret 설정 거부 확인.
- `compileall` 통과.
- Desktop UI 생성 및 event loop 초기화 확인 (숨김 창 smoke 검사; 수동 화면 조작 검증은 제외).
- 별도 Streamlit AppTest 1개 PASS: 초기 화면, 업로드 전 변환 비활성화, Crop 선택 확인.
- 프로젝트 `.venv` 설치 성공, `pip check` 통과. Streamlit 1.65.0 / keyring 25.7.0.
- 설치된 CLI에서 1초 합성 입력 → 기본 720×1280 출력 변환 성공. ffprobe로 video-only 확인 (`data/demo-720.mp4`, Git 제외).

Sandbox 내 Python 임시 폴더 ACL 제한으로 최초 테스트 실패. 프로젝트 내부 테스트 디렉터리를 사용하여 정상 사용자 권한 실행에서 전체 통과.
FFmpeg ZIP은 배포자의 SHA256 파일과 대조 후 사용했으며 `.tools/`에만 보관, Git 제외.

미검증: 장시간/대용량 영상, HDR 색변환, GPU 가속, Windows 설치 파일, Android 브라우저 직접 조작, 원격 AI API.

## URL 입력 추가 검증 (2026-10-12)

- 전체 19 tests PASS, skip 없음. 기존 Engine 회귀 검사 포함.
- YouTube Shorts/watch/youtu.be와 TikTok 개별 영상/단축 링크 입력 검증.
- 채널/playlist/위장 도메인/비 HTTPS URL 거부 확인.
- 다운로드 대역폭·길이 제한 설정, 취소 전 시작 방지, 임시 파일 성공/실패 정리 확인.
- Streamlit URL 입력 시 실행 활성화, 파일 모드 전환 시 업로드 요구 확인.
- yt-dlp 2026.8.19 + yt-dlp-ejs 0.8.0 설치.
- 다운로드 테스트는 네트워크 모의 응답 사용. 실제 YouTube/TikTok URL 다운로드 성공 여부는 아직 검증하지 않았습니다.

## 문자 제거 사용자 영상 검토 (111.mp4 원본 / 22.mp4 제거본)

- 두 영상은 길이 6.8667초, 720×1280, 30 FPS로 동일함.
- 원본 앞 3초를 별도 파일로 처리하여, 자막 제거 후 커튼 주름 손상이 기존 22.mp4보다 줄어드는 것 확인.
- 자막과 손이 겹치는 일부 프레임에는 인페인팅 흔적이 남아 추가 개선 여지가 있음.
- 새 3초 결과: `.tools/real-review/cleaned.mp4`; 비교 이미지: `.tools/real-review/comparison.jpg`.
- 111.mp4 원본과 기존 22.mp4는 수정하지 않음. 풀 영상 새 출력은 아직 검토하지 않음.

## Provider 설정 및 필수 제거 회귀 검사 (2026-10-12)

- Provider 설정 저장/불러오기 및 API key가 설정 파일에 포함되지 않는지 검사 통과.
- 원격 Provider의 HTTP URL 및 URL 내 credentials 거부, localhost HTTP 허용 검사 통과.
- vision adapter frame JSON payload, base64 JPEG 전달, 응답 JSON 파싱, 비활성 Provider·누락 key 거부를 mock으로 확인.
- 한국어 대본 writer의 길이·tone 제약, JSON schema, TTS 전 상태표시를 mock으로 확인.
- TTS settings validation, WAV 응답 처리와 endpoint payload, segment audio duration 기반 SRT timing, 문자 제거 report 필수화를 확인.
- 합성 360×640 영상과 mock WAV TTS로 FFmpeg burn-in 자막+AAC mux 통합 검증 통과. 출력 360×640, 오디오 stream 1개, SRT/voice sidecar 생성 확인.
- 로컬 합성 1초 영상에서 FFmpeg frame 추출 성공: 4 samples, 최대 JPEG 약 12 KB.
- Streamlit 초기 화면 smoke 검사 1개 통과.
- 문자인식 mask 경계 처리와 빈 mask 검사 2개 통과.
- `compileall` 통과.
- 전체 unittest는 Windows TEMP 경로의 sandbox ACL로 임시 파일 생성/정리가 차단되어 재실행 불가. 개별 실행 가능한 검사는 분리해 확인함.
- Windows Credential Manager 실저장 및 Desktop 설정 창은 사용자 PC에서 수동 확인 필요.

## 소싱·업로드 adapter 개발 후 전체 회귀 검사 (2026-10-12)

- 전체 unittest 51개 통과, Windows 전용 Credential Manager 비-Windows 검사 1개 skip.
- FFmpeg 9.0.2를 명시해 Engine 실영상 변환, 9:16 pad/crop, 무음 출력, 취소, 손상 입력, 인코더 실패 정리까지 통과.
- YouTube Data API 후보 검색 필터/응답 ID 검증과 key 설정 저장 mock 검사 통과.
- YouTube upload metadata 검증, 비공개 기본값, 공개 opt-in, 예약 입력, resumable progress, transient retry를 fake API로 확인.
- Coupang 후보 keyword rank, 중복 ID 제거, 빈 검색어/limit validation 단위 검사 통과.
- `compileall` 통과. Streamlit smoke의 bare-mode warning은 실행 컨텍스트 안내 로그이며 test는 통과.
- YouTube/TikTok 실다운로드, AI/TTS 실 Provider, OAuth 채널 업로드, YouTube key Credential Manager 저장은 사용자 계정이 필요해 수동 확인 목록에 둠.
- Provider 연결 확인 버튼, frozen worker 경로, Windows build script의 PowerShell syntax는 확인. Inno Setup이 이 환경에 없어 installer를 실제 생성하지 못했고 Desktop UI/OAuth 역시 실제 계정으로 확인하지 않음.

## Desktop job history 및 Windows frozen worker 검증 (2026-10-12)

- 당시 전체 unittest 57개 통과, Windows Credential Manager 비-Windows 검사 1개 skip. 아래 Coupang adapter 추가 후 최신 결과는 마지막 섹션에 기록.
- `compileall`, `git diff --check`, `scripts/package-windows.ps1` PowerShell parser 검사 통과.
- PyInstaller로 Desktop app과 문자 제거 worker를 생성하고, 합성 1초 영상에서 frozen worker 실행 성공: 24 frames 처리, 출력 MP4 ffmpeg decode 통과, report JSON 생성 확인.
- Frozen worker의 torchvision native extension 누락으로 발생했던 `operator torchvision::nms does not exist` 오류는 PyInstaller 수집 대상 보강 후 재검증에서 해결.
- Desktop job history의 저장/중단 상태/오래된 기록 정리 테스트 2개 통과.
- Inno Setup(ISCC.exe)이 PC에 없어 설치 파일 생성은 미완료. 앱 설치 후 Windows 계정 권한, OAuth 실제 업로드, Android 직접 접속, 원본 `111.mp4`의 전체 문자 제거 화질은 별도 수동 검증 대상으로 유지.
- Inno Setup 부재 시 self-contained portable ZIP 생성 fallback 추가. streaming ZIP으로 8,217개 파일을 묶고 Desktop EXE, OCR worker와 torchvision native extension, FFmpeg, `craft_mlt_25k.pth`, 설치/제거 script 필수 항목 확인 통과 (latest archive 550,543,894 bytes).
- portable 설치/제거 smoke test를 workspace 임시 경로에서 수행: Desktop EXE와 OCR model 설치, 앱 폴더 제거 후 model cache 보존 확인 통과. 실제 사용자 `%LOCALAPPDATA%`에는 설치하지 않음.
- 최신 frozen Desktop EXE를 임시 설정 경로에서 5초 기동 확인 통과. 최신 frozen OCR worker는 합성 영상 24프레임 처리, 출력 MP4 decode와 report JSON 확인 통과.
- PyInstaller worker에서 불필요한 `torchvision` 전체 자산 수집을 제거하고 필요한 native extensions만 명시적으로 포함하도록 변경. Desktop 본체에서 EasyOCR/PyTorch import도 분리해 OCR runtime 중복 포함을 피함.
- Product candidate JSON loader를 CLI/Desktop에서 공유하도록 정리하고, 숫자 가격 변환·잘못된 JSON 구조/가격 검증 단위 테스트 2개 추가.
- Desktop 상품 후보 JSON 선택 UI의 ranking·선택·저장 흐름 및 최신 앱 재패키징 확인 통과.
- 선택 상품 정보를 대본 JSON에 안전하게 추가하는 helper와 입력 검증 테스트 2개 추가.
- CI/Codespaces 설치 목록에 mask 테스트용 OpenCV/NumPy extra를 추가하고, initial GitHub commit 안내를 현재 저장소 상태에 맞춤.
- CI에 사용되는 `web`/`test` dependency set과 동일한 패키지 상태에서 전체 test와 `pip check` 통과. GitHub Actions workflow 자체는 push 전이므로 아직 원격 실행 전.
- 최종 Desktop EXE 5초 기동 및 portable ZIP 필수 엔트리 확인 통과.
- 최종 재실행: 번들 FFmpeg/ffprobe 경로를 명시한 전체 unittest 57개 통과, Credential Manager Windows 전용 검사 1개 skip. `compileall`, `pip check`, `git diff --check`도 통과.
- 제품 후보 JSON 테스트가 저장소 하위 폴더 ACL에 의존하지 않도록 OS 기본 temporary directory를 사용하도록 수정하고 7개 제품 테스트 통과.

## Coupang Partners search adapter 개발 (2026-10-12)

- 공식 HMAC-SHA256 request signing 예제를 바탕으로 keyword search client를 추가. HMAC에는 UTC signed date, HTTP method, path 및 실제 전송 query string을 포함.
- API access/secret key는 환경변수 또는 Windows Credential Manager에서 읽으며, Desktop에 저장 UI를 추가. 설정 파일/검색 로그에는 secret을 기록하지 않음.
- API 응답을 provider-independent `Product`로 변환하고, 15초 network timeout, 응답 2 MiB cap, sanitized API errors를 적용.
- Partners guide의 Search 시간당 10회 제한에 맞춰 로컬 호출 이력을 원자적으로 보관하고 10회를 넘는 검색을 차단. 앱 외부에서 발생한 요청은 추적할 수 없어 전체 account quota를 보장하지 않음.
- mock tests에서 Korean query percent-encoding, HMAC digest/header, response mapping, query/limit validation, 10/hour limiter 통과.
- Desktop 상품 선택에서 Partners API 검색 또는 후보 JSON 파일을 선택할 수 있음. 실제 API 응답과 계정별 사용량은 승인된 Partners account/key로 수동 검증 필요.
- 전체 최신 재실행: 61 tests 통과, Windows Credential Manager용 1 test skip. FFmpeg/ffprobe 통합 테스트 포함. `compileall`, `pip check`, `git diff --check` 통과.
- Build script에 Coupang module hidden import를 추가한 뒤 frozen app graph에서 `shorts_studio.products.coupang` 포함 확인. 최신 Desktop EXE 5초 기동 확인 통과.
- 최신 portable ZIP 8,217 entries / 550,553,425 bytes, Desktop EXE·OCR worker·torchvision native extension·모델·설치 script 엔트리 확인 통과.

## 문자 제거 마스크 품질 조정 (2026-10-12)

- 줄 단위 사각형 전체를 인페인팅해 배경 질감을 손상시키던 동작을 CRAFT per-pixel text confidence map 기반 획 마스크로 교체.
- 소스 프레임의 최대 변을 640~1280px로 제한하여 저해상도 입력의 불필요한 확대와 4K 입력의 과도한 연산을 방지.
- 합성 영문/한글/중국어 텍스트의 실제 CRAFT ink coverage 각각 100% 확인. 마스크 생성 unit test 통과.
- 사용자 원본 `111.mp4`에서 추출한 프레임의 비교 이미지: `build/user-validation/111-mask-prototype.jpg`. 문자 영역은 프레임의 1.67%였고, 줄 전체를 칠하던 이전 preview보다 손/커튼 영역 손상이 줄어든 것을 확인. 이 프레임의 희미한 watermark는 남아 있어 전체 영상 수동 확인이 필요.
- 실영상 1-frame end-to-end 통합 확인은 worker의 CPU 처리 시간이 수 분 이상 이어져 중단. 새 마스크의 full-video 품질·성능은 아직 확인되지 않았으며, 다음 수동 검증 목록에 유지.
- 본 항목의 worker end-to-end 테스트는 수 분 이상 CPU를 사용해 중단했으며, 결과 MP4는 생성되지 않음.
- 변경 후 전체 자동 검사 재실행: 62 tests 통과, Windows Credential Manager 검사 1개 skip. `compileall`, `pip check`, `git diff --check` 통과.
- OCR worker와 Desktop 재패키징 통과. Desktop EXE 5초 기동 확인. Portable ZIP 8,227 entries / 550,650,153 bytes; Desktop, worker, torchvision native extension, CRAFT model, 설치·제거 script 포함 확인.

## LaMa crop 복원 및 CRAFT 960px 적용 검증 (2026-10-12)

- 전체 unittest 64개 통과, Windows Credential Manager 비-Windows 검사 1개 skip. FFmpeg 통합 테스트 포함.
- CRAFT 픽셀 마스크와 fake ONNX network를 사용한 LaMa crop 단위 테스트에서 mask 영역 변경, mask 바깥 원본 픽셀 유지 확인.
- `compileall`, `pip check`, `git diff --check`, Windows package PowerShell parser 통과.
- LaMa model은 OpenCV Hugging Face 저장소의 고정 revision ONNX 파일이며, SHA-256 검증 후 설치/cache에 저장. 모델 라이선스는 `licenses/LaMa-LICENSE.txt`를 설치본/portable에 포함.
- 사용자 원본 `111.mp4` 전체 206프레임을 두 번 처리하고 원본은 보존. 640px 출력은 720×1280, 30 FPS, 6.8667초, 무음, 1,719,154 bytes이며 LaMa 13프레임/Telea 193프레임. 대표 frame 45에서 작은 영문 watermark가 남음.
- 기본 canvas를 960px로 올린 뒤 다시 전체 처리: 720×1280, 30 FPS, 206프레임, 6.8667초, 무음, 1,716,162 bytes, LaMa 14프레임/Telea 192프레임. 약 21분 소요. frame 45의 watermark와 화면 caption 제거를 확인했지만, 모든 장면을 완전 제거하는 보장은 없어 사용자가 결과 전체를 눈으로 확인해야 함.
- 비교 산출물: `build/user-validation/111-adaptive-lama.preview.jpg` 및 `build/user-validation/111-adaptive-lama-960-review.jpg`. 960px 처리시간을 고려해 환경변수 `SHORTS_TEXT_CANVAS=640`(빠름) 또는 `1280`(세밀함)을 선택할 수 있음.
- LaMa checksum 상수의 오타를 source setup에서 발견해 수정. `--prepare` source/frozen worker 모두 isolated cache에서 네트워크 없이 통과했으며, checksum 고정 unit test 포함.
- Windows portable 패키지 재생성: 8,229 entries / 630,698,201 bytes. Desktop/worker, FFmpeg/ffprobe, CRAFT/LaMa model, LaMa LICENSE, 설치/제거 script 포함. 패키지 안 LaMa 파일 SHA-256 일치 확인.
- 새 Desktop EXE 5초 시작 smoke 통과. Inno Setup이 없어 portable ZIP fallback 사용; 실제 설치 계정, 시작 메뉴 shortcut, 제거 과정은 아직 사용자 확인 필요.

## Stability·TikTok 광고 검색·업데이트 구현 후 회귀 및 배포 검증 (2026-10-12)

- 전체 unittest 79개 통과, Windows Credential Manager 전용 검사 1개 skip. FFmpeg/ffprobe 통합 테스트 포함.
- `compileall`, `pip check`, `git diff --check`, Windows package PowerShell parser 통과.
- Core Engine 시작 전 output 디스크 여유 추정, 12시간 이상 된 marker 임시폴더만 정리, 작업 재개 시 stale 작업 폴더 복구 동작 확인.
- TikTok Commercial Content API mock에서 client credential token, EEA keyword ad query, 검색 범위 제한, credential 미설정/실패 처리, API key 설정에 secret 미저장 확인.
- Signed GitHub updater mock에서 Release metadata, Ed25519 서명, 버전, asset host, 파일 SHA-256, tampered ZIP 거부와 helper launch 전달 확인. manifest 생성기가 암호화 private key로 서명하며 repository 내부 key 경로를 거부하는 것 확인.
- Release version 동기화 도구가 pyproject, runtime version, installer, README를 같은 버전으로 변경하는 것 확인.
- Isolated `%LOCALAPPDATA%` 경로에서 실제 PowerShell update helper가 앱 폴더를 교체하고 새 파일을 시작한 뒤 이전 폴더와 staging 파일을 정리하는 통합 smoke 통과.
- 최신 Desktop 및 OCR Worker를 PyInstaller로 다시 빌드. 추적 대상 Desktop spec에 TikTok 및 updater 모듈을 명시하고 분석 TOC 포함을 확인. Portable ZIP 8,230개 엔트리 / 630,730,674 bytes. Desktop, Worker, FFmpeg/ffprobe, CRAFT·LaMa 모델, LaMa license, 설치·제거 및 업데이트 helper 포함 확인.
- 최신 Desktop EXE 5초 기동 확인. Inno Setup이 없어 설치 EXE 대신 self-contained portable ZIP 제공.
- 실제 TikTok Commercial Content API 승인은 없으므로 실제 EEA 광고 검색은 미검증. TikTok 일반 organic video keyword search는 API 범위 밖.
- Git remote와 Git identity가 설정되지 않아 GitHub 원격 저장소 push 및 실제 signed Release 업데이트는 미수행. 설치 PC/계정/API가 필요한 수동 테스트는 `ROADMAP.md` 목록을 따른다.

## 전체 코드 재검토 및 오류 수정 (2026-10-13)

- 전체 unittest 79개 통과, Windows Credential Manager 전용 검사 1개 skip. FFmpeg/ffprobe 통합 변환 테스트 포함.
- `compileall`, `pip check`, staged/unstaged `git diff --check`, 저장소 PowerShell script 7개 parser 검사 통과.
- 업데이트 적용 후 앱 시작 실패 시 새 설치 폴더를 제거하고 기존 설치를 복원하도록 helper를 수정. 잘못된 EXE로 격리 경로에서 실패를 유도한 실제 PowerShell smoke에서 기존 버전 복원 확인.
- Engine과 문자 제거 출력의 hard link 게시를 Windows 원자적 rename으로 변경해 NTFS hard link가 없는 외장 드라이브에서도 저장하도록 개선. POSIX에서는 동시 출력 덮어쓰기를 막는 hard link 게시를 유지.
- 최신 Desktop EXE 재빌드, 5초 기동 smoke 통과. portable ZIP 8,230 entries / 732,717,295 bytes이며 Desktop, OCR Worker, FFmpeg, LaMa 모델, 설치·제거 script와 updater helper 포함 확인.
- 실제 GitHub Release 업데이트, 사용자 계정/API 연동, 전체 입력 영상 화질과 Inno Setup 설치본 검증은 별도 사용자 테스트 목록에 유지.

## 단계별 산출물 연계 검사 (2026-10-13)

- 기존 사용자 출력 `111-adaptive-lama-960.mp4`를 열어 720×1280, 6.8667초, 무음이며 206프레임 report가 붙어 있는 것을 확인. 해당 report가 TTS 입력 검증을 통과하는지 직접 검사.
- 산출물 연결에서 문자 제거 report의 `method` 값과 TTS의 허용 문자열이 달라 TTS 합성이 항상 거부되는 결함을 수정. Worker report에 versioned method ID와 schema 필드를 추가하고 기존 report도 호환.
- fake TTS WAV를 사용한 FFmpeg 통합 테스트에서 문자 제거 report → narration render → 최종 MP4/AAC, SRT, voice WAV, narration JSON 생성을 확인.
- 전체 unittest 81개 통과, Credential Manager 전용 1개 skip. 저장된 실제 단계 산출물은 demo 변환 및 문자 제거 결과이며, AI 분석 JSON·대본·상품 선택·외부 업로드 결과는 계정/API 연동 테스트 전이라 별도 파일로 존재하지 않음.
- 새 frozen Worker를 합성 1프레임 영상에서 실행해 versioned report 생성과 TTS 단계 인식까지 확인. 새 portable ZIP의 필수 app/worker/FFmpeg/model/helper 파일 포함을 확인.

## CPU·OpenCL 문자 제거 성능 개선과 MSIX 재검증 (2026-10-13)

- 설치된 Shorts Studio 0.2.1.0에서 사용자 원본 `111.mp4`(720×1280, 30 FPS, 206 frames)를 다시 실행. 기존 MSIX read-only `user_network` 경로 오류는 재현되지 않았고 worker는 문자 제거 단계에 진입했으나 94.6%에서 장시간 지연되어 취소. 결과 MP4는 생성되지 않아 이 설치본에서는 전체 처리와 품질을 검증하지 못함.
- 병목 분리 benchmark에서 현재 PC(12 logical processors, Intel Iris Xe)의 CRAFT 1280×720 frame inference는 2 torch threads에서 9.94초, 8 threads에서 5.08초로 측정. 2개 logical processor를 앱/encoder용으로 남기고 최대 8 threads를 쓰도록 변경.
- LaMa 512×512 CPU inference는 약 25초, OpenCL FP16은 약 13~17초를 측정. FP16 target을 지원하는 장치에서만 선택하고 실행 오류가 나면 CPU로 재시도하도록 구현. report에 선택된 backend를 기록. 이 benchmark는 inference latency만 비교했으므로 FP16의 영상 복원 화질은 설치본 결과에서 확인해야 함.
- Text-removal module tests 12개 통과: CPU thread budget, OpenCL capability 선택, OpenCL 실패 시 CPU fallback, mask와 LaMa crop 보존 조건 포함.
- 전체 unittest 98개 통과, Windows Credential Manager 전용 1개 skip. 번들 FFmpeg와 사용자 Temp 폴더를 지정해 Windows 통합 테스트도 실행. `test_updates`는 현재 0.2.2보다 높은 mock release를 기준으로 하도록 갱신.
- 0.2.3 설치본에서 1-frame 합성 입력을 완료: 720×1280, 30 FPS, 1 frame, 무음. Report는 `frames_with_text=1`, `lama_frames=1`, backend `opencl-fp16`이며 비교 preview에서 글자 제거를 확인.
- 취소 후 임시 파일 잠금으로 `TemporaryDirectory` 정리가 취소 결과를 덮어쓰던 WinError 32를 재현 경로에 맞춰 수정. `managed_tempdir`는 Windows의 일시 잠금에 최대 20회 재시도하며 끝내 잠긴 경우 marker와 최근 mtime을 남겨 다음 실행의 stale cleanup에 맡김. 잠금 실패 2회 후 삭제 재시도, 잠금 지속 시 marker 보존 테스트 추가.
- MSIX 0.2.3을 설치해 합성 입력을 OCR 단계에서 취소: 앱 API 상태 `cancelled`, 출력 MP4 미생성, WinError 32 없음. Full success 경로에서도 결과 파일·report가 닫힌 뒤 임시 작업 폴더가 정리됨.
- 실제 `C:\Users\user\Downloads\111.mp4`를 설치된 0.2.3에서 새 이름 `build/user-validation/0.2.3-111-retest.mp4`로 처리 완료. 41분 36초, 720×1280, 30 FPS, 206 frames, 6.8667초, 무음, 1,751,685 bytes. Report: 206/206 frames에서 텍스트 탐지, LaMa 14 frames, Telea 192 frames, CRAFT canvas 960, backend `opencl-fp16`.
- 원본/결과 0.5, 2.0, 3.5, 5.5초 비교: text는 제거됐고 전체 영상은 재생 가능한 구조지만, 2.0초 대각 레일 경계에 blocky smear, 3.5초 벽 영역에 부드러운 복원 patch가 관찰됨. 문자 제거의 시각 품질은 아직 완전 통과가 아니며 해당 artifact 감소가 다음 개선 대상.
- 앱 진행률은 Worker가 마지막 frame 처리를 끝내기 전까지 94.6%에 머물 수 있음(내부 99% cap). 이는 이번 실제 작업에서 실패 상태가 아니었고, 약 41분 36초 후 `completed`로 종료됨. UI의 마지막-frame/MP4 마무리 안내 개선은 남음.
- 취소 정리 회귀 포함 전체 unittest 100개 통과, Windows Credential Manager 전용 1개 skip. 서명된 0.2.3 MSIX SignTool 검증 0 errors / 0 warnings.

## Adaptive 문자 마스크·0.2.5 MSIX 재검증 (2026-10-13)

- 0.2.4의 고정 3px mask padding은 큰 합성 글자 일부가 남아 품질 실패로 판정했다. 글자 그룹 높이에 따라 3~8px로 margin을 조절하는 adaptive mask를 적용하고 크기별 단위 테스트를 추가.
- 실제 CRAFT/LaMa 모델로 영문 `Hello WORLD`, 한글 `한글 문자 제거`, 중국어 `中文文字测试`를 포함한 1-frame 영상을 처리. 탐지 mask ink coverage 세 언어 모두 1.000, report `frames=1`, `frames_with_text=1`, `lama_frames=1`, `mask_padding_policy=adaptive-per-text-group-3-8px` 확인.
- 소스 Pipeline 출력 preview에서 세 언어 글자가 제거되고 보정되지 않은 영역은 유지됨. FFmpeg 디코딩 성공.
- Desktop과 필수 OCR Worker를 PyInstaller 빌드하고, 모델·FFmpeg 포함 MSIX 0.2.5(601,569,761 bytes)를 서명. SignTool 검증: 오류 0, 경고 0. 설치 후 `0.2.5.0` 등록 확인.
- 설치 앱을 실행해 local UI HTTP 200, 문자 제거 준비 `ready=true` 확인. UI upload API로 같은 multilingual 영상 업로드 후 작업 `completed`; report adaptive padding, LaMa 1 frame 기록.
- 설치 앱 결과 MP4를 별도 검증 경로에 내려받아 ffprobe로 720×1280, 30 FPS, 1 frame, 무음 확인. preview에서 세 언어 글자 제거 확인. CPU 실행에서는 이 1-frame 처리도 수 분 걸려 실제 긴 영상 처리시간은 별도 검증 필요.
- 전체 unittest 102개 통과, Windows Credential Manager 검사 1개 skip. `TEMP/TMP`를 저장소 외부 시스템 Temp로 지정해 테스트 성공.
- `tests/manual_text_quality.py`는 adaptive padding을 쓰고 `build/manual-text-quality`에 산출하도록 변경. 패키지 설치 의존성 단계는 기존 venv setuptools를 사용하도록 `--no-build-isolation`을 명시.
- 실제 `C:\Users\user\Downloads\111.mp4`를 설치된 0.2.5에서 전체 처리: 29분 51초, 206/206 frames에서 text 검출, 12 LaMa / 194 Telea, 720×1280, 30 FPS, 6.8667초, 무음, 1,753,524 bytes. 이전 0.2.3 41분 36초보다 약 28% 짧게 완료.
- SignTool 서명·검증된 0.2.5 MSIX 설치 후 앱 시작, local UI 200, text-removal readiness true, 업로드부터 전체 출력까지 확인. WinError 5 `user_network` 경로 오류 없이 완료.
- 동일한 0.5/2.0/3.5/5.5초 원본·0.2.3·0.2.5 샘플 비교: text는 제거됨. 레일 경계, 벽, 커튼 주름 복원 흔적은 0.2.5에서도 남으며 일부 장면은 0.2.3과 비슷해 시각 품질 완전 해결로 보지 않음. 연속 재생과 움직이는 손·주름의 frame flicker는 사용자가 추가 검수해야 함.
- 비교 산출물: `build/review-artifacts/0.2.3-vs-0.2.5-comparison.jpg`, 새 출력 `C:\Users\user\Videos\ShortsStudio\111-0.2.5-adaptive-20261013.mp4`. 기존 원본 및 0.2.3 결과는 덮어쓰지 않음.

## 0.2.8 설치 앱에서 111.mp4 전체 재실행 (2026-10-14)

- 0.2.7에서 남았던 저대비 watermark를 보완하기 위해 CRAFT 4-frame persistent small-text consensus를 추가. 해당 mask를 각 영상 frame의 pixel mask와 합쳐 기존의 큰 Korean caption·`[광고]` 처리도 유지.
- MSIX 0.2.8.0 생성, 개발 인증서 서명 및 SignTool 검증 통과(오류 0, 경고 0). Windows 시작 메뉴에서 설치 앱을 실행해 local UI HTTP 200 및 필수 문자 제거 readiness 확인.
- 설치 앱 localhost API로 사용자 원본 `111.mp4`(1,355,711 bytes)를 업로드해 full run 완료. 처리 시간 31분 50초. 결과: `C:\Users\user\Videos\ShortsStudio\retest-0.2.8-111-20261014.mp4`.
- Report: `frames=206`, `frames_with_text=206`, `lama_frames=13`, `telea_frames=193`, `persistent_text_sample_frames=4`, `persistent_small_text_mask_pixels=1530`, CRAFT canvas 960, backend `opencl-fp16`, method `craft-pixel-mask-persistent-consensus-lama-telea-v2`.
- ffprobe: H.264, 720×1280, 30fps, 6.8667초, 1,751,647 bytes, video stream only. 0.5/2.0/3.5/5.5초 frame에서 Korean captions, `[광고]`, 영문 creator watermark를 제거했고, 정상 재생 크기에서 배경의 기하 왜곡은 보이지 않음. watermark 복원부를 확대하면 부드러운 patch 흔적이 조금 남지만 글자 잔상은 확인되지 않음.
- 비교 이미지: `build/review-artifacts/0.2.8-111/watermark-comparison.jpg`; 대표 frame: `build/review-artifacts/0.2.8-111/frame-{0_5,2_0,3_5,5_5}.jpg`.
- 전체 unittest 107개 통과, Windows Credential Manager 전용 테스트 1개 skip. `compileall src`, `pip check`, `git diff --check` 통과.
- 남은 수동 검수: 전체 영상을 연속 재생해 frame flicker/복원 질감을 확인하고, 별도 영상의 영문·중문·기울어진 글씨 샘플도 검수.

## 0.2.7 설치 앱에서 111.mp4 전체 재실행 (2026-10-14)

- 서명·설치된 MSIX 0.2.7.0을 실행해 사용자 원본 `111.mp4` 업로드와 문자 제거 전체 작업을 완료. 제한된 Codex shell에서 실행한 앱은 사용자 LocalAppData 쓰기가 차단돼 업로드가 실패했지만, Windows 권한으로 앱을 재실행한 뒤 업로드와 작업이 정상 완료됨. 제품 코드의 업로드 경로 문제는 아니며 Codex 제한 실행 환경에서만 재현.
- 처리 시간 31분 32초. 출력 `C:\Users\user\Videos\ShortsStudio\5aff3ac55fe4f6f5063d7238a4d7c050_20261014-044414.mp4`; H.264, 720×1280, 30fps, 6.8667초, 1,751,782 bytes, video stream only.
- Report: 206/206 frames에서 문자 감지, LaMa 13 / Telea 193, CRAFT canvas 960, backend `opencl-fp16`, adaptive padding 3–8px.
- 0.5/2.0/3.5/5.5초를 0.2.6 및 원본과 비교. 주요 한국어 caption과 `[광고]`는 제거되고 배경의 심한 기하 왜곡은 재현되지 않음. CLAHE로 저대비 creator watermark가 0.2.6보다 크게 약해졌으나 확대 시 흐린 잔상이 남아 사용자의 필수 기준인 “모든 문자 완전 제거”는 **미통과**. watermark mask coverage를 추가로 개선해야 함.
- 5.5초 frame에서 threshold 0.20→0.08, CRAFT canvas 960→1280 단일 frame 실험을 추가했으나 watermark 전체 glyph mask가 생성되지 않아 완전 제거를 입증하지 못함. 임계값 일괄 인하는 다른 자막/배경 영역의 과검출 위험이 있어 production 설정에 반영하지 않음.
- 비교 산출물: `build/review-artifacts/111-0.2.7-{0_5,2_0,3_5,5_5}.jpg`, `111-0.2.7-5_5-crop-contrast.png` 및 동일 시점의 원본/0.2.6 frame.
- 현재 전체 unittest 106개 통과, Windows Credential Manager 전용 1개 skip. 출력의 직접 연속 재생/flicker는 최종 수동 검수 대기.

## 0.2.6 설치 앱에서 111.mp4 전체 재실행 (2026-10-14)

- 서명된 MSIX 0.2.6 설치 앱에 사용자 원본 `111.mp4`를 선택하고 실제 문자 제거 버튼으로 full run 완료. 오류 메시지 없이 설치 경로의 Worker가 실행됐고 output/report가 자동 저장됨.
- 출력 `C:\Users\user\Videos\ShortsStudio\05dd3ab055390dc304b9e533da9cfd90_20261014-000732.mp4`; H.264, 720×1280, 30fps, 6.8667초, 1,753,524 bytes, audio stream 없음.
- Report: 206/206 frames에서 text mask가 생성됨, LaMa 12 / Telea 194, CRAFT canvas 960, backend `opencl-fp16`, adaptive padding 3–8px. 설치 경로 `user_network`의 WinError 5는 재현되지 않음.
- 0.5/2.0/3.5/5.5초 비교에서 중앙 Korean caption과 상단 `[광고]`는 제거됨. 저대비 creator watermark는 화면 좌측 하단에 상당 부분 희미하게 남아 있어 “모든 문자 제거” 기준은 **미통과**. 원본 CRAFT mask 0.2 threshold 진단에서는 워터마크 영역 탐지가 조각난 형태로 나타남; low-contrast watermark의 mask coverage/padding을 개선해야 함.
- 비교 이미지: `build/review-artifacts/111-0.2.6-0_5.jpg`, `111-0.2.6-2_0.jpg`, `111-0.2.6-3_5.jpg`, `111-0.2.6-5_5.jpg`, `111-0.2.6-watermark-crop.jpg` 및 동일 timestamp의 `111-original-*.jpg`.
- 0.2.6 설치 UI 설정에서 `Microsoft Heami` 및 “무료 로컬 TTS 사용 가능” 확인. 이번 실영상 실행에는 분석/대본이 없어 실제 Heami 합성 및 subtitle sync는 별도 수동 확인.
- 최신 unittest 105개 통과, Credential Manager 전용 테스트 1개 skip. `compileall src`, `pip check`, `git diff --check` 통과.

## 0.2.5 재실행 및 temporal 복원 prototype 검토 (2026-10-13)

- 사용자 원본 `111.mp4`를 workspace Core Engine CLI로 다시 전체 처리. MSIX에 포함된 FFmpeg/ffprobe와 OCR/LaMa 모델 경로를 명시해 설치 앱과 같은 버전의 엔진을 사용. 결과 `C:\Users\user\Videos\ShortsStudio\111-0.2.5-retest-20261013.mp4`; 원본 및 기존 출력은 덮어쓰지 않음.
- Report: `frames=206`, `frames_with_text=206`, `lama_frames=12`, `telea_frames=194`, CRAFT 960, backend `opencl-fp16`. ffprobe: H.264, 720×1280, 30fps, 6.8667초, video stream only. 결과 크기 1,753,524 bytes.
- 0.5~6.5초의 7개 샘플과 0.5초 상단 `[광고]` 확대 crop에서 표기 제거 확인. 3.5초 자막 crop도 글자는 없어졌지만 배경에 부드러운 복원 patch가 보임. 연속 재생/flicker는 사람의 최종 검수가 남음.
- 인접 프레임 optical-flow confidence merge prototype을 5.5초 영역에 적용해 5.3~5.8초 reference를 비교. 5.7초 reference만 23.6% mask coverage에 도달했으나 확대 시 옅은 얼룩을 만들 수 있어 production 경로에는 연결하지 않음. 보수적 fallback 및 scene-difference 단위 테스트만 유지.
- 번들 FFmpeg/ffprobe 지정 후 전체 unittest 104개 통과, Credential Manager 전용 1개 skip. Python `compileall`, `pip check`, `git diff --check`도 통과.
- 비교 이미지: `build/review-artifacts/111-retest-0.2.5.jpg`, `111-retest-caption-crop.jpg`, `111-retest-watermark-crop.jpg`, `temporal-neighbor-5_5.jpg`. 남은 사용자 확인: 전체 영상 연속 재생, 잔여 문자, 복원 질감/움직임 flicker 승인.

## 0.2.6 Heami TTS 패키징 및 재실행 검증 (2026-10-13)

- WinRT 음성 탐색에 필요한 `Windows.Foundation` projection 누락을 확인해 TTS 선택창이 “Windows 음성 목록을 읽지 못했습니다”로 표시되던 원인을 수정. PyInstaller 수집 설정과 pinned dependency를 보완하고 regression test를 추가.
- Desktop/Worker 재빌드 후 MSIX 0.2.6 서명·검증 통과, 설치 버전 `0.2.6.0` 확인. 설치된 Shorts Studio를 다시 실행해 local web UI를 열고 설정에서 `Microsoft Heami` 및 `무료 로컬 TTS 사용 가능` 상태를 확인.
- 전체 unittest 105개 통과, Windows Credential Manager 전용 테스트 1개 skip. FFmpeg/ffprobe 경로를 지정해 변환 integration test를 포함했고, `compileall src`, `pip check`, `git diff --check` 통과.
- 이 테스트에서는 voice readiness와 packaged UI를 확인했으며 실제 대본을 넣은 Heami WAV/최종 영상 합성은 수행하지 않음. 사용자는 영상 등록 → 문자 제거 → 대본 입력/생성 → `한국어 음성·자막 합성` 순서로 실제 발화, 자막 싱크, 음질을 확인해야 함.
