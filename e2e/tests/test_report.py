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


def linked_report(fake=None):
    """같은 가짜 통화에 서비스 연결 확인(`--service-link`)을 더해 만든 리포트 입력."""
    script = sample_script()
    result = run_fake(fake or FakeServices(), service_link=True)
    return build_report(script, "a" * 64, result, check_expectations(script, result))


def assert_no_run_specific_keys(value):
    """실행마다 달라지는 값(세션·요청 번호, 걸린 시간, 감사 행의 번호·시각)의 키가 어느 깊이에도 없다."""
    forbidden = {"session_id", "request_id", "latency_s", "at", "created_at", "updated_at", "id"}
    if isinstance(value, dict):
        assert not forbidden.intersection(value)
        for item in value.values():
            assert_no_run_specific_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_run_specific_keys(item)


def test_report_has_no_run_specific_values():
    report = sample_report()
    assert_no_run_specific_keys(report)
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


# ---------------------------------------------------------------- 서비스 연결 확인(service_link)

SECTION_TITLES = [
    "## 상담 (support-agent)",
    "## 상담 후처리 기록 (call-summary)",
    "## 확인이 필요한 번호",
    "## 검사",
]


def link_line(report):
    """Markdown에서 서비스 연결 확인을 적은 줄. 하나뿐이어야 한다."""
    lines = [line for line in render_markdown(report).splitlines() if line.startswith("- 서비스 연결 확인: ")]
    assert len(lines) == 1
    return lines[0]


def test_linked_report_adds_one_bundle_between_the_summary_and_the_checks():
    report = linked_report()
    assert list(report) == [
        "report",
        "wiring_only",
        "notice",
        "script",
        "support_agent",
        "call_summary",
        "service_link",
        "checks",
        "ok",
    ]
    assert report["service_link"] == {"status": "matched", "audit_kind": "summary_created"}
    assert_no_run_specific_keys(report)
    # 검사는 늘 다섯 개이고, 연결 확인은 그 개수에 들지 않는다.
    assert len(report["checks"]) == 5
    assert report["ok"] is True


def test_linked_report_markdown_keeps_the_layout_rules():
    report = linked_report()
    lines = render_markdown(report).splitlines()
    assert [line for line in lines if line.startswith("## ")] == SECTION_TITLES
    starts = ("# ", "## ", "> ", "| ", "- ")
    assert [line for line in lines if line and not line.startswith(starts)] == []
    # 연결 확인 줄은 머리 목록의 `- 검사: N/N 통과` 줄 바로 다음이다. 그 줄의 수는 다섯 그대로다.
    checks_line = next(index for index, line in enumerate(lines) if line.startswith("- 검사: "))
    assert lines[checks_line] == "- 검사: 5/5 통과"
    assert lines[checks_line + 1] == link_line(report)
    assert lines[checks_line + 1].startswith("- 서비스 연결 확인: 일치")
    assert "summary_created" in lines[checks_line + 1]


def test_linked_report_json_is_stable(tmp_path):
    # 서비스 연결 확인이 있어도, 세션 id·요청 id·걸린 시간·감사 행의 id와 시각만 다른 두 실행의 리포트가
    # 바이트까지 같아야 한다. 감사 로그의 마지막 행은 종류만 리포트에 들어간다.
    first = write_report(linked_report(), tmp_path / "first")
    fake = FakeServices(session_id="different-session")
    fake.request_id = "different-request"
    fake.latency_s = 12.3
    fake.audit[0].update(id=999, at="2030-01-01")
    second = write_report(linked_report(fake), tmp_path / "second")
    assert [p.read_bytes() for p in first] == [p.read_bytes() for p in second]


def test_report_without_the_flag_is_the_linked_report_minus_the_bundle():
    # 인자를 주지 않은 리포트는 인자를 준 리포트에서 묶음(JSON 키 하나, Markdown 줄 하나)만 뺀 것과 같다.
    plain, linked = sample_report(), linked_report()
    without_bundle = {key: value for key, value in linked.items() if key != "service_link"}
    assert plain == without_bundle
    assert list(plain) == list(without_bundle)
    plain_lines = render_markdown(plain).split("\n")
    linked_lines = render_markdown(linked).split("\n")
    assert len(linked_lines) == len(plain_lines) + 1
    linked_lines.remove(link_line(linked))
    assert linked_lines == plain_lines
    # 인자가 없을 때의 Markdown에는 연결 확인 줄이 없다.
    assert "서비스 연결 확인" not in "\n".join(plain_lines)


def test_mismatched_link_fails_the_report_without_failing_a_check():
    fake = FakeServices()
    fake.linked_overrides = {"model": "different:model", "attempts": 2}
    report = linked_report(fake)
    assert report["service_link"] == {
        "status": "mismatched",
        "audit_kind": "summary_created",
        "differs": ["model", "attempts"],
    }
    # 검사 다섯은 모두 통과인데, 연결이 어긋나면 리포트 전체는 실패다.
    assert all(check["ok"] for check in report["checks"])
    assert report["ok"] is False
    line = link_line(report)
    assert line.startswith("- 서비스 연결 확인: 어긋남")
    assert "다른 칸: model, attempts" in line
    assert "감사 로그의 마지막 종류: summary_created" in line
    # 검사 줄은 그대로 5/5이다.
    assert "- 검사: 5/5 통과" in render_markdown(report)


def test_mismatched_link_markdown_names_a_missing_kind_and_escapes_the_kind():
    report = deepcopy(linked_report())
    report["service_link"] = {"status": "mismatched", "audit_kind": None, "differs": []}
    assert link_line(report) == "- 서비스 연결 확인: 어긋남 — 다른 칸: 없음; 감사 로그의 마지막 종류: 없음"
    # 서버가 준 종류에 줄바꿈이나 파이프가 있어도 한 줄을 깨지 않는다.
    report["service_link"] = {"status": "mismatched", "audit_kind": "앞|뒤\n다음", "differs": []}
    assert "감사 로그의 마지막 종류: 앞\\|뒤 / 다음" in link_line(report)
