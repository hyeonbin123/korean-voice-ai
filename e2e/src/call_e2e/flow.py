"""대본의 고객 발화를 두 서비스로 보내고 고정된 다섯 검사에 필요한 결과를 모은다.

상담 서비스의 고객 이벤트와 관리자 감사 로그는 목적이 다르다. 턴의 도구 결과는 SSE에서, 실제 실행한 도구의
인자와 차례는 감사 로그에서 읽는다. 상담 전사는 관리자 조회 결과 그대로 후처리 서비스에 전달한다.

`run_call(..., service_link=True)`는 위 흐름이 끝난 뒤 선택 확인 하나를 더한다(서비스 연결 확인). 상담
서비스의 관리자 끝점을 불러 상담 서비스가 스스로 후처리 서비스를 불러 만든 기록을 받고, 그것이 시연이 직접
받은 기록과 같은지, 그 일이 감사 로그의 마지막 행으로 남았는지 본다. 다섯 검사에 여섯째로 더하지 않고 결과에
`service_link` 묶음으로 따로 담는다. 검사는 대본이 정한 기대와 견주는 것이고, 이 확인은 두 서비스가 서로를
부르는 길이 맞게 이어졌는지 보는 것이라 판정의 기준이 다르기 때문이다. 인자를 켜지 않으면 보내는 요청도
결과도 이전과 같다.
"""

from .clients import CallSummaryClient, SupportAgentClient
from .script import CallScript

# 서비스 연결 확인이 직접 받은 기록과 견주는 칸. 이 차례가 리포트에 적는 `differs`의 차례다.
LINK_FIELDS = ("record", "needs_confirmation", "model", "attempts")
# 상담 서비스가 후처리 기록을 만들면 감사 로그에 남기는 행의 종류(support-agent의
# `ChatService.create_summary`, src/support_agent/service/core.py). 연결이 맞게 이어졌다면 연결 확인이 끝난 뒤
# 감사 로그의 마지막 행이 이 종류여야 한다.
LINK_AUDIT_KIND = "summary_created"


def _object(value: object, label: str) -> dict:
    """HTTP 응답의 중첩 객체를 확인한다. 잘못된 응답을 KeyError 추적 대신 짧은 형식 오류로 알린다."""
    if not isinstance(value, dict):
        raise ValueError(f"{label}: JSON 객체가 필요하다")
    return value


def _list(value: object, label: str) -> list:
    """응답 목록을 확인한다. 누락된 필드를 빈 목록으로 간주하면 검사에 거짓 성공이 생길 수 있다."""
    if not isinstance(value, list):
        raise ValueError(f"{label}: JSON 목록이 필요하다")
    return value


def _text(value: object, label: str) -> str:
    """전사와 이벤트의 글 필드를 확인하며, 오류 글에는 응답 값 자체를 넣지 않는다."""
    if not isinstance(value, str):
        raise ValueError(f"{label}: 글이 필요하다")
    return value


def _tool_result(value: object) -> dict:
    """SSE 도구 결과에 있는 이름·성공 여부·오류 코드만 고정 순서로 남긴다."""
    tool = _object(value, "tool_result")
    name = _text(tool.get("name"), "tool_result.name")
    if not isinstance(tool.get("ok"), bool):
        raise ValueError("tool_result.ok: true 또는 false가 필요하다")
    error = tool.get("error_code")
    if error is not None:
        _text(error, "tool_result.error_code")
    return {"name": name, "ok": tool["ok"], "error_code": error}


def _approval(value: object) -> dict:
    """승인 알림의 공개 필드(승인 번호, 도구, 환불 금액)만 옮긴다.

    승인 번호(AP-1 같은 표기)는 고객 안내 문장에도 들어가는 값이라 리포트에 남긴다. 앱이 차례대로
    발급하는 번호이므로 두 실행의 리포트가 같으려면 앱의 처음 상태(DB)가 같아야 한다. 도구 결과가
    DB 상태에 따라 달라지는 것과 같은 조건이다.
    """
    approval = _object(value, "approval")
    if type(approval.get("refund_won")) is not int:
        raise ValueError("approval.refund_won: 정수 금액이 필요하다")
    return {
        "code": _text(approval.get("code"), "approval.code"),
        "tool": _text(approval.get("tool"), "approval.tool"),
        "refund_won": approval["refund_won"],
    }


