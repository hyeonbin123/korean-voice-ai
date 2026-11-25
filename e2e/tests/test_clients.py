"""두 서비스 클라이언트와 이벤트 스트림(SSE) 읽기 시험.

네트워크를 쓰지 않는다. httpx.MockTransport가 두 오프라인 앱의 응답을 대신하고, 이 시험은 클라이언트가 보낸
요청의 차례·경로·헤더·본문과 예상 밖 응답을 다루는 방식을 본다. 대역 응답의 꼴은 support-agent
(src/support_agent/service/app.py, core.py)와 call-summary(src/call_summary/service.py)의 코드가 정한
계약을 따른다.
"""

import json

import httpx
import pytest

from call_e2e.clients import (
    CREATE_SUMMARY_TIMEOUT_S,
    CallSummaryClient,
    StepError,
    SupportAgentClient,
    parse_sse,
    wait_until_ready,
)

SUPPORT_URL = "http://support.test"
SUMMARY_URL = "http://summary.test"
# 시험 안에서만 쓰는 가짜 관리자 토큰. 어떤 오류 글·repr에도 나타나지 않아야 하는 값이다. 무작위처럼 보이는
# 문자열로 지으면 비밀값 검사기(gitleaks 같은 도구)가 진짜 키로 읽으므로 뜻이 있는 낱말로 지었다. 대역 응답의
# 글(예: "wrong admin token")에 통째로 들어 있지 않아서 `TOKEN not in shown` 단언이 의미를 가진다.
TOKEN = "test-admin-token"


def sse(event: str, data: dict) -> str:
    """support-agent의 app.py가 이벤트 한 덩어리를 만드는 것과 같은 꼴: event 줄, data 줄, 빈 줄."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# 한 턴이 흘려 보내는 이벤트의 예: 단계 → 도구 → 도구 결과 → 답 → 끝.
REPLY_EVENTS = [
    ("status", {"stage": "thinking"}),
    ("tool", {"name": "find_customer", "label": "고객 확인"}),
    ("tool_result", {"name": "find_customer", "ok": True, "error_code": None}),
    ("reply", {"text": "처리했습니다. 본인 확인을 마쳤습니다."}),
    ("end", {"status": "open"}),
]
SSE_BODY = "".join(sse(name, data) for name, data in REPLY_EVENTS)

ADMIN_DETAIL = {
    "transcript": {
        "session_id": "s-1",
        "status": "open",
        "messages": [
            {"role": "customer", "text": "안녕하세요"},
            {"role": "agent", "text": "본인 확인을 위해 성함과 가입하신 전화번호를 알려 주세요."},
        ],
        "pending_approvals": [],
    },
    "audit": [{"id": 1, "at": "2026-01-01T00:00:00", "kind": "session_started", "payload": {}}],
}

# 상담 서비스의 관리자 끝점 POST /api/admin/sessions/{id}/summary의 201 응답 꼴(support-agent
# `src/support_agent/service/core.py`의 create_summary가 돌려주는 값).
LINKED_ANSWER = {
    "session_id": "s-1",
    "summary": {
        "record": {"category": "배송", "resolution": "해결", "entities": [], "summary": "고정 응답"},
        "needs_confirmation": [],
        "model": "offline:canned",
        "attempts": 1,
    },
}


def support_client(handler, token: str = TOKEN) -> SupportAgentClient:
    return SupportAgentClient(SUPPORT_URL, token, transport=httpx.MockTransport(handler))


def summary_client(handler) -> CallSummaryClient:
    return CallSummaryClient(SUMMARY_URL, transport=httpx.MockTransport(handler))


def support_app(seen: list | None = None):
    """계약대로 답하는 support-agent 대역 처리기. seen을 주면 받은 요청을 차례로 담는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        route = (request.method, request.url.path)
        if route == ("GET", "/healthz"):
            health = {"ok": True, "model": "m", "think": False, "policy": "P1", "voice": False}
            return httpx.Response(200, json=health)
        if route == ("POST", "/api/sessions"):
            body = {"session_id": "s-1", "status": "open", "messages": [], "pending_approvals": []}
            return httpx.Response(201, json=body)
        if route == ("POST", "/api/sessions/s-1/messages"):
            headers = {"content-type": "text/event-stream; charset=utf-8"}
            return httpx.Response(200, headers=headers, content=SSE_BODY.encode("utf-8"))
        if route == ("GET", "/api/admin/sessions/s-1"):
            return httpx.Response(200, json=ADMIN_DETAIL)
        return httpx.Response(404, json={"detail": "no such route"})

    return handler


