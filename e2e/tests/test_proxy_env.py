"""프록시 환경 변수가 클라이언트의 로컬 연결을 가로채지 않는지 보는 시험.

httpx.Client는 기본으로 HTTP_PROXY·HTTPS_PROXY·ALL_PROXY·NO_PROXY 환경 변수를 읽는다(`trust_env=True`).
프록시 변수가 켜져 있는 PC에서는 127.0.0.1로 가는 요청도 프록시로 먼저 가므로, 로컬 앱이 떠 있어도
`ready()`가 늘 False가 되어 시연이 "앱이 안 떴다"로 잘못 보인다. 이 시연은 지정한 주소로만 직접 붙으므로
클라이언트는 환경을 읽지 않는다(`trust_env=False`).

다른 시험이 쓰는 httpx.MockTransport는 이 경로를 지나지 않는다(httpx는 transport를 직접 받으면 환경 프록시를
읽지 않는다). 그래서 여기서는 127.0.0.1의 임시 포트에 아주 작은 HTTP 서버 둘을 띄워 진짜 소켓으로 확인한다.
하나는 앱 대역(늘 200), 다른 하나는 프록시 대역(늘 502, 받은 요청을 기록)이다. 바깥 네트워크는 쓰지 않는다.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from call_e2e.clients import CallSummaryClient, SupportAgentClient

# 시험 안에서만 쓰는 가짜 관리자 토큰 (이 값을 고른 까닭은 test_clients.py의 TOKEN 주석에 있다).
ADMIN_TOKEN = "test-admin-token"

# 프록시 주소를 담는 환경 변수. 윈도우는 변수 이름의 대소문자를 구분하지 않지만 리눅스는 구분하므로
# 둘 다 정한다.
PROXY_VARIABLES = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")
NO_PROXY_VARIABLES = ("NO_PROXY", "no_proxy")


@pytest.fixture
def start_server():
    """127.0.0.1의 임시 포트에서 도는 작은 HTTP 서버를 띄우는 함수를 준다. 시험이 끝나면 모두 닫는다.

    `start_server(status)`는 (서버 주소, 받은 요청 경로 목록)을 돌려준다. 서버는 어떤 GET에도 `status`와 빈
    본문으로 답하고, 받은 요청 줄의 경로를 목록에 덧붙인다. 프록시를 거친 요청이면 경로가 전체 주소 꼴이다.
    """
    servers: list[ThreadingHTTPServer] = []

    def start(status: int) -> tuple[str, list[str]]:
        hits: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                hits.append(self.path)
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                pass  # 시험 출력에 요청 로그를 섞지 않는다

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        # 확인 간격을 줄이면 `shutdown()`이 기본(0.5초)만큼 기다리지 않고 바로 끝난다.
        poll = {"poll_interval": 0.05}
        threading.Thread(target=server.serve_forever, kwargs=poll, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}", hits

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def test_clients_ignore_proxy_environment_variables(monkeypatch, start_server):
    app_url, app_hits = start_server(200)
    proxy_url, proxy_hits = start_server(502)
    # 이 PC에 NO_PROXY가 이미 있으면 요청이 프록시 쪽으로 가지 않아 이 시험이 아무것도 보지 못한다.
    # 먼저 지운다.
    for name in NO_PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name in PROXY_VARIABLES:
        monkeypatch.setenv(name, proxy_url)

    support = SupportAgentClient(app_url, ADMIN_TOKEN)
    summary = CallSummaryClient(app_url)
    try:
        assert support.ready() is True
        assert summary.ready() is True
    finally:
        support.close()
        summary.close()

    assert proxy_hits == []  # 프록시 대역은 한 번도 불리지 않았다
    assert sorted(app_hits) == ["/health", "/healthz"]
