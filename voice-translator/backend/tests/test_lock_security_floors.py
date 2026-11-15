"""uv.lock의 판이 알려진 보안 권고를 고친 판 아래로 돌아가지 않는지 지키는 테스트다. 모델·DB 없이 잠금 파일만
읽는다."""

# [파일 역할] backend/uv.lock을 tomllib로 읽어, 권고 때문에 올린 여섯 패키지(2026-10-30의 세 개, 2026-11-05의
# pyasn1, 2026-11-07의 mako, 2026-11-15의 opentelemetry-api)가 고친 판 아래로 내려가지 않았는지 확인한다
# (docs/security.md '의존성 취약점'의 2026-10-30·2026-11-05·2026-11-07·2026-11-15 덧붙임).
# - filelock ≥ 4.2.1(잠금의 모든 항목): MeloTTS가 고정한 cached-path 1.8.10이 `filelock<4.0`을 요구해, 그냥
#   잠그면 고친 판이 없는 3.x에 묶인다(2026-10 공개 권고 13건, 고친 판 4.2.1 — 하나는 4.0.9). pyproject.toml의
#   [tool.uv] override-dependencies "filelock>=4.2.1"이 그 상한을 덮어 서버·도구 환경 모두 4.x를 쓴다. 그
#   override를 지우거나 MeloTTS·cached-path를 바꿔 다시 잠그면 3.x로 돌아갈 수 있어 지킨다.
# - dnspython ≥ 2.9.2(잠금의 모든 항목): email-validator가 끌어오는 패키지로 두 환경 모두에 있다. 권고 둘을
#   고친 판이다: CVE-2026-114605(조작한 DNS 메시지의 이름 압축 풀기, 고친 판 2.9.0 — 2026-10-30부터 하한
#   2.9.0으로 지킴)와 CVE-2026-128089(글 형식 zone 파서가 WKS 레코드의 서비스 번호 범위를 검사하지 않아
#   메모리와 CPU를 지나치게 씀, 고친 판 2.9.2 — 2026-11-15에 하한을 2.9.2로 올림). 서비스는 이메일의 형식만
#   검사하고 DNS를 묻지 않는다.
# - setuptools ≥ 84.1.0(도구 환경 = eval 그룹이 가리키는 판): eval 그룹의 하한 "setuptools>=84.1.0"이 정한다
#   (GHSA-xmj3-9gf7-h52w, 고친 판 84.1.0). 서버 환경(tts 그룹)은 torch 2.11.0+cu128이 `setuptools<82`를
#   요구하고 MeloTTS의 중국어 전처리가 import 때 부르는 cn2an·jieba가 pkg_resources(84.0.0에는 없음)를 쓰므로
#   81.0.0을 받아들였다. 그래서 setuptools는 eval 그룹 쪽만 본다.
# - pyasn1 ≥ 0.6.5(잠금의 모든 항목): MeloTTS → cached-path → google-cloud-storage → google-auth →
#   pyasn1-modules 0.4.2가 끌어오는 패키지로, 서버 환경(tts 그룹)에만 있다. 0.6.4에는 조작한 BER/CER/DER
#   입력을 디코딩할 때 CPU 시간이 입력 크기의 제곱에 가깝게 느는 권고 4건(CVE-2026-119194·119195·119196·
#   119197)이 있고 고친 판은 0.6.5다. pyasn1-modules가 요구하는 범위(`pyasn1>=0.6.1,<0.7.0`) 안이라
#   override 없이 잠금의 판만 올렸다. 서비스 코드는 google-auth·pyasn1을 직접 쓰지 않는다.
#   MeloTTS·cached-path를 바꿔 다시 잠글 때 내려가지 않게 지킨다.
# - mako ≥ 1.4.2(잠금의 모든 항목): alembic이 끌어오는 템플릿 라이브러리로 두 환경 모두에 있다. 1.4.1에는
#   Windows에서 드라이브 문자로 시작하는 TemplateLookup URI가 템플릿 폴더 밖 파일을 읽는 권고가 있다
#   (PYSEC-2026-4243 / CVE-2026-102991, 고친 판 1.4.2). 서비스는 컨테이너 시작 때 alembic upgrade head만
#   돌리고 Mako 템플릿은 새 마이그레이션 파일을 만들 때만 쓰므로 닿지 않지만, 이 권고는 PyPI 권고 자료에
#   없어 CI의 pip-audit(PyPI 서비스)에 나오지 않았고 OSV 검사에서만 나왔다. 그래서 판이 내려가도 CI가
#   바로 알리지 못할 수 있어 여기서 지킨다(1.4.3으로 올림).
# - opentelemetry-api ≥ 1.45.2(잠금의 모든 항목): MeloTTS → cached-path → google-cloud-storage →
#   google-api-core가 끌어오는 패키지로, 서버 환경(tts 그룹)에만 있다. 1.45.1에는 조작한 traceparent 값을
#   읽을 때 정규식 처리 시간이 값 길이의 제곱으로 느는 권고가 있고(CVE-2026-126360 / GHSA-mf5v-w3w3-f6cg)
#   고친 판은 1.45.2다. 서비스 코드는 opentelemetry를 쓰지 않지만(backend/app에 import 없음) 고친 판이
#   있어 override 없이 잠금의 판만 올렸다. MeloTTS·cached-path를 바꿔 다시 잠글 때 내려가지 않게 지킨다.
# [왜 중요한가] 서버 이미지와 CI는 `--locked`로 이 파일 그대로 설치하므로 잠금의 판이 곧 설치되는 판이다. CI의
# audit 작업(pip-audit)은 보고만 해서(continue-on-error) 판이 내려가도 워크플로가 통과한다. 이 테스트는 맨 위
# Test 단계에서 돌아 바로 실패로 드러난다. `uv lock --check`는 pyproject와 잠금이 어긋났는지만 보고 판이
# 몇인지는 보지 않는다.
# [주의] 판 비교는 packaging.version으로 한다(pytest가 의존하는 패키지라 CI의 기본 환경에도 있다). 잠금에 같은
# 이름이 여러 판으로 있으면(그룹끼리 따로 풀린 경우) 모두 하한 이상이어야 한다.

