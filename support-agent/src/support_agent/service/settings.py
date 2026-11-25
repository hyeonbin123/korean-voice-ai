"""서비스 설정. 환경 변수(접두사 SUPPORT_AGENT_)에서 읽는다."""

# [파일 역할] 채팅 서비스(3단계)의 설정 전부를 한 클래스(Settings)로 모은다. 값은 SUPPORT_AGENT_ 접두사가 붙은
# 환경 변수에서 읽는다(docs/service.md의 설정 목록).
# [왜 필요한가] 같은 코드를 Docker Compose(PostgreSQL), 호스트의 SQLite 실행, 모델 없는 오프라인 앱,
# 테스트에서 돌리므로 DB 주소·모델·한도 같은 값을 코드 밖에서 바꿀 수 있어야 한다. pydantic 모델로 두어 잘못된
# 값(예: THINK=false)은 앱이 뜰 때 바로 거절된다.
# [연결] service/app.py의 create_app, service/offline.py, mcp_server.py가 Settings.from_env()로 만든다.
# service/core.py는 clock()으로 쇼핑몰의 현재 시각을 얻는다.

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any, Literal

# pydantic: 환경 변수 문자열을 타입(int, bool, Literal, 시간대 있는 datetime)으로 바꾸고 범위(ge/le)를
# 검사한다. AwareDatetime은 시간대 없는 시각을 거절해, 고정 시계가 KST/UTC를 헷갈리지 않게 한다.
# field_validator는 한 필드의 형식(KEEP_ALIVE)을 따로 검사한다.
from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

# 환경 변수 접두사. 필드 이름을 대문자로 바꿔 붙인다(model → SUPPORT_AGENT_MODEL).
PREFIX = "SUPPORT_AGENT_"
# 생성한 쇼핑몰 데이터는 이 시각을 기준으로 쓰였다(과제도 이 시각을 쓴다). 벽시계를 쓰면 모든 주문이 곧
# 반품 기한을 넘기므로, 시연은 SUPPORT_AGENT_NOW=real이 아니면 고정 시계로 돈다.
DEMO_NOW = "2026-09-14T10:00:00+09:00"
# 2026-10-04부터 기본 모델(docs/experiments.md 8단계): 사고 모드를 끄고 잰 시험용 pass^1이 qwen2.5 7B의
# 18.1%에 비해 55.6%였다. 다만 과제가 요구하지 않은 쓰기도 6건에 비해 13건이었으므로 승인 관문은 그대로 둔다.
# MODEL=qwen2.5:7b-instruct로 이전 모델로 돌아갈 수 있다.
DEFAULT_MODEL = "qwen3.5:4b"
# THINK 설정 문자열 → Ollama 요청의 think 값. None은 요청에 think 필드를 아예 넣지 않는다는 뜻이다(사고 모드가
# 없는 모델은 이 필드를 거부할 수 있어서, docs/service.md).
_THINK = {"on": True, "off": False, "omit": None}
# KEEP_ALIVE 값이 Ollama가 읽을 수 있는 꼴인지 보는 두 패턴(Settings._keep_alive_ollama_can_read). Ollama
# 0.35.1의 api/types.go `Duration.UnmarshalJSON`은 JSON 숫자를 초로 읽고(음수는 '내리지 않음'), 문자열은 Go의
# time.ParseDuration으로 읽어 형식이 틀리면 오류를 돌려줘 요청이 처리되지 않는다(2026-10-30 원본으로 확인).
# - _KEEP_ALIVE_SECONDS: 부호 있는 정수. 숫자로 바꿔 보내면 초다(agent_keep_alive)
# - _KEEP_ALIVE_DURATION: ParseDuration의 꼴. 앞에 부호 하나, 숫자(소수 가능)와 단위(ns, us, µs, μs, ms, s, m,
#   h)의 이어 붙임(1h30m), 또는 "0". 숫자는 ASCII만 받는다(re의 \d는 다른 문자권의 숫자도 받지만 Go는 0~9만
#   읽으므로 [0-9]로 쓴다). 단위는 대소문자를 가린다("60M"은 틀림)
_KEEP_ALIVE_SECONDS = re.compile(r"[-+]?[0-9]+")
_KEEP_ALIVE_DURATION = re.compile(r"[-+]?(0|(([0-9]+(\.[0-9]*)?|\.[0-9]+)(ns|us|µs|μs|ms|s|m|h))+)")

