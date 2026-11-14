# 통화 한 건 시연

모델 없는 두 오프라인 앱(support-agent와 call-summary)을 HTTP로 이어 통화 한 건을 흘려 보내는 배선 시연이다. 리포트에 나오는 상담 답과 후처리 기록은 규칙과 고정 답이 만든 것이라 품질 수치가 아니다.

## 무엇을 하나

통화 대본 [`calls/shop-cancel.json`](calls/shop-cancel.json)(주문 하나를 취소하는 통화)의 고객 발화 세 개를 support-agent의 오프라인 앱에 차례로 보내고, 그 앱에 남은 대화를 call-summary의 오프라인 앱에 넘겨 상담 후처리 기록을 받는다. 그 결과를 리포트 두 파일(`call-report.json`, `call-report.md`)로 쓰고, 대본에 적은 기대와 견준 검사 다섯 개를 판정한다.

- `turns_completed`: 대본의 발화를 모두 보냈고, 턴마다 `end` 이벤트가 왔고, `error` 이벤트가 없다.
- `tool_calls`: 감사 로그에 남은 도구 호출의 (이름, 성공 여부) 차례가 대본의 기대와 같다.
- `session_status`: 통화가 끝난 뒤의 세션 상태가 대본의 기대와 같다.
- `transcript_matches_script`: 대화에 남은 고객 말이 대본의 발화와 차례대로 같다.
- `summary_model`: 후처리 응답의 `model`이 대본의 기대(`offline:canned`)와 같다.

예시 리포트는 [`examples/shop-cancel/call-report.md`](examples/shop-cancel/call-report.md)다(같은 내용의 JSON은 [`call-report.json`](examples/shop-cancel/call-report.json)). 두 앱을 실제로 띄워 이 대본을 돌린 결과를 그대로 넣은 것이고, CI가 main에 push할 때와 pull request마다 다시 돌려 바이트까지 같은지 본다.

리포트에는 실행마다 달라지는 값(세션 id, 요청 id, 걸린 시간, 감사 로그 행의 id와 시각)을 넣지 않는다. 명령줄 `call-e2e`([`src/call_e2e/cli.py`](src/call_e2e/cli.py))의 종료 코드는 0 = 리포트를 썼고 검사가 모두 통과, 1 = 리포트를 썼지만 검사가 실패, 2 = 돌리지 못함(대본 오류, 관리자 토큰 없음, 제한 시간 안에 두 앱이 준비되지 않음, HTTP 요청 실패나 응답 형식 오류)이다.

## 배선 시연이지 품질 측정이 아니다

- support-agent 쪽 답은 언어 모델이 아니라 규칙 몇 줄짜리 대역([`offline.py`](../support-agent/src/support_agent/service/offline.py))이 만든다. 이름과 휴대전화 번호를 읽으면 `find_customer`를, 본인 확인 뒤 주문 번호와 '취소'를 함께 읽으면 `cancel_order`를 부르고, 도구 결과 글의 앞부분을 '처리했습니다.'(실패면 '처리하지 못했습니다.') 뒤에 붙여 답으로 돌려준다. 웹 계층, 세션·감사 로그·승인 대기열, 도구 실행은 실제 서비스와 같은 코드이고, DB는 실행마다 새로 만드는 SQLite 파일이다.
- call-summary 쪽 기록은 업종마다 늘 같은 고정 답(`CannedProvider`, [`service.py`](../call-summary/src/call_summary/service.py))이다. 고정 답에 든 주문 번호는 이 대본의 통화에 나오지 않으므로 '확인이 필요한 번호'에 그 번호 하나가 `not_in_transcript`로 표시된다. 요약 품질과는 상관없다.
- 그래서 이 시연이 보여 주는 것은 두 서비스가 아래 HTTP 계약대로 이어지는지뿐이다: 대본의 고객 말이 상담 세션에 들어가고, 그 대화가 후처리 요청으로 넘어가고, 두 응답이 리포트로 남는지. 모델을 올리지 않으므로 GPU가 필요 없다.
- 두 구성 요소의 품질 수치와 그 조건은 각 구성 요소의 README([support-agent](../support-agent/README.md), [call-summary](../call-summary/README.md))에 있다.

## 흐름과 HTTP 계약

대본 → support-agent 메시지(SSE) → 관리 API로 대화·감사 로그 → call-summary `/summarize` → 리포트

