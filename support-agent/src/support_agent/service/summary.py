"""상담 후처리 서비스(call-summary)의 POST /summarize를 부르는 클라이언트. 실패는 SummaryError로 올린다."""

# [파일 역할] 고객에게 보인 대화(ChatService.transcript의 messages)를 상담 후처리 서비스의 요청 꼴로 바꾸고
# (summary_turns), 그 서비스의 POST /summarize를 한 번 불러 상담 후처리 기록을 받는다(SummaryClient). 실패는
# 모두 SummaryError 하나로 올리고, 그 status는 이 서비스가 HTTP 응답에 그대로 쓸 수 있게 고른 값이다(아래
# '상태 코드'). 주소와 시간 상한은 설정(settings.py의 summary_url·summary_timeout_s)이 준다.
#
# [주소는 설정에서만] 부를 주소는 설정(SUPPORT_AGENT_SUMMARY_URL)에서만 받고 요청에서 받지 않는다. 요청의
# 본문이나 질의로 주소를 받으면, 관리자 토큰을 가진 사람(또는 그 토큰이 실린 요청을 보내게 된 누구든)이
# 서비스를 시켜 서비스만 닿을 수 있는 내부 주소로 상담 대화를 보내게 할 수 있다(서버 쪽 요청 위조, SSRF).
# 주소를 운영자가 정한 한 곳으로 묶으면 이 클라이언트가 대화를 보내는 곳은 늘 그 서비스뿐이다.
#
# [넘겨 주기와 프록시] 넘겨 주기(3xx 응답의 Location)를 따라가지 않는다(follow_redirects=False). 따라가면
# 그쪽의 답 하나로 요청이 설정에 없는 주소로 옮겨 가고, 307·308이면 대화를 담은 본문까지 그 주소로 다시
# 보낸다. 그래서 3xx는 실패(502)로 본다. 프록시 환경 변수(HTTP_PROXY·HTTPS_PROXY·ALL_PROXY)도 읽지 않는다
# (trust_env=False). 그 PC나 컨테이너에 다른 까닭으로 둔 프록시로 고객의 대화가 나가지 않게 하고, 로컬
# 주소를 부르는데 요청이 프록시로 먼저 가서 엉뚱한 이유로 실패하는 일도 막는다(통화 한 건 시연 e2e의
# 클라이언트가 trust_env=False를 쓰는 까닭과 같다). 주의: trust_env를 끄면 httpx는 SSL_CERT_FILE·
# SSL_CERT_DIR도 읽지 않는다. 그래서 https 주소의 인증서는 httpx의 기본(certifi의 공개 인증서 묶음)으로만
# 확인한다.
#
# [크기] 보내는 본문은 직접 직렬화한 UTF-8 바이트로 재고 그 바이트를 그대로 보낸다(MAX_REQUEST_BYTES).
# 받는 답은 흘려 받으며(stream) 쌓은 바이트가 MAX_REPLY_BYTES를 넘는 즉시 끊는다. 큰 답을 메모리에 다 올린
# 뒤에 재면 이미 그만큼 메모리를 쓴 뒤다. 압축한 답은 읽지 않는다: 압축을 풀면 작은 조각 하나가 아주 큰
# 바이트로 불어날 수 있어(httpx는 조각마다 크기 제한 없이 푼다) 크기 한도가 메모리를 지키지 못한다. 그래서
# 압축하지 않은 답을 청하고(Accept-Encoding: identity), Content-Encoding이 identity가 아닌 답은 읽지 않고
# 502다.
#
# [시간] httpx의 시간 제한은 단계마다 따로 걸린다: 연결은 10초와 timeout_s 가운데 작은 값, 보내기와 응답
# 기다리기(조각 하나를 읽는 사이)와 연결 풀 대기는 timeout_s다. 읽기 제한은 조각이 올 때마다 새로
# 시작하므로 천천히 흘려보내는 답은 그것만으로 끊기지 않는다. 그래서 요청을 시작한 때부터 clock()으로 잰
# 전체 시간이 timeout_s를 넘기면, 200 답의 머리를 받았을 때와 본문 조각을 받을 때마다 끊고 시간 초과(504)로
# 본다. 이 확인은 머리나 조각이 도착할 때 하므로 그 사이에 멈춘 서버는 httpx의 제한이 끊는다. 그래서 한
# 요청이 스레드를 쥐는 시간은 최악에 timeout_s의 약 두 배(와 연결 시간)다. 응답 머리를 받는 동안에는 이
# 전체 상한을 볼 수 없어 단계별 제한만 걸린다(머리를 아주 천천히 흘리는 서버는 그보다 오래 붙잡을 수 있다).
#
# [다시 보내지 않음] 한 번 부르고 끝이다. 후처리 서비스의 일은 모델 호출이라 무겁고, 그 서비스는 기록의
# 형식이 틀리면 안에서 이미 한 번 다시 시도한다(응답의 attempts). 실패하면 사람이 다시 누르면 된다.
#
# [상태 코드] SummaryError.status는 이 서비스가 그대로 답할 상태 코드다.
# - 504: 시간 초과(httpx의 단계별 제한, 또는 위 전체 상한). 앞단이 제때 답하지 않은 게이트웨이의 뜻이다.
# - 502: 그 밖의 전송 오류(연결 거절, 이름 풀기 실패, 답 도중 끊김), 200이 아닌 그 밖의 상태(3xx 포함),
#   쓸 수 없는 200 답(JSON 객체가 아님, record가 객체가 아님, 압축함, MAX_REPLY_BYTES를 넘음). 앞단이
#   잘못 답한 게이트웨이의 뜻이다.
# - 422: 그쪽의 422(모르는 업종, 발화 꼴·제어문자)와 413(조립한 전사가 너무 김, 모델의 컨텍스트 초과),
#   그리고 보내기 전에 잰 본문이 MAX_REQUEST_BYTES를 넘을 때. 같은 대화를 다시 보내도 결과가 같으므로 다시
#   시도할 일이 아니고, 이 서비스로 온 요청이 큰 것이 아니라 그 대화가 그쪽 한도에 안 맞는 것이라 413이
#   아니다. 그쪽 오류 본문의 글은 옮기지 않는다: 그쪽 422의 기본 본문에는 문제가 된 입력 원문(고객의 글)이
#   들어 있어, 옮기면 고객의 글이 이 서비스의 오류 응답과 기록에 남는다. 이 서비스의 422 처리기가 요청 검사
#   오류에서 입력 원문을 빼는 것(app.py의 validation_error)과 같은 까닭이다.
# - 429: 그쪽의 503(붐빔, 또는 그쪽 모델 서버를 쓸 수 없음). 503을 쓰지 않는 까닭: 관리 화면
#   (static/admin.js의 api)은 503을 '관리자 기능이 꺼짐'으로 읽어 로그인 화면을 띄우므로, 잠깐 붐빈 것만으로
#   관리 화면이 로그인 화면으로 바뀐다. 답 읽어 주기가 붐빌 때 429를 쓰는 것(app.py의 speak)과 같은
#   까닭이다. retry_after는 그쪽 Retry-After가 1~3600의 정수 글일 때만 그 값이고 아니면 "30"이다. 그쪽 머리
#   값을 검사 없이 이 서비스의 응답 머리에 옮기지 않는다.
# detail은 영어 한 문장(이 서비스의 다른 오류 글과 같은 꼴)이고, 고정 글과 상태 코드만 담는다. 대화의 글,
# 그쪽 본문, 주소(설정값)는 넣지 않는다.
#
# [스레드] 여러 스레드가 한 SummaryClient의 summarize를 함께 불러도 된다. 인스턴스에는 만들 때 정한
# 값(시간 상한, 시계, httpx.Client)만 있고 호출마다 바뀌는 값(시작 시각, 받은 바이트)은 모두 지역
# 변수다. 연결 풀을 가진 httpx.Client는 스레드 여럿이 함께 써도 되는 객체다.

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

