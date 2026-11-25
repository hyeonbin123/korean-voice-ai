"""명령줄의 종료 코드·출력 파일·실패 안내·관리자 토큰 비노출을 확인한다."""

import json

import httpx
import pytest
from fakes import SCRIPT_PATH, SUMMARY_URL, SUPPORT_URL, TOKEN, FakeServices

from call_e2e.cli import build_parser, main

# 서비스 연결 확인이 부르는 상담 서비스의 관리자 끝점(대역의 세션 번호는 s-1).
LINK_ROUTE = ("POST", "/api/admin/sessions/s-1/summary")


def arguments(tmp_path):
    """기본 포트 대신 대역 주소를 쓰고 출력은 pytest 임시 폴더 아래에 둔다."""
    return [
        "--script",
        str(SCRIPT_PATH),
        "--out",
        str(tmp_path / "report"),
        "--support-url",
        SUPPORT_URL,
        "--summary-url",
        SUMMARY_URL,
    ]


def link_arguments(tmp_path):
    """`arguments`에 서비스 연결 확인을 켜는 인자를 더한다."""
    return [*arguments(tmp_path), "--service-link"]


def read_json(tmp_path):
    return json.loads((tmp_path / "report" / "call-report.json").read_text(encoding="utf-8"))


def test_cli_returns_0_and_writes_both_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    assert main(arguments(tmp_path), transport=FakeServices().transport) == 0
    assert (tmp_path / "report" / "call-report.json").is_file()
    assert (tmp_path / "report" / "call-report.md").is_file()
    captured = capsys.readouterr()
    assert captured.out.splitlines()[-1] == "검사 5/5 통과"
    assert captured.err == ""


def test_cli_returns_1_when_a_check_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    fake.model = "different:model"
    assert main(arguments(tmp_path), transport=fake.transport) == 1
    assert capsys.readouterr().out.splitlines()[0] == "summary_model"
    assert (tmp_path / "report" / "call-report.json").is_file()


