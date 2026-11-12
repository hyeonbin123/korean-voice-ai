"""통화 대본(call-e2e-script/1)의 형식과 읽기.

통화 대본은 "고객이 이렇게 말하고, 이런 도구가 불리고, 통화가 이렇게 끝나야 한다"를 JSON 파일 하나에 적은
것이다. 시연은 대본의 고객 발화를 support-agent 오프라인 앱에 차례로 보내고, 대본의 `expect`는 그 결과와 맞춰
본다(맞춰 보는 일은 이 모듈이 하지 않는다). 이 모듈은 파일을 읽어 검사한 뒤 바꿀 수 없는 `CallScript`로
돌려주는 일만 한다.

파일 꼴(형식 이름 `call-e2e-script/1`):

    {
      "format": "call-e2e-script/1",
      "call_id": "shop-cancel",
      "title": "주문 하나를 취소하는 통화",
      "domain": "shop",
      "customer_turns": ["안녕하세요, 주문을 취소하려고요.", "..."],
      "expect": {
        "tool_calls": [["find_customer", true], ["cancel_order", true]],
        "session_status": "open",
        "summary_model": "offline:canned"
      }
    }

키는 모두 필수이고 위에 없는 키는 거절한다. 예외는 `expect.summary_model` 하나로, 없거나 null이면 그 확인을
하지 않는다는 뜻이다.

- call_id: 영소문자·숫자·하이픈 1~40자. 이 통화를 가리키는 이름.
- title: 리포트 제목에 쓰는 글. 비어 있지 않아야 한다.
- domain: call-summary에 넘기는 업종 키 (1~32자).
- customer_turns: 고객 발화 1~40개. 각각 앞뒤 공백을 뺀 길이가 1~1,000자.
- expect.tool_calls: 상담 에이전트가 부를 도구를 (이름, 성공 여부) 짝으로 부른 차례대로. 비워 둘 수 있다.
- expect.session_status: 통화가 끝났을 때의 세션 상태. open, handoff, closed 가운데 하나.
- expect.summary_model: call-summary 응답의 `model` 값.

한도는 시연이 부르는 서비스의 기본 설정에서 온 값이다. 대본이 한도를 넘으면 서버가 422나 409로 거절해서 시연이
대본 때문에 멈췄는지 배선 때문에 멈췄는지 알기 어려워지므로, 보내기 전에 여기서 먼저 걸러 낸다.

- 발화 40개: support-agent 설정 `max_turns_per_session`의 기본값
  (support-agent/src/support_agent/service/settings.py). 서버는 이만큼 턴을 처리하면 세션을 닫고,
  닫힌 세션에 온 다음 발화는 409로 거절한다.
- 발화 1,000자: 같은 설정 파일의 `max_message_chars` 기본값. 서버는 앞뒤 공백을 뺀 글의 길이로 검사한다
  (support-agent/src/support_agent/service/app.py의 `post_message`). 그래서 여기서도 같은 기준으로 세고,
  글 자체는 파일에 적힌 그대로 둔다.
- 업종 32자: call-summary의 요청 모델 `SummarizeRequest.domain`의 `max_length`
  (call-summary/src/call_summary/service.py). 업종 키가 허용 목록(shop, telecom, parcel, card)에 드는지는
  서비스가 정하고 모르는 업종에는 422로 답하므로 여기서는 따지지 않는다.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

# 대본 파일의 `format` 값. 형식이 바뀌면 이름 끝의 숫자를 올려, 옛 판의 파일을 새 판으로 잘못 읽지 않게 한다.
SCRIPT_FORMAT = "call-e2e-script/1"

# 고객 발화 개수와 길이, 업종 키 길이의 한도(위 모듈 설명의 근거 참고).
MAX_TURNS = 40
MAX_TURN_CHARS = 1000
MAX_DOMAIN_CHARS = 32

# 통화 번호(call_id)는 통화를 가리키는 짧은 이름이라 어디에 적어도 이스케이프가 필요 없는 영소문자·숫자·
# 하이픈만 받는다. 이 패턴은 `fullmatch`로 써야 한다: `match`는 앞부분만 맞으면 통과시키고 `$`를 붙여도
# 끝의 줄바꿈 하나는 통과한다.
CALL_ID_PATTERN = re.compile(r"[a-z0-9-]{1,40}")

# support-agent 세션의 상태 값(support-agent/src/support_agent/service/store.py의 SessionStatus)과 같다.
SESSION_STATUSES = ("open", "handoff", "closed")

_TOP_LEVEL_KEYS = ("format", "call_id", "title", "domain", "customer_turns", "expect")
_EXPECT_REQUIRED_KEYS = ("tool_calls", "session_status")
_EXPECT_OPTIONAL_KEYS = ("summary_model",)


class ScriptError(ValueError):
    """대본을 읽을 수 없거나 형식·한도를 어긴다.

    파일을 못 열거나 JSON·UTF-8이 아닌 경우도 같은 예외로 알려, 부르는 쪽이 "대본 문제"를 한 가지 예외로
    다룰 수 있게 한다. 메시지 앞에는 대본 파일 이름이, 안에는 틀린 항목의 이름이 들어 있다.
    """


@dataclass(frozen=True)
class CallScript:
    """검사를 통과한 통화 대본. 바꿀 수 없다(frozen).

    call_id: 이 통화를 가리키는 이름 (영소문자·숫자·하이픈 1~40자).
    title: 리포트 제목에 쓰는 글.
    domain: call-summary에 넘기는 업종 키.
    customer_turns: 고객 발화를 말한 차례대로. 파일에 적힌 글 그대로다(앞뒤 공백을 고치지 않는다).
    expect_tool_calls: 상담 에이전트가 부를 것으로 기대하는 도구를 (이름, 성공 여부) 짝으로 부른 차례대로.
    expect_session_status: 통화가 끝났을 때 기대하는 세션 상태 (open, handoff, closed).
    expect_summary_model: call-summary 응답의 `model`에 기대하는 값. None이면 확인하지 않는다.
    """

    call_id: str
    title: str
    domain: str
    customer_turns: tuple[str, ...]
    expect_tool_calls: tuple[tuple[str, bool], ...]
    expect_session_status: str
    expect_summary_model: str | None


def load_script(path: Path) -> CallScript:
    """대본 파일을 읽어 검사하고 `CallScript`로 돌려준다.

    입력: UTF-8(BOM 없음) JSON 파일의 경로. 출력: 검사를 통과한 `CallScript`.
    주의: 파일을 못 열거나 UTF-8·JSON이 아니거나 형식·한도를 어기면 모두 `ScriptError`다. 한 번에 첫 번째
    문제만 알린다. BOM이 붙은 파일은 JSON 읽기 단계에서 거절된다(저장소의 파일은 BOM이 없고, 해시를 바이트로
    잡기 때문에 BOM을 몰래 걷어 내지 않는다).
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ScriptError(f"{path.name}: 읽을 수 없다 ({type(exc).__name__}: {exc})") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScriptError(f"{path.name}: JSON이 아니다 ({exc})") from exc
    return _parse(raw, path.name)