# httpx: 동기 HTTP 클라이언트(ollama.py와 같은 기본 의존성). 응답을 흘려 받을 수 있고(stream), 시간
# 제한을 단계별로 줄 수 있으며, 시험에서 가짜 transport(httpx.MockTransport)를 끼울 수 있다.
import httpx

# 후처리 서비스에 보내는 업종 키. 이 상담 서비스는 가상 쇼핑몰의 고객센터라 늘 shop이다(그 서비스의 업종
# 키는 shop·telecom·parcel·card).
DOMAIN = "shop"
# 받아들이는 응답 본문의 상한(바이트, 1 MiB). 이것은 이 서비스가 받는 답의 상한이다(보내는 본문의 상한은
# 아래 MAX_REQUEST_BYTES). 정상 답은 모델이 컨텍스트 4,096토큰 안에서 쓴 기록 하나와 번호 확인 표시 몇
# 개라 이보다 훨씬 작고, 넘는 답은 쓸 수 없는 답으로 본다(502).
MAX_REPLY_BYTES = 1 << 20
# 보내는 요청 본문의 상한(바이트, 64 KiB). 후처리 서비스의 요청 본문 한도(call-summary의
# MAX_BODY_BYTES)와 같은 값이다. 그 서비스는 Content-Length가 한도를 넘으면 본문을 읽기 전에 413으로
# 답하므로, 큰 본문을 보내는 쪽은 그 413 대신 본문을 쓰는 도중의 전송 오류를 볼 수 있다(그러면 위 표에서
# 502가 되어 까닭이 흐려진다). 그래서 넘는 본문은 보내지 않고 그쪽이 413을 줬을 때와 같은 422로 끝낸다.
# 재는 것은 글자 수가 아니라 실제로 보내는 UTF-8 바이트다(한글 한 글자는 3바이트). 그 서비스의 한도가
# 바뀌면 이 값도 함께 바꾼다.
MAX_REQUEST_BYTES = 64 * 1024