def test_cli_returns_2_without_admin_token(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("E2E_ADMIN_TOKEN", raising=False)
    fake = FakeServices()
    assert main(arguments(tmp_path), transport=fake.transport) == 2
    assert fake.requests == []
    assert "E2E_ADMIN_TOKEN" in capsys.readouterr().err
    assert not (tmp_path / "report").exists()


def test_cli_returns_2_when_services_are_not_ready(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices(health_status=503)
    assert main(arguments(tmp_path) + ["--wait", "0.2"], transport=fake.transport) == 2
    assert "준비 확인 실패" in capsys.readouterr().err
    assert all(r.method == "GET" and r.url.path in {"/healthz", "/health"} for r in fake.requests)
    assert not (tmp_path / "report").exists()


@pytest.mark.parametrize("token", [TOKEN, TOKEN + "\n", " " + TOKEN, TOKEN + "한글"])
def test_cli_never_prints_the_admin_token(tmp_path, monkeypatch, capsys, token):
    # 쓸 수 있는 토큰은 서버가 401 본문에 되돌려 적는 경우를, 쓸 수 없는 토큰(줄바꿈·공백·한글)은
    # 클라이언트를 만들다 거절되는 경우를 본다. 어느 쪽도 토큰이 출력에 남으면 안 된다.
    monkeypatch.setenv("E2E_ADMIN_TOKEN", token)
    fake = FakeServices()
    if token == TOKEN:
        fake.failures[("GET", "/api/admin/sessions/s-1")] = (401, "denied " + TOKEN)
    assert main(arguments(tmp_path), transport=fake.transport) == 2
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err
    assert not (tmp_path / "report").exists()


@pytest.mark.parametrize("token", ['test-admin-"token', "test-admin-\\token", "test-admin/token"])
def test_cli_hides_a_token_echoed_in_a_json_error_body(tmp_path, monkeypatch, capsys, token):
    # 서버가 JSON 오류 본문에 토큰을 되돌려 적는 경우다. JSON 안에서는 큰따옴표와 역슬래시 앞에
    # 역슬래시가 붙고 인코더에 따라 빗금 앞에도 붙으므로, 원래 글자만 가리면 토큰이 남는다.
    # 어느 꼴도 stderr에 남으면 안 된다.
    monkeypatch.setenv("E2E_ADMIN_TOKEN", token)
    fake = FakeServices()
    quoted = json.dumps(token)[1:-1]
    body = json.dumps({"detail": f"denied {token}"}) + " " + quoted.replace("/", "\\/")
    fake.failures[("GET", "/api/admin/sessions/s-1")] = (401, body)
    assert main(arguments(tmp_path), transport=fake.transport) == 2
    error = capsys.readouterr().err
    assert "session_detail" in error
    assert "401" in error
    assert "test-admin" not in error
    assert not (tmp_path / "report").exists()


def test_http_failure_reports_step_status_and_body(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    fake.failures[("POST", "/summarize")] = (503, "summary unavailable")
    assert main(arguments(tmp_path), transport=fake.transport) == 2
    error = capsys.readouterr().err
    assert all(word in error for word in ["summarize", "503", "summary unavailable"])
    assert not (tmp_path / "report").exists()


def test_cli_uses_short_separate_readiness_clients(tmp_path, monkeypatch):
    # httpx는 요청에 적용한 제한 시간을 request.extensions["timeout"]에 남긴다. 준비 확인 요청은 짧은
    # 제한(5초 이하)을, 발화 요청은 기본 60초를 써야 한다. 준비 확인에 긴 제한을 쓰면 말이 없는 서버
    # 앞에서 오래 멈춘다.
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    assert main(arguments(tmp_path), transport=fake.transport) == 0
    health = [r for r in fake.requests if r.url.path in {"/healthz", "/health"}]
    assert len(health) == 2
    assert all(r.extensions["timeout"]["read"] <= 5 for r in health)
    say = next(r for r in fake.requests if r.url.path.endswith("/messages"))
    assert say.extensions["timeout"]["read"] == 60


@pytest.mark.parametrize("wait", ["-1", "nan", "inf"])
def test_cli_rejects_invalid_wait(tmp_path, monkeypatch, wait):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    assert main(arguments(tmp_path) + ["--wait", wait], transport=fake.transport) == 2
    assert fake.requests == []


def test_cli_rejects_invalid_script(tmp_path, monkeypatch):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"format": "wrong"}), encoding="utf-8", newline="\n")
    args = arguments(tmp_path)
    args[1] = str(path)
    assert main(args, transport=FakeServices().transport) == 2


def test_cli_reports_malformed_summary_as_execution_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()

    def handler(request):
        response = fake._handle(request)
        if request.url.path == "/summarize":
            body = response.json()
            body["record"]["follow_up"] = None
            return httpx.Response(200, json=body)
        return response

    assert main(arguments(tmp_path), transport=httpx.MockTransport(handler)) == 2
    assert "summarize.record.follow_up" in capsys.readouterr().err
    assert not (tmp_path / "report").exists()


# ---------------------------------------------------------------- --service-link


def test_service_link_is_off_by_default_and_documented_in_the_help(capsys):
    required = ["--script", "script.json", "--out", "out"]
    assert build_parser().parse_args(required).service_link is False
    assert build_parser().parse_args([*required, "--service-link"]).service_link is True
    assert main(["--help"]) == 0
    # 도움말은 줄을 접어 보여 주므로 공백을 하나로 모아 읽는다.
    help_text = " ".join(capsys.readouterr().out.split())
    assert "--service-link" in help_text
    # 상담 앱을 후처리 앱의 주소로 띄워야 한다는 것, 오프라인 앱일 때만 뜻이 있다는 것이 도움말에 있다.
    assert "SUPPORT_AGENT_SUMMARY_URL" in help_text
    assert "오프라인" in help_text