# ---------------------------------------------------------------- 이벤트 스트림 읽기


def test_parse_sse_reads_support_agent_frames():
    assert parse_sse(SSE_BODY) == REPLY_EVENTS
    # 한국어가 이스케이프 없이 그대로 오는 꼴(서버가 ensure_ascii=False로 보낸다)도 읽는다.
    assert "처리했습니다" in SSE_BODY
    # 단계와 끝 이벤트만 있는 가장 짧은 꼴도 읽는다.
    short = 'event: status\ndata: {"stage": "thinking"}\n\nevent: end\ndata: {"status": "open"}\n\n'
    assert parse_sse(short) == [("status", {"stage": "thinking"}), ("end", {"status": "open"})]


@pytest.mark.parametrize(
    "body",
    [
        "event: end\n\n",
        'event: status\ndata: {"stage": "thinking"}\n\nevent: end\n\n',
        "event: end\nid: 7\n\n",
    ],
    ids=["only_an_event_line", "second_frame_has_no_data", "event_and_id_without_data"],
)
def test_parse_sse_rejects_a_frame_without_data(body):
    with pytest.raises(ValueError):
        parse_sse(body)


@pytest.mark.parametrize(
    "body",
    ["", "\n\n", "\n", ": keep-alive\n\n", "id: 3\n\n", "retry: 1000\n\n"],
    ids=["empty", "blank_lines", "one_newline", "comment_only", "id_only", "retry_only"],
)
def test_parse_sse_ignores_frames_that_carry_no_event(body):
    assert parse_sse(body) == []


def test_parse_sse_accepts_crlf_line_ends():
    body = (
        'event: status\r\ndata: {"stage": "thinking"}\r\n\r\nevent: end\r\ndata: {"status": "open"}\r\n\r\n'
    )
    assert parse_sse(body) == [("status", {"stage": "thinking"}), ("end", {"status": "open"})]


def test_parse_sse_accepts_a_last_frame_without_the_closing_blank_line():
    assert parse_sse('event: end\ndata: {"status": "open"}') == [("end", {"status": "open"})]


def test_parse_sse_follows_the_event_stream_field_rules():
    body = (
        ": a comment line is skipped\n"
        "id: 1\n"
        "event:reply\n"  # 콜론 뒤 공백은 있어도 없어도 된다.
        'data: {"text":\n'
        'data: "두 줄에 걸친 data는 줄바꿈으로 이어 붙인다"}\n'
        "\n"
        'data: {"a": 1}\n'  # event 줄이 없으면 규격의 기본 이름 message다.
        "\n"
    )
    assert parse_sse(body) == [
        ("reply", {"text": "두 줄에 걸친 data는 줄바꿈으로 이어 붙인다"}),
        ("message", {"a": 1}),
    ]


@pytest.mark.parametrize(
    "data",
    ["not json", "[1, 2]", '"text"', "5", "null", '{"unfinished": '],
    ids=["not_json", "list", "string", "number", "null", "cut_off"],
)
def test_parse_sse_rejects_data_that_is_not_a_json_object(data):
    with pytest.raises(ValueError):
        parse_sse(f"event: reply\ndata: {data}\n\n")


# ---------------------------------------------------------------- StepError


def test_step_error_carries_the_step_status_and_detail():
    error = StepError("say", 409, "the session is closed")
    assert (error.step, error.status, error.detail) == ("say", 409, "the session is closed")
    assert "say" in str(error) and "409" in str(error) and "the session is closed" in str(error)
    assert isinstance(error, RuntimeError)
    # 응답을 받지 못한 실패(연결 거절 등)는 상태가 없다.
    no_answer = StepError("new_session", None, "ConnectError")
    assert no_answer.status is None
    assert "HTTP" not in str(no_answer)


