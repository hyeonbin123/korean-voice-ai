"""HTTP 요청 순서와 서비스 응답을 검사 가능한 통화 결과로 바꾸는 흐름을 확인한다."""

import json
from dataclasses import replace

import pytest
from fakes import GREETING, SUMMARY_URL, SUPPORT_URL, TOKEN, FakeServices, sample_script

from call_e2e.clients import CallSummaryClient, SupportAgentClient
from call_e2e.flow import (
    check_expectations,
    last_audit_kind,
    run_call,
    summary_turns,
    tool_calls_from_audit,
)

# 통화 한 건의 기본 요청 차례: 세션 열기, 발화 셋, 대화·감사 로그 읽기, 후처리 서비스 직접 부르기.
BASE_REQUESTS = [
    ("POST", "/api/sessions"),
    *[("POST", "/api/sessions/s-1/messages")] * 3,
    ("GET", "/api/admin/sessions/s-1"),
    ("POST", "/summarize"),
]
# 서비스 연결 확인이 그 뒤에 더하는 요청: 상담 서비스가 후처리 서비스를 부르게 하고, 감사 로그를 다시 읽는다.
LINK_REQUESTS = [("POST", "/api/admin/sessions/s-1/summary"), ("GET", "/api/admin/sessions/s-1")]


def run_fake(fake, *, service_link=False):
    """실제 클라이언트 둘을 대역에 연결해 실행하고, 실패해도 연결을 닫는다.

    service_link를 주지 않으면 서비스 연결 확인 인자 없이, 예전과 같은 꼴(`run_call(대본, 상담, 후처리)`)로
    부른다. 인자를 쓰지 않는 호출이 그대로 되는지도 이 도우미를 쓰는 모든 시험이 함께 보게 하려는 것이다.
    """
    support = SupportAgentClient(SUPPORT_URL, TOKEN, transport=fake.transport)
    summary = CallSummaryClient(SUMMARY_URL, transport=fake.transport)
    options = {"service_link": True} if service_link else {}
    try:
        return run_call(sample_script(), support, summary, **options)
    finally:
        support.close()
        summary.close()


def test_run_call_requests_in_order():
    fake = FakeServices()
    result = run_fake(fake)
    assert [(r.method, r.url.path) for r in fake.requests] == [
        ("POST", "/api/sessions"),
        *[("POST", "/api/sessions/s-1/messages")] * 3,
        ("GET", "/api/admin/sessions/s-1"),
        ("POST", "/summarize"),
    ]
    assert [json.loads(r.content)["text"] for r in fake.requests[1:4]] == list(sample_script().customer_turns)
    assert json.loads(fake.requests[-1].content) == {"domain": "shop", "turns": summary_turns(fake.messages)}
    assert result["call_summary"]["request"] == json.loads(fake.requests[-1].content)
    # 새 세션은 상담원 인사말 한 줄로 시작하고, 그 줄도 전사와 후처리 요청에 그대로 들어간다.
    assert result["support_agent"]["transcript"][0] == {"role": "agent", "text": GREETING}
    assert result["call_summary"]["request"]["turns"][0] == {"speaker": "상담원", "text": GREETING}
    assert result["support_agent"]["turns"][1]["tools"] == [
        {"name": "find_customer", "ok": True, "error_code": None}
    ]


def test_summary_turns_maps_roles():
    assert summary_turns([{"role": "customer", "text": "안녕"}, {"role": "agent", "text": "네"}]) == [
        {"speaker": "고객", "text": "안녕"},
        {"speaker": "상담원", "text": "네"},
    ]
    with pytest.raises(ValueError):
        summary_turns([{"role": "system", "text": "규칙"}])


def test_tool_calls_come_from_the_audit_log():
    fake = FakeServices()
    result = run_fake(fake)
    expected = [tool for tools in fake.tools for tool in tools]
    assert result["support_agent"]["tool_calls"] == expected
    assert tool_calls_from_audit(fake.audit) == expected


def test_turns_stop_when_the_session_is_not_open():
    result = run_fake(FakeServices(end_statuses=["open", "handoff", "open"]))
    assert len(result["support_agent"]["turns"]) == 2
    assert result["support_agent"]["unsent_turns"] == 1
    assert not check_expectations(sample_script(), result)[0]["ok"]


