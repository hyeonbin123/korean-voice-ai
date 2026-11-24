# 환경

이 저장소의 맨 위에는 파이썬 프로젝트가 없다(`pyproject.toml`·`uv.lock`이 없다). 다섯 구성 요소는 폴더마다 자기 파이썬 버전 범위, 잠금 파일, 의존성 그룹을 따로 가지고, 설치와 시험은 각 구성 요소 폴더 안에서 한다.

## 구성 요소별 환경

| 구성 요소 | 파이썬 | 잠금 파일 | CI 설치 범위 | 로컬 환경에 더하는 그룹 | GPU를 쓰는 곳 | 기본 포트 | compose 프로젝트 |
|---|---|---|---|---|---|---|---|
| whisper-ko-ft | `>=3.11,<3.13` | `uv.lock` | 기본 + `dev`·`ct2` 그룹의 잠긴 판(torch는 같은 판의 CPU 빌드) | `ct2` | 학습·측정 | 없음 | 없음 |
| stt-scratch | `>=3.11,<3.13` | `uv.lock` | 기본 + `dev`(torch·torchaudio는 같은 판의 CPU 빌드) | 없음 | 학습·측정, 스트리밍 자막 서버(CUDA가 있으면 기본으로 GPU) | 8765(스트리밍 자막 서버) | 없음 |
| voice-translator | `>=3.11`(`backend/`) | `backend/uv.lock`, `frontend/package-lock.json` | 백엔드 `uv sync --locked`(기본 + `dev`), 화면 `npm ci`(Node.js 24) | 측정 도구는 `gpu`, `eval`. 서버는 `gpu`, `tts` | 서버(`api`·`ollama` 컨테이너)와 측정 | DB 55442, 웹 8080 | 폴더 이름 |
| support-agent | `>=3.11` | `uv.lock` | `uv sync --frozen`(기본 + `dev`) | `voice`(음성 채널) | 에이전트·시뮬레이터 언어 모델(Ollama), `voice` 그룹의 음성 합성·인식 | DB 55462, 앱 8062, MCP 서버 8063(`--http`) | `support-agent`(compose 파일에 고정) |
| call-summary | `>=3.11` | `uv.lock` | `uv sync --frozen`(기본 + `dev`) | `train`(학습·transformers 추론) | 학습, 서빙 모델(Ollama) | 8072 | 폴더 이름 |