def script_sha256(path: Path) -> str:
    """대본 파일 바이트의 SHA-256 (소문자 16진수 64자).

    리포트가 "어떤 대본으로 돌렸는지"를 남기는 데 쓴다. 글자가 아니라 파일 바이트를 해시하므로 줄바꿈이 바뀐
    파일(예: Windows 기본 설정으로 받아 CRLF가 된 복사본)은 다른 값이 된다.
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _show(value: object, limit: int = 60) -> str:
    """오류 글에 넣을 값 표시. 너무 긴 값이 메시지를 덮지 않게 자른다."""
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _check_keys(obj: dict, required: tuple[str, ...], optional: tuple[str, ...], label: str) -> None:
    """객체의 키가 필수 키를 모두 갖추고 그 밖의 키는 선택 키뿐인지 본다. 모르는 키를 먼저 알린다."""
    unknown = sorted(set(obj) - set(required) - set(optional))
    if unknown:
        raise ScriptError(f"{label}: 모르는 키 {unknown}")
    missing = [key for key in required if key not in obj]
    if missing:
        raise ScriptError(f"{label}: 빠진 키 {missing}")


def _parse(raw: object, name: str) -> CallScript:
    """JSON에서 읽은 값을 검사해 `CallScript`로 만든다. `name`은 오류 글 앞에 붙일 파일 이름이다."""
    if not isinstance(raw, dict):
        raise ScriptError(f"{name}: 최상위 값이 JSON 객체가 아니다")
    # 형식 이름부터 본다. 다른 판의 대본이면 키 구성이 달라서, 키부터 검사하면 '모르는 키'라는 엉뚱한 이유로
    # 거절되기 때문이다.
    if raw.get("format") != SCRIPT_FORMAT:
        found = _show(raw.get("format"))
        raise ScriptError(f"{name}: format이 {SCRIPT_FORMAT!r}이어야 한다 (읽은 값: {found})")
    _check_keys(raw, _TOP_LEVEL_KEYS, (), name)

    call_id = raw["call_id"]
    if not isinstance(call_id, str) or not CALL_ID_PATTERN.fullmatch(call_id):
        raise ScriptError(
            f"{name}: call_id는 영소문자·숫자·하이픈 1~40자여야 한다 (읽은 값: {_show(call_id)})"
        )

    title = raw["title"]
    if not isinstance(title, str) or not title.strip():
        raise ScriptError(f"{name}: title은 비어 있지 않은 글이어야 한다 (읽은 값: {_show(title)})")

    domain = raw["domain"]
    if not isinstance(domain, str) or not 1 <= len(domain) <= MAX_DOMAIN_CHARS:
        raise ScriptError(f"{name}: domain은 1~{MAX_DOMAIN_CHARS}자 글이어야 한다 (읽은 값: {_show(domain)})")

    turns = raw["customer_turns"]
    if not isinstance(turns, list) or not 1 <= len(turns) <= MAX_TURNS:
        raise ScriptError(f"{name}: customer_turns는 고객 발화 1~{MAX_TURNS}개의 목록이어야 한다")
    for number, turn in enumerate(turns, start=1):
        if not isinstance(turn, str) or not turn.strip():
            raise ScriptError(f"{name}: customer_turns의 {number}번째 발화가 비어 있거나 글이 아니다")
        if len(turn.strip()) > MAX_TURN_CHARS:
            raise ScriptError(f"{name}: customer_turns의 {number}번째 발화가 {MAX_TURN_CHARS}자를 넘는다")

    expect = raw["expect"]
    if not isinstance(expect, dict):
        raise ScriptError(f"{name}: expect가 JSON 객체가 아니다")
    _check_keys(expect, _EXPECT_REQUIRED_KEYS, _EXPECT_OPTIONAL_KEYS, f"{name}: expect")

    tool_calls = _parse_tool_calls(expect["tool_calls"], name)

    status = expect["session_status"]
    if not isinstance(status, str) or status not in SESSION_STATUSES:
        raise ScriptError(
            f"{name}: expect.session_status는 {'·'.join(SESSION_STATUSES)} 가운데 하나여야 한다 "
            f"(읽은 값: {_show(status)})"
        )

    summary_model = expect.get("summary_model")
    if summary_model is not None and (not isinstance(summary_model, str) or not summary_model):
        raise ScriptError(
            f"{name}: expect.summary_model은 비어 있지 않은 글이거나 null이어야 한다 "
            f"(읽은 값: {_show(summary_model)})"
        )

    return CallScript(
        call_id=call_id,
        title=title,
        domain=domain,
        customer_turns=tuple(turns),
        expect_tool_calls=tool_calls,
        expect_session_status=status,
        expect_summary_model=summary_model,
    )


def _parse_tool_calls(value: object, name: str) -> tuple[tuple[str, bool], ...]:
    """`expect.tool_calls`를 (도구 이름, 성공 여부) 짝의 튜플로 바꾼다.

    성공 여부는 JSON의 true/false만 받는다. 파이썬에서는 1이 True와 같지만, 대본에 숫자를 적은 것은 실수일
    가능성이 커서 거절한다.
    """
    if not isinstance(value, list):
        raise ScriptError(f"{name}: expect.tool_calls는 [도구 이름, 성공 여부] 짝의 목록이어야 한다")
    pairs = []
    for number, item in enumerate(value, start=1):
        valid = (
            isinstance(item, list)
            and len(item) == 2
            and isinstance(item[0], str)
            and bool(item[0])
            and isinstance(item[1], bool)
        )
        if not valid:
            raise ScriptError(
                f"{name}: expect.tool_calls의 {number}번째 항목이 [도구 이름, true 또는 false] 짝이 아니다 "
                f"(읽은 값: {_show(item)})"
            )
        pairs.append((item[0], item[1]))
    return tuple(pairs)
