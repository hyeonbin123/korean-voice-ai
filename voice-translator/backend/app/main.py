# [파일 역할] FastAPI 앱의 진입점이다(`uvicorn app.main:app`). 로그 설정, 앱 수명 주기(lifespan: 모델
# 적재·예열·정리), 라우터 등록, 요청 크기 상한(검증 오류 응답의 모양, 요청 본문 한도)을 맡는다.
# [설계 이유] (1) 로그에 사용자 글·번역문이 새지 않게 예외 메시지를 지우는 로그 필터를 앱 로거와 uvicorn 오류
# 로거에 붙인다. (2) 모델 적재는 수십 초 걸리므로 이벤트 루프 밖 스레드에서 하고, 끝난 뒤에만 요청을 받는다.
# (3) 모델을 올린 직후 gc.freeze()로 번역 중 다른 요청이 막히던 문제를 없앤다(docs/experiments.md 5절).
# (4) 로그인 없이 부르는 JSON 경로에 보낸 큰 본문 하나가 이벤트 루프를 수 초 멈추지 않게, 검증 오류(422)는
# 보낸 값을 되돌려 주지 않고 업로드 밖 요청 본문은 64KiB에서 끊는다(docs/security.md 2026-11-24 덧붙임).
# [흐름] 로그 필터·핸들러 설정 → lifespan(LOAD_MODELS면 load_models → warm_up → gc.freeze, 종료 때 오타 교정
# 준비 스레드 정리) → 라우터를 /api 아래에 등록 → 422 처리기와 본문 한도 미들웨어 등록.

import asyncio
import gc
import logging
from contextlib import asynccontextmanager

# fastapi: 앱·HTTP 오류와 검증 오류(RequestValidationError)·JSON 응답. starlette: 요청 머리글 읽기
# (Content-Length)와 ASGI 미들웨어의 타입. 프로젝트 내부: 설정, 각 API 라우터, 예외를 메시지 없이 요약하는
# describe, 모델 적재·예열 함수.
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.routers import audio, auth, health, history, live, translate
from app.services.errors import describe
from app.services.models import load_models, warm_up

logger = logging.getLogger(__name__)


