"""상담 후처리 서비스 연결의 설정과 클라이언트(service/summary.py)를 가짜 서비스로 시험한다."""

# [테스트 묶음] (1) 고객에게 보인 대화를 후처리 요청의 발화로 바꾸는 규칙(summary_turns) (2) 보내는
# 요청의 꼴: POST /summarize, 업종 shop, 인증 머리 없음, 압축하지 않은 답을 청함, 잰 바이트 그대로의 본문
# (3) 후처리 서비스 쪽 실패(시간 초과, 연결 실패, 거절, 붐빔, 넘겨 주기, 그 밖의 상태, 쓸 수 없는 답)를
# 설명이 붙은 상태 코드로 옮기는 표 (4) 그쪽 거절 본문의 글을 옮기지 않음 (5) 너무 큰 답과 느린 답은 흘려
# 받는 동안 끊음 (6) 너무 큰 요청은 보내지 않음 (7) 프록시 환경 변수를 읽지 않음과 기다리는 시간의 제한
# (8) 두 스레드가 한 클라이언트를 함께 씀 (9) 설정의 기본값(꺼짐)과 주소·시간 검사.
# [왜 중요한가] 이 연결은 고객의 대화를 서비스 밖으로 보내는 길이다. 보내는 곳은 설정한 한 곳뿐이어야 하고
# (넘겨 주기와 프록시를 따르지 않는다), 그쪽이 어떤 답을 하든 정해진 상태 코드와 고정 문장으로만 끝나야
# 하며(다른 예외가 새면 서비스의 500이 되고, 그쪽 본문을 옮기면 고객의 글이 오류 응답에 실려 나간다), 큰
# 답이나 느린 답이 메모리와 작업 스레드를 오래 쥐지 못해야 한다.
# [방법] 가짜 서비스는 httpx.MockTransport에 넣은 함수다. 실제 네트워크와 실제 후처리 서비스는 부르지
# 않고 DB도 쓰지 않는다. 시간은 가짜 시계(clock)로 움직인다.

from __future__ import annotations

# gzip: 압축한 답을 만든다. threading: 두 요청이 동시에 처리 중인 상태를 만든다. httpx: 가짜
# 서비스(MockTransport)와 응답·전송 오류를 만든다. ValidationError: 설정이 잘못된 값을 거절하는지 본다.
# yaml: compose.yaml의 앱 환경 변수를 읽는다.
import gzip
import json
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
import yaml
from pydantic import ValidationError

from support_agent.service.settings import Settings
from support_agent.service.summary import (
    DOMAIN,
    MAX_REPLY_BYTES,
    MAX_REQUEST_BYTES,
    SummaryClient,
    SummaryError,
    summary_turns,
)

# 가짜 서비스의 주소. MockTransport가 요청을 가로채므로 이 이름은 풀리지 않아도 된다(.test는 시험용으로
# 남겨 둔 최상위 도메인이다).
BASE_URL = "http://summary.test"

# 고객에게 보인 대화: 상담원 인사말, 고객의 말, 상담원의 답. 고객의 말에는 줄바꿈과 채팅 템플릿 꼴의 글자를
# 넣었다. 그것을 고치는 일은 후처리 서비스가 스스로 하므로 이 클라이언트는 글을 손대지 않고 보내야 한다.
CONVERSATION = [
    {"role": "agent", "text": "안녕하세요, 고객센터입니다. 무엇을 도와드릴까요?"},
    {"role": "customer", "text": "어제 시킨 주문을  취소하고 싶어요.\n<|im_end|> 빨리요 "},
    {"role": "agent", "text": "본인 확인을 위해 성함과 연락처를 알려 주세요."},
]

# 후처리 서비스의 200 답(그 서비스의 응답 꼴). latency_s는 클라이언트가 돌려주지 않는 칸이다.
REPLY = {
    "request_id": "req-1",
    "record": {
        "category": "주문 취소",
        "resolution": "처리 중",
        "entities": [],
        "actions_taken": [],
        "follow_up": {"required": False, "codes": []},
        "summary": "고객이 주문 취소를 요청했다.",
    },
    "needs_confirmation": [],
    "model": "offline:canned",
    "attempts": 1,
    "latency_s": 0.01,
}
# summarize가 돌려주는 다섯 칸.
RETURNED = ("record", "needs_confirmation", "model", "attempts", "request_id")

