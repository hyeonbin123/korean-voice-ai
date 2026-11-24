# [파일 역할] 로그인 없이도 부를 수 있는 HTTP 경로가 큰 요청 하나로 API 서버의 이벤트 루프를 오래 붙잡지
# 않는지 확인한다: (1) 검증 실패(422) 응답이 보낸 값을 되돌려 주지 않고 위치(loc)·문구(msg)·종류(type)만
# 담는지, (2) 음성 업로드 두 경로 밖의 요청 본문은 64KiB를 넘는 순간 읽기를 멈추고 413으로 답하는지, (3)
# 음성 업로드 두 경로는 이 한도 대신 자기 파서의 10MB 한도를 따르는지.
# [왜 중요한가] FastAPI 기본 422 처리기는 오류 항목마다 보낸 값(input)을 담아 jsonable_encoder로 원소마다
# 다시 만들고 같은 크기로 돌려줘, 가입·토큰 갱신에 보낸 11MB JSON 목록 하나가 이벤트 루프를 수 초 멈췄다.
# 그동안 모든 HTTP 요청과 동시통역 자막이 함께 멈춘다(docs/security.md 2026-11-24 덧붙임, 규칙은 docs/api.md
# 오류 응답).
# [연결] app/main.py의 validation_error_without_input(422 처리기)과 RequestBodyLimit(본문 한도 미들웨어).
# 배포의 nginx 한도(frontend/nginx.conf: server 64k, 업로드 두 경로만 11m)는
# frontend/src/test/nginx.test.ts가 본다.

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import MAX_REQUEST_BODY_BYTES, UPLOAD_PATHS, app
from tests.fakes import silent_wav

# 원소 30,000개짜리 JSON 목록(60,001바이트). 본문 한도(64KiB) 안이라 검증까지 가서 422가 된다.
LIST_BODY = ("[" + ",".join(["0"] * 30_000) + "]").encode()


# 검증 실패의 본문: 목록·너무 긴 문자열·깨진 JSON 모두 오류 항목마다 loc·msg·type만 있고, 보낸 값(input)과
# 부가 정보(ctx)는 없다. 그래서 60KB를 보내도 응답은 수백 바이트이고 보낸 글자가 응답에 나오지 않는다. 글자
# 번역 경로는 로그인이 필요해 auth_headers를 붙인다(다른 경로에는 쓰이지 않는 머리글이다).
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/auth/refresh", LIST_BODY),
        ("/api/auth/register", LIST_BODY),
        ("/api/translate/text", LIST_BODY),
        ("/api/auth/refresh", b'{"refresh_token": "' + b"x" * 5_000 + b'"}'),
        ("/api/auth/refresh", b'{"refresh_token": '),
    ],
    ids=["refresh-list", "register-list", "text-list", "refresh-too-long", "refresh-broken-json"],
)
async def test_a_validation_error_names_the_place_and_reason_but_not_the_input(
    client, auth_headers, path, body
):
    response = await client.post(
        path, content=body, headers={**auth_headers, "content-type": "application/json"}
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail and all(set(item) == {"loc", "msg", "type"} for item in detail)
    assert detail[0]["loc"][0] == "body"
    assert len(response.content) < 1_000
    assert b"xxxxxxxxxx" not in response.content


# 본문 한도의 경계: 한도와 같은 크기(유효한 JSON 뒤를 공백으로 채움)는 평소처럼 처리되고(틀린 토큰이라 401),
# 1바이트 넘으면 본문을 풀기 전에 413이다.
@pytest.mark.parametrize("extra", [0, 1])
async def test_the_body_limit_takes_its_size_and_refuses_one_byte_more(client, extra):
    body = b'{"refresh_token": "not a token"}'
    body += b" " * (MAX_REQUEST_BODY_BYTES + extra - len(body))
    response = await client.post(
        "/api/auth/refresh", content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == (413 if extra else 401), response.text
    if extra:
        assert response.json() == {"detail": "Request body is too large"}


# 본문을 읽는 다른 경로(가입 JSON, 로그인 폼, 글자 번역 JSON)도 같은 한도다. 로그인은 폼이라 폼 형식으로
# 보낸다 (JSON으로 보내면 폼 읽기가 본문을 읽지 않아 한도와 상관없이 422가 된다).
@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/api/auth/register", "application/json"),
        ("/api/auth/login", "application/x-www-form-urlencoded"),
        ("/api/translate/text", "application/json"),
    ],
)
async def test_every_path_that_reads_a_body_has_the_limit(client, auth_headers, path, content_type):
    response = await client.post(
        path,
        content=b"a" * (MAX_REQUEST_BODY_BYTES + 1),
        headers={**auth_headers, "content-type": content_type},
    )
    assert response.status_code == 413