1. 두 앱이 준비될 때까지 기다린다. support-agent의 `GET /healthz`와 call-summary의 `GET /health`가 둘 다 200을 줄 때까지 `--wait` 초(기본 30초)까지 다시 묻는다.
2. `POST /api/sessions`로 상담 세션을 연다. 새 세션의 대화에는 상담원의 고정 인사말 한 줄이 이미 들어 있다.
3. 고객 발화마다 `POST /api/sessions/{id}/messages`를 보내고 SSE 응답을 끝까지 읽는다. 턴에 `end` 이벤트가 없거나 그 세션 상태가 `open`이 아니면 남은 발화를 보내지 않는다.
4. 관리 API `GET /api/admin/sessions/{id}`로 고객이 본 대화와 감사 로그를 읽는다. 부른 도구의 이름·인자·성공 여부는 감사 로그의 `tool_call` 행에서 가져온다.
5. 그 대화의 `customer`·`agent`를 `고객`·`상담원`으로 바꿔 call-summary의 `POST /summarize`에 보낸다(업종은 대본에 적은 것, 이 대본은 `shop`).
6. 두 응답으로 리포트를 쓰고 검사 다섯 개를 판정한다.

| 끝점 | 요청 | 응답 | 근거 |
|---|---|---|---|
| support-agent `GET /healthz` | — | 200 | [`app.py`](../support-agent/src/support_agent/service/app.py#L257) |
| support-agent `POST /api/sessions` | 본문 없음 | 201 `{"session_id", "status", "messages", "pending_approvals"}` | [`app.py`](../support-agent/src/support_agent/service/app.py#L271), [`core.py`](../support-agent/src/support_agent/service/core.py) |
| support-agent `POST /api/sessions/{id}/messages` | `{"text": 고객 발화}`. 서버 한도(기본 1,000자)를 넘으면 422 | 200 `text/event-stream`. 이벤트마다 `event: <이름>` 줄, `data: <JSON>` 줄, 빈 줄. 차례는 `status` → 도구마다 `tool`과 `tool_result`(사람 승인이 필요한 환불이면 `approval`도) → `error`(있을 때) → `reply` → `end`. 없는 세션 404, 닫힌 세션 409, 동시에 도는 턴이 한도에 닿으면 503 | [`app.py`](../support-agent/src/support_agent/service/app.py#L367), [`core.py`](../support-agent/src/support_agent/service/core.py) |
| support-agent `GET /api/admin/sessions/{id}` | 헤더 `X-Admin-Token` | 200 `{"transcript": {"session_id", "status", "messages", "pending_approvals"}, "audit": [{"id", "at", "kind", "payload"}]}`. 관리자 토큰이 설정되지 않았으면 503, 틀리면 401 | [`app.py`](../support-agent/src/support_agent/service/app.py#L507), [`core.py`](../support-agent/src/support_agent/service/core.py) |
| call-summary `GET /health` | — | 200 | [`service.py`](../call-summary/src/call_summary/service.py#L779) |
| call-summary `POST /summarize` | `{"domain", "turns": [{"speaker": "상담원" 또는 "고객", "text"}]}`. 업종은 shop·telecom·parcel·card, 발화 1~200개, 발화당 2,000자, 이어 붙인 전사 4,000자까지 | 200 `{"request_id", "record", "needs_confirmation", "model", "attempts", "latency_s"}`. 모르는 업종 422, 너무 길면 413, 기록을 거절하면 502, 붐비면 503 | [`service.py`](../call-summary/src/call_summary/service.py#L878) |

이 폴더는 두 구성 요소의 코드를 가져오지(import) 않고 위 계약대로 HTTP로만 부른다. 클라이언트는 [`src/call_e2e/clients.py`](src/call_e2e/clients.py), 흐름과 검사는 [`src/call_e2e/flow.py`](src/call_e2e/flow.py), 리포트는 [`src/call_e2e/report.py`](src/call_e2e/report.py)에 있다.

## 로컬에서 돌리기

저장소 뿌리에서 Windows PowerShell로 돌린다(5.1에서 확인). 경로는 모두 저장소 뿌리 기준 상대 경로이고, uv 0.13.1 이상이 필요하다.

준비: 새로 받은 복제본이면 두 서비스의 기본 의존성 환경과 이 폴더의 환경을 먼저 만든다(CI와 같은 설치 범위). 두 서비스 폴더에 이미 쓰는 환경(`.venv`)이 있으면 그 환경은 고치지 않고 그대로 쓰고, 없는 환경만 만든다. 아래 시연은 그 환경의 파이썬을 부르기만 한다. Windows에서는 줄바꿈을 바꾸지 않고 받은 복제본(`git clone -c core.autocrlf=false …`)에서 돌린다. `core.autocrlf=true`로 받으면 대본 파일이 CRLF로 풀려, 리포트의 대본 SHA-256이 예시와 달라지고 예시 시험([`tests/test_examples.py`](tests/test_examples.py))이 실패한다.

```powershell
uv sync --frozen --no-dev --directory support-agent
uv sync --frozen --no-dev --directory call-summary
uv sync --frozen --directory e2e
```

시연: 아래 덩어리를 한 번에 붙여 넣는다. 두 앱을 포트 18062·18072에 띄우고, 통화 한 건을 돌리고, 두 앱을 멈춘다. 리포트는 `e2e/out/report-1/`에 생긴다(`e2e/out/`은 git이 무시한다). 출력의 끝 두 줄은 `검사 5/5 통과`와 `exit 0`이다.

```powershell
$out = 'out/report-1'
$env:PYTHONUTF8 = '1'
$token = [guid]::NewGuid().ToString('N')
$env:E2E_ADMIN_TOKEN = $token; $env:SUPPORT_AGENT_ADMIN_TOKEN = $token
New-Item -ItemType Directory -Force e2e\out | Out-Null
$db = ((Resolve-Path e2e\out).Path + "\support-$(Get-Date -Format yyyyMMdd-HHmmss).db") -replace '\\', '/'
$env:SUPPORT_AGENT_DATABASE_URL = "sqlite:///$db"
$sa = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory support-agent -FilePath (Resolve-Path support-agent\.venv\Scripts\python.exe) -ArgumentList '-m','uvicorn','support_agent.service.offline:create_offline_app','--factory','--host','127.0.0.1','--port','18062' -RedirectStandardOutput e2e\out\support-agent.out.log -RedirectStandardError e2e\out\support-agent.err.log
$cs = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory call-summary -FilePath (Resolve-Path call-summary\.venv\Scripts\python.exe) -ArgumentList '-m','uvicorn','call_summary.service:create_offline_app','--factory','--host','127.0.0.1','--port','18072' -RedirectStandardOutput e2e\out\call-summary.out.log -RedirectStandardError e2e\out\call-summary.err.log
"$($sa.Id) $($cs.Id)" | Set-Content -Encoding ascii e2e\out\pids.txt
try {
  uv run --directory e2e --frozen --no-sync call-e2e --script calls/shop-cancel.json --support-url http://127.0.0.1:18062 --summary-url http://127.0.0.1:18072 --wait 180 --out $out
  $code = $LASTEXITCODE
} finally {
  Stop-Process -Id $sa.Id, $cs.Id -ErrorAction SilentlyContinue
}
"exit $code"
```

- 포트는 서비스 기본값(support-agent 8062, call-summary 8072)이 아니라 18062·18072만 쓴다. 그 PC에 두 서비스가 Docker Compose로 떠 있으면 기본 포트로 돌린 시연은 오프라인 앱이 아니라 진짜 서비스와 이야기하는데, support-agent `/healthz`의 `model`은 설정값이라 응답만 보고는 오프라인 앱인지 알 수 없다.
- `$env:PYTHONUTF8 = '1'`은 파이썬이 표준 출력과 두 앱의 로그(`e2e/out/*.log`)를 UTF-8로 쓰게 한다. Windows의 파이썬은 출력이 파일이나 파이프면 시스템 코드 페이지(한국어 Windows는 cp949)로 써서 한글이 깨질 수 있다.
- 관리자 토큰은 실행마다 새로 만드는 임시 값이고 화면이나 파일에 찍지 않는다. support-agent는 `SUPPORT_AGENT_ADMIN_TOKEN`으로, `call-e2e`는 `E2E_ADMIN_TOKEN`으로 같은 값을 읽는다.
- 덩어리가 정한 환경 변수 넷(`PYTHONUTF8`, `E2E_ADMIN_TOKEN`, `SUPPORT_AGENT_ADMIN_TOKEN`, `SUPPORT_AGENT_DATABASE_URL`)은 그 PowerShell 창에 남는다. 그 창에서 support-agent 서비스를 따로 띄우면 이 값을 읽으므로, 다른 일은 새 창에서 한다.
- support-agent의 DB는 실행마다 `e2e/out/` 안의 새 SQLite 파일이다. 앞 실행이 주문 O-90005를 이미 취소한 DB를 다시 쓰면 결과가 달라진다. 지난 파일은 지우지 않고 남겨 둔다.
- 두 앱은 각 서비스 폴더 `.venv`의 파이썬으로 직접 띄우고, `Start-Process`가 준 프로세스 번호로 멈춘다. 그 번호는 `e2e/out/pids.txt`에도 적는다. 덩어리가 중간에 끊기면 그 두 번호를 `Stop-Process -Id <번호>`로 멈춘 뒤, 아래 명령이 아무것도 보여 주지 않는지 확인한다.

```powershell
Get-NetTCPConnection -LocalPort 18062,18072 -State Listen -ErrorAction SilentlyContinue
```

예시 리포트는 대본이나 리포트 코드를 고쳤을 때만 다시 만든다. 덩어리를 돌린 뒤 두 파일을 예시 폴더로 복사한다.

```powershell
Copy-Item e2e\out\report-1\call-report.* e2e\examples\shop-cancel\
```

날짜가 바뀌어도 같은 바이트가 나온다. support-agent 서비스의 시계는 기본으로 고정 시각이고(`SUPPORT_AGENT_NOW`를 정하지 않으면 `2026-09-14T10:00:00+09:00`, [`settings.py`](../support-agent/src/support_agent/service/settings.py)의 `DEMO_NOW`), 위 덩어리와 CI는 이 값을 바꾸지 않는다.

## CI

[`.github/workflows/e2e.yml`](../.github/workflows/e2e.yml)이 같은 일을 Linux 러너의 bash로 한다. main에 push할 때와 pull request마다 돌고, 경로 필터가 없어 어느 폴더가 바뀌어도 돈다.

1. 두 서비스를 기본 의존성만으로 설치하고(`uv sync --frozen --no-dev`, 두 서비스의 Docker 이미지와 같은 설치 범위), 이 폴더를 설치한다(`uv sync --frozen`).
2. 이 폴더의 린트(`ruff check`, `ruff format --check`)와 시험(`pytest`)을 돌린다. 시험은 앱 없이 가짜 서비스로 돌고, 예시 리포트가 대본과 렌더링 코드에 맞는지도 본다.
3. 임시 관리자 토큰을 만들어 로그에서 가리고, 두 오프라인 앱을 기본 포트 8062·8072에 띄운다. CI 러너는 매번 새것이라 그 포트에 다른 서비스가 없다.
4. `call-e2e`로 통화 한 건을 돌리고, 새로 나온 리포트가 [`examples/shop-cancel/`](examples/shop-cancel/)과 바이트까지 같은지 `diff -u`로 본다.
5. 성공·실패와 상관없이 리포트를 작업 요약에, 두 앱의 로그를 작업 로그에 남긴다.

## 한계

- 고정 규칙과 고정 답이다. support-agent 대역은 이름과 전화번호, 주문 번호와 '취소' 같은 정해진 꼴만 알아듣고, call-summary는 통화 내용과 상관없이 업종마다 같은 기록을 돌려준다. 다른 대본은 대역이 알아듣는 꼴로 써야 기대한 도구가 불린다.
- 두 구성 요소의 주문 번호 꼴이 다르다. support-agent는 `O-`와 숫자 다섯 자리([`offline.py` 41행](../support-agent/src/support_agent/service/offline.py#L41)), call-summary의 쇼핑몰 업종은 `D`와 숫자 일곱 자리([`domains.py` 231행](../call-summary/src/call_summary/domains.py#L231))다. 그래서 예시 리포트에서도 상담 도구가 다룬 번호와 후처리 기록의 번호가 다르다. 실모델로 잇기 전에 두 쪽의 업종 정의를 맞춰야 한다.
- support-agent 서비스의 기본 한도 안에서만 돈다: 세션당 40턴, 메시지당 1,000자([`settings.py`](../support-agent/src/support_agent/service/settings.py)). 대본을 읽을 때 이 한도를 넘는 발화 수와 길이는 거절한다.
- 서비스 코드는 바꾸지 않고 HTTP로만 잇는다. 그래서 서비스 응답의 꼴이 바뀌면 이 폴더의 클라이언트와 시험을 함께 고쳐야 한다.
- 같은 입력이면 같은 바이트라는 것은 두 앱을 새로 띄우고 support-agent를 새 DB로 시작한 처음 상태에서 같은 대본을 돌릴 때만 성립한다(그래서 실행마다 새 DB 파일을 쓴다). 사람 승인이 걸리는 통화라면 승인 번호(`AP-1` 같은 일련번호)가 리포트에 남는데, 이것도 처음 상태가 같아야 같다.