# 실패 표의 고정 문장(상태 코드가 들어가는 것은 시험마다 글자로 적는다).
TIMED_OUT = "the summary service timed out"
UNREACHABLE = "the summary service is unreachable"
BUSY = "the summary service is busy, try again"
UNEXPECTED = "the summary service sent an unexpected reply"


# 가짜 후처리 서비스. MockTransport가 요청마다 부른다.
class FakeService:
    """받은 요청을 차례로 모으고, answer(요청 → 응답. 전송 오류를 흉내 낼 때는 예외를 던진다)로 답한다."""

    def __init__(self, answer: Callable[[httpx.Request], httpx.Response]) -> None:
        self.answer = answer
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.answer(request)


# 가짜 시계. now를 시험이 손으로 옮긴다. SummaryClient의 clock 자리에 넣는다.
class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# 가짜 서비스에 붙은 SummaryClient를 만드는 함수를 준다. 만든 클라이언트는 시험이 끝나면 닫는다.
@pytest.fixture
def connect():
    clients: list[SummaryClient] = []

    def make(
        service: FakeService, *, timeout_s: float = 60.0, clock: Callable[[], float] | None = None
    ) -> SummaryClient:
        extra = {} if clock is None else {"clock": clock}
        client = SummaryClient(BASE_URL, timeout_s=timeout_s, transport=httpx.MockTransport(service), **extra)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


# summarize가 SummaryError로 끝나야 한다. 그 예외를 돌려준다(대화를 주지 않으면 CONVERSATION).
def refused(client: SummaryClient, messages: list[dict[str, str]] | None = None) -> SummaryError:
    with pytest.raises(SummaryError) as caught:
        client.summarize(CONVERSATION if messages is None else messages)
    return caught.value


# 그 상태 코드(와 머리)로 답하는 answer. 본문은 그 서비스의 오류 꼴({"detail": …})이다. 머리 값을 바이트로
# 주면 회선에서 온 바이트처럼 httpx가 글자로 푼다.
def answer_with(
    status: int, headers: dict[str, str | bytes] | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(status, headers=headers, json={"detail": "something went wrong"})


# 200과 그 본문 바이트로 답하는 answer.
def reply_with(content: bytes) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, content=content)


# 요청을 받으면 그 전송 오류(시간 초과, 연결 실패 등)를 던지는 answer.
def fail_with(error: type[httpx.TransportError]) -> Callable[[httpx.Request], httpx.Response]:
    def answer(request: httpx.Request) -> httpx.Response:
        raise error("simulated", request=request)

    return answer


# -------------------------------------------------------------------- 대화 → 요청


# 통화 한 건 시연(e2e)과 같은 규칙: customer → 고객, agent → 상담원, 글은 그대로(첫 줄의 상담원 인사말과
# 줄바꿈·공백 포함). 그 밖의 역할(도구·시스템 메시지)이나 꼴이 틀린 항목은 조용히 버리지 않고 ValueError다.
def test_turns_follow_the_demo_mapping():
    assert summary_turns(CONVERSATION) == [
        {"speaker": "상담원", "text": CONVERSATION[0]["text"]},
        {"speaker": "고객", "text": CONVERSATION[1]["text"]},
        {"speaker": "상담원", "text": CONVERSATION[2]["text"]},
    ]
    with pytest.raises(ValueError):
        summary_turns([*CONVERSATION, {"role": "tool", "text": "{}"}])
    odd_messages = (
        [{"role": "system", "text": "지시"}],
        [{"role": "customer"}],
        [{"role": "customer", "text": None}],
        [{"role": ["customer"], "text": "네"}],
        ["고객: 네"],
    )
    for messages in odd_messages:
        with pytest.raises(ValueError):
            summary_turns(messages)
    with pytest.raises(ValueError):
        summary_turns({"role": "customer", "text": "네"})  # 목록이 아니다
    assert summary_turns([]) == []


