"""서비스는 Host 헤더가 허용 목록에 없는 요청을 400으로 거절한다(DNS 리바인딩 방어)."""

# [테스트 묶음] (1) 허용 목록의 기본값과 `ALLOWED_HOSTS` 설정(쉼표로 구분, 이름·IPv4만, 와일드카드·포트·주소
# 거절) (2) 목록 밖 Host의 요청은 화면·정적 파일·고객 API·관리자 API·API 설명 어디로 가든 400이고 아무것도
# 만들거나 바꾸지 않는다 (3) 거절 응답에도 보안 헤더가 붙는다 (4) 127.0.0.1·localhost는 포트가 있든 없든
# 그대로 된다 (5) 설정으로 더한 이름은 되고 나머지는 계속 400이다 (6) 모델 없는 오프라인 앱도 같다.
# [왜 중요한가] 이 서비스는 로그인 없는 고객 API와 공유 토큰 하나뿐인 관리자 API를 127.0.0.1에만 열어
# 쓰는데, 포트를 127.0.0.1에만 여는 것은 브라우저를 거치는 경로(DNS 리바인딩)를 막지 못한다. 공격자
# 페이지(예: http://attacker.example:8062)의 이름을 공격자의 DNS가 127.0.0.1로 다시 풀면, 그 페이지의
# fetch는 같은 출처 요청이라 CORS 사전 요청 없이 사용자 정의 헤더(X-Admin-Token)까지 붙여 이 포트에 닿는다.
# 그 요청은 서버에 `Host: attacker.example:8062`로 도착한다. 이 시험들이 지키는 것은 그 Host를 서비스가 받지
# 않는다는 점이다. 고치기 전에는 이 꼴의 요청으로 세션 만들기, 본인 확인, 큰 취소의 승인 대기, 관리자의 승인
# 목록·감사 로그 읽기, 승인 실행(compose의 기본 토큰이면)까지 모두 통과했다.
# [방법] 시험 클라이언트는 서비스가 듣는 주소(127.0.0.1:8062)로 부르고, 요청마다 Host(와 Origin) 헤더를 바꿔
# 보낸다. 서버는 띄우지 않는다. 모든 시험은 쇼핑몰 데이터 없이 마이그레이션만 한 DB를 쓴다(세션 번호와 요청
# 검사만 보므로).

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_service import ADMIN, FakeListener, FakeSpeaker, local_client

from support_agent.chat import ScriptedProvider
from support_agent.service import store
from support_agent.service.app import create_app
from support_agent.service.offline import create_offline_app
from support_agent.service.settings import Settings
from support_agent.service.voice_frontend import VoiceFrontEnd

# 리바인딩한 페이지의 fetch가 싣는 헤더 꼴: Host와 Origin이 모두 공격자의 이름이다.
FOREIGN = "attacker.example:8062"
REBOUND = {"Host": FOREIGN, "Origin": f"http://{FOREIGN}"}


# 모든 경로가 살아 있는 앱: 음성 앞단(대역)과 API 설명(/openapi.json)까지 켠다. 경로가 없거나 꺼져 있어서 나온
# 404·503이 아니라 Host 검사가 400을 낸 것임을 보이려는 것이다.
def app_with_every_route(engine, **overrides):
    settings = Settings(admin_token="test-token", expose_openapi=True, **overrides)
    front_end = VoiceFrontEnd(FakeSpeaker(), FakeListener())
    return create_app(settings, provider=ScriptedProvider(["네."]), engine=engine, voice=front_end)


# 서비스 테이블의 행 수. 거절된 요청이 세션·감사 행·승인 대기를 만들거나 바꾸지 않았는지 본다.
def row_counts(engine) -> dict[str, int]:
    tables = (store.ChatSession, store.AuditEvent, store.Approval)
    with Session(engine) as session:
        return {t.__tablename__: session.scalar(select(func.count()).select_from(t)) for t in tables}


# -------------------------------------------------------------------- 설정