# ---------------------------------------------------------------- support-agent 클라이언트


def test_support_client_uses_the_documented_paths():
    seen: list[httpx.Request] = []
    client = support_client(support_app(seen))

    session_id = client.new_session()
    events = client.say(session_id, "안녕하세요")
    detail = client.session_detail(session_id)

    assert session_id == "s-1"
    assert events == REPLY_EVENTS
    assert detail == ADMIN_DETAIL
    assert [(r.method, r.url.path) for r in seen] == [
        ("POST", "/api/sessions"),
        ("POST", "/api/sessions/s-1/messages"),
        ("GET", "/api/admin/sessions/s-1"),
    ]
    assert {r.url.host for r in seen} == {"support.test"}
    assert json.loads(seen[1].content) == {"text": "안녕하세요"}
    # 관리자 토큰은 관리자 끝점에만 간다. 고객 쪽 요청에는 붙지 않는다.
    assert [r.headers.get("x-admin-token") for r in seen] == [None, None, TOKEN]


def test_support_client_raises_step_error_on_unexpected_status():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/sessions":
            return httpx.Response(201, json={"session_id": "s-1"})
        return httpx.Response(409, json={"detail": "the session is closed"})

    client = support_client(handler)
    session_id = client.new_session()
    with pytest.raises(StepError) as info:
        client.say(session_id, "안녕하세요")
    assert info.value.step == "say"
    assert info.value.status == 409
    assert "the session is closed" in info.value.detail


def test_support_client_asks_readiness_from_healthz():
    seen: list[httpx.Request] = []
    assert support_client(support_app(seen)).ready() is True
    assert [(r.method, r.url.path) for r in seen] == [("GET", "/healthz")]

    assert support_client(lambda request: httpx.Response(503)).ready() is False

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    assert support_client(refuse).ready() is False


def test_session_ids_are_quoted_in_request_paths():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, content=SSE_BODY.encode("utf-8"))
        return httpx.Response(200, json=ADMIN_DETAIL)

    client = support_client(handler)
    client.say("a/b c?x#y", "안녕하세요")
    client.session_detail("a/b c?x#y")
    assert [r.url.raw_path for r in seen] == [
        b"/api/sessions/a%2Fb%20c%3Fx%23y/messages",
        b"/api/admin/sessions/a%2Fb%20c%3Fx%23y",
    ]


@pytest.mark.parametrize(
    ("response", "status"),
    [
        (httpx.Response(200, json={"session_id": "s-1"}), 200),
        (httpx.Response(503, json={"detail": "busy"}), 503),
        (httpx.Response(201, json={"status": "open"}), 201),
        (httpx.Response(201, json={"session_id": ""}), 201),
        (httpx.Response(201, json=["s-1"]), 201),
        (httpx.Response(201, content=b"<html>not json</html>"), 201),
    ],
    ids=["not_201", "busy", "no_session_id", "empty_session_id", "not_an_object", "not_json"],
)
def test_new_session_requires_a_201_with_a_session_id(response, status):
    client = support_client(lambda request: response)
    with pytest.raises(StepError) as info:
        client.new_session()
    assert info.value.step == "new_session"
    assert info.value.status == status


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, json={"detail": "no such session"}),
        httpx.Response(503, json={"detail": "busy"}),
        httpx.Response(200, content=b"not an event stream"),
        httpx.Response(200, content=b"event: end\n\n"),
    ],
    ids=["no_such_session", "busy", "not_an_event_stream", "frame_without_data"],
)
def test_say_reports_failures_and_unreadable_streams(response):
    client = support_client(lambda request: response)
    with pytest.raises(StepError) as info:
        client.say("s-1", "안녕하세요")
    assert info.value.step == "say"
    assert info.value.status == response.status_code


@pytest.mark.parametrize(
    ("response", "status"),
    [
        (httpx.Response(401, json={"detail": "wrong admin token"}), 401),
        (httpx.Response(503, json={"detail": "the admin API is disabled"}), 503),
        (httpx.Response(404, json={"detail": "no such session"}), 404),
        (httpx.Response(200, json={"transcript": {}}), 200),
        (httpx.Response(200, json=[]), 200),
        (httpx.Response(200, content=b"not json"), 200),
    ],
    ids=["wrong_token", "admin_disabled", "no_such_session", "no_audit", "not_an_object", "not_json"],
)
def test_session_detail_reports_failures_and_incomplete_answers(response, status):
    client = support_client(lambda request: response)
    with pytest.raises(StepError) as info:
        client.session_detail("s-1")
    assert info.value.step == "session_detail"
    assert info.value.status == status