def test_without_the_flag_the_output_and_the_requests_stay_as_they_were(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    assert main(arguments(tmp_path), transport=fake.transport) == 0
    lines = capsys.readouterr().out.splitlines()
    report_dir = tmp_path / "report"
    assert lines == [
        f"리포트: {report_dir / 'call-report.json'}",
        f"리포트: {report_dir / 'call-report.md'}",
        "검사 5/5 통과",
    ]
    assert not any(request.url.path.endswith("/summary") for request in fake.requests)
    assert "service_link" not in read_json(tmp_path)
    assert "서비스 연결 확인" not in (report_dir / "call-report.md").read_text(encoding="utf-8")


def test_service_link_match_returns_0_and_adds_one_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    assert main(link_arguments(tmp_path), transport=fake.transport) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines()[-2:] == ["검사 5/5 통과", "서비스 연결 확인: 일치"]
    assert captured.err == ""
    report = read_json(tmp_path)
    assert report["service_link"] == {"status": "matched", "audit_kind": "summary_created"}
    assert report["ok"] is True
    markdown = (tmp_path / "report" / "call-report.md").read_text(encoding="utf-8")
    assert "- 서비스 연결 확인: 일치" in markdown
    assert [(r.method, r.url.path) for r in fake.requests].count(LINK_ROUTE) == 1


def test_service_link_mismatch_returns_1_and_marks_the_report_not_ok(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    fake.linked_overrides = {"record": {**fake.canned_summary()["record"], "summary": "다른 요약입니다."}}
    assert main(link_arguments(tmp_path), transport=fake.transport) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines()[-2:] == ["검사 5/5 통과", "서비스 연결 확인: 어긋남"]
    assert captured.err == ""
    report = read_json(tmp_path)
    assert report["ok"] is False
    assert report["service_link"]["status"] == "mismatched"
    assert report["service_link"]["differs"] == ["record"]
    assert all(check["ok"] for check in report["checks"])
    markdown = (tmp_path / "report" / "call-report.md").read_text(encoding="utf-8")
    assert "- 서비스 연결 확인: 어긋남" in markdown


def test_service_link_disabled_support_app_returns_2_and_says_why(tmp_path, monkeypatch, capsys):
    # 후처리 연결이 꺼진 채 뜬 상담 앱은 501과 까닭을 준다. 오류 글만 보고 켜는 설정을 알 수 있어야 하고,
    # 실행하지 못한 것이므로 리포트는 쓰지 않는다.
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    detail = "the summary link is disabled (SUPPORT_AGENT_SUMMARY_URL is not set)"
    fake.failures[LINK_ROUTE] = (501, json.dumps({"detail": detail}))
    assert main(link_arguments(tmp_path), transport=fake.transport) == 2
    error = capsys.readouterr().err
    assert all(word in error for word in ["create_summary", "501", "SUPPORT_AGENT_SUMMARY_URL"])
    assert not (tmp_path / "report").exists()


@pytest.mark.parametrize("status", [401, 404, 409, 422, 429, 502, 504])
def test_service_link_http_failures_return_2(tmp_path, monkeypatch, capsys, status):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    fake.failures[LINK_ROUTE] = (status, "explained failure")
    assert main(link_arguments(tmp_path), transport=fake.transport) == 2
    error = capsys.readouterr().err
    assert all(word in error for word in ["create_summary", str(status), "explained failure"])
    assert not (tmp_path / "report").exists()


def test_service_link_never_prints_the_admin_token(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    fake.failures[LINK_ROUTE] = (401, "denied " + TOKEN)
    assert main(link_arguments(tmp_path), transport=fake.transport) == 2
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err
    assert not (tmp_path / "report").exists()


def test_service_link_reports_a_malformed_linked_answer_as_execution_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    fake.linked_overrides = {"record": "글"}
    assert main(link_arguments(tmp_path), transport=fake.transport) == 2
    assert "create_summary.summary.record" in capsys.readouterr().err
    assert not (tmp_path / "report").exists()


def test_service_link_request_uses_the_long_wait_and_the_other_requests_keep_theirs(tmp_path, monkeypatch):
    # 연결 확인 요청은 상담 서비스가 후처리 서비스를 기다리는 시간(기본 120초)보다 길게 기다리고, 발화 요청은
    # 기본 60초 그대로다.
    monkeypatch.setenv("E2E_ADMIN_TOKEN", TOKEN)
    fake = FakeServices()
    assert main(link_arguments(tmp_path), transport=fake.transport) == 0
    link = next(r for r in fake.requests if r.url.path.endswith("/summary"))
    say = next(r for r in fake.requests if r.url.path.endswith("/messages"))
    assert link.extensions["timeout"]["read"] > 120
    assert say.extensions["timeout"]["read"] == 60