import tomllib
from pathlib import Path

import pytest
from packaging.version import Version

# BACKEND: 이 파일 기준 backend/ 폴더. 테스트를 어느 작업 폴더에서 돌려도 같은 잠금 파일을 읽게 한다.
BACKEND = Path(__file__).resolve().parents[1]
LOCK_PATH = BACKEND / "uv.lock"

# 잠금의 모든 항목이 지켜야 하는 하한 → (권고, 왜 이 패키지가 잠금에 있는지).
FLOORS = {
    "filelock": ("4.2.1", "CVE-2026-112907 등 13건, cached-path의 filelock<4.0을 override로 덮음"),
    "dnspython": ("2.9.2", "CVE-2026-114605(고친 판 2.9.0)·CVE-2026-128089(2.9.2), email-validator의 의존성"),
    "pyasn1": ("0.6.5", "CVE-2026-119194~119197, cached-path → google-auth → pyasn1-modules의 의존성"),
    "mako": ("1.4.2", "PYSEC-2026-4243 / CVE-2026-102991, alembic의 의존성(OSV에만 있는 권고)"),
    "opentelemetry-api": (
        "1.45.2",
        "CVE-2026-126360, cached-path → google-cloud-storage → google-api-core의 의존성",
    ),
}
# 도구 환경(eval 그룹)의 setuptools 하한(GHSA-xmj3-9gf7-h52w).
EVAL_SETUPTOOLS_FLOOR = "84.1.0"


def load_lock() -> dict:
    with LOCK_PATH.open("rb") as f:
        return tomllib.load(f)


def locked_versions(lock: dict, name: str) -> set[str]:
    return {package["version"] for package in lock["package"] if package["name"] == name}


@pytest.mark.parametrize("name", sorted(FLOORS))
def test_every_locked_version_is_at_or_above_the_advisory_fix(name: str):
    floor, why = FLOORS[name]
    versions = locked_versions(load_lock(), name)
    assert versions, (
        f"uv.lock에 {name}이(가) 없다. 의존성 경로가 바뀌었으면 이 표와 docs/security.md를 다시 본다"
    )
    too_old = sorted(v for v in versions if Version(v) < Version(floor))
    assert not too_old, (
        f"uv.lock의 {name} {too_old}는 권고를 고친 {floor}보다 낮다({why}). docs/security.md "
        "'의존성 취약점'의 날짜 붙은 덧붙임(2026-10-30·2026-11-05·2026-11-07·2026-11-15)을 보고, "
        "filelock이면 pyproject.toml의 override-dependencies가 남아 있는지 확인한다"
    )


# eval 그룹이 가리키는 setuptools 판. 잠금의 프로젝트 항목은 그룹마다 고른 의존성을 적고, 같은 이름이 여러
# 판으로 잠겼으면 판도 함께 적는다(하나뿐이면 판이 빠지므로 그때는 잠금의 유일한 판을 쓴다). 잠금은 uv 판에
# 따라 dependency-groups 또는 dev-dependencies 키로 그룹을 적으므로 둘 다 본다.
def test_the_tools_environment_setuptools_is_at_or_above_the_advisory_fix():
    lock = load_lock()
    project = next(p for p in lock["package"] if p["name"] == "voice-translator-backend")
    groups = project.get("dependency-groups") or project.get("dev-dependencies") or {}
    entries = [dependency for dependency in groups.get("eval", []) if dependency["name"] == "setuptools"]
    assert entries, (
        "eval 그룹에 setuptools 하한이 없다. torch 2.14가 끌어오는 setuptools가 GHSA-xmj3-9gf7-h52w를 고친 "
        f"{EVAL_SETUPTOOLS_FLOOR} 아래로 잠길 수 있으므로 pyproject.toml의 eval 그룹에 하한을 둔다"
    )
    versions = {entry.get("version") for entry in entries}
    if None in versions:
        versions = locked_versions(lock, "setuptools")
    too_old = sorted(v for v in versions if Version(v) < Version(EVAL_SETUPTOOLS_FLOOR))
    assert not too_old, (
        f"도구 환경(eval 그룹)의 setuptools {too_old}가 {EVAL_SETUPTOOLS_FLOOR}보다 낮다(GHSA-xmj3-9gf7-h52w)"
    )
