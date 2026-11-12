"""support-agent와 call-summary 오프라인 앱을 HTTP로 부르는 클라이언트와 이벤트 스트림(SSE) 읽기.

두 앱의 코드는 가져오지(import) 않고 HTTP로만 부른다. 그래서 이 패키지는 모델 라이브러리 없이 설치되고,
시연은 서비스를 바깥에서 쓰는 사람과 같은 길(공개된 끝점)만 지난다.

부르는 끝점과 응답 꼴은 각 앱의 코드가 정한 계약을 그대로 따른다.

  support-agent (support-agent/src/support_agent/service/app.py, core.py)
    GET  /healthz                         200
    POST /api/sessions                    201 {"session_id", "status", "messages", "pending_approvals"}
    POST /api/sessions/{id}/messages      200 text/event-stream (요청 본문 {"text": 고객 발화})
    GET  /api/admin/sessions/{id}         200 {"transcript": {...}, "audit": [...]} (헤더 X-Admin-Token)

  call-summary (call-summary/src/call_summary/service.py)
    GET  /health                          200
    POST /summarize                       200 {"request_id", "record", "needs_confirmation", "model", ...}
                                          (요청 본문 {"domain": 업종 키, "turns": [{"speaker", "text"}, ...]})

기대한 것과 다른 응답, 연결 실패, 시간 초과는 모두 `StepError` 하나로 알린다. 어느 단계에서 어떤 상태로
실패했는지(단계 이름, HTTP 상태, 응답 본문 앞부분)가 담겨 있어, 부르는 쪽이 리포트 없이 그대로 보여 줄
수 있다.
"""

import json
import time
from collections.abc import Callable, Sequence
from typing import Protocol
from urllib.parse import quote

import httpx

# StepError.detail에 담는 응답 본문의 길이. 오류 응답이 긴 HTML 쪽이어도 메시지가 화면을 덮지 않게 한다.
DETAIL_CHARS = 500

# support-agent 관리자 API가 인증에 읽는 헤더(service/app.py의 admin 의존성).
ADMIN_TOKEN_HEADER = "X-Admin-Token"


class StepError(RuntimeError):
    """시연의 한 단계(HTTP 요청 하나)가 기대와 다르게 끝났다.

    step: 실패한 단계 이름. 메서드 이름과 같다: `new_session`, `say`, `session_detail`, `summarize`.
    status: HTTP 상태 코드. 응답을 받지 못한 실패(연결 거절, 시간 초과, 중간에 끊김)는 None이다.
    detail: 응답 본문의 앞 500자. 응답이 없으면 예외 종류와 메시지. 관리자 토큰은 어떤 경우에도 담지 않는다.
    """

    def __init__(self, step: str, status: int | None, detail: str) -> None:
        self.step = step
        self.status = status
        self.detail = detail
        where = "응답 없음" if status is None else f"HTTP {status}"
        super().__init__(f"{step} 단계 실패 ({where}): {detail}")


class SupportsReady(Protocol):
    """`wait_until_ready`가 기다릴 수 있는 것: 준비가 됐는지 예/아니오로 답하는 `ready()`를 가진 객체."""

    def ready(self) -> bool: ...


# ---------------------------------------------------------------- 이벤트 스트림 읽기


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """이벤트 스트림(text/event-stream) 본문을 (이벤트 이름, data 객체) 목록으로 바꾼다.

    support-agent는 이벤트 하나를 `event: <이름>`, `data: <JSON 한 줄>`, 빈 줄로 보낸다(service/app.py의
    `sse`). 이 함수는 그 꼴을 읽되 SSE 규격의 규칙도 따른다: 줄 끝은 LF·CRLF·CR 모두 받고, `:`로 시작하는
    줄(주석)과 `id`·`retry` 같은 필드는 건너뛰며, `data` 줄이 여럿이면 줄바꿈으로 이어 붙이고, `event` 줄이
    없으면 규격의 기본 이름 `message`로 둔다. 마지막 덩어리 뒤에 빈 줄이 없어도 그 덩어리를 읽는다.

    규격과 다른 점이 하나 있다: 규격은 `data`가 없는 덩어리를 조용히 버리지만, 여기서는 `event` 줄만 있고
    `data`가 없는 덩어리를 ValueError로 알린다. 서버가 보낸 이벤트가 말없이 사라지면 시연이 "이벤트가
    없었다"고 잘못 보일 수 있기 때문이다. 주석이나 `id`만 있는 덩어리는 이벤트가 아니므로 건너뛴다.

    입력: 응답 본문 글. 출력: 받은 차례대로의 (이름, data 사전) 목록. 본문이 비어 있으면 빈 목록.
    ValueError: data가 없는 이벤트 덩어리, 또는 data가 JSON 객체가 아닌 경우.
    """
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    frames: list[list[str]] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line:
            current.append(line)
        elif current:  # 빈 줄이 덩어리 하나의 끝이다
            frames.append(current)
            current = []
    if current:
        frames.append(current)

    events = []
    for lines in frames:
        event = _parse_frame(lines)
        if event is not None:
            events.append(event)
    return events