# 고객에게 보인 대화의 역할 → 후처리 서비스의 화자. 통화 한 건 시연(e2e/src/call_e2e/flow.py의
# summary_turns)과 같은 규칙이다. 서비스 코드는 그 폴더를 가져다 쓸 수 없어(구성 요소마다 따로 설치하는
# 프로젝트다) 같은 규칙을 여기 따로 둔다.
_SPEAKERS = {"customer": "고객", "agent": "상담원"}
# summarize가 돌려주는 칸. 그쪽 답의 latency_s는 빼고 돌려준다(후처리 기록의 내용이 아니라 그 요청 한
# 번을 처리한 시간이다).
_RETURNED = ("record", "needs_confirmation", "model", "attempts", "request_id")
# 보내는 요청의 머리. 본문은 JSON이고, 압축하지 않은 답을 청한다(위 '크기'). 관리자 토큰이나 인증 머리는
# 싣지 않는다(후처리 서비스에는 인증이 없다).
_REQUEST_HEADERS = {"Content-Type": "application/json", "Accept-Encoding": "identity"}
# 그쪽 503의 Retry-After가 없거나 받아들일 수 없는 값일 때 쓰는 초. 그 서비스가 붐빌 때 주는 값의
# 기본(대기 상한 30초)과 같다.
_RETRY_AFTER_FALLBACK = "30"
# 여러 곳에서 쓰는 실패 글.
_TIMED_OUT = "the summary service timed out"
_UNREACHABLE = "the summary service is unreachable"
_UNEXPECTED = "the summary service sent an unexpected reply"