def test_check_expectations_names_and_results():
    result = run_fake(FakeServices())
    checks = check_expectations(sample_script(), result)
    assert [c["name"] for c in checks] == [
        "turns_completed",
        "tool_calls",
        "session_status",
        "transcript_matches_script",
        "summary_model",
    ]
    assert all(c["ok"] for c in checks)
    # 설명 글은 리포트 표에 그대로 실리므로 사람이 읽는 꼴을 고정한다.
    calls = "find_customer(성공) → cancel_order(성공)"
    assert checks[1]["detail"] == f"기대: {calls}; 실제: {calls}"
    changed = replace(sample_script(), expect_tool_calls=(("wrong_tool", True),))
    assert [c["name"] for c in check_expectations(changed, result) if not c["ok"]] == ["tool_calls"]
    assert check_expectations(replace(changed, expect_summary_model=None), result)[-1]["ok"]


@pytest.mark.parametrize("missing_end", [False, True])
def test_missing_end_or_error_fails_turn_completion(missing_end):
    # HTTP 200만으로는 턴이 끝났다고 볼 수 없다. end가 없거나 error 이벤트가 있으면 turns_completed가
    # 실패해야 하고, end가 없으면 다음 발화를 보내지 않는다.
    fake = FakeServices()
    if missing_end:
        fake.omit_end.add(0)
    else:
        fake.extra_events[0] = [("error", {"message": "처리 오류"})]
    result = run_fake(fake)
    assert not check_expectations(sample_script(), result)[0]["ok"]
    if missing_end:
        assert result["support_agent"]["unsent_turns"] == 2


def test_approval_and_error_events_are_recorded():
    fake = FakeServices()
    approval = {"code": "A-1", "tool": "cancel_order", "refund_won": 50000}
    fake.extra_events[0] = [("approval", approval), ("error", {"message": "처리 오류"})]
    fake.pending_approvals = [approval]
    result = run_fake(fake)["support_agent"]
    assert result["turns"][0]["approvals"] == [approval]
    assert result["turns"][0]["errors"] == ["처리 오류"]
    assert result["pending_approvals"] == [approval]


@pytest.mark.parametrize("name", ["session_status", "transcript_matches_script", "summary_model"])
def test_each_expectation_fails_independently(name):
    result = run_fake(FakeServices())
    if name == "session_status":
        result["support_agent"]["session_status"] = "closed"
    elif name == "transcript_matches_script":
        # 전사의 첫 줄은 상담원 인사말이므로, 첫 고객 말을 찾아 바꾼다.
        first_customer = next(m for m in result["support_agent"]["transcript"] if m["role"] == "customer")
        first_customer["text"] = "다른 고객 발화"
    else:
        result["call_summary"]["model"] = "different:model"
    assert [c["name"] for c in check_expectations(sample_script(), result) if not c["ok"]] == [name]


# ---------------------------------------------------------------- 서비스 연결 확인(service_link)


def different_values(fake):
    """연결 확인이 견주는 네 칸마다, 대역의 고정 기록과 다르면서 꼴은 맞는 값."""
    return {
        "record": {**fake.canned_summary()["record"], "summary": "다른 요약입니다."},
        "needs_confirmation": [],
        "model": "different:model",
        "attempts": 2,
    }


def test_service_link_matches_the_direct_summary():
    fake = FakeServices()
    result = run_fake(fake, service_link=True)
    # 앞 단계의 요청은 그대로이고, 연결 확인의 요청 둘이 그 끝에 붙는다.
    assert [(r.method, r.url.path) for r in fake.requests] == BASE_REQUESTS + LINK_REQUESTS
    link_request = fake.requests[len(BASE_REQUESTS)]
    assert json.loads(link_request.content) == {"by": "e2e"}
    assert link_request.headers["X-Admin-Token"] == TOKEN
    assert result["service_link"] == {"status": "matched", "audit_kind": "summary_created"}
    # 연결 확인은 검사를 하나 더하지 않는다: 검사는 여전히 다섯이고 모두 통과한다.
    assert len(check_expectations(sample_script(), result)) == 5
    assert all(c["ok"] for c in check_expectations(sample_script(), result))
    # 직접 받은 기록과 앞 단계의 결과는 인자가 없을 때와 같다.
    assert result["call_summary"] == run_fake(FakeServices())["call_summary"]


def test_without_the_flag_nothing_changes():
    fake = FakeServices()
    result = run_fake(fake)
    assert [(r.method, r.url.path) for r in fake.requests] == BASE_REQUESTS
    assert not any(r.url.path.endswith("/summary") for r in fake.requests)
    assert "service_link" not in result
    assert list(result) == ["support_agent", "call_summary"]
    # 인자를 명시적으로 끄는 것도 같다.
    explicit = FakeServices()
    support = SupportAgentClient(SUPPORT_URL, TOKEN, transport=explicit.transport)
    summary = CallSummaryClient(SUMMARY_URL, transport=explicit.transport)
    try:
        assert run_call(sample_script(), support, summary, service_link=False) == result
    finally:
        support.close()
        summary.close()
    assert [(r.method, r.url.path) for r in explicit.requests] == BASE_REQUESTS


