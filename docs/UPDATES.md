# GitHub Release 자동 업데이트

Desktop의 `업데이트 설정`에 GitHub `owner/repo`와 Ed25519 공개키의 base64 값을 입력합니다. 공개키는 `[LOCALAPPDATA]\ShortsStudio\updates.toml`에 저장되며 private key는 앱이나 저장소에 넣지 않습니다. 설정 후 `업데이트 확인`은 최신 정식 GitHub Release와 서명을 검사합니다.

새 Release를 만들 때는 먼저 앱/패키지/installer 버전을 동기화하고 Portable ZIP을 다시 빌드합니다. `set-version.py`가 네 곳의 version을 함께 변경합니다.

```powershell
.\.venv\Scripts\python.exe .\scripts\set-version.py 0.2.1
powershell -ExecutionPolicy Bypass -File .\scripts\package-windows.ps1
```

Release에는 다음 두 파일을 같은 tag로 업로드해야 합니다.

- `ShortsStudio-Portable.zip`
- `shorts-studio-update.json`

업데이트 manifest는 ZIP의 SHA-256과 버전에 Ed25519 서명을 붙입니다. 자동 검증용 키 쌍을 한 번 생성하고 private key PEM은 저장소 밖의 안전한 위치에 보관합니다. 공개키는 앱 설정에 등록합니다. 서명 private key를 저장소, Release asset, 채팅에 올리지 않습니다.

```powershell
# 저장소 루트에서 실행하되, private key 파일은 저장소 밖에 둡니다.
$keyPath = 'C:\secure\shorts-studio-update-private.pem'
New-Item -ItemType Directory -Force (Split-Path $keyPath) | Out-Null
$env:SHORTS_SIGNING_KEY_PATH = $keyPath
@'
from getpass import getpass
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import base64
import os
key = Ed25519PrivateKey.generate()
with open(os.environ["SHORTS_SIGNING_KEY_PATH"], "wb") as f:
    f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(getpass("New signing-key passphrase: ").encode())))
print(base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode())
'@ | .\.venv\Scripts\python.exe -

# 저장소 루트에서 빌드 결과에 서명하고 ZIP과 manifest를 GitHub Release assets에 업로드
C:\path\to\shorts-studio\.venv\Scripts\python.exe .\scripts\create-update-manifest.py 0.2.1 `
  .\build\package-dist\ShortsStudio-Portable.zip `
  C:\secure\shorts-studio-update-private.pem
```

Release tag는 `v0.2.1`처럼 앱 version보다 큰 안정 버전이어야 합니다. manifest는 `scripts/create-update-manifest.py`로 만들고 두 파일을 GitHub Release에 올립니다. 실제 공개 저장소·서명키·Release가 준비되기 전에는 updater가 설정 또는 네트워크 오류를 보여 주며 앱 파일을 변경하지 않습니다.

다운로드 후 updater는 서명, 버전, 파일명, SHA-256과 크기를 검사합니다. 서명한 ZIP을 사용자별 staging 경로에 받은 뒤 현재 앱 종료를 기다리고, 새 앱과 mandatory OCR worker가 모두 있을 때 설치 경로를 교체합니다. 교체가 실패하면 기존 디렉터리를 복구합니다. 작업 기록, 설정, OCR 모델 캐시는 설치 디렉터리 밖에 둡니다.