def summary_turns(messages: list[dict]) -> list[dict]:
    """상담 전사의 customer·agent를 후처리 API의 고객·상담원으로 바꾼다.

    입력은 관리자 조회의 messages 목록이며 출력은 speaker·text만 가진 새 목록이다. 시스템·도구 메시지는
    고객에게 보인 전사에 없어야 하므로 알 수 없는 역할을 조용히 버리지 않고 ValueError로 알린다.
    """
    roles = {"customer": "고객", "agent": "상담원"}
    turns = []
    for message in _list(messages, "transcript.messages"):
        message = _object(message, "transcript.message")
        role = _text(message.get("role"), "transcript.role")
        if role not in roles:
            raise ValueError("transcript.role: customer 또는 agent만 허용한다")
        turns.append({"speaker": roles[role], "text": _text(message.get("text"), "transcript.text")})
    return turns


def tool_calls_from_audit(audit: list[dict]) -> list[dict]:
    """감사 로그의 tool_call 행만 골라 name·args·ok·error_code를 실행 순서대로 반환한다.

    payload.arguments는 모델이 보낸 원래 값이고 payload.args가 검증을 거친 실제 인자다(감사 행을
    만드는 곳은 support-agent의 `src/support_agent/service/core.py`). 그래서 args를 쓰고, 감사 행의
    id·at와 내부 처리 정보는 복사하지 않는다.
    """
    calls = []
    for row in _list(audit, "audit"):
        row = _object(row, "audit.row")
        if row.get("kind") != "tool_call":
            continue
        payload = _object(row.get("payload"), "audit.payload")
        tool = _tool_result(payload)
        # 인자 검증에 실패한 도구 호출은 args가 null이다(support-agent `src/support_agent/toolkit.py`의
        # ToolResult.args). 그런 행도 빼지 않고 실패한 호출로 남긴다.
        args = payload.get("args")
        if args is not None:
            _object(args, "audit.payload.args")
        calls.append({"name": tool["name"], "args": args, "ok": tool["ok"], "error_code": tool["error_code"]})
    return calls


def _summary_fields(response: dict, step: str) -> dict:
    """후처리 기록의 네 칸(model, attempts, record, needs_confirmation)을 검증하고 고정된 구조로 옮긴다.

    response는 후처리 서비스의 200 응답이거나, 상담 서비스가 그 서비스를 불러 받아 돌려준 201 응답의
    `summary`다. 두 응답은 같은 네 칸을 같은 꼴로 가진다. 그래서 직접 받은 기록과 상담 서비스를 거쳐 받은
    기록을 같은 함수로 같은 규칙에 따라 정리해야 둘을 견준 '같다'가 뜻이 있다(한쪽만 정리하면 정리 방식의
    차이가 기록의 차이로 보인다). 요청 id·지연 시간처럼 실행마다 달라지거나 리포트에 싣지 않는 칸은 옮기지
    않는다. step은 오류 글 앞에 붙는 이름(`summarize`, `create_summary.summary`)으로, 어느 응답이 계약을
    어겼는지 알게 한다. 계약을 어기면 단계 이름이 든 ValueError다.
    """
    record = _object(response.get("record"), f"{step}.record")
    follow_up = _object(record.get("follow_up"), f"{step}.record.follow_up")
    if not isinstance(follow_up.get("required"), bool):
        raise ValueError(f"{step}.record.follow_up.required: true 또는 false가 필요하다")
    if type(response.get("attempts")) is not int:
        raise ValueError(f"{step}.attempts: 정수가 필요하다")
    entities = []
    for entity in _list(record.get("entities"), f"{step}.record.entities"):
        entity = _object(entity, f"{step}.entity")
        entities.append(
            {
                "type": _text(entity.get("type"), f"{step}.entity.type"),
                "value": _text(entity.get("value"), f"{step}.entity.value"),
            }
        )
    flags = []
    for flag in _list(response.get("needs_confirmation"), f"{step}.needs_confirmation"):
        flag = _object(flag, f"{step}.flag")
        flags.append(
            {
                "type": _text(flag.get("type"), f"{step}.flag.type"),
                "value": _text(flag.get("value"), f"{step}.flag.value"),
                "reasons": [
                    _text(r, f"{step}.flag.reason")
                    for r in _list(flag.get("reasons"), f"{step}.flag.reasons")
                ],
            }
        )
    return {
        "model": _text(response.get("model"), f"{step}.model"),
        "attempts": response["attempts"],
        "record": {
            "category": _text(record.get("category"), f"{step}.record.category"),
            "resolution": _text(record.get("resolution"), f"{step}.record.resolution"),
            "entities": entities,
            "actions_taken": [
                _text(a, f"{step}.record.action")
                for a in _list(record.get("actions_taken"), f"{step}.record.actions_taken")
            ],
            "follow_up": {
                "required": follow_up["required"],
                "codes": [
                    _text(c, f"{step}.record.code")
                    for c in _list(follow_up.get("codes"), f"{step}.record.codes")
                ],
            },
            "summary": _text(record.get("summary"), f"{step}.record.summary"),
        },
        "needs_confirmation": flags,
    }


