# 구조와 연결

이 저장소의 다섯 구성 요소는 폴더마다 자기 환경과 잠금 파일(파이썬은 `uv.lock`, voice-translator의 화면은 `package-lock.json`)을 가진 독립 프로젝트다. 서로의 `pyproject.toml`에 의존성으로 적혀 있지 않고, 각자 자기 폴더 안에서 설치하고 실행한다. 이 문서는 그 사이가 어디서 이어지는지를 적는다: 바깥으로 내놓는 인터페이스, 파일 경로로 이어진 의존, 코드로는 잇지 않은 관계. 파일 의존은 [`tools/cross-deps.toml`](../tools/cross-deps.toml)에 선언하고 [`tools/check_cross_deps.py`](../tools/check_cross_deps.py)로 검사한다.

## 구성 요소와 인터페이스

whisper-ko-ft만 서비스가 없고, 나머지 넷은 각자 자기 서비스를 내놓는다.

| 구성 요소 | 하는 일 | 바깥 인터페이스 | 진입 파일 | 기본 포트 |
|---|---|---|---|---|
| [`whisper-ko-ft`](../whisper-ko-ft/) | 공개 한국어 음성 데이터로 Whisper를 파인튜닝하고, 미리 정한 규칙으로 전후를 측정한다 | 서비스 없음. 학습·평가 명령줄(`uv run python -m whisper_ko_ft.<모듈>`, [README의 실행](../whisper-ko-ft/README.md#실행)). 학습한 모델을 CTranslate2로 바꾼 폴더를 다른 구성 요소가 파일로 읽는다 | `src/whisper_ko_ft/`의 모듈(`download`, `prepare`, `train`, `evaluate`, `evaluate_ct2` 등) | 없음 |
| [`stt-scratch`](../stt-scratch/) | 한국어 음성 인식 모델을 처음부터 설계·학습하고 스트리밍 자막 서비스로 묶는다 | WebSocket 스트리밍 자막 서버: `ws://<호스트>:<포트>/ws`로 16 kHz 모노 16비트 PCM을 보내면 JSON 자막 이벤트를 돌려준다. 같은 포트의 `/`에서 브라우저 자막 페이지도 연다 | [`src/stt_scratch/service/server.py`](../stt-scratch/src/stt_scratch/service/server.py) (`uv run python -m stt_scratch.service.server`) | 8765 ([`--port` 기본값](../stt-scratch/src/stt_scratch/service/server.py#L602)) |
| [`voice-translator`](../voice-translator/) | 영어↔한국어 음성 번역 웹 서비스. 음성 인식, 번역, 음성 합성을 거쳐 원문과 번역문을 보여 주고 번역문을 읽어 준다 | FastAPI HTTP API(`/api` 아래, 계약은 [`docs/api.md`](../voice-translator/docs/api.md))와 웹소켓 `/api/translate/live`(동시통역, 로그인한 화면의 대화 모드·두 사람 대화), React 화면 | [`backend/app/main.py`](../voice-translator/backend/app/main.py), 화면은 `frontend/` | 8080 (웹. [compose의 `WEB_HOST_PORT` 기본값](../voice-translator/docker-compose.yml#L128)) |
| [`support-agent`](../support-agent/) | 가상 쇼핑몰 고객센터 업무를 도구 호출로 처리하는 한국어 LLM 상담 에이전트와, 그 에이전트를 미리 정한 규칙으로 재는 평가 환경 | HTTP 채팅 API(답을 SSE로 흘려 준다), 관리자 API와 관리 화면, MCP 서버 | 서비스 [`src/support_agent/service/app.py`](../support-agent/src/support_agent/service/app.py), MCP 서버 [`src/support_agent/mcp_server.py`](../support-agent/src/support_agent/mcp_server.py) (`uv run python -m support_agent.mcp_server`) | 8062 ([compose](../support-agent/compose.yaml#L47)). MCP의 `--http`는 8063 ([`--port` 기본값](../support-agent/src/support_agent/mcp_server.py#L242), [문서의 실행 예](../support-agent/docs/mcp.md#L10)) |
| [`call-summary`](../call-summary/) | 상담 대화 전사를 상담 후처리 기록(JSON)으로 바꾸는 소형 LLM을 학습하고 로컬에서 서빙한다 | HTTP `POST /summarize` | [`src/call_summary/service.py`](../call-summary/src/call_summary/service.py) | 8072 ([compose](../call-summary/compose.yaml#L6)) |

support-agent와 call-summary에는 모델 없이 도는 오프라인 앱이 있다. support-agent는 [`create_offline_app`](../support-agent/src/support_agent/service/offline.py#L114)에서 언어 모델과 음성 모델 자리에 규칙 몇 줄짜리 대역을 끼우고, call-summary는 [`create_offline_app`](../call-summary/src/call_summary/service.py#L1082)에서 늘 같은 기록을 돌려주는 가짜 제공자를 쓴다. 둘 다 모델을 올리지 않으므로 GPU가 필요 없고, 웹 계층은 실제 서비스와 같은 코드다.

## 통화 한 건이 지나가는 길

콜센터 통화 한 건은 개념상 네 곳을 차례로 지난다.

1. 음성 인식: 통화 음성을 글로 받아 적는다. whisper-ko-ft(Whisper 파인튜닝과 측정)와 stt-scratch(처음부터 만든 스트리밍 인식)가 이 일을 다룬다.
2. 실시간 음성 계층: 말하는 동안 음성 인식, 처리, 음성 합성을 이어 붙여 실시간으로 돌린다. 이 저장소에서 이 모양을 가진 것은 voice-translator다(대화 모드와 동시통역).
3. 상담 에이전트: 받아 적은 고객의 말에 도구를 호출해 업무를 처리하고 답한다. support-agent가 맡는다.
4. 상담 후처리: 끝난 통화의 전사를 요약, 문의 유형, 처리 결과를 담은 기록(JSON)으로 바꾼다. call-summary가 맡는다.

이 순서는 개념이고, 다섯 구성 요소를 처음부터 끝까지 이은 하나의 서버나 프로그램은 없다. 이 저장소에서 구성 요소 사이를 실제 코드로 잇는 곳은 둘이다.

- 통화 한 건 배선 시연(`e2e/`): support-agent의 오프라인 앱에 고객 발화를 HTTP로 보내고, 관리 API(`GET /api/admin/sessions/{id}`)로 읽은 대화를 call-summary의 오프라인 앱 `POST /summarize`에 넘겨 상담 후처리 기록을 받는다. 두 앱이 모델 없이 도는 오프라인 판이라 GPU가 필요 없다. call-summary 쪽이 늘 같은 기록을 돌려주므로 요약 품질을 재는 것이 아니라 두 서비스가 이어지는지만 보는 시연이다.
- 아래 [구성 요소 사이 의존](#구성-요소-사이-의존)의 파일 의존 네 군데.

## 구성 요소 사이 의존

한 구성 요소의 스크립트나 시험이 다른 구성 요소의 파일을 형제 폴더 경로로 직접 쓰는 곳은 아래 네 군데다. 검사 열의 '저장소 안'은 `--local` 없이 보는 것(코드의 글자, 추적 여부, 이력)이고, '로컬'은 `--local`을 줄 때만 보는 것(git이 추적하지 않아 이 PC에만 있는 폴더)이다.

| 무엇 | 쓰는 쪽 코드 | 대상 | 검사 |
|---|---|---|---|
| call-summary의 음성 조건 스크립트가 support-agent의 음성 환경과 소스에서 돈다. MeloTTS가 transformers 4.27을 요구해 call-summary 환경이 아니라 support-agent의 `.venv`에서 `PYTHONPATH=../support-agent/src`로 실행한다 | [`asr_condition.py` 7행](../call-summary/scripts/asr_condition.py#L7), [8행](../call-summary/scripts/asr_condition.py#L8), [`test_asr_condition.py` 33행](../call-summary/tests/test_asr_condition.py#L33) | [`speech.py`](../support-agent/src/support_agent/voice/speech.py), [`pyproject.toml`](../support-agent/pyproject.toml), 가상환경 `support-agent/.venv` | 저장소 안: 코드의 글자, 두 파일의 추적 여부. 로컬: `.venv`가 있는지 |
| call-summary가 음성 조건의 읽기를 support-agent 커밋 `a5717ce`의 `verbalize.py` 사본으로 고정했다. support-agent가 그 뒤 운송장번호 읽기를 고쳐서 현재 파일로는 기록된 읽기를 재현하지 못한다 | [`asr_condition.py` 89행](../call-summary/scripts/asr_condition.py#L89)(사본 경로), [90~92행](../call-summary/scripts/asr_condition.py#L90-L92)(커밋·원본 경로·blob) | 사본 [`verbalize_a5717ce.py`](../call-summary/scripts/verbalize_a5717ce.py), 원본의 현재 파일 [`verbalize.py`](../support-agent/src/support_agent/voice/verbalize.py) | 저장소 안: 코드의 글자, 두 파일의 추적 여부, 고정 커밋이 이 저장소 이력에 있는지와 그 시점 원본의 blob이 코드에 적힌 값과 같은지 |
| call-summary가 whisper-ko-ft에서 학습해 CTranslate2로 바꾼 `turbo-n`을 인식기로 쓴다(인식기를 바꿔 비교하는 갈래 중 N 팔) | [`asr_condition.py` 101행](../call-summary/scripts/asr_condition.py#L101) | `whisper-ko-ft/outputs/turbo-n/ct2`(학습·변환 결과라 git이 추적하지 않는다) | 저장소 안: 코드의 글자. 로컬: 그 폴더가 있는지 |
| stt-scratch의 봉인 test 사후 분석이 whisper-ko-ft의 발화별 turbo 제로샷 보고서와 숫자 발화 목록을 읽어, 같은 발화로 짝지어 다시 채점한다 | [`sealed_breakdown.py` 14행](../stt-scratch/scripts/sealed_breakdown.py#L14), [15행](../stt-scratch/scripts/sealed_breakdown.py#L15), [`test_sealed_breakdown.py` 42행](../stt-scratch/tests/test_sealed_breakdown.py#L42) | [turbo 제로샷 보고서](../whisper-ko-ft/reports/whisper-large-v3-turbo/zeroth-test.json), [숫자 발화 목록](../whisper-ko-ft/reports/digit_utterances/zeroth-test.json) | 저장소 안: 코드의 글자, 두 파일의 추적 여부 |

위 코드는 형제 폴더를 `../support-agent`처럼 상대 경로로 가리키거나 부모 폴더에서 폴더 이름으로 찾는다. 구성 요소 폴더 이름이 옛 저장소 이름과 같아서 이 경로가 이 저장소에서도 그대로 맞는다. 그래서 구성 요소의 코드와 시험은 고치지 않았다. 경로 계산을 이 저장소에 맞춰 바꾸면 기록된 측정을 낸 실행과 같은 실행이 아니게 되고 구성 요소의 시험 수집 수도 달라지기 때문이다. 대신 의존을 `tools/cross-deps.toml`에 글자로 묶었다. 코드의 그 글이 바뀌거나 대상이 추적에서 빠지면 검사가 실패해서 이 문서를 함께 고치게 한다.

검사는 저장소 뿌리에서 돌린다.

```bash
uv run --no-project tools/check_cross_deps.py            # 저장소 안의 것만 본다 (새로 받은 복제본, CI)
uv run --no-project tools/check_cross_deps.py --local    # 가상환경과 모델 폴더가 제자리에 있는지도 본다
```

검사하는 것은 넷이다. 쓰는 쪽 코드에 선언한 글이 아직 있는지, 대상 파일을 git이 추적하는지, 고정 사본의 커밋·원본 경로·blob이 이 저장소의 이력과 맞는지, 이 문서가 위 경로들과 고정 커밋의 앞 7자를 적고 있는지. 고정 커밋을 이력에서 풀기 때문에 전체 이력이 필요하다(얕은 복제에서는 `git fetch --unshallow`). 사본 파일의 본문이 원본과 같은지는 call-summary의 시험([`test_asr_condition.py`](../call-summary/tests/test_asr_condition.py))이 본다.

## 코드로 잇지 않은 관계

- voice-translator에서 support-agent로 이어진 설계 계보. support-agent의 음성 계층이 쓰는 MeloTTS는 voice-translator에서 합성한 음성을 다시 인식한 오류를 재서 한국어용으로 고른 것이고, Windows에서 MeloTTS를 불러오기 전에 필요한 우회 세 가지도 voice-translator에서 가져왔다. support-agent는 voice-translator의 코드를 부르지 않는다. 근거는 support-agent의 [`speech.py` 4행](../support-agent/src/support_agent/voice/speech.py#L4)과 [174행](../support-agent/src/support_agent/voice/speech.py#L174), [`experiments.md` 344행](../support-agent/docs/experiments.md#L344)이다.
- stt-scratch와 whisper-ko-ft의 같은 채점 정규화. stt-scratch의 주지표 CER_ns는 whisper-ko-ft와 같은 규칙으로 정규화해 재서 두 프로젝트의 수치를 나란히 놓을 수 있다. 규칙은 stt-scratch가 [`text.py`의 `normalize_score`](../stt-scratch/src/stt_scratch/text.py#L69)에 따로 구현했고 whisper-ko-ft의 코드를 가져다 쓰지 않는다. 두 수치를 견주는 문장은 stt-scratch의 [README 23행](../stt-scratch/README.md#L23)에 있다.
