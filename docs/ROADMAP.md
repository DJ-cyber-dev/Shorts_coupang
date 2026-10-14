# Shorts Studio 개발 항목

개발은 아래 순서로 진행한다. 영상에 포함된 문자 탐지·제거는 모든 제작 경로에서 필수 단계다. 각 단계에서 자동 검사와 수동 검증 항목을 분리하고, 계정/API나 실제 영상이 필요한 수동 검증은 사용자가 실행할 목록에 기록한다.

## 개발 항목

| 순서 | 영역 | 개발 항목 | 현재 상태 |
|---|---|---|---|
| 0 | 저장소·구조 | Git 기반 프로젝트, Windows/다른 PC 개발 환경, UI/Core/Provider/기능 모듈 분리 | 구현됨. GitHub remote 연결과 다른 PC 접근은 사용자 계정 작업 필요 |
| 1 | Core Engine | 로컬 파일 및 YouTube/TikTok URL 입력, 임시 다운로드, 9:16 pad/crop, CFR 변환, 무음화, 진행률·취소·오류 정리 | 기본 구현됨. 용량 기반 디스크 사전 점검과 marker가 있는 오래된 임시 폴더 정리 추가. 실제 사이트별 다운로드는 미검증 |
| 2 | 필수 문자 제거 | 언어 필터 없는 전체 화면 문자 탐지, 문자 영역 복원, 비교 미리보기, 결과 보고서 | CRAFT pixel mask와 작은 반복 문자를 위한 4-frame persistent consensus, 큰 영역용 crop LaMa 및 작은 영역용 Telea 구현. CPU 논리 프로세서 수를 보고 PyTorch 최대 8 threads 사용, 지원 PC는 LaMa OpenCL FP16 가속 및 오류 시 CPU 재시도. 모든 제작 경로에서 필수 실행. MSIX 0.2.11에서 `111.mp4` 전체 6.8667초/206 frames 처리하고 `WinError 5` 없이 완료. Korean captions, `[광고]`, 저대비 영문 watermark 제거와 대표 frame 배경 보존 확인. 2026-10-14 실제 CRAFT 모델 합성 영상 검증에서 영어·한글·중문 mask coverage 각각 100%, LaMa 포함 pipeline 출력과 decode 통과. watermark 복원부 smoothing과 연속 재생/flicker 최종 검수는 남음 |
| 3 | 설정·Provider | Provider 설정 화면, 모델/base URL 선택, 환경변수·Windows Credential Manager 키 등록, 연결 확인 | AI/Gemini 설정 구현. 0.2.13 설치본에서 stable 4개 모델 선택·저장, 기존 key 보존, 실제 Gemini 연결 확인 완료. TTS는 Windows Heami local voice; 현재 설치본 준비 상태 정상, 0.2.9에서 실합성 완료 |
| 4 | AI 영상 분석 | 장면/행동/제품/텍스트 요약, 구간별 timestamp, 분석 결과 편집·저장 | OpenAI-compatible vision adapter, 최대 8개 저해상도 frame 샘플, CLI, Desktop 확인·편집·JSON 저장 UI 구현. 실제 Provider 확인 미구현 |
| 5 | 한국어 Shorts 생성 | 길이·톤 템플릿, 분석 기반 한국어 대본 생성, 대본 편집·재생성 | Gemini API 기반 생성, stable 모델 선택, 전용 API Key 설정·연결, 입력 가이드, 길이·톤·CTA, 결과 JSON 편집 구현. 0.2.13 실연결 성공; 실제 영상 분석 JSON 기반 대본 품질 검수는 남음 |
| 6 | 한국어 음성·자막 | 무료 로컬 TTS 음성 생성, 문장별 타이밍, 자막 편집, 영상 합성 | Heami WinRT TTS adapter, WAV, SRT, burn-in 구현. MSIX 0.2.9에서 `테스트입니다.` 실합성, WAV/SRT 생성, H.264+AAC mux와 전체 decode 확인. 실제 대본의 발음·자막 싱크는 수동 청취/화면 검수 |
| 7 | 상품 매칭 | 영상/대본 키워드로 쿠팡 후보 최대 10개 자동 검색, 상품 후보·가격·링크·제공되는 리뷰/판매 지표 표시, 사용자 선택 및 대본 연결 | provider 독립 schema/ranking, JSON 후보 입력, Coupang Partners HMAC-SHA256 search adapter, Windows Credential Manager credentials UI, 로컬 hourly limit, 웹 검색 결과 10개 및 자동 게시 문안 초안 구현. 판매/리뷰 지표는 API 응답에 포함된 경우만 표시하며 미제공은 명시. mock 통과. 실제 응답·affiliate link 검증은 승인된 account/key가 필요 |
| 8 | 소싱 자동화 | 키워드 기반 후보 검색, 출처·URL·길이·라이선스 정보 기록, 미리보기 및 사용자 선택, 다운로드 후 Core 연결 | YouTube Data API Creative Commons·4분 미만 후보 검색 UI, 사용자 선택 후 URL 전달, API key Credential Manager 저장, 출처 JSON 기록 구현. TikTok 직접 URL 및 승인된 Commercial Content API의 EEA 광고 keyword search를 구현. 광고는 참고 후보이며 재사용 권리는 별도 확인. 일반 organic video keyword search는 제공 API 범위 밖 ([Commercial Content API](https://developers.tiktok.com/products/commercial-content-api), [Research API eligibility](https://developers.tiktok.com/products/research-api/)) |
| 9 | 업로드 | YouTube 우선 업로드 adapter, OAuth 자격증명, 제목/설명/태그/공개 범위, 예약 및 결과 기록 | Desktop metadata 입력·OAuth 업로드 UI와 CLI, resumable upload, retry, 비공개 기본값, 예약·receipt 구현. OAuth Cloud 설정과 실제 채널 검증은 수동 |
| 10 | Desktop 마감 | 작업 설정·대본·상품·자막 편집 UI, 작업 재개/로그/임시파일 복구, 설치형 패키지·업데이트·제거 | Desktop AI/대본/TTS/source/upload UI와 로컬 작업 기록·중단 복구/재실행, marker 기반 stale temp 정리 구현. PyInstaller app/worker 및 per-user 설치·제거 패키지 구현. Ed25519 서명된 GitHub Release 업데이트 확인·검증·단계 설치와 복구 helper 구현. 공개 저장소·서명키·Release 설정 및 clean Windows 설치 검증은 별도 수동 |

## 별도 테스트 목록

### 자동 테스트

- 각 모듈의 단위 테스트와 mocked Provider/API 테스트.
- URL 검증, 실패·취소 시 임시 파일 정리, 출력 검증과 원본 보존.
- 인코딩 전 디스크 여유 공간 추정 및 force-close 후 stale marker 임시 폴더 정리.
- 문자 탐지 mask 생성, 빈 mask, 다국어 샘플, 프레임 경계·고정/이동 배경 회귀.
- LaMa crop 입력/출력 shape, mask 안 픽셀 복원, mask 밖 원본 보존.
- 분석 구간 timestamp, 한국어 대본 형식, TTS 파일·자막 시간 정렬.
- 상품 후보 매핑, 중복·빈 검색 응답, 업로드 메타데이터와 재시도.
- 상품 후보 JSON 형식/가격 파싱, ranking과 중복 ID 제거, script에 선택 상품 metadata 연결.
- Coupang Partners HMAC 서명, 한글 query encoding, 응답 mapping, API 실패 처리와 시간당 호출 제한.
- Windows 설치·설정 저장 경로, secret 평문 미저장, 로그 내 민감정보 마스킹.
- Desktop AI 설정 화면에서 Provider 저장, 환경 변수명 적용, Windows Credential Manager 저장/불러오기.
- GitHub Release manifest 서명, 버전/파일명/SHA-256 검증, 손상·위조 ZIP 거부와 설정 저장 검사.
- Windows local TTS WAV adapter, 기본 Heami 설정, MSIX 빌드 script 구문 검사.

### 설치 앱에서 완료한 수동 검증

- MSIX 0.2.8에서 실제 `111.mp4` 전체 처리: 206/206 frames, 13 LaMa / 193 Telea, 720×1280, 30fps, 무음. 대표 frame에서 Korean caption, `[광고]`, 영문 watermark 제거를 확인. 확대 복원부의 약한 smoothing과 연속 재생/flicker 평가는 계속 남음.
- MSIX 0.2.11에서 `111.mp4` 전체 6.8667초/206 frames 처리: 206/206 text 감지, LaMa 13 / Telea 193, `WinError 5` 재발 없음, 전체 decode PASS. 0.5/2.0/3.5/5.5초 비교에서 한국어 caption, `[광고]`, 저대비 영문 watermark 제거 확인. frame montage는 `build/review-artifacts/0.2.11-retest-111-full-frames.jpg`.
- 0.2.11 웹 화면의 1~5단계 버튼을 눌러 각 섹션으로 이동하는 동작 확인.
- MSIX 0.2.13에서 Gemini 모델 선택·저장, API key 보존, 실제 Gemini 연결 성공. 전체 suite 111 pass / 1 Windows-only skip; MSIX signature verification pass.
- 실제 CRAFT/LaMa 모델로 영어 `Hello WORLD`, 한글 `한글 문자 제거`, 중문 `中文文字测试` 샘플을 탐지·처리. 각 언어 mask coverage 100%, 필수 제거 report와 H.264 출력 decode PASS.
- Windows Portable ZIP 0.2.13 생성, 8,247개 항목 CRC 및 앱·Worker·FFmpeg·모델·license·install/uninstall helper 포함 확인. ZIP은 Core Engine/문자 제거용이며 Heami WinRT TTS는 package identity가 필요한 MSIX에서만 제공. 새 Windows 계정에서 ZIP 추출·실행·제거 검증은 남음.
- MSIX 0.2.9에서 Heami offline 실합성과 최종 H.264/AAC 렌더 확인. 샘플 문장 `테스트입니다.`로 WAV·SRT 생성 및 전체 decode PASS.

### 사용자 계정·장비에서 남은 수동 검증

- `111.mp4` 전체 출력의 연속 재생으로 잔상·flicker 및 복원부 smoothing 최종 확인. 한글·영문·중문·작은 글씨·기울어진 글씨·워터마크가 함께 있는 다른 영상도 확인.
- 실제 YouTube Shorts와 TikTok 공개 URL의 다운로드, 취소, 실패 동작 확인.
- Gemini 모델 선택과 연결은 0.2.13에서 확인 완료. 실제 영상 분석 JSON 기반 대본의 정확성·톤·제품 표현을 검수. AI Provider key로 frame 분석과 분석 JSON 편집·저장 확인.
- 실제 대본으로 Heami 발음, 음량, 자막 timestamp·위치·폰트·음성 싱크 검수.
- YouTube API key로 Creative Commons 검색·다운로드와 `.source.json` 출처 기록 확인.
- TikTok Commercial Content API 승인이 나면 client key/secret을 설정하고 EEA 광고 검색을 확인.
- Coupang Partners 계정/API key 발급 후 최대 10개 검색, 실제 판매·리뷰 지표와 affiliate URL 검증. 현재 계정이 없어 실제 API 연동 확인은 대기 중.
- 후보 상품 선택 후 게시 metadata 자동 입력 확인. OAuth client JSON과 본인 YouTube 채널로 비공개 업로드·재생을 먼저 검증.
- Desktop 작업 기록에서 강제 종료 작업을 `interrupted`로 복구·재실행. 게시 metadata 편집, 비공개 기본값 및 공개 전 확인 동작 검증.
- 깨끗한 Windows 계정/PC에서 설치, 실행, 업데이트, 제거·재설치. PyInstaller/Inno Setup 및 Portable ZIP 패키지의 worker·FFmpeg·model 포함 여부 확인.
- GitHub 저장소 URL을 받아 remote를 연결한 뒤 PC에서 push/pull 및 다른 PC·Android 개발 UI 접근 확인. 현재 저장소는 첫 commit과 remote가 없음.
- 실제 signed GitHub Release를 통한 update와 rollback, 저장공간 부족 안내 및 12시간 지난 임시 폴더 정리, Android 브라우저 장시간 CPU·메모리 사용 검증.

현재 자동 테스트 실행 기록은 `VALIDATION.md`에 유지한다. 사용자가 필요한 계정/API 키를 제공하지 않아도 개발 가능한 adapter, mock, UI, 오류 처리는 먼저 구현하고 실제 연동 테스트는 별도 수동 목록에 둔다.