# Content-Length 없이 조각으로 오는(chunked) 본문도 받은 만큼 세어, 한도를 넘는 조각에서 읽기를 멈춘다: 16KiB
# 조각 64개(1MiB)를 보내도 다섯 번째 조각(80KiB)에서 413이고 나머지 조각은 읽지 않는다.
async def test_a_chunked_body_stops_being_read_at_the_limit(client):
    sent = 0

    async def body():
        nonlocal sent
        for _ in range(64):
            sent += 1
            yield b" " * 16_384

    response = await client.post(
        "/api/auth/refresh", content=body(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert sent == MAX_REQUEST_BODY_BYTES // 16_384 + 1


# 음성 업로드 두 경로만 이 한도를 받지 않는다. 그 경로의 multipart 파서가 파일 바이트를 따로 세어 10MB에서
# 끊는다(routers/translate.py, tests/test_translate_api.py의 한도 시험). nginx도 같은 두 경로에만 11m를 준다.
def test_only_the_two_audio_upload_paths_skip_the_body_limit():
    assert UPLOAD_PATHS == {"/api/translate/speech", "/api/translate/dialog"}


# 64KiB보다 큰 음성 업로드가 본문 한도에 걸리지 않고 그 뒤의 인증 확인까지 가는지 본다(로그인 없이 보내 401).
@pytest.mark.parametrize("path", sorted(UPLOAD_PATHS))
async def test_the_upload_paths_take_bodies_over_the_limit(client, path):
    audio = silent_wav(3_000)  # 96,044바이트
    assert len(audio) > MAX_REQUEST_BODY_BYTES
    response = await client.post(path, files={"audio": ("clip.wav", audio, "audio/wav")})
    assert response.status_code == 401


# 앱을 주소 접두 아래에 올린 배포(예: uvicorn --root-path /vt)에서는 요청 경로에 접두가 붙어
# 온다("/vt/api/translate/speech"). 본문 한도는 라우터와 같은 규칙으로 접두를 떼고 경로를 보므로, 접두가
# 있어도 업로드 두 경로는 한도를 받지 않고(96KB 음성이 인증 확인까지 가서 401) 다른 경로는 그대로
# 받는다(413). 접두를 떼지 않고 견주면 업로드 경로를 못 알아봐 64KiB가 넘는 음성이 모두 413으로 막힌다.
# client 픽스처는 앱의 DB 의존성을 테스트 DB로 바꿔 끼우려고 받고, 요청은 접두(root_path)를 단 별도
# 클라이언트로 보낸다.
async def test_a_path_prefix_does_not_change_which_paths_have_the_limit(client):
    audio = silent_wav(3_000)  # 96,044바이트
    transport = ASGITransport(app=app, root_path="/vt")
    async with AsyncClient(transport=transport, base_url="http://test") as prefixed:
        for path in sorted(UPLOAD_PATHS):
            upload = await prefixed.post("/vt" + path, files={"audio": ("clip.wav", audio, "audio/wav")})
            assert upload.status_code == 401, (path, upload.text)
        refused = await prefixed.post(
            "/vt/api/auth/refresh",
            content=b" " * (MAX_REQUEST_BODY_BYTES + 1),
            headers={"content-type": "application/json"},
        )
        assert refused.status_code == 413