def test_connection_failures_become_step_errors_without_a_status():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(StepError) as info:
        support_client(refuse).new_session()
    assert info.value.step == "new_session"
    assert info.value.status is None
    assert "ConnectError" in info.value.detail


def test_step_error_detail_is_the_first_500_characters_of_the_body():
    body = "가" * 2000
    client = support_client(lambda request: httpx.Response(409, content=body.encode("utf-8")))
    with pytest.raises(StepError) as info:
        client.say("s-1", "안녕하세요")
    assert info.value.detail == "가" * 500


def test_say_without_events_keeps_only_the_first_500_characters_of_the_body():
    client = support_client(lambda request: httpx.Response(200, content=("x" * 2000).encode("utf-8")))
    with pytest.raises(StepError) as info:
        client.say("s-1", "안녕하세요")
    assert info.value.status == 200
    # 설명 글 뒤에 본문이 정확히 500자만 붙는다. 본문은 x뿐이고 설명 글에는 x가 없다.
    assert info.value.detail.count("x") == 500


def test_admin_token_never_appears_in_errors_or_repr():
    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "wrong admin token"})

    client = support_client(reject)
    with pytest.raises(StepError) as info:
        client.session_detail("s-1")
    shown = " ".join([str(info.value), repr(info.value), info.value.detail, repr(client), str(client)])
    assert TOKEN not in shown


@pytest.mark.parametrize(
    "token",
    ["", "two words", "tab\tinside", "line\nbreak", "trailing ", "한글토큰"],
    ids=["empty", "space", "tab", "newline", "trailing_space", "non_ascii"],
)
def test_unusable_admin_tokens_are_refused_without_echoing_them(token):
    with pytest.raises(ValueError) as info:
        SupportAgentClient(SUPPORT_URL, token)
    if token:
        assert token not in str(info.value)
        assert token.strip() not in str(info.value)


# ---------------------------------------------------------------- 서비스 연결 확인: create_summary


def test_create_summary_posts_to_the_admin_summary_path_with_the_token():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json=LINKED_ANSWER)

    client = support_client(handler)
    assert client.create_summary("s-1") == LINKED_ANSWER
    assert client.create_summary("s-1", by="reviewer") == LINKED_ANSWER
    assert [(r.method, r.url.path) for r in seen] == [("POST", "/api/admin/sessions/s-1/summary")] * 2
    assert {r.url.host for r in seen} == {"support.test"}
    # 담당자 이름 칸 `by`의 기본값은 e2e다. 관리자 토큰은 이 관리자 끝점에 헤더로 간다.
    assert [json.loads(r.content) for r in seen] == [{"by": "e2e"}, {"by": "reviewer"}]
    assert [r.headers.get("x-admin-token") for r in seen] == [TOKEN, TOKEN]


def test_create_summary_quotes_the_session_id_in_the_path():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json=LINKED_ANSWER)

    support_client(handler).create_summary("a/b c?x#y")
    assert [r.url.raw_path for r in seen] == [b"/api/admin/sessions/a%2Fb%20c%3Fx%23y/summary"]


def test_create_summary_waits_longer_than_the_support_agent_waits_for_the_summary_service():
    # 상담 서비스는 후처리 서비스를 기다리는 시간의 상한이 기본 120초다(support-agent 설정 summary_timeout_s의
    # 기본값). 이 요청은 그 기다림을 통째로 품으므로 클라이언트가 먼저 끊지 않게 그보다 길어야 한다. 생성자의
    # 기본 시간 제한(60초)은 이 요청에만 비켜 가고, 다른 요청에는 그대로다(기본값 시험이 따로 고정한다).
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(201, json=LINKED_ANSWER)

    support_client(handler).create_summary("s-1")
    assert CREATE_SUMMARY_TIMEOUT_S > 120
    assert [set(timeout.values()) for timeout in seen] == [{CREATE_SUMMARY_TIMEOUT_S}]