def _parse_frame(lines: list[str]) -> tuple[str, dict] | None:
    """빈 줄 없이 이어진 줄 묶음(덩어리) 하나를 이벤트 하나로 읽는다. 이벤트가 아니면 None."""
    name: str | None = None
    data_lines: list[str] = []
    for line in lines:
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]  # 규격: 콜론 뒤 공백 하나는 구분용이라 값이 아니다
        if field == "event":
            name = value
        elif field == "data":
            data_lines.append(value)
        # 그 밖의 필드(id, retry와 규격에 없는 것)는 시연이 쓰지 않는다. 규격도 모르는 필드는 무시하라고 한다.
    if name is None and not data_lines:
        return None
    if not data_lines:
        raise ValueError(f"data 줄이 없는 이벤트 덩어리가 있다 (event: {name!r})")
    label = name or "message"
    try:
        data = json.loads("\n".join(data_lines))
    except json.JSONDecodeError as exc:
        raise ValueError(f"data가 JSON이 아니다 (event: {label!r}): {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"data가 JSON 객체가 아니다 (event: {label!r}): {type(data).__name__}")
    return label, data


# ---------------------------------------------------------------- 공통 부분


def _body_text(response: httpx.Response) -> str:
    """응답 본문을 UTF-8 글로 읽는다. 이벤트 스트림은 규격상 UTF-8이고, 깨진 바이트는 대체 문자로 둔다."""
    return response.content.decode("utf-8", errors="replace")


def _head(response: httpx.Response) -> str:
    """오류 글에 넣을 응답 본문의 앞부분 (`DETAIL_CHARS`자)."""
    return _body_text(response)[:DETAIL_CHARS]


def _require_status(step: str, response: httpx.Response, expected: int) -> None:
    """응답 상태가 기대와 같지 않으면 본문 앞부분을 담아 StepError를 낸다."""
    if response.status_code != expected:
        raise StepError(step, response.status_code, _head(response))


def _json_object(step: str, response: httpx.Response) -> dict:
    """응답 본문을 JSON 객체로 읽는다. JSON이 아니거나 객체가 아니면 StepError."""
    try:
        data = json.loads(_body_text(response))
    except ValueError as exc:
        raise StepError(step, response.status_code, f"응답이 JSON이 아니다: {_head(response)}") from exc
    if not isinstance(data, dict):
        raise StepError(step, response.status_code, f"응답이 JSON 객체가 아니다: {_head(response)}")
    return data


class _ServiceClient:
    """두 클라이언트가 함께 쓰는 부분: HTTP 클라이언트 하나, 요청 보내기, 준비 확인, 닫기.

    요청 중 생긴 연결 실패·시간 초과·중간에 끊김(httpx.HTTPError)은 StepError로 바꾼다. 응답이 아직 안
    왔으므로 상태는 None이다. 준비 확인(`ready`)은 같은 실패를 "아직 아님"(False)으로 읽는다: 서비스가 뜨는
    중이면 연결이 거절되는 것이 정상이기 때문이다.

    프록시 환경 변수(HTTP_PROXY 등)는 읽지 않고 주어진 주소로 곧장 연결한다(`trust_env=False`). 이 시연이
    부르는 것은 보통 이 PC의 로컬 포트인데, httpx의 기본값대로 환경 변수를 따르면 프록시가 켜져 있는 PC에서
    요청이 프록시로 먼저 가서, 앱이 떠 있어도 `ready()`가 늘 False가 되는 식으로 엉뚱한 이유로 실패한다.
    """

    def __init__(
        self,
        base_url: str,
        *,
        health_path: str,
        transport: httpx.BaseTransport | None,
        timeout_s: float,
    ) -> None:
        self._base_url = base_url
        self._health_path = health_path
        self._http = httpx.Client(base_url=base_url, transport=transport, timeout=timeout_s, trust_env=False)

    def ready(self) -> bool:
        """상태 확인 끝점이 200으로 답하면 True. 그 밖의 상태나 연결 실패는 False (예외를 내지 않는다)."""
        try:
            return self._http.get(self._health_path).status_code == 200
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        """HTTP 연결을 닫는다. 한 번만 부르면 되고, 닫은 뒤에는 다른 메서드를 부르지 않는다."""
        self._http.close()

    def __repr__(self) -> str:
        # 기본 repr 대신 주소만 보인다. 서브클래스가 비밀값(관리자 토큰)을 들고 있어도 출력에 나오지
        # 않게 한다.
        return f"{type(self).__name__}(base_url={self._base_url!r})"

    def _call(self, step: str, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            kind = type(exc).__name__
            reason = str(exc)  # 메시지가 비어 있는 예외도 있다
            raise StepError(step, None, f"{kind}: {reason}" if reason else kind) from exc


# ---------------------------------------------------------------- support-agent


def _check_admin_token(token: str) -> None:
    """관리자 토큰이 HTTP 헤더 값으로 안전하게 쓸 수 있는 꼴인지 본다. 아니면 값을 적지 않고 ValueError.

    값을 적지 않는 까닭: HTTP 라이브러리(h11)는 줄바꿈이나 앞뒤 공백이 든 헤더 값을 거절하면서 그 값 전체를
    예외 글에 넣는다(httpx에서 `Illegal header value b'...'`로 확인했다). 환경 변수나 파일에서 읽은 토큰
    끝에 줄바꿈이 붙어 있으면 토큰이 오류 출력으로 새게 되므로, 요청을 보내기 전에 여기서 먼저 막는다.
    허용하는 글자는 공백 없는 ASCII 출력 글자(0x21~0x7E)다.
    """
    if not token or not all("!" <= char <= "~" for char in token):
        raise ValueError(
            "관리자 토큰은 비어 있지 않아야 하고 공백·제어 문자·ASCII 밖의 글자 없이 ASCII 출력 글자로만 "
            "이루어져야 한다 (값은 보안상 이 메시지에 적지 않는다)"
        )


class SupportAgentClient(_ServiceClient):
    """support-agent 오프라인 앱의 고객 쪽 끝점과 관리자 조회 끝점을 부르는 클라이언트.

    base_url: 앱 주소 (예: http://127.0.0.1:18062).
    admin_token: 관리자 API용 토큰. 관리자 조회(`session_detail`) 요청에만 `X-Admin-Token` 헤더로 보내고,
        고객 쪽 요청에는 붙이지 않는다. 오류 글·`repr`·`StepError`에 넣지 않으며, HTTP 헤더 값으로 쓸 수 없는
        꼴이면 만들 때 ValueError로 거절한다(값은 메시지에 적지 않는다).
    transport: 시험에서 httpx.MockTransport를 넣는 자리. None이면 실제 네트워크.
    timeout_s: 요청 하나에 쓰는 시간 제한(초), 기본 60초. httpx의 제한이라 연결·쓰기·읽기 각각에 적용되고,
        읽기는 응답 조각이 도착하는 사이를 기다리는 시간이다.
    """

    def __init__(
        self,
        base_url: str,
        admin_token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        _check_admin_token(admin_token)
        super().__init__(base_url, health_path="/healthz", transport=transport, timeout_s=timeout_s)
        self._admin_token = admin_token

    def new_session(self) -> str:
        """새 상담 세션을 만들고 세션 id를 돌려준다 (POST /api/sessions, 201).

        StepError(step="new_session"): 201이 아니거나, 응답이 JSON 객체가 아니거나, session_id가 없을 때.
        """
        response = self._call("new_session", "POST", "/api/sessions")
        _require_status("new_session", response, 201)
        session_id = _json_object("new_session", response).get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise StepError(
                "new_session", response.status_code, f"응답에 session_id가 없다: {_head(response)}"
            )
        return session_id

    def say(self, session_id: str, text: str) -> list[tuple[str, dict]]:
        """고객 발화 하나를 보내고, 그 턴이 끝날 때까지 받은 이벤트를 차례대로 돌려준다.

        POST /api/sessions/{id}/messages (본문 {"text": text}, 200 text/event-stream). 서버는 턴이 끝나면
        응답을 닫는다. 이 호출은 응답을 끝까지 읽으므로 한 턴이 끝나야 돌아온다.

        출력: (이름, data 사전) 목록. 이름은 `status`(처리 단계), `tool`·`tool_result`(도구를 부르는 중·결과),
        `approval`(담당자 승인 대기), `error`, `reply`(고객에게 보낼 답), `end`(턴의 끝, data의 status가 세션
        상태)다. HTTP 200은 응답이 시작됐다는 뜻일 뿐이라 턴이 잘 끝났는지는 `error`·`end` 이벤트를 봐야 안다.
        StepError(step="say"): 200이 아니거나(404 없는 세션, 409 닫힌 세션, 422 발화 길이, 503 붐빔), 이벤트
        스트림을 읽을 수 없거나, 이벤트가 하나도 없을 때. 서버는 턴마다 적어도 `status`와 `end`를 보낸다.
        """
        path = f"/api/sessions/{quote(session_id, safe='')}/messages"
        response = self._call("say", "POST", path, json={"text": text})
        _require_status("say", response, 200)
        body = _body_text(response)
        try:
            events = parse_sse(body)
        except ValueError as exc:
            raise StepError("say", response.status_code, f"이벤트 스트림을 읽을 수 없다: {exc}") from exc
        if not events:
            detail = f"응답에 이벤트가 하나도 없다: {body[:DETAIL_CHARS]}"
            raise StepError("say", response.status_code, detail)
        return events

    def session_detail(self, session_id: str) -> dict:
        """한 세션의 고객이 본 대화와 감사 로그를 읽는다 (GET /api/admin/sessions/{id}, 200).

        출력: {"transcript": {...}, "audit": [...]}. 관리자 토큰이 틀리면 401, 서버에 토큰이 설정되어 있지
        않으면 503이다.
        StepError(step="session_detail"): 200이 아니거나, 응답이 JSON 객체가 아니거나, transcript나 audit이
        없을 때.
        """
        path = f"/api/admin/sessions/{quote(session_id, safe='')}"
        response = self._call("session_detail", "GET", path, headers={ADMIN_TOKEN_HEADER: self._admin_token})
        _require_status("session_detail", response, 200)
        detail = _json_object("session_detail", response)
        if "transcript" not in detail or "audit" not in detail:
            message = f"응답에 transcript 또는 audit이 없다: {_head(response)}"
            raise StepError("session_detail", response.status_code, message)
        return detail


# ---------------------------------------------------------------- call-summary


class CallSummaryClient(_ServiceClient):
    """call-summary 오프라인 앱의 상담 후처리 끝점을 부르는 클라이언트.

    base_url: 앱 주소 (예: http://127.0.0.1:18072).
    transport: 시험에서 httpx.MockTransport를 넣는 자리. None이면 실제 네트워크.
    timeout_s: 요청 하나에 쓰는 시간 제한(초), 기본 120초. 적용 방식은 SupportAgentClient와 같다. 모델이
        기록을 만드는 시간을 넉넉히 잡은 값이다.
    """

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        super().__init__(base_url, health_path="/health", transport=transport, timeout_s=timeout_s)

    def summarize(self, domain: str, turns: list[dict]) -> dict:
        """통화 전사를 보내 상담 후처리 기록을 받는다 (POST /summarize, 200).

        domain: 업종 키 (shop, telecom, parcel, card).
        turns: [{"speaker": "고객" 또는 "상담원", "text": ...}] 발화 목록.
        출력: 서버가 준 JSON 객체 그대로 (request_id, record, needs_confirmation, model, attempts, latency_s).
        StepError(step="summarize"): 200이 아니거나(422 모르는 업종, 413 너무 긴 전사, 502 모델 출력 거절, 503
        붐빔), 응답이 JSON 객체가 아닐 때.
        """
        response = self._call("summarize", "POST", "/summarize", json={"domain": domain, "turns": turns})
        _require_status("summarize", response, 200)
        return _json_object("summarize", response)


# ---------------------------------------------------------------- 준비될 때까지 기다리기


def wait_until_ready(
    clients: Sequence[SupportsReady],
    timeout_s: float,
    *,
    interval_s: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """모든 클라이언트의 `ready()`가 True가 될 때까지 `timeout_s`초 동안 `interval_s`초 간격으로 확인한다.

    출력: 제한 시간 안에 모두 준비되면 True, 아니면 False. 시간 제한이 0이어도 확인은 한 번 한다. 한 바퀴마다
    모든 클라이언트를 확인한다(앞 것이 아직이어도 뒤 것을 건너뛰지 않는다). 마지막 잠은 남은 시간보다 길지
    않게 줄여, 제한 시간을 넘겨 자지 않는다.
    sleep·clock: 시험에서 가짜 시계를 넣는 자리. 기본은 time.sleep·time.monotonic.
    """
    deadline = clock() + timeout_s
    while True:
        # 목록으로 만들어 모두 확인한다. all(제너레이터)로 쓰면 앞 클라이언트가 아직일 때 뒤 것을 건너뛴다.
        if all([client.ready() for client in clients]):
            return True
        remaining = deadline - clock()
        if remaining <= 0:
            return False
        sleep(min(interval_s, remaining))
