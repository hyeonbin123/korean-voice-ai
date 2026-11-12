"""HTTP 요청 순서와 서비스 응답을 검사 가능한 통화 결과로 바꾸는 흐름을 확인한다."""

import json
from dataclasses import replace

import pytest
from fakes import SUMMARY_URL, SUPPORT_URL, TOKEN, FakeServices, sample_script

from call_e2e.clients import CallSummaryClient, SupportAgentClient
from call_e2e.flow import check_expectations, run_call, summary_turns, tool_calls_from_audit


def run_fake(fake):
    """실제 클라이언트 둘을 대역에 연결해 실행하고, 실패해도 연결을 닫는다."""
    support = SupportAgentClient(SUPPORT_URL, TOKEN, transport=fake.transport)
    summary = CallSummaryClient(SUMMARY_URL, transport=fake.transport)
    try:
        return run_call(sample_script(), support, summary)
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
        result["support_agent"]["transcript"][0]["text"] = "다른 고객 발화"
    else:
        result["call_summary"]["model"] = "different:model"
    assert [c["name"] for c in check_expectations(sample_script(), result) if not c["ok"]] == [name]