@pytest.mark.parametrize(
    ("response", "status"),
    [
        (httpx.Response(401, json={"detail": "wrong admin token"}), 401),
        (httpx.Response(404, json={"detail": "no such session"}), 404),
        (httpx.Response(409, json={"detail": "this session has no conversation to summarize"}), 409),
        (httpx.Response(422, json={"detail": "the summary service rejected this conversation (422)"}), 422),
        (httpx.Response(429, json={"detail": "the summary service is busy, try again"}), 429),
        (httpx.Response(501, json={"detail": "the summary link is disabled"}), 501),
        (httpx.Response(502, json={"detail": "the summary service is unreachable"}), 502),
        (httpx.Response(503, json={"detail": "the admin API is disabled"}), 503),
        (httpx.Response(504, json={"detail": "the summary service timed out"}), 504),
        (httpx.Response(200, json=LINKED_ANSWER), 200),
        (httpx.Response(201, content=b"not json"), 201),
        (httpx.Response(201, json=["summary"]), 201),
        (httpx.Response(201, json={"session_id": "s-1"}), 201),
    ],
    ids=[
        "wrong_token",
        "no_such_session",
        "empty_conversation",
        "summary_service_rejected",
        "busy",
        "link_disabled",
        "unreachable",
        "admin_disabled",
        "timed_out",
        "not_201",
        "not_json",
        "not_an_object",
        "no_summary",
    ],
)
def test_create_summary_reports_failures_and_incomplete_answers(response, status):
    client = support_client(lambda request: response)
    with pytest.raises(StepError) as info:
        client.create_summary("s-1")
    assert info.value.step == "create_summary"
    assert info.value.status == status


def test_create_summary_failure_carries_the_reason_the_server_gave():
    # 상담 서비스가 후처리 연결이 꺼진 채 떠 있으면 501과 함께 까닭(켜는 설정 이름)을 준다. 오류 글만 보고
    # 무엇을 고칠지 알 수 있어야 하므로 본문 앞부분이 그대로 StepError에 실린다.
    body = {"detail": "the summary link is disabled (SUPPORT_AGENT_SUMMARY_URL is not set)"}
    client = support_client(lambda request: httpx.Response(501, json=body))
    with pytest.raises(StepError) as info:
        client.create_summary("s-1")
    assert "SUPPORT_AGENT_SUMMARY_URL" in info.value.detail
    assert "SUPPORT_AGENT_SUMMARY_URL" in str(info.value)


def test_create_summary_keeps_the_admin_token_out_of_errors():
    client = support_client(lambda request: httpx.Response(401, json={"detail": "wrong admin token"}))
    with pytest.raises(StepError) as info:
        client.create_summary("s-1")
    shown = " ".join([str(info.value), repr(info.value), info.value.detail, repr(client), str(client)])
    assert TOKEN not in shown


# ---------------------------------------------------------------- call-summary 클라이언트


def test_summary_client_posts_domain_and_turns():
    seen: list[httpx.Request] = []
    answer = {
        "request_id": "r-1",
        "record": {"category": "배송", "resolution": "해결", "entities": [], "summary": "고정 응답"},
        "needs_confirmation": [],
        "model": "offline:canned",
        "attempts": 1,
        "latency_s": 0.0,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answer)

    turns = [
        {"speaker": "고객", "text": "주문을 취소하려고요."},
        {"speaker": "상담원", "text": "처리했습니다."},
    ]
    assert summary_client(handler).summarize("shop", turns) == answer
    assert [(r.method, r.url.path) for r in seen] == [("POST", "/summarize")]
    assert {r.url.host for r in seen} == {"summary.test"}
    assert json.loads(seen[0].content) == {"domain": "shop", "turns": turns}
    assert "x-admin-token" not in seen[0].headers