# Host 헤더 허용 목록의 기본값: 이 PC의 루프백 이름. 브라우저는 주소창의 호스트를 Host 헤더에 그대로 싣고,
# 서비스는 포트를 뗀 호스트 부분만 이 목록과 정확히 비교해 목록 밖이면 400을 돌려준다(app.py의
# TrustedHostMiddleware). 왜 필요한가: 포트를 127.0.0.1에만 여는 것은 브라우저를 거치는 경로를 막지 못한다.
# 공격자 페이지의 이름을 공격자의 DNS가 127.0.0.1로 다시 풀면(DNS 리바인딩) 그 페이지의 fetch가 같은 출처
# 요청으로 이 포트에 닿고, 그 요청은 `Host: 공격자의 이름`으로 도착하므로 Host를 목록으로 걸러 그 경로를
# 닫는다(docs/service.md "정한 것과 이유"). `[::1]`(IPv6 루프백 주소 표기)은 넣지 않는다: 잠금의 Starlette
# 1.6.0은 Host에서 첫 `:` 앞만 읽어 `[::1]`이 어떤 목록 항목과도 같을 수 없다(이 저장소의 stt-scratch가
# 쓰는 Starlette 1.7.0은 괄호를 보존해 읽는다). 맞지 않는 항목을 넣어 두면 읽는 사람이 되는 줄 안다.
# `localhost`는 IPv6 루프백으로도 풀리므로 그 이름으로 접속하면 된다.
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost")
# ALLOWED_HOSTS 한 항목의 모양: 영문 소문자·숫자·하이픈·밑줄을 점으로 이은 이름(토막마다 63자 이하, 처음과
# 끝은 영숫자). 밑줄은 DNS 규격이 금하지만 Docker 서비스 이름에 쓰일 수 있어 받는다(이 목록은 그 글자가
# Host에 그대로 실려 올 때만 맞추므로 받아도 맞추는 범위가 넓어지지 않는다). 포트(`:`), 주소(`/`), 사용자
# 정보(`@`), 괄호(IPv6 주소), 와일드카드(`*`), 공백은 이 모양에 없다.
_HOST_NAME = re.compile(r"[a-z0-9](?:[a-z0-9_-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9_-]{0,61}[a-z0-9])?)*")
# IPv4 주소: 점으로 이은 네 수(0~255, 앞에 0을 붙이지 않는다). 마지막 토막이 숫자뿐인 항목은 이 모양이어야
# 한다.
_OCTET = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
_IPV4 = re.compile(rf"(?:{_OCTET}\.){{3}}{_OCTET}")
# SUMMARY_URL의 꼴: `http://`·`https://`(대소문자 무관) + 호스트 + 선택 포트(`:` 뒤 숫자 1~5자리) + 선택
# 경로(`/`로 시작하고 영문·숫자와 `-._~/`만). host 묶음은 `/`·`:` 앞까지를 잡고, 그것이 이름이나 IPv4
# 주소인지는 검증기가 위 _HOST_NAME·_IPV4로 다시 본다. 사용자 정보(`@`), 질의(`?`), 조각(`#`), 공백, 퍼센트
# 인코딩, 역슬래시, IPv6 주소(대괄호)는 이 꼴에 들 수 없다(Settings._summary_url_is_a_plain_http_address).
# 스킴의 대소문자는 글자마다 [Hh]로 적는다. 정규식의 대소문자 무시 옵션(`(?i:…)`)을 쓰면 ASCII가 아닌
# 글자도 알파벳으로 접혀 받아들여지기 때문이다: 긴 s(`ſ`, U+017F)가 `s`로 받아들여져 `httpſ://…`가 이
# 검사를 지난다(httpx는 그런 주소를 스킴 없는 주소로 읽어 요청마다 실패한다). 호스트는 검증기가 ASCII 이름만
# 받고 경로는 이 정규식이 ASCII 글자만 받는다.
_SUMMARY_URL = re.compile(
    r"[Hh][Tt][Tt][Pp][Ss]?://(?P<host>[^/:]+)(?::(?P<port>[0-9]{1,5}))?(?:/[A-Za-z0-9._~/-]*)?"
)