# 기본 허용은 이 PC의 루프백 이름 둘이고, 설정이 없으면 목록은 그대로다. IPv6 표기(`[::1]`)는 넣지 않는다:
# 잠금의 Starlette는 Host에서 첫 `:` 앞만 읽어 그 표기가 목록과 같을 수 없다(settings.py).
def test_the_default_list_is_the_two_loopback_names():
    assert Settings().allowed_hosts == ()
    assert Settings().host_allow_list() == ("127.0.0.1", "localhost")
    assert Settings.from_env({}).host_allow_list() == ("127.0.0.1", "localhost")
    # Compose는 `ALLOWED_HOSTS`가 비어 있으면 빈 문자열을 넘기고, 빈 값은 '설정 안 함'이다.
    assert Settings.from_env({"SUPPORT_AGENT_ALLOWED_HOSTS": ""}).allowed_hosts == ()
    assert Settings(allowed_hosts="  ").allowed_hosts == ()


# 환경 변수의 값은 쉼표로 나눈다. 앞뒤 공백은 떼고 소문자로 맞추며(브라우저는 이름을 소문자로 싣는다) 같은
# 이름을 두 번 적어도 한 번이다. 더한 이름은 기본 이름 뒤에 붙고, 기본 이름을 다시 적어도 목록에는 한
# 번이다. 코드에서는 목록으로도 줄 수 있다.
def test_the_setting_adds_plain_names_after_the_defaults():
    env = {"SUPPORT_AGENT_ALLOWED_HOSTS": " Support.Example ,intranet,support.example,127.0.0.1, my_service "}
    settings = Settings.from_env(env)
    assert settings.allowed_hosts == ("support.example", "intranet", "127.0.0.1", "my_service")
    assert settings.host_allow_list() == (
        "127.0.0.1",
        "localhost",
        "support.example",
        "intranet",
        "my_service",
    )
    assert Settings(allowed_hosts=["a.example", "10.0.0.7"]).host_allow_list() == (
        "127.0.0.1",
        "localhost",
        "a.example",
        "10.0.0.7",
    )


# 이름이나 IPv4 주소로 읽히지 않는 값은 서비스가 시작할 때 거절한다. 와일드카드(`*`)는 검사를 통째로 끄거나
# 범위를 하염없이 넓히고(`*.com`), 포트·주소·경로·사용자 정보가 든 항목은 Host에서 포트를 뗀 이름과 같을 수
# 없어서 조용히 아무 요청도 통과시키지 못한다. 쉼표 사이가 빈 항목(오타)과 IPv6 주소(잠금의 Starlette가
# 맞추지 못함)도 거절한다. 이 값들이 그대로 떴다면 운영자는 방어가 켜졌다고 믿고 쓸 것이다.
@pytest.mark.parametrize(
    "value",
    [
        "*",
        "*.example.com",
        "support.example,*",
        "support.example:8062",
        "http://support.example",
        "support.example/path",
        "support.example?x=1",
        "user@support.example",
        "[::1]",
        "::1",
        "fe80::1",
        "support example",
        "support.example;intranet",
        "a.example,,b.example",
        "a.example,",
        ",",
        "  ,  ",
        "-a.example",
        "a-.example",
        "a..example",
        ".example",
        "example.",
        "localhost.",
        "a" * 64 + ".example",
        ".".join(["a"] * 130),
        "한글.example",
        "192.168.0",
        "1.2.3.4.5",
        "127.000.000.001",
        "256.0.0.1",
        "8062",
    ],
)
def test_a_value_that_cannot_name_a_host_is_refused_at_start(value):
    with pytest.raises(ValidationError):
        Settings.from_env({"SUPPORT_AGENT_ALLOWED_HOSTS": value})
    with pytest.raises(ValidationError):
        Settings(allowed_hosts=value)


# -------------------------------------------------------------------- 요청