@pytest.mark.parametrize(
    ("response", "status"),
    [
        (httpx.Response(422, json={"detail": "unknown domain"}), 422),
        (httpx.Response(413, json={"detail": "transcript too long"}), 413),
        (httpx.Response(502, json={"detail": {"error": "model output rejected"}}), 502),
        (httpx.Response(503, json={"detail": {"error": "server busy"}}), 503),
        (httpx.Response(200, content=b"not json"), 200),
        (httpx.Response(200, json=["record"]), 200),
    ],
    ids=["unknown_domain", "too_long", "rejected", "busy", "not_json", "not_an_object"],
)
def test_summary_client_reports_failures(response, status):
    client = summary_client(lambda request: response)
    with pytest.raises(StepError) as info:
        client.summarize("shop", [{"speaker": "고객", "text": "안녕하세요"}])
    assert info.value.step == "summarize"
    assert info.value.status == status


def test_summary_client_asks_readiness_from_health():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "ok"})

    assert summary_client(handler).ready() is True
    assert [(r.method, r.url.path) for r in seen] == [("GET", "/health")]
    assert summary_client(lambda request: httpx.Response(503)).ready() is False

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    assert summary_client(refuse).ready() is False


def test_summary_client_turns_connection_failures_into_step_errors():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(StepError) as info:
        summary_client(refuse).summarize("shop", [{"speaker": "고객", "text": "안녕하세요"}])
    assert info.value.step == "summarize"
    assert info.value.status is None


# ---------------------------------------------------------------- 응답이 없는 실패, 시간 제한, 준비 확인