@pytest.mark.parametrize("field", ["record", "needs_confirmation", "model", "attempts"])
def test_service_link_names_the_field_that_differs(field):
    fake = FakeServices()
    fake.linked_overrides = {field: different_values(fake)[field]}
    result = run_fake(fake, service_link=True)
    assert result["service_link"] == {
        "status": "mismatched",
        "audit_kind": "summary_created",
        "differs": [field],
    }


def test_service_link_lists_every_differing_field_in_a_fixed_order():
    fake = FakeServices()
    # 덮어쓰는 차례와 상관없이 리포트의 차례는 record, needs_confirmation, model, attempts로 고정이다.
    fake.linked_overrides = dict(reversed(different_values(fake).items()))
    result = run_fake(fake, service_link=True)
    assert result["service_link"]["differs"] == ["record", "needs_confirmation", "model", "attempts"]


@pytest.mark.parametrize("kind", ["summary_failed", "tool_call", None], ids=["failed", "other_row", "no_row"])
def test_service_link_with_equal_fields_still_needs_the_summary_created_row(kind):
    # 네 칸이 같아도 감사 로그의 마지막 행이 summary_created가 아니면(기록이 실패로 남았거나, 201인데 행이
    # 없거나) 연결은 맞게 이어진 것이 아니다. differs는 비어 있다.
    fake = FakeServices()
    fake.linked_audit_kind = kind
    result = run_fake(fake, service_link=True)["service_link"]
    last_kind = kind if kind is not None else "tool_call"  # 행이 없으면 마지막은 상담 중 도구 호출 행이다
    assert result == {"status": "mismatched", "audit_kind": last_kind, "differs": []}


def test_service_link_compares_both_sides_after_the_same_shaping():
    # 직접 받은 기록과 연결로 받은 기록은 같은 함수로 같은 꼴로 정리한 뒤 견준다. 리포트에 나오지 않는 칸이
    # 한쪽에만 더 있다고 다른 기록이 되지는 않는다.
    fake = FakeServices()
    fake.linked_overrides = {"record": {**fake.canned_summary()["record"], "internal": "not in the report"}}
    assert run_fake(fake, service_link=True)["service_link"]["status"] == "matched"


def test_service_link_runs_after_a_call_that_stopped_early():
    # 세션이 상담원에게 넘어가(handoff) 발화를 다 보내지 못한 부분 통화도, 그 대화에 대한 연결 확인은
    # 같은 방식으로 한다. 직접 받은 기록과 연결로 받은 기록이 같은 대화로 만들어지기 때문이다.
    fake = FakeServices(end_statuses=["open", "handoff", "open"])
    result = run_fake(fake, service_link=True)
    assert result["support_agent"]["unsent_turns"] == 1
    assert result["service_link"] == {"status": "matched", "audit_kind": "summary_created"}


@pytest.mark.parametrize(
    ("override", "label"),
    [
        ({"record": "글"}, "create_summary.summary.record"),
        ({"record": {"follow_up": None}}, "create_summary.summary.record.follow_up"),
        ({"needs_confirmation": None}, "create_summary.summary.needs_confirmation"),
        ({"model": 3}, "create_summary.summary.model"),
        ({"attempts": "1"}, "create_summary.summary.attempts"),
        ({"attempts": True}, "create_summary.summary.attempts"),
    ],
    ids=["record", "follow_up", "needs_confirmation", "model", "attempts", "attempts_bool"],
)
def test_service_link_rejects_a_linked_answer_that_breaks_the_contract(override, label):
    # 상담 서비스의 답이 계약을 어기면 어긋남이 아니라 실행 불가(ValueError)다. 오류 글에는 단계 이름
    # (create_summary)과 어느 칸인지가 들어 있다.
    fake = FakeServices()
    fake.linked_overrides = override
    with pytest.raises(ValueError, match=label) as info:
        run_fake(fake, service_link=True)
    assert "create_summary" in str(info.value)


def test_service_link_rejects_a_summary_that_is_not_an_object():
    fake = FakeServices()
    body = json.dumps({"session_id": "s-1", "summary": ["record"]})
    fake.failures[("POST", "/api/admin/sessions/s-1/summary")] = (201, body)
    with pytest.raises(ValueError, match=r"create_summary\.summary"):
        run_fake(fake, service_link=True)


def test_last_audit_kind_reads_the_kind_of_the_last_row():
    assert last_audit_kind([{"kind": "session_started"}, {"kind": "summary_created"}]) == "summary_created"
    assert last_audit_kind([]) is None
    for broken in ({"kind": "summary_created"}, [1], [{"kind": 7}], [{"payload": {}}]):
        with pytest.raises(ValueError):
            last_audit_kind(broken)