# 보내는 요청: POST /summarize 하나, 본문은 업종 shop과 바꾼 발화. 본문은 httpx의 json= 과 같은 꼴(줄인
# 구분자, 한글은 UTF-8 그대로)로 직접 만든 바이트이고 Content-Length가 그 길이다. 관리자 토큰이나 인증 머리는
# 싣지 않고, 압축하지 않은 답을 청한다. 200 답에서는 다섯 칸만 돌려준다(latency_s는 뺀다).
def test_request_shape(connect):
    service = FakeService(lambda request: httpx.Response(200, json=REPLY))
    result = connect(service).summarize(CONVERSATION)
    (request,) = service.requests
    assert (request.method, str(request.url)) == ("POST", "http://summary.test/summarize")
    assert DOMAIN == "shop"
    payload = {"domain": "shop", "turns": summary_turns(CONVERSATION)}
    assert json.loads(request.content) == payload
    assert request.content == json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert request.headers["content-length"] == str(len(request.content))
    assert request.headers["content-type"] == "application/json"
    assert request.headers["accept-encoding"] == "identity"
    assert "x-admin-token" not in request.headers
    assert "authorization" not in request.headers
    assert result == {key: REPLY[key] for key in RETURNED}


# 짝 없는 서로게이트가 든 글은 UTF-8로 보낼 수 없다. 보내지 않고 ValueError(UnicodeEncodeError)다. 서비스가
# 받는 고객 메시지는 그런 글을 받지 않으므로(요청 검사가 422로 거절한다) 저장된 대화에는 없어야 하는 값이다.
def test_text_that_cannot_be_written_as_utf8_is_not_sent(connect):
    service = FakeService(lambda request: httpx.Response(200, json=REPLY))
    with pytest.raises(ValueError):
        connect(service).summarize([{"role": "customer", "text": "\ud800"}])
    assert service.requests == []