- 파이썬 열은 각 `pyproject.toml`의 `requires-python`이다. 다섯 구성 요소의 워크플로에서 시험(`pytest`)을 돌리는 작업(voice-translator는 `backend`, 나머지는 `test`)은 파이썬 3.11로 돈다(워크플로의 `python-version` 또는 `UV_PYTHON`).
- CI는 GPU가 없는 Linux 러너에서 돈다. 그래서 다섯 구성 요소의 시험은 GPU 없이 돈다. support-agent와 call-summary에는 모델 없이 도는 오프라인 앱도 있다([architecture.md](architecture.md#구성-요소와-인터페이스)).
- '로컬 환경에 더하는 그룹'은 학습·측정·서비스를 로컬에서 돌릴 때 `uv sync --frozen` 뒤에 `--group <이름>`으로 붙이는 의존성 그룹이다. 시험·린트 도구(pytest, ruff 등)를 담은 `dev`는 uv가 따로 붙이지 않아도 설치하는 기본 그룹이라 이 열에 적지 않았다. voice-translator 백엔드의 `eval`과 `tts`는 함께 설치할 수 없다(아래).
- 기본 포트는 compose 파일이나 명령줄 옵션의 기본값이다. voice-translator와 support-agent의 compose는 환경 변수로 호스트 포트를 바꿀 수 있다.
- voice-translator와 call-summary의 compose 파일에는 프로젝트 `name`이 없어, compose 프로젝트 이름이 그 폴더 이름이 된다. 같은 이름의 폴더에서 compose를 돌리면 같은 프로젝트로 묶인다.
- 통화 한 건 시연(`e2e/`)도 자기 `pyproject.toml`과 `uv.lock`을 가진다. 설치와 실행은 [`e2e/README.md`](../e2e/README.md)에 있다.

## 하나의 잠금으로 묶지 않는 이유

구성 요소의 잠금 파일은 같은 패키지를 서로 다른 판으로 고정한다(각 `uv.lock` 기준, 2026-11-14 확인).

- support-agent는 음성 합성 MeloTTS 때문에 `transformers 4.27.4`, `tokenizers 0.13.3`, `numpy 1.26.4`다.
- whisper-ko-ft와 call-summary는 `transformers 5.17.0`, `numpy 2.4.6`(파이썬 3.11) 또는 `2.5.3`(3.12 이상)이다.
- voice-translator 백엔드는 한 잠금 안에 둘 다 있다. 측정 도구 그룹(`eval`)은 `transformers 5.17.0`, 음성 합성 그룹(`tts`)은 MeloTTS 때문에 `transformers 4.27.4`이고, 두 그룹은 함께 설치하지 않도록 `backend/pyproject.toml`에 충돌로 적혀 있다.

그래서 다섯 구성 요소의 환경(위 표의 그룹까지 붙인 것)은 한 가상환경에 함께 설치할 수 없다(예: support-agent의 `voice` 그룹은 `transformers==4.27.4`를, whisper-ko-ft는 `transformers>=4.57`을 요구한다). 잠금 파일 하나로 합치려면 다섯의 의존성을 다시 풀어야 하고, 그때 판이 바뀌면 기록된 수치를 낸 환경과 달라진다. 예를 들어 whisper-ko-ft의 영어 보조 지표 정규화는 transformers 판에 따라 동작이 바뀔 수 있어 5.17.0을 기준으로 규칙을 적었다([`src/whisper_ko_ft/en_norm.py`](../whisper-ko-ft/src/whisper_ko_ft/en_norm.py) 머리 주석).

잠금 파일은 등록한 갱신으로만 바뀐다. 추적되는 `uv.lock`과 `package-lock.json`마다 그 파일을 들인 커밋과 그 뒤의 갱신(어느 커밋이 어떤 판을 왜 바꿨는지)을 [`tools/locks.toml`](../tools/locks.toml)에 적어 두고, [`tools/check_lock_drift.py`](../tools/check_lock_drift.py)가 CI에서 그 등록을 git 이력과 맞춰 본다. 등록하지 않은 변경이 있으면 실패한다.

## 쓰는 법

- 각 구성 요소 폴더 안에서 잠금 파일대로 가상환경을 새로 만든다: `uv sync --frozen`에 위 표의 그룹을 붙인다(예: call-summary는 `uv sync --frozen --group train`). `--frozen`은 잠금 파일을 고치지 않고 그 판 그대로 설치한다.
- 그룹을 붙여 만든 환경에서 그룹 없이 `uv sync`를 다시 부르면 그 그룹의 패키지가 지워진다(call-summary README의 설치 절). 만든 환경을 그대로 쓰려면 `uv run --frozen --no-sync`로 실행한다. 기본 `uv run`은 실행하기 전에 환경을 잠금 파일에 맞춘다.
- 다른 구성 요소의 환경이 필요한 스크립트는 그 구성 요소의 `.venv` 안 파이썬을 직접 부른다. 예: call-summary의 음성 조건 스크립트는 support-agent의 `.venv`에서 돈다([architecture.md](architecture.md#구성-요소-사이-의존)).

## Windows에서 받기

```bash
git clone -c core.autocrlf=false -c core.longpaths=true https://github.com/hyeonbin123/korean-voice-ai
```

- `core.autocrlf=false`: Git for Windows를 설치할 때 기본으로 고르는 설정(`core.autocrlf=true`)으로 받으면, `.gitattributes`가 줄바꿈을 정하지 않은 파일이 CRLF로 풀려 바이트가 바뀐다(stt-scratch와 voice-translator에는 `.gitattributes`가 없다). 기록에는 LF 바이트로 계산한 해시가 남아 있다. 예: stt-scratch `manifests/vocab.json`의 SHA-256이 `reports/stage6/client-dev_h-defaults-meta.json`의 `vocab_sha256`에 있다.
- `core.longpaths=true`: Windows의 경로 길이 제한(260자)을 넘는 경로도 git이 다루게 한다. 저장소 안 경로만 100자가 넘는 파일이 있어, 깊은 폴더 아래에 받으면 그 제한에 닿을 수 있다.
