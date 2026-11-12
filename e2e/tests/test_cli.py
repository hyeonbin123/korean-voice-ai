"""명령줄의 종료 코드·출력 파일·실패 안내·관리자 토큰 비노출을 확인한다."""

import json

import httpx
import pytest
from fakes import SCRIPT_PATH, SUMMARY_URL, SUPPORT_URL, TOKEN, FakeServices

from call_e2e.cli import main


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