# 보내는 본문의 상한은 후처리 서비스의 요청 본문 한도(64 KiB)와 같다. 꼭 그만큼인 본문은 보내고, 1바이트라도
# 넘는 본문은 보내지 않고 422로 끝낸다(그쪽은 넘는 본문을 읽기 전에 413으로 답해, 보내는 쪽이 그 답 대신
# 쓰기 중 전송 오류를 볼 수 있다). 재는 것은 글자 수가 아니라 실제로 보내는 UTF-8 바이트다(한글 한 글자는
# 3바이트).
def test_oversized_request_is_not_sent(connect):
    assert MAX_REQUEST_BYTES == 64 * 1024
    service = FakeService(lambda request: httpx.Response(200, json=REPLY))
    client = connect(service)
    frame = {"domain": DOMAIN, "turns": [{"speaker": "고객", "text": ""}]}
    room = MAX_REQUEST_BYTES - len(
        json.dumps(frame, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    client.summarize([{"role": "customer", "text": "a" * room}])
    assert len(service.requests[-1].content) == MAX_REQUEST_BYTES
    error = refused(client, [{"role": "customer", "text": "a" * (room + 1)}])
    assert (error.status, error.detail, error.retry_after) == (
        422,
        "the conversation is too long for the summary service",
        None,
    )
    korean = "가" * (room // 3 + 1)
    assert len(korean) < MAX_REQUEST_BYTES // 2
    assert refused(client, [{"role": "customer", "text": korean}]).status == 422
    assert len(service.requests) == 1  # 넘는 두 요청은 보내지 않았다


# -------------------------------------------------------------------- 실패를 옮기는 표


# 후처리 서비스 쪽 실패마다 정해진 상태 코드와 고정 문장이다: 시간 초과 504, 연결 실패 502, 그쪽 422·413은
# 422(대화 자체를 받지 않음), 그쪽 503은 429(관리 화면이 503을 '관리자 기능이 꺼짐'으로 읽으므로 503을 쓰지
# 않는다)와 검사한 Retry-After, 그 밖의 상태(넘겨 주기 302 포함)는 502, 쓸 수 없는 200 답은 502. 어느 경우든
# 요청은 하나뿐이다(다시 보내지 않고, 넘겨 주기를 따라가지 않는다).
@pytest.mark.parametrize(
    ("answer", "status", "detail", "retry_after"),
    [
        pytest.param(
            answer_with(422), 422, "the summary service rejected this conversation (422)", None, id="422"
        ),
        pytest.param(
            answer_with(413), 422, "the summary service rejected this conversation (413)", None, id="413"
        ),
        pytest.param(answer_with(503, {"Retry-After": "7"}), 429, BUSY, "7", id="503-retry-after-7"),
        pytest.param(answer_with(503, {"Retry-After": "soon"}), 429, BUSY, "30", id="503-retry-after-soon"),
        pytest.param(answer_with(503, {"Retry-After": "99999"}), 429, BUSY, "30", id="503-retry-after-99999"),
        pytest.param(answer_with(500), 502, "the summary service answered 500", None, id="500"),
        pytest.param(
            answer_with(302, {"Location": "http://elsewhere.test/summarize"}),
            502,
            "the summary service answered 302",
            None,
            id="302",
        ),
        pytest.param(fail_with(httpx.ReadTimeout), 504, TIMED_OUT, None, id="read-timeout"),
        pytest.param(fail_with(httpx.ConnectError), 502, UNREACHABLE, None, id="connect-error"),
        pytest.param(
            lambda request: httpx.Response(200, text="not json"), 502, UNEXPECTED, None, id="200-not-json"
        ),
        pytest.param(
            lambda request: httpx.Response(200, json={}), 502, UNEXPECTED, None, id="200-empty-object"
        ),
    ],
)
def test_upstream_failures_become_explained_statuses(connect, answer, status, detail, retry_after):
    service = FakeService(answer)
    error = refused(connect(service))
    assert (error.status, error.detail, error.retry_after) == (status, detail, retry_after)
    assert len(service.requests) == 1


# 그쪽 503의 Retry-After는 1~3600의 정수 글일 때만 넘겨준다(앞의 0은 떼어 같은 수로). 없거나, 범위 밖이거나,
# 소수·음수·날짜·ASCII 밖의 숫자면 30초다. 그쪽 머리 값을 검사 없이 이 서비스의 응답 머리에 옮기지 않는다.
@pytest.mark.parametrize(
    ("header", "passed_on"),
    [
        (None, "30"),
        ("1", "1"),
        ("3600", "3600"),
        ("007", "7"),
        ("0", "30"),
        ("3601", "30"),
        ("-5", "30"),
        ("1.5", "30"),
        (chr(0xFF17).encode(), "30"),  # 전각 숫자 7(U+FF17)을 UTF-8 바이트로 보낸 머리
        ("Wed, 21 Oct 2026 07:28:00 GMT", "30"),
    ],
)
def test_busy_passes_on_only_a_small_whole_number_of_seconds(connect, header, passed_on):
    headers = None if header is None else {"Retry-After": header}
    error = refused(connect(FakeService(answer_with(503, headers))))
    assert (error.status, error.detail, error.retry_after) == (429, BUSY, passed_on)


# 표의 나머지 경우도 같은 상태 코드로 끝나고, 어느 것도 SummaryError 밖의 예외로 새지 않는다: 200이 아닌 2xx와
# 307도 502, 연결·쓰기·연결 풀 대기의 시간 초과도 504, 읽다가 끊기거나 HTTP 꼴이 틀린 답은 502(연결 실패와
# 같은 문장), JSON 객체가 아니거나 record가 객체가 아니거나 너무 깊게 겹친(json이 RecursionError로 멈추는)
# 답과 UTF-8이 아닌 답도 502.
@pytest.mark.parametrize(
    ("answer", "status", "detail"),
    [
        pytest.param(answer_with(201), 502, "the summary service answered 201", id="201"),
        pytest.param(answer_with(404), 502, "the summary service answered 404", id="404"),
        pytest.param(answer_with(502), 502, "the summary service answered 502", id="502"),
        pytest.param(
            answer_with(307, {"Location": "http://elsewhere.test/summarize"}),
            502,
            "the summary service answered 307",
            id="307",
        ),
        pytest.param(fail_with(httpx.ConnectTimeout), 504, TIMED_OUT, id="connect-timeout"),
        pytest.param(fail_with(httpx.WriteTimeout), 504, TIMED_OUT, id="write-timeout"),
        pytest.param(fail_with(httpx.PoolTimeout), 504, TIMED_OUT, id="pool-timeout"),
        pytest.param(fail_with(httpx.ReadError), 502, UNREACHABLE, id="read-error"),
        pytest.param(fail_with(httpx.RemoteProtocolError), 502, UNREACHABLE, id="remote-protocol-error"),
        pytest.param(reply_with(b"[]"), 502, UNEXPECTED, id="200-json-list"),
        pytest.param(reply_with(b'{"record": null}'), 502, UNEXPECTED, id="200-record-null"),
        pytest.param(reply_with(b'{"record": "summary"}'), 502, UNEXPECTED, id="200-record-text"),
        pytest.param(reply_with(b"[" * 100_000), 502, UNEXPECTED, id="200-nested-too-deep"),
        pytest.param(reply_with(b'{"record": "\xc3\x28"}'), 502, UNEXPECTED, id="200-not-utf8"),
    ],
)
def test_other_unusable_answers_get_the_same_statuses(connect, answer, status, detail):
    service = FakeService(answer)
    error = refused(connect(service))
    assert (error.status, error.detail, error.retry_after) == (status, detail, None)
    assert len(service.requests) == 1


# 후처리 서비스가 FastAPI 기본 꼴의 422(오류마다 문제가 된 입력 원문 `input`이 든다)를 줘도, 오류 글에는 그
# 상태 코드만 있고 고객의 글은 없다. 그쪽 본문을 읽지도 않으므로 예외에 딸린 다른 예외도 없다.
def test_rejection_does_not_echo_the_conversation(connect):
    said = "비밀스러운 고객 문장\x1b[31m 주문 취소"
    body = {
        "detail": [
            {
                "type": "string_pattern_mismatch",
                "loc": ["body", "turns", 0, "text"],
                "msg": "String should match pattern '^[^\\x00-\\x08\\x0e-\\x1b]*$'",
                "input": said,
                "ctx": {"pattern": "^[^\\x00-\\x08\\x0e-\\x1b]*$"},
            }
        ]
    }
    service = FakeService(lambda request: httpx.Response(422, json=body))
    error = refused(connect(service), [{"role": "customer", "text": said}])
    assert (error.status, error.detail) == (422, "the summary service rejected this conversation (422)")
    for shown in (error.detail, str(error), repr(error), *map(str, error.args)):
        assert "비밀스러운" not in shown
    assert error.__cause__ is None and error.__context__ is None


# -------------------------------------------------------------------- 크기와 시간


# 끝없이 조각을 내는 답은 흘려 받는 동안 한도를 넘는 즉시 끊는다: 생성기가 낸 조각은 한도 + 한 조각을 넘지
# 않는다(큰 답을 메모리에 다 올린 뒤에 재지 않는다). Content-Length가 한도를 넘는다고 적힌 답은 본문을
# 한 조각도 읽지 않는다.
def test_oversized_reply_is_cut_off_while_streaming(connect):
    chunk = 64 * 1024
    sent: list[int] = []

    def endless() -> Iterator[bytes]:
        while True:
            # 클라이언트가 끊지 못하는 회귀가 생겨도 시험이 멈추지 않고 실패하게, 한도의 네 배를 읽으면
            # 멈춘다.
            assert sum(sent) < 4 * MAX_REPLY_BYTES, "the client kept reading past the reply limit"
            sent.append(chunk)
            yield b" " * chunk

    error = refused(connect(FakeService(lambda request: httpx.Response(200, content=endless()))))
    assert (error.status, error.detail) == (502, UNEXPECTED)
    assert MAX_REPLY_BYTES < sum(sent) <= MAX_REPLY_BYTES + chunk

    pulled: list[int] = []

    def declared_body() -> Iterator[bytes]:
        pulled.append(1)
        yield json.dumps(REPLY).encode("utf-8")

    declared = {"Content-Length": str(MAX_REPLY_BYTES + 1)}
    service = FakeService(lambda request: httpx.Response(200, headers=declared, content=declared_body()))
    error = refused(connect(service))
    assert (error.status, error.detail) == (502, UNEXPECTED)
    assert pulled == []


# 한도는 '넘으면' 끊는다: 꼭 한도만큼인 답(JSON 뒤의 공백으로 채움)은 읽고, 1바이트 더 크면 502다.
def test_a_reply_of_exactly_the_limit_is_read(connect):
    body = json.dumps(REPLY).encode("utf-8")
    exact = body + b" " * (MAX_REPLY_BYTES - len(body))
    assert len(exact) == MAX_REPLY_BYTES
    service = FakeService(lambda request: httpx.Response(200, content=iter([exact[:1000], exact[1000:]])))
    assert connect(service).summarize(CONVERSATION) == {key: REPLY[key] for key in RETURNED}
    over = FakeService(lambda request: httpx.Response(200, content=iter([exact, b" "])))
    assert refused(connect(over)).status == 502


# 압축한 답(Content-Encoding이 identity가 아님)은 본문을 읽지 않고 502다. 압축을 풀면 작은 조각 하나가 아주
# 큰 바이트로 불어날 수 있어 크기 한도가 메모리를 지키지 못한다. 클라이언트는 압축하지 않은 답을 청하므로
# 정상적인 서비스는 압축하지 않는다. identity라고 적은 답은 그대로 읽는다.
def test_a_compressed_reply_is_refused_without_reading_it(connect):
    pulled: list[int] = []

    def gzipped() -> Iterator[bytes]:
        pulled.append(1)
        yield gzip.compress(json.dumps(REPLY).encode("utf-8"))

    headers = {"Content-Encoding": "gzip"}
    service = FakeService(lambda request: httpx.Response(200, headers=headers, content=gzipped()))
    error = refused(connect(service))
    assert (error.status, error.detail) == (502, UNEXPECTED)
    assert pulled == []
    assert service.requests[0].headers["accept-encoding"] == "identity"
    plain = FakeService(
        lambda request: httpx.Response(200, headers={"Content-Encoding": "identity"}, json=REPLY)
    )
    assert connect(plain).summarize(CONVERSATION)["model"] == REPLY["model"]


# 전체 시간 상한: 요청을 시작한 때부터 가짜 시계로 잰 시간이 timeout_s를 넘기면, 조각이 계속 오더라도 그
# 조각에서 끊고 504다(httpx의 시간 제한은 조각마다 새로 시작하므로 천천히 흘리는 답을 끊지 못한다). 답의
# 머리가 상한을 넘겨 도착하면 본문을 읽지 않는다. 상한과 같은 시간은 넘긴 것이 아니다.
def test_slow_reply_hits_the_total_deadline(connect):
    clock = FakeClock()
    pulled: list[int] = []

    def trickle() -> Iterator[bytes]:
        pulled.append(1)
        yield b'{"record": {}, '
        clock.now += 61  # 다음 조각은 요청을 시작한 지 61초 뒤에 온다
        pulled.append(2)
        yield b'"model": "offline:canned"'
        pulled.append(3)
        yield b"}"

    service = FakeService(lambda request: httpx.Response(200, content=trickle()))
    error = refused(connect(service, timeout_s=60, clock=clock))
    assert (error.status, error.detail, error.retry_after) == (504, TIMED_OUT, None)
    assert pulled == [1, 2]

    late_clock = FakeClock()
    unread: list[int] = []

    def late_body() -> Iterator[bytes]:
        unread.append(1)
        yield json.dumps(REPLY).encode("utf-8")

    def late(request: httpx.Request) -> httpx.Response:
        late_clock.now += 61
        return httpx.Response(200, content=late_body())

    assert refused(connect(FakeService(late), timeout_s=60, clock=late_clock)).status == 504
    assert unread == []

    on_time_clock = FakeClock()

    def on_time() -> Iterator[bytes]:
        yield b'{"record": {}, '
        on_time_clock.now += 60
        yield b'"model": "offline:canned"}'

    service = FakeService(lambda request: httpx.Response(200, content=on_time()))
    result = connect(service, timeout_s=60, clock=on_time_clock).summarize(CONVERSATION)
    assert (result["record"], result["model"]) == ({}, "offline:canned")


# -------------------------------------------------------------------- 클라이언트의 꼴


# 프록시 환경 변수가 있어도 따르지 않는다(trust_env=False): 요청은 환경의 프록시가 아니라 클라이언트 자신의
# 연결로 곧장 간다. 넘겨 주기도 따라가지 않게 만든다.
def test_client_ignores_proxy_environment(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://proxy.invalid:3128")
    client = SummaryClient(BASE_URL, timeout_s=120)
    try:
        assert client._http.trust_env is False
        assert client._http._transport_for_url(httpx.URL(f"{BASE_URL}/summarize")) is client._http._transport
        assert client._http.follow_redirects is False
    finally:
        client.close()


# 응답 머리를 받기 전의 기다림(연결, 보내기, 첫 바이트)에도 httpx의 제한이 걸린다: 읽기·쓰기·연결 풀은
# timeout_s, 연결은 10초와 timeout_s 가운데 작은 값.
def test_each_wait_before_the_reply_is_limited_too():
    for timeout_s, connect_s in ((120, 10.0), (5, 5)):
        client = SummaryClient(BASE_URL, timeout_s=timeout_s)
        try:
            assert client._http.timeout == httpx.Timeout(timeout_s, connect=connect_s)
        finally:
            client.close()


# 관리자 API 처리기처럼 여러 스레드가 한 클라이언트를 함께 써도 된다: 두 요청이 동시에 처리 중일 때만
# 지나가는 가짜 서비스로, 두 호출이 서로 막지 않고 각자 자기 답을 받는지 본다.
def test_two_threads_can_share_one_client(connect):
    both_in = threading.Barrier(2, timeout=10)

    def answer(request: httpx.Request) -> httpx.Response:
        both_in.wait()
        first = json.loads(request.content)["turns"][0]["text"]
        return httpx.Response(200, json={**REPLY, "request_id": first})

    client = connect(FakeService(answer))
    results: dict[str, str] = {}

    def call(name: str) -> None:
        results[name] = client.summarize([{"role": "customer", "text": name}])["request_id"]

    threads = [threading.Thread(target=call, args=(name,)) for name in ("첫째", "둘째")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert results == {"첫째": "첫째", "둘째": "둘째"}


# -------------------------------------------------------------------- 설정


# 후처리 연결은 기본으로 꺼져 있다(주소가 빈 글). 주소는 http://·https:// 와 호스트가 있어야 하고 끝의 `/`는
# 뗀다. 시간 상한은 1~600초(기본 120초). 잘못된 값은 서비스가 시작할 때 거절한다. Compose가 넘기는 빈 값은
# '설정 안 함'이다.
def test_settings_default_is_off_and_validated():
    assert Settings().summary_url == ""
    assert Settings().summary_timeout_s == 120
    assert Settings(summary_url="http://127.0.0.1:8072/").summary_url == "http://127.0.0.1:8072"
    for wrong in ("ftp://x", "127.0.0.1:8072", "http://"):
        with pytest.raises(ValidationError):
            Settings(summary_url=wrong)
    for wrong in (0, 601):
        with pytest.raises(ValidationError):
            Settings(summary_timeout_s=wrong)
    assert Settings(summary_timeout_s=1).summary_timeout_s == 1
    assert Settings(summary_timeout_s=600).summary_timeout_s == 600
    assert Settings.from_env({"SUPPORT_AGENT_SUMMARY_URL": ""}).summary_url == ""
    env = {"SUPPORT_AGENT_SUMMARY_URL": "http://127.0.0.1:8072", "SUPPORT_AGENT_SUMMARY_TIMEOUT_S": "30"}
    settings = Settings.from_env(env)
    assert (settings.summary_url, settings.summary_timeout_s) == ("http://127.0.0.1:8072", 30)
    with pytest.raises(ValidationError):
        Settings.from_env({"SUPPORT_AGENT_SUMMARY_TIMEOUT_S": "0"})


# 주소는 http(s)://호스트[:포트][/경로] 꼴만 받는다. 사용자 정보(httpx가 Authorization 머리로 바꿔 보낸다),
# 질의·조각(뒤에 붙는 /summarize와 섞여 경로가 깨진다), 공백, 역슬래시, 퍼센트 인코딩, IPv6 주소, ASCII 밖의
# 이름, IPv4 꼴이지만 틀린 주소, 범위 밖 포트는 서비스가 시작할 때 거절한다.
@pytest.mark.parametrize(
    "wrong",
    [
        "http://user:secret@127.0.0.1:8072",
        "http://user@summary.example",
        "http://127.0.0.1:8072/?x=1",
        "http://127.0.0.1:8072/#top",
        "http://127.0.0.1:8072/a b",
        "http://summary example",
        "http://127.0.0.1:8072\\@summary.example",
        "http://127.0.0.1:8072/%2e%2e",
        "http://[::1]:8072",
        "http://요약.example",
        "http://999.1.1.1",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:",
        "https:/127.0.0.1",
    ],
)
def test_the_summary_url_takes_only_a_plain_http_address(wrong):
    with pytest.raises(ValidationError):
        Settings(summary_url=wrong)


# 받는 꼴: https, 경로 접두사(앞단 프록시), 밑줄이 든 이름(Docker 서비스 이름), 대문자. 앞뒤 공백과 끝의 `/`는
# 떼고, 공백뿐인 값은 빈 값(꺼짐)이다.
@pytest.mark.parametrize(
    ("value", "stored"),
    [
        ("https://summary.example", "https://summary.example"),
        ("http://call_summary:8072/prefix/", "http://call_summary:8072/prefix"),
        ("HTTP://Summary.Example:8072//", "HTTP://Summary.Example:8072"),
        ("  http://127.0.0.1:8072 ", "http://127.0.0.1:8072"),
        ("   ", ""),
    ],
)
def test_the_summary_url_keeps_a_plain_address(value, stored):
    assert Settings(summary_url=value).summary_url == stored


# Docker로 띄운 서비스에도 두 설정이 닿는다: compose가 `.env`의 값을 앱 환경 변수로 넘기고(비어 있으면 빈
# 글 = 설정 안 함이라 기본값 그대로), `.env.example`에 두 항목이 있다. compose는 파일에 적힌 변수만 `.env`에서
# 가져가므로 이 줄이 없으면 `.env`에 값을 적어도 앱은 모른다.
def test_compose_and_the_env_example_pass_the_summary_settings_through():
    root = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((root / "compose.yaml").read_text(encoding="utf-8"))
    app_env = compose["services"]["app"]["environment"]
    assert app_env["SUPPORT_AGENT_SUMMARY_URL"] == "${SUMMARY_URL:-}"
    assert app_env["SUPPORT_AGENT_SUMMARY_TIMEOUT_S"] == "${SUMMARY_TIMEOUT_S:-}"
    example = (root / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "SUMMARY_URL=" in example and "SUMMARY_TIMEOUT_S=" in example
    empty = Settings.from_env({"SUPPORT_AGENT_SUMMARY_URL": "", "SUPPORT_AGENT_SUMMARY_TIMEOUT_S": ""})
    assert (empty.summary_url, empty.summary_timeout_s) == ("", 120)