class WithoutExceptionMessages(logging.Filter):
    """예외를 종류의 사슬과 위치로만 기록하고 메시지나 traceback은 남기지 않는 로그 필터.

    로그 레코드에 예외 정보가 붙어 있으면 그 예외를 describe() 요약(예외 종류의 사슬과 위치)으로 바꾸고
    traceback·메시지를 지운다. 라이브러리 예외 메시지에는 사용자가 입력한 글이나 번역문이 그대로 들어갈 수
    있기 때문이다. 앱 자체 로그는 이미 describe()를 쓰고, 이 필터는 나머지를 잡는다: uvicorn이 "Exception
    in ASGI application"으로 남기는 예상하지 못한 오류(Starlette는 늘 다시 raise함)와, exc_info를 붙여
    남긴 앱 로그 레코드다. tests/test_log_privacy.py가 확인한다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # getMessage()로 원래 로그 문장(인자 채운 것)만 남기고 뒤에 요약을 붙인다. args를 None으로 해 포매터가
        # 다시 % 치환을 하지 않게 하고, exc_info·exc_text를 지워 핸들러가 traceback을 찍지 않게 한다. 레코드는
        # 버리지 않는다(return True).
        if record.exc_info and record.exc_info[1] is not None:
            record.msg = f"{record.getMessage()}: {describe(record.exc_info[1])}"
            record.args = None
            record.exc_info = None
            record.exc_text = None
        return True


# 모듈을 불러올 때 로그 설정을 한 번 한다. 테스트처럼 같은 모듈을 여러 번 불러도 핸들러·필터가 중복으로 붙지
# 않게 '이미 있으면 건너뛰기'로 짰다.
_without_messages = WithoutExceptionMessages()
# uvicorn은 자기 로거만 설정하므로, 핸들러를 따로 붙이지 않으면 앱의 INFO 줄(모델 적재·예열 시간)이
# 버려졌다. 전파(propagate)는 켠 채로 두어 pytest의 caplog도 계속 이 줄을 받는다.
_app_logger = logging.getLogger("app")
if not _app_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
    _app_logger.addHandler(_handler)
for _handler in _app_logger.handlers:
    # 필터를 로거가 아니라 핸들러에 붙여, app.* 하위 로거에서 올라온 레코드에도 적용되게 한다.
    if not any(isinstance(f, WithoutExceptionMessages) for f in _handler.filters):
        _handler.addFilter(_without_messages)
_app_logger.setLevel(logging.INFO)
# 예상하지 못한 예외는 uvicorn이 'uvicorn.error' 로거로 traceback과 함께 남기므로 이 로거에도 같은 필터를
# 붙인다.
_uvicorn_errors = logging.getLogger("uvicorn.error")
if not any(isinstance(f, WithoutExceptionMessages) for f in _uvicorn_errors.filters):
    _uvicorn_errors.addFilter(_without_messages)


# 앱 수명 주기. yield 앞은 서버가 요청을 받기 전에 한 번, finally는 종료 때 한 번 실행된다. 그래서
# LOAD_MODELS=true면 모델 적재·예열이 끝난 뒤에야 /api/health가 응답하고, Docker compose의 상태 검사도 그때
# 통과한다(docs/api.md 상태 확인).
# LOAD_MODELS=false(테스트·CI)면 아무것도 올리지 않아 app.state.models가 없고, dependencies.get_models가 빈
# 묶음을 준다.
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.load_models:
        logger.info("Loading the models (about a minute on the first start)")
        # 적재는 CPU와 GPU를 수십 초 동안 쥐므로 이벤트 루프 밖 스레드에서 한다. app.state에 둔 모델
        # 묶음을 dependencies.get_models가 모든 요청에 넘겨준다.
        app.state.models = await asyncio.to_thread(load_models, settings)
        # 각 모델의 첫 호출은 추가로 더 올린다(MeloTTS의 BERT 등). 그 비용을 첫 요청 대신 여기서 치른다.
        # 아래 freeze보다 먼저 해야 예열이 만든 객체도 함께 얼려진다.
        if settings.warm_up:
            await asyncio.to_thread(warm_up, app.state.models)
        # faster-whisper는 디코딩한 업로드마다 전체 gc.collect()를 부른다. 모델의 수백만 객체 때문에 이것이
        # GIL을 약 0.4초 쥐어 다른 모든 요청이 멈췄다(docs/experiments.md 5절). freeze는 지금 살아 있는
        # 객체를 모두 컬렉터가 훑는 대상에서 빼므로 그 수집이 짧게 끝난다.
        if settings.gc_freeze:
            gc.freeze()
        logger.info("Models loaded")
    try:
        yield
    finally:
        # 종료 정리: 오타 교정기의 백그라운드 준비 스레드에 멈추라고 알리고(close는 기다리지 않음), 모델
        # 참조를 놓는다.
        models = getattr(app.state, "models", None)
        if models is not None:
            corrector = getattr(models, "corrector", None)
            if corrector is not None:
                corrector.close()
            del app.state.models


# FastAPI 앱 객체. 위의 lifespan으로 모델 적재·예열·정리를 건다.
app = FastAPI(title="voice-translator API", version="0.1.0", lifespan=lifespan)

# 모든 라우터를 /api 아래에 두어 빌드한 화면과 API가 한 출처(origin)를 함께 쓸 수 있게 한다. Docker에서는
# nginx가 화면과 `/api` 프록시를 함께 맡고(README 배포), 개발 중에는 Vite 개발 서버가 /api를 이
# 앱(8000번)으로 넘긴다.
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(translate.router, prefix="/api")
app.include_router(live.router, prefix="/api")
app.include_router(audio.router, prefix="/api")

# 음성 업로드 두 경로 밖 요청 본문의 최대 바이트(64KiB = 65,536). 이 앱의 JSON·폼 본문은 가장 커도 수 KB다:
# refresh 토큰(4,096자 이하)을 담은 갱신, 이메일과 72바이트 이하 비밀번호의 가입·로그인, 500자 글자
# 번역(모든 글자를 \uXXXX로 이스케이프해도 약 6KB). 배포의 nginx도 server 단계에 같은 64k를
# 둔다(frontend/nginx.conf). nginx를 거치지 않고 uvicorn에 바로 닿는 개발 서버에도 같은 한도가 걸리게 앱에서
# 다시 센다(아래 RequestBodyLimit).
MAX_REQUEST_BODY_BYTES = 64 * 1024
# 음성 업로드 경로: 제한된 multipart 파서를 쓰는 경로(routers/translate.py의 LimitedUploadRoute), 곧
# /api/translate/speech와 /api/translate/dialog. 그 파서가 파일 바이트를 따로 세어 10MB에서 끊으므로 위 본문
# 한도를 받지 않는다. nginx도 이 두 경로에만 11m를 준다. 경로 목록을 손으로 적지 않고 번역 라우터에 등록된
# 경로에서 읽어(앞의 "/api"는 위 include_router의 prefix), 업로드 경로가 늘거나 바뀌어도 어긋나지 않게 했다.
# app.routes를 훑지 않는 이유: 이 판의 FastAPI는 포함한 라우터를 경로 목록으로 펼치지 않고 묶음 하나로 둔다.
UPLOAD_PATHS = frozenset(
    "/api" + route.path
    for route in translate.router.routes
    if isinstance(route, translate.LimitedUploadRoute)
)


# 검증 실패(422) 응답. FastAPI 기본 처리기는 오류 항목마다 보낸 값(input)과 부가 정보(ctx)를 담아
# jsonable_encoder로 돌려준다. 로그인 없이 부르는 가입·토큰 갱신에 큰 JSON 목록을 보내면 그 값을 원소마다
# 파이썬으로 다시 만들고 같은 크기로 돌려주느라 이벤트 루프가 수 초 멈췄다(11MB 본문 하나에 7초 넘게,
# docs/security.md 2026-11-24 덧붙임). 그동안 모든 HTTP 요청과 동시통역 자막이 함께 멈춘다. 그래서
# 계약(docs/api.md '오류 응답')대로 항목마다 위치(loc)·문구(msg)·종류(type)만 돌려준다. 화면은 422 본문의
# 값을 쓰지 않고 상태 코드로 고정 문구를 고른다(frontend/src/api/client.ts). 보낸 값을 되돌려 주지 않으므로
# 비밀번호 같은 입력이 응답에 다시 실리지도 않는다. 라우터가 직접 낸 검증 오류(routers/translate.py의 언어
# 쌍)도 이 처리기를 거친다.
@app.exception_handler(RequestValidationError)
async def validation_error_without_input(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


# 요청 경로에서 앱이 올라간 주소 접두(root_path)를 뗀다. uvicorn을 --root-path /vt로 띄우면 uvicorn이
# 접두를 붙여 scope의 path가 "/vt/api/…"로 오고, 라우터는 접두를 떼고 경로를 찾는다(Starlette의
# get_route_path). 본문 한도가 접두를 떼지 않고 견주면 업로드 두 경로를 못 알아봐 64KiB가 넘는 음성이
# 413으로 막히므로, 라우터와 같은 규칙으로 뗀다: 접두 바로 뒤가 "/"일 때만 떼고(접두가 "/vt"일 때
# "/vtx/…"는 그대로 둔다), 경로가 접두와 같으면 빈 글이다. 접두가 없으면(기본 배포) 경로 그대로다.
# 입력은 ASGI scope, 출력은 라우터가 보는 경로다. 접두는 서버 설정에서 오고 요청이 정하지 못한다.
# Starlette의 그 함수를 가져다 쓰지 않는 이유: 밑줄로 시작하는 내부 모듈에 있어 판이 바뀌면 사라질 수
# 있다. 두 규칙이 어긋나지 않는지는 tests/test_request_limits.py의 접두 시험이 본다.
def route_path(scope: Scope) -> str:
    path: str = scope["path"]
    root_path: str = scope.get("root_path", "")
    if not root_path or not path.startswith(root_path):
        return path
    if path == root_path:
        return ""
    return path[len(root_path) :] if path[len(root_path)] == "/" else path


class RequestBodyLimit:
    """음성 업로드 경로 밖의 HTTP 요청 본문을 limit 바이트까지만 받는 ASGI 미들웨어.

    본문을 읽는 쪽(FastAPI의 JSON·폼 읽기)이 receive를 부를 때, 요청이 밝힌 Content-Length나 실제로 받은
    바이트가 limit를 넘는 순간 HTTPException(413)을 낸다. FastAPI는 본문을 읽다 난 HTTPException을 그대로
    올리므로 응답은 413 {"detail": "Request body is too large"}이고, 넘친 본문은 더 읽지 않는다(풀지도
    않는다). Content-Length 없이 조각으로 오는(chunked) 본문은 받은 만큼 센다. 웹소켓, 본문을 읽지 않는
    경로(GET 등), exempt의 경로(음성 업로드 두 개: 그 경로의 multipart 파서가 파일 바이트를 따로 세어
    10MB에서 끊는다)는 건드리지 않는다. 주의: 넘었다고 바로 답하지 않고 본문을 읽으려 할 때 오류를 내므로,
    본문을 읽지 않는 경로의 응답은 그대로다. nginx를 거치는 배포에서는 nginx가 같은 64k에서 먼저
    끊고(frontend/nginx.conf), 이 미들웨어는 uvicorn에 바로 닿는 개발 서버에도 같은 한도를 건다.
    """

    def __init__(self, app: ASGIApp, limit: int, exempt: frozenset[str]) -> None:
        self.app = app
        self.limit = limit
        self.exempt = exempt

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or route_path(scope) in self.exempt:
            await self.app(scope, receive, send)
            return
        # 요청이 밝힌 Content-Length는 숫자일 때만 쓰고, 없거나 숫자가 아니면 실제로 받은 바이트로만 판단한다.
        declared = Headers(scope=scope).get("content-length", "")
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            if declared.isdigit() and int(declared) > self.limit:
                raise HTTPException(413, "Request body is too large")
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    raise HTTPException(413, "Request body is too large")
            return message

        await self.app(scope, limited_receive, send)


app.add_middleware(RequestBodyLimit, limit=MAX_REQUEST_BODY_BYTES, exempt=UPLOAD_PATHS)