def _summary_result(response: dict, request: dict) -> dict:
    """후처리 응답의 공개 기록을 검증하고 요청 id·지연 시간 없이 고정된 구조로 옮긴다."""
    return {"request": request, **_summary_fields(response, "summarize")}


def last_audit_kind(audit: list[dict]) -> str | None:
    """감사 로그의 마지막 행의 종류(`kind`)를 돌려준다. 행이 하나도 없으면 None.

    감사 로그는 추가만 하고 기록한 차례대로 읽히므로(관리자 조회가 행 번호 순으로 준다) 마지막 행이 가장
    나중에 일어난 일이다. 목록이 아니거나, 마지막 행이 객체가 아니거나, 종류가 글이 아니면 ValueError다.
    """
    rows = _list(audit, "audit")
    if not rows:
        return None
    return _text(_object(rows[-1], "audit.row").get("kind"), "audit.kind")


def _service_link(support: SupportAgentClient, session_id: str, direct: dict) -> dict:
    """상담 서비스가 후처리 서비스를 직접 불러 만든 기록을 시연이 직접 받은 기록과 견준다.

    순서: 상담 서비스의 관리자 끝점을 불러 기록을 만들게 한다(`create_summary`) → 받은 기록을 직접 받은 것과
    같은 규칙으로 정리한다 → 세션을 다시 읽어 감사 로그의 마지막 행의 종류를 본다. direct는
    `_summary_result`가 정리한 직접 받은 기록이다.

    견주는 것은 `LINK_FIELDS`의 네 칸이다. 요청 id는 요청마다 새로 생기는 값이라 견주지 않는다. 네 칸이
    모두 같고 감사 로그의 마지막 행이 `LINK_AUDIT_KIND`일 때만 `matched`다. 어긋나면 `mismatched`에 다른
    칸의 이름을 `LINK_FIELDS` 차례로 `differs`에 적는다(네 칸이 같은데 감사 로그만 다르면 빈 목록). 세션
    번호·요청 번호·시각은 넣지 않는다. 같은 입력이면 같은 리포트여야 하기 때문이다.
    HTTP 실패는 StepError를 그대로 전달하고, 상담 서비스의 답이 계약을 어기면 ValueError다.
    """
    answer = support.create_summary(session_id)
    step = "create_summary.summary"
    linked = _summary_fields(_object(answer.get("summary"), step), step)
    audit_kind = last_audit_kind(support.session_detail(session_id)["audit"])
    differs = [name for name in LINK_FIELDS if linked[name] != direct[name]]
    if not differs and audit_kind == LINK_AUDIT_KIND:
        return {"status": "matched", "audit_kind": audit_kind}
    return {"status": "mismatched", "audit_kind": audit_kind, "differs": differs}