# ALLOWED_HOSTS의 한 항목을 검사해 Host 헤더에 실리는 꼴(소문자)로 돌려준다. 잘못된 항목은
# ValueError(메시지는 영어다. pydantic이 ValidationError로 감싸 서비스가 시작할 때 보여 준다). 받지 않는
# 것과 이유:
# - 빈 항목: 쉼표 오타(`a.example,`)다. 조용히 넘기면 방어를 켰다고 믿고 쓴다
# - 와일드카드(`*`, `*.example.com`): `*` 하나는 Host 검사를 통째로 끈다(Starlette가 그렇게 읽는다). 하위
#   도메인 패턴도 범위를 하염없이 넓힐 수 있어(`*.com`) 받지 않고, 필요한 이름을 하나씩 적게 한다. 이 저장소의
#   stt-scratch는 명령행 옵션이라 `*`(시작 경고와 함께)와 `*.example.com` 패턴을 받지만, 이 서비스는 값을
#   환경 변수와 `.env`로 주고 시작 경고를 읽는 사람이 없을 수 있어 검사를 끄거나 넓히는 값은 받지 않는다
# - 포트·http://·경로·사용자 정보·IPv6 주소: 서비스는 Host에서 포트를 뗀 이름만 비교하므로 그런 항목은 어떤
#   요청과도 같을 수 없다. 조용히 아무것도 통과시키지 못하는 항목이 되는 대신 시작할 때 거절한다
# - 마지막 토막이 숫자뿐인데 IPv4 주소가 아닌 이름(`192.168.0`, `127.000.000.001`): 오타다
def _allowed_host(entry: str) -> str:
    host = entry.strip().lower()
    if not host:
        raise ValueError("ALLOWED_HOSTS has an empty entry (a stray comma?)")
    if "*" in host:
        raise ValueError(
            f"{entry!r}: wildcards are not accepted ('*' would switch the Host check off); list each name"
        )
    if len(host) > 253 or not _HOST_NAME.fullmatch(host):
        raise ValueError(
            f"{entry!r} is not a host name or an IPv4 address: write only the name, without a port, scheme, "
            "path, user info, brackets or an IPv6 address"
        )
    if host.rsplit(".", 1)[-1].isdigit() and not _IPV4.fullmatch(host):  # 숫자로 끝나면 IPv4 주소여야 한다
        raise ValueError(f"{entry!r} looks like an IPv4 address but is not one")
    return host


