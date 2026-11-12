"""리포트의 고정 구조·결정성·Markdown 표시와 파일 저장 계약을 확인한다."""

from copy import deepcopy

from fakes import FakeServices, sample_script
from test_flow import run_fake

from call_e2e.flow import check_expectations
from call_e2e.report import WIRING_NOTICE, build_report, render_markdown, write_report


def sample_report():
    """가짜 통화를 한 번 처리해 실제 응답 모양의 리포트 입력을 만든다."""
    script = sample_script()
    result = run_fake(FakeServices())
    return build_report(script, "a" * 64, result, check_expectations(script, result))


def test_report_has_no_run_specific_values():
    report = sample_report()
    forbidden = {"session_id", "request_id", "latency_s", "at", "created_at", "updated_at", "id"}

    def visit(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(report)
    assert list(report) == [
        "report",
        "wiring_only",
        "notice",
        "script",
        "support_agent",
        "call_summary",
        "checks",
        "ok",
    ]
    assert list(report["support_agent"]) == [
        "turns",
        "unsent_turns",
        "session_status",
        "transcript",
        "tool_calls",
        "pending_approvals",
    ]
    assert list(report["call_summary"]) == ["request", "model", "attempts", "record", "needs_confirmation"]


def test_report_json_is_stable(tmp_path):
    # 세션 id, 요청 id, 걸린 시간, 감사 행의 id·시각만 다른 두 실행의 리포트가 바이트까지 같아야 한다.
    first = write_report(sample_report(), tmp_path / "first")
    fake = FakeServices(session_id="different-session")
    fake.request_id = "different-request"
    fake.latency_s = 12.3
    fake.audit[0].update(id=999, at="2030-01-01")
    script = sample_script()
    result = run_fake(fake)
    second = write_report(
        build_report(script, "a" * 64, result, check_expectations(script, result)), tmp_path / "second"
    )
    assert [p.read_bytes() for p in first] == [p.read_bytes() for p in second]


def test_markdown_has_notice_and_sections():
    text = render_markdown(sample_report())
    assert text.splitlines()[0].startswith("# 통화 한 건 리포트: ")
    assert text.splitlines()[2] == f"> {WIRING_NOTICE}"
    assert [line for line in text.splitlines() if line.startswith("## ")] == [
        "## 상담 (support-agent)",
        "## 상담 후처리 기록 (call-summary)",
        "## 확인이 필요한 번호",
        "## 검사",
    ]
    assert "O-90005" in text
    assert "not_in_transcript" in text


def test_markdown_has_no_plain_lines_that_would_merge():
    # Markdown은 빈 줄 없이 이어진 보통 줄을 한 문단으로 붙여 보여 준다. 그래서 리포트의 모든 줄은
    # 제목·인용·표·목록 가운데 하나로 시작해야 한다(줄마다 따로 보인다).
    text = render_markdown(sample_report())
    starts = ("# ", "## ", "> ", "| ", "- ")
    plain = [line for line in text.splitlines() if line and not line.startswith(starts)]
    assert plain == []


def test_table_cells_escape_pipes_and_newlines():
    report = deepcopy(sample_report())
    report["support_agent"]["turns"][0]["customer"] = "앞|뒤\r\n다음\r끝\n마침"
    report["checks"][0]["detail"] = "검사|설명\n계속"
    text = render_markdown(report)
    assert "앞\\|뒤 / 다음 / 끝 / 마침" in text
    assert "검사\\|설명 / 계속" in text


def test_write_report_uses_lf(tmp_path):
    for path in write_report(sample_report(), tmp_path):
        data = path.read_bytes()
        assert b"\r\n" not in data
        assert data.endswith(b"\n")
        assert not data.startswith(b"\xef\xbb\xbf")


def test_write_report_creates_output_directory(tmp_path):
    out = tmp_path / "missing" / "nested"
    paths = write_report(sample_report(), out)
    assert [p.name for p in paths] == ["call-report.json", "call-report.md"]
    assert all(p.is_file() for p in paths)