def run_call(
    script: CallScript,
    support: SupportAgentClient,
    summary: CallSummaryClient,
    *,
    service_link: bool = False,
) -> dict:
    """세션 생성 → 발화별 SSE → 관리자 전사·감사 조회 → 후처리 요청을 동기로 실행한다.

    턴 끝 상태가 open이 아니거나 end가 없으면 다음 발화를 보내지 않는다. 부분 통화도 조회·후처리해 검사
    실패 리포트로 남길 수 있다. HTTP 실패는 클라이언트의 StepError를 그대로 전달한다. 중첩 응답 계약을 어기면
    단계 이름이 든 ValueError로 알리고, 실행마다 달라지는 식별자와 시간은 결과에 넣지 않는다.

    service_link: True이면 후처리 요청까지 끝낸 뒤에 서비스 연결 확인을 더하고 결과에 `service_link` 묶음을
    담는다(`_service_link`). 앞 단계의 요청과 결과는 이 인자와 상관없이 같다. 기본은 False이고, 그러면 새
    끝점을 부르지 않으며 결과에도 `service_link`가 없다.
    """
    session_id = support.new_session()
    turns = []
    for customer in script.customer_turns:
        turn = {
            "customer": customer,
            "tools": [],
            "approvals": [],
            "replies": [],
            "errors": [],
            "end_status": None,
        }
        for name, data in support.say(session_id, customer):
            if name == "tool_result":
                turn["tools"].append(_tool_result(data))
            elif name == "approval":
                turn["approvals"].append(_approval(data))
            elif name == "reply":
                turn["replies"].append(_text(data.get("text"), "say.reply.text"))
            elif name == "error":
                turn["errors"].append(_text(data.get("message"), "say.error.message"))
            elif name == "end":
                status = _text(data.get("status"), "say.end.status")
                if status not in {"open", "handoff", "closed"}:
                    raise ValueError("say.end.status: 알 수 없는 세션 상태")
                turn["end_status"] = status
        turns.append(turn)
        if turn["end_status"] != "open":
            break
    detail = support.session_detail(session_id)
    transcript = _object(detail["transcript"], "session_detail.transcript")
    messages = _list(transcript.get("messages"), "session_detail.transcript.messages")
    request = {"domain": script.domain, "turns": summary_turns(messages)}
    support_result = {
        "turns": turns,
        "unsent_turns": len(script.customer_turns) - len(turns),
        "session_status": _text(transcript.get("status"), "session_detail.transcript.status"),
        "transcript": [{"role": m["role"], "text": m["text"]} for m in messages],
        "tool_calls": tool_calls_from_audit(detail["audit"]),
        "pending_approvals": [
            _approval(a)
            for a in _list(transcript.get("pending_approvals"), "session_detail.transcript.pending_approvals")
        ],
    }
    response = summary.summarize(script.domain, request["turns"])
    result = {"support_agent": support_result, "call_summary": _summary_result(response, request)}
    if service_link:
        result["service_link"] = _service_link(support, session_id, result["call_summary"])
    return result


def _calls_text(calls: tuple[tuple[str, bool], ...]) -> str:
    """도구 호출 차례를 리포트 글로 바꾼다: `이름(성공) → 이름(실패)` 꼴, 없으면 `없음`."""
    return " → ".join(f"{name}({'성공' if ok else '실패'})" for name, ok in calls) or "없음"


def check_expectations(script: CallScript, result: dict) -> list[dict]:
    """다섯 검사를 고정 순서로 반환한다. 기대 모델이 없으면 해당 검사는 통과와 생략 이유를 남긴다.

    HTTP 성공만으로 턴 성공을 판단하지 않는다. 전송하지 않은 발화, end 누락, error 이벤트를 모두 확인하며
    도구 검사는 감사 로그의 이름·성공 여부 순서 전체를 비교한다.
    """
    support = result["support_agent"]
    turns = support["turns"]
    total = len(script.customer_turns)
    without_end = sum(1 for t in turns if t["end_status"] is None)
    with_error = sum(1 for t in turns if t["errors"])
    completed = support["unsent_turns"] == 0 and len(turns) == total and not without_end and not with_error
    actual_tools = tuple((t["name"], t["ok"]) for t in support["tool_calls"])
    customers = [m["text"] for m in support["transcript"] if m["role"] == "customer"]
    same_customers = customers == list(script.customer_turns)
    model = result["call_summary"]["model"]
    expected_model = script.expect_summary_model
    comparisons = [
        (
            "turns_completed",
            completed,
            f"대본 발화 {total}개 가운데 {len(turns)}개를 보냄; end 없이 끝난 턴 {without_end}개, "
            f"error 이벤트가 있는 턴 {with_error}개",
        ),
        (
            "tool_calls",
            actual_tools == script.expect_tool_calls,
            f"기대: {_calls_text(script.expect_tool_calls)}; 실제: {_calls_text(actual_tools)}",
        ),
        (
            "session_status",
            support["session_status"] == script.expect_session_status,
            f"기대: {script.expect_session_status}; 실제: {support['session_status']}",
        ),
        (
            "transcript_matches_script",
            same_customers,
            f"전사의 고객 말 {len(customers)}개와 대본 발화 {total}개가 차례대로 "
            + ("같음" if same_customers else "같지 않음"),
        ),
        (
            "summary_model",
            expected_model is None or model == expected_model,
            "대본이 기대 모델을 정하지 않아 비교하지 않음"
            if expected_model is None
            else f"기대: {expected_model}; 실제: {model}",
        ),
    ]
    return [{"name": name, "ok": ok, "detail": detail} for name, ok, detail in comparisons]