# 이 PC의 이름(127.0.0.1, localhost)은 포트가 있든 없든 그대로 된다: 브라우저는 주소창의 호스트를 Host 헤더에
# 싣고, 서비스는 포트를 뗀 이름만 목록과 비교한다. Compose가 여는 8062, 컨테이너 안 HEALTHCHECK의 8000, 시연용
# 18062 같은 포트가 모두 같다.
@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "127.0.0.1:8062", "127.0.0.1:8000", "127.0.0.1:18062", "localhost", "localhost:8062"],
)
def test_the_loopback_names_are_served_with_or_without_a_port(blank_service_engine, host):
    with local_client(app_with_every_route(blank_service_engine)) as client:
        assert client.get("/healthz", headers={"Host": host}).status_code == 200
        assert client.post("/api/sessions", headers={"Host": host}).status_code == 201
        assert client.get("/api/admin/approvals", headers={"Host": host, **ADMIN}).status_code == 200


# 목록 밖의 Host는 모두 400이다. 공격자의 이름(포트 유무), 목록의 이름을 앞이나 뒤에 붙인 이름(접두·접미
# 일치나 하위 도메인 일치가 아니다), 사용자 정보로 위장한 값, 같은 PC의 다른 주소, 시험용 기본 이름, 빈
# Host, IPv6 표기. 경로·본문을 보기 전에 걸러 400이 곧 판정이다.
@pytest.mark.parametrize(
    "host",
    [
        "attacker.example",
        "attacker.example:8062",
        "127.0.0.1.attacker.example",
        "localhost.attacker.example:8062",
        "attacker-localhost",
        "127.0.0.1@attacker.example",
        "127.0.0.2:8062",
        "0.0.0.0:8062",
        "[::1]",
        "[::1]:8062",
        "testserver",
        "",
    ],
)
def test_a_host_outside_the_list_is_refused(blank_service_engine, host):
    with local_client(app_with_every_route(blank_service_engine)) as client:
        answer = client.get("/healthz", headers={"Host": host})
        assert (answer.status_code, answer.text) == (400, "Invalid host header")


# 리바인딩한 페이지의 요청(Host·Origin이 공격자의 이름, 관리자 토큰은 compose의 기본값처럼 알려진 값)은 어느
# 경로로 가든 400이고 서비스의 상태를 만들지도 바꾸지도 않는다: 세션·감사 행·승인 대기가 하나도 늘지 않는다.
# 화면(`/`, `/admin`)과 정적 파일(시험용 고객 이름·전화번호가 든 demo.json 포함), 없는 경로, API 설명도
# 포함이다. 경로가 없어서 나온 404·503이 아님을 보이도록 앱은 모든 경로를 켠다. 같은 앱이 루프백 Host로는
# 정상으로 답한다.
SURFACES = [
    ("GET", "/", {}),
    ("GET", "/admin", {}),
    ("GET", "/healthz", {}),
    ("GET", "/openapi.json", {}),
    ("GET", "/static/chat.js", {}),
    ("GET", "/static/demo.json", {}),
    ("GET", "/no/such/path", {}),
    ("POST", "/api/sessions", {}),
    ("GET", "/api/sessions/{id}", {}),
    ("POST", "/api/sessions/{id}/messages", {"json": {"text": "안녕하세요"}}),
    ("POST", "/api/sessions/{id}/voice", {"content": b"hello"}),
    ("POST", "/api/sessions/{id}/speech", {"json": {"text": "안녕하세요"}}),
    ("GET", "/api/admin/approvals?status=pending", {"headers": ADMIN}),
    ("POST", "/api/admin/approvals/1/decision", {"json": {"approve": True}, "headers": ADMIN}),
    ("GET", "/api/admin/sessions", {"headers": ADMIN}),
    ("GET", "/api/admin/sessions/{id}", {"headers": ADMIN}),
]