# 서비스 설정 한 묶음. 필드 기본값이 곧 시연용 기본 구성이다.
# - database_url: 기본은 SQLite 파일(outputs/service.db). Compose는 PostgreSQL 주소를 넣는다
# - num_ctx: 서비스는 16384. 8단계 측정은 12288로 쟀으므로 잰 구성과 다른 점이다(docs/service.md)
# - keep_alive·preload: 모델을 메모리에 두는 시간(기본 60분)과 시작 때 미리 올리기(기본 끔)
# - approval_refund_won: 이 금액 이상 환불되는 취소·반품은 관리 화면에서 사람이 승인해야 실행된다
# - admin_token: 빈 문자열이면 관리자 API가 꺼진다
# - max_*: 메시지 길이, 턴당 LLM 호출, 세션당 턴, 음성 파일 크기·길이, 동시에 도는 턴 수, 동시에 도는 답
#   읽어 주기(합성) 수의 한도(docs/service.md "한도")
# 정수 설정에는 모두 범위(Field의 ge/le)를 둔다. 범위 밖 값(0, 음수, 너무 작은 num_ctx, 너무 큰 동시 턴 수)은
# 서비스가 시작할 때 ValidationError로 멈춘다: 전에는 글자 한도 둘만 검사해, 예컨대
# MAX_TURNS_PER_SESSION=0으로 띄우면 /healthz는 정상인데 모든 상담이 첫 메시지 뒤 닫히는 상태가
# 됐다(2026-10-24 고침, tests/test_review_t7.py).
class Settings(BaseModel):
    database_url: str = "sqlite:///outputs/service.db"
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = DEFAULT_MODEL
    # 모든 에이전트 요청에 넣는 Ollama의 `think` 필드. 비워 두면 기본 모델은 "off"(그렇게 쟀다), 다른 모델은
    # "omit"(보내지 않음)이 된다: 사고 모드가 없는 모델은 이 필드를 거절한다.
    think: Literal["on", "off", "omit"] = "off"
    # 에이전트 호출의 컨텍스트 길이(Ollama의 num_ctx). 서비스는 16384(8단계 측정은 12288, docs/service.md).
    # 하한 4096: 시스템 프롬프트(규정·지침)와 도구 설명만으로 첫 에이전트 호출의 프롬프트가 이미 약
    # 3,500토큰이라(실제 모델로 확인한 상담의 첫 호출이 3,526토큰, docs/service.md) 그보다 작으면 모든 상담이
    # 첫 턴에 컨텍스트 한도로 닫힌다. 0·음수도 전에는 그대로 받아들여졌다(2026-10-24 고침).
    num_ctx: int = Field(default=16384, ge=4096)
    # 요청 뒤 Ollama가 모델을 메모리(GPU)에 두는 시간. 모든 에이전트 요청과 예열 요청의 keep_alive로 가고,
    # 요청에 실린 값이 Ollama 서버의 OLLAMA_KEEP_ALIVE보다 앞선다. 기본 60m은 이 설정이 생기기 전에 서비스가
    # 늘 보내던 값이다(OllamaProvider의 기본값). GPU를 다른 작업과 나눠 쓰므로 고객이 없을 때 모델이 자리를
    # 오래 쥐지 않게 그대로 둔다. 그래서 띄운 직후와 60분 넘게 쉰 뒤의 첫 메시지는 모델을 올리는 시간만큼
    # 늦다(docs/service.md "실행"). 값은 Ollama의 형식 그대로다: 단위가 붙은 기간(60m, 24h, 1h30m), 초 단위
    # 정수(3600), 음수(-1, -1m: 내리지 않음), 0(답한 뒤 바로 내림). 읽을 수 없는 값은 시작할 때 거절한다.
    keep_alive: str = "60m"
    # 서비스가 시작할 때 모델을 한 번 미리 올린다(예열). 작업 스레드에서 하므로 시작을 막지 않고, 실패해도
    # 서비스는 그대로 뜬다(app.py의 start_preload). 기본은 끔: 예열은 고객이 오기 전부터 GPU 메모리를 쓴다.
    # 켜도 빨라지는 것은 띄운 직후의 첫 메시지뿐이고, keep_alive보다 오래 쉬면 모델은 다시 내려간다.
    preload: bool = False
    # 서비스는 규정이 금지하는 것을 거절한다(P1). 그것이 성공률을 올리는지는 docs/experiments.md의 질문이고,
    # 여기서는 잘못된 환불이 돈을 잃게 하므로 코드가 검사할 수 있는 것은 도구가 모두 검사한다.
    policy: Literal["P0", "P1"] = "P1"
    # C1: 이 대화의 어떤 도구 결과도 보여 주지 않는데 일이 끝났다고 말하는 답은 절대 전달하지 않는다. 기본은
    # 꺼짐: 개발용 과제에서 C1은 −2.1%p와 정답에 없는 쓰기 1건 증가, C2는 −5.2%p라 둘 다 측정 전에 적은 규칙을
    # 만족하지 못했다(docs/experiments.md 7단계). CLAIMS=C1로 켠다.
    claims: Literal["C0", "C1", "C2"] = "C0"
    # 13단계 후보(docs/experiments.md 13단계). 모두 기본은 꺼짐이고, 켜는 조건은 13단계 규칙에 측정 전에
    # 적었다. GUARD=G1: "확인해 보겠습니다"만 하는 답을 붙잡아 다시 시킨다(2단계 멈춤 가드). ERRORS=E1: 규정이
    # 막은 쓰기의 오류 글에 그 검사가 쓴 사실(수령·출고 시각, 접수 마감일, 이미 발급된 쿠폰, 도착 예정일)을
    # 붙인다. REPEAT=D1: 바로 앞에 고객에게 전달한 답과 같은 답을 붙잡아 한 번 다시 시킨다.
    guard: Literal["G0", "G1"] = "G0"
    errors: Literal["E0", "E1"] = "E0"
    repeat: Literal["D0", "D1"] = "D0"
    now: AwareDatetime | Literal["real"] = Field(default_factory=lambda: datetime.fromisoformat(DEMO_NOW))
    # 이 금액 이상 환불되는 취소·반품은 사람이 승인해야 실행된다(core.py의 승인 관문, docs/service.md "사람
    # 승인"). 0이면 환불액과 상관없이 취소·반품이 모두 승인 대기에 오른다('전부 승인' 구성이라 받는다). 음수는
    # 뜻이 없어 거절한다.
    approval_refund_won: int = Field(default=100_000, ge=0)
    admin_token: str = ""  # ""이면 관리자 API가 꺼진다
    max_message_chars: int = Field(default=1000, ge=1, le=4000)  # 요청 모델(MessageIn)의 상한이 4000이다
    # 턴당 LLM 호출 수와 세션당 턴 수는 1 이상이어야 한다. 0이면 모든 턴이 호출 한도의 고정 안내로 끝나거나
    # 모든 세션이 첫 메시지 뒤 닫히는데, 서비스는 /healthz가 정상인 채 떠서 설정이 원인이라는 신호가
    # 없었다(2026-10-24 고침). 세션당 턴 수에 상한은 두지 않는다: 보안 스캔은 세션이 닫히지 않게 100000으로
    # 띄운다(docs/service.md "모델 없이 띄우기, 보안 스캔").
    max_agent_calls_per_turn: int = Field(default=12, ge=1)
    max_turns_per_session: int = Field(default=40, ge=1)
    load_seed: bool = True  # 빈 쇼핑몰 DB를 생성 데이터로 채운다
    expose_openapi: bool = False  # /openapi.json을 내놓는다(API 스캐너와 클라이언트용, 기본은 꺼짐)
    voice: bool = False  # 음성 입출력(`voice` 의존성 그룹이 필요하다)
    tts_device: Literal["cuda", "cpu"] = "cuda"
    stt_device: Literal["cuda", "cpu"] = "cuda"
    # 녹음 파일 크기와 풀었을 때 길이의 한도. 기본 5 MB는 브라우저로 녹음한 말 약 5분 분량이고, 길이 한도가
    # 따로 있는 것은 낮은 비트레이트면 작은 파일에도 몇 시간 분량의 말이 들어갈 수 있어서다. 둘 다 0이면 모든
    # 녹음이 거절되므로 1 이상만 받는다.
    max_audio_bytes: int = Field(default=5_000_000, ge=1)
    max_tts_chars: int = Field(default=600, ge=1, le=4000)
    max_audio_seconds: int = Field(default=60, ge=1)
    # 모든 세션을 통틀어 동시에 도는 턴(과 인식) 수. 0이면 모든 메시지가 503이고 음수는 create_app의
    # BoundedSemaphore가 ValueError를 내므로 1 이상만 받는다. 상한 16을 두는 이유: 턴의 SSE 응답 생성기는 동기
    # 함수라 Starlette가 이벤트를 하나 꺼낼 때마다 anyio 스레드 풀(기본 40자리)에서 돌리는데, 다음 이벤트를
    # 기다리는 동안(모델이 답할 때까지) 그 자리를 쥔 채 멈춰 있다(app.py turn_stream의 stream). 같은 풀을
    # /healthz·글 메시지 수신·대화 조회·관리자 API의 동기 처리기가 쓰므로, 이 값을 40 가까이 올리면 턴이
    # 자리를 모두 차지해 /healthz가 답하지 못하고 Docker의 HEALTHCHECK가 실패해 재시작될 수 있다. 16이면 턴이
    # 모두 차도 자리 24개가 남는다(docs/service.md "한도").
    max_concurrent_turns: int = Field(default=4, ge=1, le=16)
    # 모든 세션을 통틀어 동시에 도는 답 읽어 주기(/speech 합성) 수. 턴 자리와는 따로 센다: 합성은 턴을 쓰지
    # 않으므로 위 한도가 /speech를 막지 못했고, 음성 모델은 한 번에 하나만 돌리므로(voice_frontend의 잠금)
    # 겹친 합성 요청은 모두 작업 스레드를 쥔 채 그 잠금을 기다렸다. 넘으면 기다리지 않고 429와 Retry-After로
    # 돌려보낸다(app.py speak). 기본 2 = 하나는 합성 중, 하나는 그 뒤에 줄 서기(화면은 조각을 한 번에 하나씩만
    # 청한다). 0이면 모든 요청을 거절하게 되므로 받지 않는다(ge=1).
    max_concurrent_speech: int = Field(default=2, ge=1)
    # Host 허용 목록에 더할 이름(쉼표로 구분한 호스트 이름이나 IPv4 주소). 기본은 비어 있어 목록은
    # DEFAULT_ALLOWED_HOSTS 그대로다. 서비스를 127.0.0.1·localhost가 아닌 이름으로 불러야 할 때(앞단 프록시의
    # 이름 등) 더한다. 환경 변수에서는 쉼표로 나눈 한 문자열이고(SUPPORT_AGENT_ALLOWED_HOSTS=a.example,b),
    # 코드에서는 문자열이나 목록으로 준다. 값은 앞뒤 공백을 떼고 소문자로 맞추며 같은 이름은 한 번만 남긴다.
    # 이름이나 IPv4 주소가 아닌 값(`*`와 하위 도메인 패턴, 포트, http://, 경로, IPv6 주소, 빈 항목)은 서비스가
    # 시작할 때 거절한다(_allowed_host). 목록이 실제로 쓰이는 곳은 app.py의 Host 검사다(host_allow_list).
    allowed_hosts: tuple[str, ...] = ()
    # 상담 후처리 서비스(call-summary)의 주소. 비어 있으면(기본) 후처리 연결이 꺼진다. 이 주소 뒤에
    # /summarize를 붙여 부르는 클라이언트는 service/summary.py의 SummaryClient다. 값은 http:// 또는
    # https://와 호스트(이름이나 IPv4 주소)가 있어야 하고, 포트와 경로(앞단 프록시의 경로 접두사 등)는 붙여도
    # 된다. 앞뒤 공백과 끝의 `/`는 떼고, 공백뿐인 값은 빈 값(꺼짐)이다. 그 밖의 값(다른 스킴, 호스트 없음,
    # 사용자 정보, 질의·조각, IPv6 주소 등)은 서비스가 시작할 때 거절한다
    # (_summary_url_is_a_plain_http_address). 이 주소로 고객의 대화가 나가므로 주소는 이 설정에서만
    # 받는다(까닭은 service/summary.py의 머리 주석).
    summary_url: str = ""
    # 후처리 요청 하나를 기다리는 시간 상한(초, 1~600, 기본 120). 연결·보내기·응답을 기다리는 단계마다
    # httpx의 제한으로 걸리고(연결은 10초 이하), 응답 본문을 받는 동안과 다 받은 뒤에는 요청을 시작한 때부터
    # 잰 전체 시간이 이 값을 넘으면 끊는다(응답 머리를 받는 동안은 단계별 제한뿐이다. service/summary.py).
    # 후처리 서비스 쪽의 최악 대기는 약 270초(자리 대기 30초 + 모델 호출 한도 120초 × 두 번)라, 그쪽이 오래
    # 줄을 서거나 다시 시도하는 요청은 기본값에서 시간 초과(504)로 끝날 수 있다. 그런 일이 잦으면 600까지
    # 올린다. 상한을 두는 것은 summarize가 동기 호출이라 끝날 때까지 부른 스레드를 쥐기 때문이다. 범위 밖
    # 값은 시작할 때 거절한다.
    summary_timeout_s: int = Field(default=120, ge=1, le=600)

    # THINK를 비워 두면 모델에 맞춰 채운다: 기본 모델(qwen3.5:4b)은 잰 그대로 "off", 다른 모델은 "omit"(보내지
    # 않음).
    # mode="before"라서 필드 검증 전에 원래 입력 dict를 고친다. Compose는 THINK가 없으면 빈 문자열을
    # 넘기므로(compose.yaml) None과 ""를 같이 본다.
    # 이전 모델(qwen2.5:7b-instruct)로 돌아갈 때 MODEL만 바꿔도 think가 거부되지 않게 하려는
    # 것이다(tests/test_service.py가 두 경우를 확인한다).
    @model_validator(mode="before")
    @classmethod
    def _think_follows_the_model(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("think") in (None, ""):
            model = data.get("model") or DEFAULT_MODEL
            data = {**data, "think": "off" if model == DEFAULT_MODEL else "omit"}
        return data

    # KEEP_ALIVE가 Ollama가 읽을 수 있는 꼴인지 시작할 때 본다. 읽을 수 없는 값을 그대로 보내면 Ollama가 모든
    # 에이전트 요청을 처리하지 않아 상담이 모두 대체 안내로 끝나는데 /healthz는 정상이라, 설정이 원인이라는
    # 신호가 없다(위의 정수 설정 범위와 같은 이유). 단위 없는 소수("3600.5")는 받지 않는다: 문자열로는
    # Ollama가 읽지 못하고, 숫자로 바꿔 줄 만큼 쓸모 있는 값도 아니다.
    @field_validator("keep_alive")
    @classmethod
    def _keep_alive_ollama_can_read(cls, value: str) -> str:
        if _KEEP_ALIVE_SECONDS.fullmatch(value) or _KEEP_ALIVE_DURATION.fullmatch(value):
            return value
        raise ValueError(
            "keep_alive must be whole seconds (3600, -1) or a duration with a unit (60m, 24h, 1h30m, -1m, 0)"
        )

    # ALLOWED_HOSTS는 환경 변수에서 쉼표로 나눈 한 문자열로 온다. 문자열이면 쉼표로 나누고(공백뿐인 문자열은
    # 항목이 없는 것), 이미 목록이면 그대로 둔다. mode="before"라서 tuple[str, ...] 검증 전에 문자열을
    # 목록으로 바꾼다.
    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def _split_allowed_hosts(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.split(",") if value.strip() else []
        return value

    # 항목마다 이름이나 IPv4 주소인지 시작할 때 본다(위 _allowed_host). 같은 이름을 두 번 적어도 한 번만
    # 남기고 적은 순서는 지킨다.
    @field_validator("allowed_hosts")
    @classmethod
    def _allowed_hosts_are_plain_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(_allowed_host(entry) for entry in value))

    # SUMMARY_URL이 부를 수 있는 주소 꼴인지 시작할 때 본다(위 _SUMMARY_URL과 필드 주석). 받지 않는 것과
    # 이유:
    # - 사용자 정보(`http://이름:비밀번호@호스트`): httpx는 주소의 사용자 정보를 Authorization 머리로 바꿔
    #   보낸다. 후처리 요청은 인증 머리를 싣지 않는 약속이다(후처리 서비스에는 인증이 없다)
    # - 질의·조각(`?`, `#`): 클라이언트가 주소 뒤에 붙이는 /summarize와 섞여 요청 경로가 깨진다. 서비스가
    #   떠서 요청마다 실패하는 대신 시작할 때 거절한다(ALLOWED_HOSTS의 _allowed_host와 같은 까닭)
    # - IPv6 주소, ASCII 밖의 이름, IPv4 꼴이지만 틀린 주소: ALLOWED_HOSTS가 받는 이름과 같은 범위로 묶었다.
    #   그런 주소가 필요하면 이름을 붙여 쓴다
    # - 0이나 65535를 넘는 포트: 연결할 수 없는 포트다
    # 오류 글(영어)에는 값을 넣지 않는다.
    @field_validator("summary_url")
    @classmethod
    def _summary_url_is_a_plain_http_address(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        found = _SUMMARY_URL.fullmatch(value)
        host = found.group("host").lower() if found else ""
        port = found.group("port") if found else None
        if (
            found is None
            or len(host) > 253
            or not _HOST_NAME.fullmatch(host)
            or (host.rsplit(".", 1)[-1].isdigit() and not _IPV4.fullmatch(host))
            or (port is not None and not 1 <= int(port) <= 65535)
        ):
            raise ValueError(
                "summary_url must be an http:// or https:// address with a host name or an IPv4 address and "
                "optionally a port and a path (no user info, query, fragment, spaces or IPv6 address)"
            )
        return value.rstrip("/")

    # OllamaProvider에 넘길 think 값(True/False/None). app.py의 create_app이 제공자를 만들 때 쓴다.
    def agent_think(self) -> bool | None:
        """OllamaProvider가 `think`로 보낼 값. None이면 아무것도 보내지 않는다."""
        return _THINK[self.think]

    # OllamaProvider에 넘길 keep_alive 값. 정수 문자열은 정수로 바꾼다: Ollama는 JSON 숫자만 초로 읽고, 단위
    # 없는 숫자 문자열("3600")은 기간으로 읽지 못한다. 나머지(60m 등)는 문자열 그대로라, 기본값이면 요청
    # 본문이 이 설정이 생기기 전과 같다("keep_alive": "60m").
    def agent_keep_alive(self) -> str | int:
        """OllamaProvider가 `keep_alive`로 보낼 값."""
        return int(self.keep_alive) if _KEEP_ALIVE_SECONDS.fullmatch(self.keep_alive) else self.keep_alive

    # 서비스가 Host 헤더로 받는 이름 전부: 기본 루프백 이름 뒤에 ALLOWED_HOSTS로 더한 것(중복 없이, 적은
    # 순서대로). app.py의 create_app이 이 목록을 Host 검사 미들웨어에 넘긴다. 입력 없음, 출력은 소문자
    # 이름의 튜플이다.
    def host_allow_list(self) -> tuple[str, ...]:
        """Host 헤더로 받는 이름. 이 밖의 Host가 실린 요청은 400이다."""
        return tuple(dict.fromkeys((*DEFAULT_ALLOWED_HOSTS, *self.allowed_hosts)))

    # 도구와 규정이 보는 "쇼핑몰의 지금". 기본은 고정 시각(DEMO_NOW)이고, NOW=real일 때만 실제 UTC 시각이다.
    # 세션·감사 로그·승인 기록의 시각은 이것이 아니라 항상 실제 시각을 쓴다(core.py의 wall_clock,
    # docs/service.md "고정 시계").
    def clock(self) -> datetime:
        return datetime.now(UTC) if self.now == "real" else self.now

    # 환경 변수(또는 테스트가 넘긴 dict)에서 Settings를 만든다.
    # 값이 빈 문자열인 변수는 없는 것으로 친다. Compose의 `${THINK:-}`처럼 비어 있는 변수가 기본값을 덮어쓰지
    # 않게 하려는 것이다.
    # 문자열 → 타입 변환과 범위 검사는 model_validate가 맡으므로 잘못된 값은 여기서 ValidationError로 멈춘다.
    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ) if env is None else env
        values = {
            name: env[PREFIX + name.upper()]
            for name in Settings.model_fields
            if env.get(PREFIX + name.upper(), "") != ""
        }
        return Settings.model_validate(values)