def raising(exc_type: type[httpx.TransportError], message: str):
    """요청을 받으면 exc_type 예외를 던지는 처리기.

    응답을 받지 못하는 실패(연결 거절·시간 초과·끊김)를 흉내 낸다.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type(message, request=request)

    return handler


# (예외 종류, 예외 메시지, StepError.detail에 기대하는 글). 동기 소켓의 연결·읽기 시간 초과는 원래 예외의
# 글을 전달한다. httpx 0.28.1로 로컬 소켓에서 확인한 글은 "timed out"이다. 연결 풀이 가득 차 기다리다
# 끝나는 PoolTimeout은 메시지가 비므로, 그 경우에는 종류 이름만 담고 뒤에 ": "를 붙이지 않는다.
NO_ANSWER_FAILURES = [
    (httpx.ConnectError, "connection refused", "ConnectError: connection refused"),
    (httpx.ConnectTimeout, "timed out", "ConnectTimeout: timed out"),
    (httpx.ReadTimeout, "timed out", "ReadTimeout: timed out"),
    (httpx.PoolTimeout, "", "PoolTimeout"),
    (httpx.ReadError, "connection reset by peer", "ReadError: connection reset by peer"),
    (httpx.RemoteProtocolError, "server disconnected", "RemoteProtocolError: server disconnected"),
]
NO_ANSWER_IDS = [
    "connect_refused",
    "connect_timeout",
    "read_timeout",
    "pool_timeout",
    "read_error",
    "disconnected",
]


@pytest.mark.parametrize(("exc_type", "message", "detail"), NO_ANSWER_FAILURES, ids=NO_ANSWER_IDS)
def test_failures_without_an_answer_become_step_errors(exc_type, message, detail):
    turns = [{"speaker": "고객", "text": "안녕하세요"}]
    with pytest.raises(StepError) as info:
        support_client(raising(exc_type, message)).new_session()
    assert (info.value.step, info.value.status, info.value.detail) == ("new_session", None, detail)
    with pytest.raises(StepError) as info:
        summary_client(raising(exc_type, message)).summarize("shop", turns)
    assert (info.value.step, info.value.status, info.value.detail) == ("summarize", None, detail)
    with pytest.raises(StepError) as info:
        support_client(raising(exc_type, message)).create_summary("s-1")
    assert (info.value.step, info.value.status, info.value.detail) == ("create_summary", None, detail)


@pytest.mark.parametrize(
    ("exc_type", "message"), [(t, m) for t, m, _ in NO_ANSWER_FAILURES], ids=NO_ANSWER_IDS
)
def test_readiness_is_false_when_the_request_gets_no_answer(exc_type, message):
    assert support_client(raising(exc_type, message)).ready() is False
    assert summary_client(raising(exc_type, message)).ready() is False


@pytest.mark.parametrize("status", [204, 301, 302, 401, 404, 500, 503])
def test_readiness_needs_a_plain_200(status):
    """상태 확인 경로가 200이 아닌 다른 답을 주면 준비된 것으로 읽지 않는다.

    예를 들어 같은 포트를 다른 프로그램이 쓰고 있어 404나 리디렉션이 오는 경우를 준비됨으로 읽으면 안 된다.
    """
    assert support_client(lambda request: httpx.Response(status)).ready() is False
    assert summary_client(lambda request: httpx.Response(status)).ready() is False


def test_default_timeouts_and_the_timeout_argument_reach_the_http_client():
    """기본 시간 제한과 `timeout_s` 인자가 httpx 클라이언트까지 전해지는지 본다.

    httpx가 요청마다 붙이는 시간 제한은 `request.extensions["timeout"]`에서 읽을 수 있다.
    """
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    SupportAgentClient(SUPPORT_URL, TOKEN, transport=transport).ready()
    CallSummaryClient(SUMMARY_URL, transport=transport).ready()
    SupportAgentClient(SUPPORT_URL, TOKEN, transport=transport, timeout_s=7.5).ready()
    CallSummaryClient(SUMMARY_URL, transport=transport, timeout_s=3.0).ready()

    # 연결·쓰기·읽기·연결 풀 기다리기 네 가지에 같은 값이 걸린다.
    # 기본은 60초(support-agent)와 120초(call-summary)다.
    assert [set(timeout.values()) for timeout in seen] == [{60.0}, {120.0}, {7.5}, {3.0}]


# ---------------------------------------------------------------- 준비될 때까지 기다리기


class FakeTime:
    """진짜 시간을 쓰지 않는 시계와 잠. sleep이 시계를 그만큼 앞으로 돌린다."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def answering(*statuses: int):
    """요청마다 statuses를 차례로 답하고 다 쓰면 마지막 값을 되풀이하는 처리기. 받은 경로도 기록한다."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(statuses[min(len(paths), len(statuses)) - 1])

    return handler, paths


def test_wait_until_ready_polls_until_both_answer():
    fake = FakeTime()
    support_handler, support_paths = answering(503, 200)
    summary_handler, summary_paths = answering(200)
    clients = [support_client(support_handler), summary_client(summary_handler)]

    assert wait_until_ready(clients, 10.0, interval_s=0.5, sleep=fake.sleep, clock=fake.clock) is True
    assert support_paths == ["/healthz", "/healthz"]
    assert summary_paths == ["/health", "/health"]  # 앞 클라이언트가 아직이어도 뒤 것을 건너뛰지 않는다
    assert fake.sleeps == [0.5]


def test_wait_until_ready_gives_up_after_the_timeout():
    fake = FakeTime()
    support_handler, support_paths = answering(503)
    summary_handler, summary_paths = answering(200)
    clients = [support_client(support_handler), summary_client(summary_handler)]

    assert wait_until_ready(clients, 2.0, interval_s=0.5, sleep=fake.sleep, clock=fake.clock) is False
    assert fake.sleeps == [0.5, 0.5, 0.5, 0.5]
    assert len(support_paths) == 5  # 시간 0, 0.5, 1.0, 1.5, 2.0에 한 번씩
    assert len(summary_paths) == 5  # 준비된 클라이언트도 매 바퀴 확인한다


def test_wait_until_ready_does_not_sleep_past_the_deadline():
    fake = FakeTime()
    handler, _ = answering(503)
    clients = [summary_client(handler)]

    assert wait_until_ready(clients, 1.2, interval_s=0.5, sleep=fake.sleep, clock=fake.clock) is False
    assert fake.sleeps == pytest.approx([0.5, 0.5, 0.2])


def test_wait_until_ready_checks_once_even_with_a_zero_timeout():
    fake = FakeTime()
    ready_handler, ready_paths = answering(200)
    assert wait_until_ready([summary_client(ready_handler)], 0, sleep=fake.sleep, clock=fake.clock) is True
    assert ready_paths == ["/health"]
    down_handler, down_paths = answering(503)
    assert wait_until_ready([summary_client(down_handler)], 0, sleep=fake.sleep, clock=fake.clock) is False
    assert down_paths == ["/health"]
    assert fake.sleeps == []