def test_a_foreign_host_gets_400_on_every_route_and_changes_nothing(blank_service_engine):
    with local_client(app_with_every_route(blank_service_engine)) as client:
        assert client.get("/healthz").status_code == 200  # 같은 앱이 루프백 Host로는 답한다
        assert client.get("/api/admin/approvals", headers=ADMIN).status_code == 200
        session_id = client.post("/api/sessions").json()["session_id"]  # 루프백으로 만든 진짜 세션
        before = row_counts(blank_service_engine)
        for method, path, kwargs in SURFACES:
            kwargs = dict(kwargs)
            headers = {**REBOUND, **kwargs.pop("headers", {})}
            answer = client.request(method, path.format(id=session_id), headers=headers, **kwargs)
            assert (answer.status_code, answer.text) == (400, "Invalid host header"), (method, path)
        assert row_counts(blank_service_engine) == before


# 거절 응답에도 다른 응답과 같은 보안 헤더가 붙는다(Host 검사를 보안 헤더 미들웨어 안쪽에 둔 까닭: app.py).
# /api/ 경로의 거절은 캐시도 막는다. 화면 경로(`/`)의 거절도 CSP와 프레임 금지를 단다.
def test_the_refusal_carries_the_security_headers(blank_service_engine):
    with local_client(app_with_every_route(blank_service_engine)) as client:
        for path in ("/", "/healthz", "/static/chat.js", "/api/sessions", "/api/admin/approvals"):
            answer = client.get(path, headers=REBOUND)
            assert answer.status_code == 400, path
            assert answer.headers["X-Content-Type-Options"] == "nosniff", path
            assert answer.headers["X-Frame-Options"] == "DENY", path
            assert answer.headers["Referrer-Policy"] == "no-referrer", path
            assert "default-src 'self'" in answer.headers["Content-Security-Policy"], path
            assert answer.headers["Cross-Origin-Opener-Policy"] == "same-origin", path
            if path.startswith("/api/"):
                assert answer.headers["Cache-Control"] == "no-store", path


# `ALLOWED_HOSTS`로 더한 이름(앞단 프록시의 이름 등)은 포트가 있든 없든 되고, 기본 이름도 그대로 되며,
# 나머지는 계속 400이다. 더한 이름에 이어 붙인 이름이나 그 이름을 접미로 가진 하위 이름은 되지 않는다.
def test_hosts_added_by_the_setting_are_served_and_the_rest_still_are_not(blank_service_engine):
    settings = Settings(admin_token="test-token", allowed_hosts="Support.Example, intranet")
    app = create_app(settings, provider=ScriptedProvider([]), engine=blank_service_engine)
    with local_client(app) as client:
        for host in (
            "support.example",
            "support.example:8062",
            "intranet:18062",
            "127.0.0.1:8062",
            "localhost",
        ):
            assert client.get("/healthz", headers={"Host": host}).status_code == 200, host
        for host in (
            "attacker.example",
            "sub.support.example",
            "support.example.attacker.example",
            "intranet.lan",
        ):
            assert client.get("/healthz", headers={"Host": host}).status_code == 400, host


# 모델 없는 오프라인 앱(보안 스캔과 e2e 시연이 쓰는 앱)도 같은 웹 계층이라 같은 검사를 받고, 같은 설정을
# 읽는다.
def test_the_offline_app_refuses_a_foreign_host_too(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_DATABASE_URL", f"sqlite:///{(tmp_path / 'offline.db').as_posix()}")
    monkeypatch.setenv("SUPPORT_AGENT_LOAD_SEED", "0")
    monkeypatch.setenv("SUPPORT_AGENT_ADMIN_TOKEN", "test-token")
    monkeypatch.setenv("SUPPORT_AGENT_ALLOWED_HOSTS", "stand-in.test")
    with local_client(create_offline_app()) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/healthz", headers={"Host": "stand-in.test:8062"}).status_code == 200
        assert client.get("/healthz", headers=REBOUND).status_code == 400
        assert client.post("/api/sessions", headers=REBOUND).status_code == 400
        assert client.get("/api/admin/approvals", headers={**REBOUND, **ADMIN}).status_code == 400
        assert client.get("/api/admin/approvals", headers=ADMIN).status_code == 200