def summary_turns(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """고객에게 보인 대화를 후처리 요청의 발화 목록으로 바꾼다.

    입력: ChatService.transcript의 messages — [{"role": "customer" 또는 "agent", "text": 글}, ...].
    출력: [{"speaker": "고객" 또는 "상담원", "text": 같은 글}, ...]. 새 목록이고 입력은 바꾸지 않는다.
    ValueError: 목록이 아니거나, role·text가 글인 객체가 아닌 항목이 있거나, 역할이 customer·agent
        밖일 때.
    """
    # 글은 가공하지 않는다(첫 줄의 상담원 인사말 포함). 줄바꿈이나 채팅 템플릿 꼴의 글자를 고치는 일은
    # 후처리 서비스가 스스로 하고 그 수를 기록한다. 고객에게 보인 대화에는 도구·시스템 메시지가 없어야
    # 하므로, 다른 역할을 조용히 버리지 않고 ValueError로 알린다. 오류 글에는 메시지의 값을 넣지 않는다
    # (대화의 글이 오류로 새지 않게).
    if not isinstance(messages, list):
        raise ValueError("the messages must be a list")
    turns = []
    for message in messages:
        if not (
            isinstance(message, dict)
            and isinstance(message.get("role"), str)
            and isinstance(message.get("text"), str)
        ):
            raise ValueError("each message must be an object with the text fields role and text")
        speaker = _SPEAKERS.get(message["role"])
        if speaker is None:
            raise ValueError("only customer and agent messages can be sent to the summary service")
        turns.append({"speaker": speaker, "text": message["text"]})
    return turns


class SummaryError(Exception):
    """후처리 서비스를 부르지 못했거나 그 답을 쓸 수 없다.

    status: 이 서비스가 HTTP 응답에 쓸 상태 코드(파일 머리의 '상태 코드').
    detail: 영어 한 문장. 고정 글과 상태 코드만 담고 대화의 글, 그쪽 본문, 주소는 넣지 않는다.
    retry_after: 429일 때 응답의 Retry-After에 쓸 초(1~3600의 정수 글), 그 밖에는 None.
    """

    def __init__(self, status: int, detail: str, retry_after: str | None = None) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


class SummaryClient:
    """후처리 서비스 하나에 붙은 클라이언트. 여러 스레드가 한 인스턴스의 summarize를 함께 불러도 된다.

    base_url: 서비스 주소(설정의 summary_url, 끝의 `/` 없이). 그 뒤에 /summarize를 붙여 부른다.
    timeout_s: 요청 하나를 기다리는 시간 상한(초, 파일 머리의 '시간').
    transport: 시험에서 httpx.MockTransport를 넣는 자리. None이면 실제 네트워크.
    clock: 전체 시간 상한을 재는 시계(초). 기본은 time.monotonic이고, 시험은 가짜 시계를 넣는다.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._timeout_s = timeout_s
        self._clock = clock
        # 연결 제한은 ollama.py와 같이 10초 이하로 짧게 둔다. trust_env=False·follow_redirects=False의
        # 까닭은 파일 머리의 '넘겨 주기와 프록시'다(follow_redirects=False는 httpx의 기본값이기도 하지만
        # 뜻을 드러내려고 적는다).
        # 쉬는 연결은 남기지 않는다(max_keepalive_connections=0): 요청마다 새 연결을 열고 답을 받으면 닫는다.
        # 관리자가 가끔 부르는 호출이라 연결을 다시 쓸 이득이 거의 없다. 반대로 쉬던 연결을 다시 쓰면, 그
        # 순간 그쪽 서버가 그 연결을 닫는 경우(uvicorn은 기본으로 5초 쉰 연결을 닫고, httpx도 쉬는 연결을
        # 기본 5초 남겨 두므로 두 시계가 겹칠 수 있다) 요청이 답 없이 끊겨 드물게 502가 된다. 그 길을 막는다.
        self._http = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_s, connect=min(10.0, timeout_s)),
            limits=httpx.Limits(max_keepalive_connections=0),
            transport=transport,
            trust_env=False,
            follow_redirects=False,
        )

    def close(self) -> None:
        """HTTP 연결을 닫는다. 닫은 뒤에는 summarize를 부르지 않는다."""
        self._http.close()

    def summarize(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """대화 하나를 후처리 서비스에 보내 상담 후처리 기록을 받는다(POST /summarize 한 번).

        입력: ChatService.transcript의 messages. 보내는 본문은
            {"domain": DOMAIN, "turns": summary_turns(messages)}이고, 다시 보내지 않는다.
        출력: {"record", "needs_confirmation", "model", "attempts", "request_id"} — 그쪽 200 답의 그
            칸들. record는 JSON 객체여야 하고, 다른 칸은 그쪽이 준 값 그대로이며 없으면 None이다.
        SummaryError: 보내지 못했거나 그쪽이 실패했거나 그 답을 쓸 수 없을 때(status는 파일 머리의
            '상태 코드').
        ValueError: 대화의 꼴이 틀렸거나(summary_turns) 글을 UTF-8로 쓸 수 없을 때(짝 없는
            서로게이트). 둘 다 보내기 전에 난다.
        """
        # httpx의 json= 과 같은 꼴(줄인 구분자, 한글은 UTF-8 그대로)로 직접 직렬화한다. 잰 바이트와 보내는
        # 바이트가 같아야 MAX_REQUEST_BYTES 검사가 그쪽 한도와 맞는다.
        body = json.dumps(
            {"domain": DOMAIN, "turns": summary_turns(messages)},
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise SummaryError(422, "the conversation is too long for the summary service")
        started = self._clock()
        try:
            with self._http.stream("POST", "/summarize", content=body, headers=_REQUEST_HEADERS) as response:
                return self._read_reply(response, started)
        except httpx.TimeoutException as exc:
            raise SummaryError(504, _TIMED_OUT) from exc
        except httpx.HTTPError as exc:
            # 그 밖의 httpx 오류(연결 실패, 이름 풀기 실패, 답 도중 끊김, HTTP 꼴이 틀린 답)는 모두 전송
            # 오류로 본다.
            raise SummaryError(502, _UNREACHABLE) from exc

    # 응답의 상태 코드를 표대로 옮기고, 200이면 본문을 흘려 받아 기록을 꺼낸다. 200이 아닌 답의 본문은
    # 읽지 않는다(그 글을 쓰지 않으므로). started는 요청을 시작한 때의 clock() 값이다.
    def _read_reply(self, response: httpx.Response, started: float) -> dict[str, Any]:
        status = response.status_code
        if status in (413, 422):
            raise SummaryError(422, f"the summary service rejected this conversation ({status})")
        if status == 503:
            raise SummaryError(429, "the summary service is busy, try again", _retry_after(response))
        if status != 200:
            raise SummaryError(502, f"the summary service answered {status}")
        if self._over_time(started):
            raise SummaryError(504, _TIMED_OUT)
        if _compressed(response) or _declared_size(response) > MAX_REPLY_BYTES:
            raise SummaryError(502, _UNEXPECTED)
        received = bytearray()
        for chunk in response.iter_bytes():
            if len(received) + len(chunk) > MAX_REPLY_BYTES:
                raise SummaryError(502, _UNEXPECTED)
            received += chunk
            if self._over_time(started):
                raise SummaryError(504, _TIMED_OUT)
        reply = _json_object(bytes(received))
        if reply is None or not isinstance(reply.get("record"), dict):
            raise SummaryError(502, _UNEXPECTED)
        return {key: reply.get(key) for key in _RETURNED}

    # 요청을 시작한 때부터 잰 시간이 timeout_s를 넘었는가(같으면 넘지 않았다).
    def _over_time(self, started: float) -> bool:
        return self._clock() - started > self._timeout_s


# 그쪽 503의 Retry-After를 이 서비스의 응답 머리에 쓸 값으로 바꾼다. ASCII 숫자만으로 된 1~3600의 정수
# 글이면 같은 수(앞의 0은 뗀다), 아니면(없음, 소수, 음수, 날짜 꼴, 다른 문자권의 숫자, 범위 밖) "30"이다.
# 길이를 먼저 보는 것은 아주 긴 숫자 글을 int()로 바꾸지 않으려는 것이다.
def _retry_after(response: httpx.Response) -> str:
    value = response.headers.get("retry-after", "").strip()
    if value.isascii() and value.isdigit() and len(value) <= 4 and 1 <= int(value) <= 3600:
        return str(int(value))
    return _RETRY_AFTER_FALLBACK


# 답에 identity가 아닌 Content-Encoding이 붙었는가(압축한 답). 쉼표로 이은 여러 값도 하나씩 본다.
def _compressed(response: httpx.Response) -> bool:
    codings = response.headers.get_list("content-encoding", split_commas=True)
    return any(coding.strip().lower() not in ("", "identity") for coding in codings)


# 답의 Content-Length가 적은 바이트 수. 없거나 ASCII 숫자가 아니면 0이다(본문을 받으면서 센다).
# 20자리가 넘는 수는 한도보다 큰 것으로 본다(아주 긴 숫자 글을 int()로 바꾸지 않는다).
def _declared_size(response: httpx.Response) -> int:
    value = response.headers.get("content-length", "").strip()
    if not (value.isascii() and value.isdigit()):
        return 0
    return int(value) if len(value) <= 20 else MAX_REPLY_BYTES + 1


# 받은 바이트를 JSON 객체로 읽는다. JSON이 아니거나(글로 풀 수 없는 바이트 포함) 객체가 아니면 None이다.
# 너무 깊게 겹친 JSON은 json이 ValueError가 아니라 RecursionError로 멈추므로 함께 받는다. 예외를 밖으로
# 올리지 않고 None을 돌려주는 까닭: 그 예외에는 받은 글 전체(JSONDecodeError.doc)가 딸려 있어, 이어서
# 올리는 SummaryError에 붙으면 그쪽 답의 글이 오류 기록으로 새어 나갈 수 있다.
def _json_object(data: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(data)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None
