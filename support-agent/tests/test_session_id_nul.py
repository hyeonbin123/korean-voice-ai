"""경로의 세션 번호에 NUL(`%00`)이 든 요청은 데이터베이스에 묻지 않고 없는 세션(404)으로 끝난다."""

# [테스트 묶음] 세션 번호를 받는 모든 길(고객의 대화 조회·글 메시지·음성 메시지·답 읽어 주기, 관리자의 대화
# 조회)과 서비스 계층(`session_status`, `transcript`, `audit`, `handle`)이 NUL(0x00)이 든 번호를 '없는
# 세션'으로 돌려주는지 확인한다.
# [왜 중요한가] 요청 경로의 `%00`은 디코딩되어 NUL 문자로 처리기에 온다. PostgreSQL의 text 값에는 NUL을 넣을
# 수 없어서, PostgreSQL 드라이버(psycopg 3)는 그런 문자열을 쿼리 인자로 쓰려는 순간(서버로 보내기 전,
# 클라이언트 쪽에서) `DataError`를 낸다. 이 예외를 아무도 잡지 않아 로그인 전의 누구나 요청 하나로 500과
# 트레이스백을 낼 수 있었다. SQLite는 NUL이 든 인자를 받아 그냥 '없는 세션'(404)으로 끝나서, SQLite 위의
# 다른 시험과 보안 스캔 (모두 SQLite 오프라인 앱을 대상으로 했다)에는 잡히지 않았다. 서비스가 만드는 세션
# 번호는 `token_urlsafe`라 NUL이 들어 있을 수 없으므로, 그런 번호는 '없는 세션'이 맞다(기존 계약 그대로
# 404).
# [방법] PostgreSQL 서버 없이, SQLite 엔진에 쿼리를 보내기 직전 NUL이 든 문자열 인자를 보면 드라이버처럼
# `DataError`를 내는 이벤트 처리기를 단다(refuse_nul_like_postgresql). 처리기가 한 번이라도 걸리면 그 번호가
# 데이터베이스까지 간 것이다. 실제 PostgreSQL에서의 같은 확인은 tests/test_postgres.py에 있다.

from __future__ import annotations

import psycopg
import pytest
from sqlalchemy import event
from sqlalchemy.exc import DataError
from test_service import ADMIN, FakeListener, FakeSpeaker, local_client

from support_agent.chat import ScriptedProvider
from support_agent.service.app import create_app
from support_agent.service.core import ChatService, SessionNotFoundError
from support_agent.service.settings import Settings
from support_agent.service.voice_frontend import VoiceFrontEnd

# 요청 경로에 넣는 NUL의 자리: 맨 앞, 맨 뒤, 가운데. `%00`은 URL 인코딩이고 처리기에는 `\x00`으로 온다.
URL_IDS = ["%00abc", "abc%00", "ab%00cd"]
RAW_IDS = ["\x00", "\x00abc", "abc\x00", "ab\x00cd"]


# 값 안의 문자열을 모두 꺼낸다(바인드 인자는 튜플·목록·딕셔너리이고 executemany면 그 목록이다).
def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


# 엔진이 NUL이 든 문자열 인자를 받으면 PostgreSQL 드라이버(psycopg 3)처럼 DataError를 내게 한다(SQLite는
# 그런 인자도 받는다). 쿼리를 보내기 직전(before_cursor_execute)에 보므로, 어떤 코드 경로든 NUL이 든 번호가
# DB까지 가면 여기서 걸린다. 걸린 인자를 돌려주는 목록에 적어, 시험이 '드라이버까지 가지 않았다'를 확인할 수
# 있게 한다.
def refuse_nul_like_postgresql(engine) -> list[str]:
    reached: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def refuse(connection, cursor, statement, parameters, context, executemany):
        bad = [text for text in _strings(parameters) if "\x00" in text]
        if bad:
            reached.append(bad[0])
            raise DataError(
                statement,
                parameters,
                psycopg.DataError("PostgreSQL text fields cannot contain NUL (0x00) bytes"),
            )

    return reached


# 서비스 계층: NUL이 든 번호는 DB에 묻지 않고 SessionNotFoundError다(웹 계층이 404로 바꾼다). 세션을 읽는 세
# 메서드와, 한 턴을 처리하는 handle(세션 잠금을 잡은 뒤 같은 확인을 한다) 모두.
@pytest.mark.parametrize("method", ["session_status", "transcript", "audit"])
def test_the_service_treats_a_session_id_with_a_nul_as_unknown(blank_service_engine, method):
    reached = refuse_nul_like_postgresql(blank_service_engine)
    service = ChatService(Settings(), blank_service_engine, ScriptedProvider([]))
    for session_id in RAW_IDS:
        with pytest.raises(SessionNotFoundError):
            getattr(service, method)(session_id)
    assert reached == []  # NUL이 든 번호는 쿼리 인자가 되지 않았다


def test_a_turn_for_a_session_id_with_a_nul_is_refused_before_any_query(blank_service_engine):
    reached = refuse_nul_like_postgresql(blank_service_engine)
    service = ChatService(Settings(), blank_service_engine, ScriptedProvider(["네."]))
    events: list = []
    for session_id in RAW_IDS:
        with pytest.raises(SessionNotFoundError):
            service.handle(session_id, "안녕하세요", lambda *event: events.append(event))
    assert reached == [] and events == []  # 아무것도 읽거나 쓰지 않았고 이벤트도 나가지 않았다
    assert service._locks == {}  # 이 번호들의 세션 잠금도 남지 않았다


# 번호를 받는 모든 길. 음성 끝점과 답 읽어 주기는 음성 앞단이 있어야 503이 아닌 404까지 간다.
ROUTES = [
    ("GET", "/api/sessions/{id}", {}),
    ("POST", "/api/sessions/{id}/messages", {"json": {"text": "안녕하세요"}}),
    ("POST", "/api/sessions/{id}/voice", {"content": b"hello"}),
    ("POST", "/api/sessions/{id}/speech", {"json": {"text": "안녕하세요"}}),
    ("GET", "/api/admin/sessions/{id}", {}),
]


# 웹 계층: 어느 길로 NUL이 든 번호를 보내도 404와 고정 문장이다(500과 트레이스백이 아니다). raise_server_
# exceptions=False라서 처리되지 않은 예외가 다시 생기면 테스트가 터지는 대신 500으로 보인다. 관리자 토큰은
# 맞게 보내므로 관리자 경로도 인증이 아니라 세션 확인에서 끝난다.
@pytest.mark.parametrize("session_id", URL_IDS)
@pytest.mark.parametrize(("method", "path", "kwargs"), ROUTES)
def test_a_session_id_with_a_nul_is_404_on_every_route(
    blank_service_engine, method, path, kwargs, session_id
):
    reached = refuse_nul_like_postgresql(blank_service_engine)
    front_end = VoiceFrontEnd(FakeSpeaker(), FakeListener())
    app = create_app(
        Settings(admin_token="test-token"),
        provider=ScriptedProvider([]),
        engine=blank_service_engine,
        voice=front_end,
    )
    with local_client(app, raise_server_exceptions=False) as client:
        answer = client.request(method, path.format(id=session_id), headers=ADMIN, **kwargs)
    assert answer.status_code == 404, (answer.status_code, answer.text)
    assert answer.json() == {"detail": "no such session"}
    assert reached == []
