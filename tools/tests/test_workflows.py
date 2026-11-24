"""루트 워크플로 둘이 지키기로 한 규칙과 첫 화면의 워크플로 배지를 읽어서 확인하는 시험.

대상은 `.github/workflows/repo-checks.yml`과 `e2e.yml`이다.

왜 있나
    워크플로의 설정은 한 줄을 지워도 기능 시험이 하나도 깨지지 않는다. 토큰을 읽기 전용으로 두는 줄과 액션을 커밋
    SHA로 고정하는 줄이 그렇고, 전체 이력을 받는 줄(`fetch-depth: 0`)은 지우면 CI에서만 다른 시험이 실패한다. 줄을
    더하는 편집도 마찬가지다. 검사를 무력화하는 편집(명령 뒤에 `|| true`를 붙이거나 단계에 `continue-on-error`나
    `if`를 다는 것)과 위험한 사건이나 비밀값을 끌어들이는 편집은 지금 워크플로가 맞아도 조용히 들어올 수 있다. 구성
    요소 워크플로 가운데 일부는 그 구성 요소의 시험이 이미 같은 규칙을 지킨다(예: support-agent의
    tests/test_deploy_config.py). 루트 워크플로 둘은 어느 구성 요소의 시험도 읽지 않으므로 이 파일이 글자로 지킨다.

무엇을 지키나
    1. 두 워크플로 모두: 맨 위 permissions는 `contents: read` 하나뿐이고 작업마다 다시 넓히지 않는다. actions/checkout은
       토큰을 .git/config에 남기지 않는다(`persist-credentials: false`). 모든 `uses:`는 40자리 커밋 SHA로 고정하고 줄
       끝에 릴리스 태그(v7.0.1 꼴)를 주석으로 적는다. 태그는 다른 커밋으로 옮겨질 수 있어 태그로 부른 액션은 검토하지
       않은 코드가 CI에서 돌 수 있고, 줄 끝 주석이 없으면 SHA가 무엇을 고정했는지 알 수 없어 판을 올릴 때 실수한다.
       `on`은 사건별 표이고 `pull_request_target`과 `workflow_run`을 쓰지 않는다(둘 다 바탕 저장소의 권한과 비밀값으로
       돌 수 있는 사건인데, 이 워크플로들은 저장소를 읽고 검사만 한다). 글에 비밀값 문맥(`${{ secrets.… }}`)을 쓰지
       않는다(비밀값이 필요 없고, 쓰는 단계는 포크의 pull request에서 값이 비어 다르게 돈다).
    2. repo-checks.yml: main push, pull request, 수동 실행에서 돌고(경로 필터와 주기 실행은 없다), 전체 이력을 받으며
       (`fetch-depth`가 정수 0), `run`이 있는 단계가 루트 검사 넷(tools/tests 시험 하나와 검사 도구 셋)의 명령과
       차례까지 글자 그대로 같다. 어느 작업이나 단계에도 `continue-on-error`와 `if`가 없다(검사가 실패하면 실행이
       실패해야 하고, 조건이 붙은 단계는 어떤 사건에서 검사를 건너뛸 수 있다).
    3. e2e.yml: 두 오프라인 앱을 띄워 통화 한 건을 흘리고, 나온 리포트를 저장소의 예시와 견준다.
    4. 첫 화면(README.md)의 워크플로 배지가 가리키는 파일이 .github/workflows/에 모두 있다. 없는 워크플로를 가리키면
       화면에 상태가 나오지 않는데 다른 시험은 그것을 잡지 못한다.
    5. 워크플로 폴더의 파일이 구성 요소 다섯의 워크플로와 루트 워크플로 둘뿐이다. 새 파일이 생기면 시험이 실패해, 그
       파일을 루트 워크플로로 두어 위 1번의 규칙을 받게 할지 정하게 한다(정하지 않은 워크플로가 규칙 없이 들어오지
       못한다).
    6. 위 1번을 검사하는 함수(rule_violations) 자체가 규칙 위반을 실제로 잡는다. 아무것도 못 잡는 껍데기가 되면 1번이
       늘 통과하기 때문이다.
    7. 루트 워크플로 둘의 setup-uv 단계는 정확한 uv 판(x.y.z) 하나를 적고, 그 판은 0.13.4 이상이다. 0.13.4 미만은 번들한
       루트 인증서 묶음에 폐기된 중간 CA와 이어진 루트가 들어 있는 판이다(공개 권고 PYSEC-2026-4321).

읽는 것
    워크플로 파일의 글(`uses:` 줄은 글 그대로 한 줄씩, 비밀값 문맥은 글 전체에서 정규식으로, 나머지는 PyYAML가 해석한
    값), 워크플로 폴더의 파일 이름, README.md. GitHub에서 실제로 도는지는 이 시험이 증명하지 못한다. PyYAML가
    필요하다(루트 도구 시험 명령에 `--with pyyaml==6.0.3`이 들어 있다). PyYAML는 YAML 1.1을 따라 키 `on`을 불리언
    True로 읽으므로 raw_on()이 두 꼴을 모두 찾는다(triggers()와 rule_violations()가 이것을 쓴다).
    파일이 없으면 시험은 건너뛰지 않고 실패한다.
"""

import re

import pytest
import yaml
from conftest import REPO

WORKFLOWS = REPO / ".github" / "workflows"

# 이 시험이 규칙을 지키는 루트 워크플로 둘(워크플로 폴더의 파일 이름).
ROOT_WORKFLOWS = ("repo-checks.yml", "e2e.yml")

# 구성 요소 다섯이 각자 자기 폴더를 검사하는 워크플로(워크플로 폴더의 파일 이름). 이 파일은 이들에게 규칙을 걸지 않고 각
# 구성 요소에 맡긴다. 아래 test_every_workflow_file_is_guarded가 이 목록과 ROOT_WORKFLOWS를 합친 것을 폴더의 실제 파일과
# 견주어, 어느 쪽인지 정하지 않은 새 워크플로가 들어오면 실패한다.
COMPONENT_WORKFLOWS = (
    "whisper-ko-ft.yml",
    "stt-scratch.yml",
    "call-summary.yml",
    "support-agent.yml",
    "voice-translator.yml",
)

# 워크플로의 `uses: 소유자/저장소@참조  # 버전` 한 줄. 참조는 40자리 16진수 커밋 SHA여야 하고, 줄 끝 주석에 사람이 읽을
# 수 있는 버전(v7.0.1 같은)이 있어야 한다. support-agent/tests/test_deploy_config.py의 같은 이름 정규식과 글자까지
# 같은 꼴이다(그 구성 요소의 워크플로를 지키는 규칙을 루트 워크플로 둘에도 같은 방법으로 건다).
_USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<action>[^\s@]+)@(?P<ref>\S+)(?:\s+#\s*(?P<version>\S+))?\s*$")
# `uses:`로 시작하는 줄 전부(위 정규식에 맞지 않는 줄도 잡아서 위반으로 알리려고 더 넓게 읽는다).
_USES_LINE = re.compile(r"^\s*(?:-\s*)?uses:")
# 커밋 SHA와 판 주석의 꼴. \d가 다른 나라 숫자까지 받지 않도록 ASCII로 한정한다.
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)
_VERSION = re.compile(r"v\d+\.\d+\.\d+", re.ASCII)

# 루트 워크플로 둘의 `on`에 있으면 안 되는 사건. pull_request_target은 포크에서 온 pull request가 일으켜도 바탕 저장소의
# 권한과 비밀값으로 도는 사건이라, 워크플로가 그 pull request의 코드를 받아 돌리면 포크의 코드가 그 권한으로 실행된다.
# workflow_run도 다른 워크플로의 실행 뒤에 바탕 저장소의 권한으로 돈다. 이 워크플로 둘은 저장소를 읽고 검사만 하므로
# 둘 다 필요 없다.
_FORBIDDEN_EVENTS = ("pull_request_target", "workflow_run")

# GitHub 비밀값 문맥을 쓰는 식의 머리: `${{` 바로 뒤(공백과 줄바꿈은 건너뛴다)에 `secrets.이름`이나 `secrets['이름']`이
# 온다. 낱말 `secrets`만 찾지 않는 까닭은 `run` 글이 파이썬 secrets 모듈을 부르는 것(`import secrets` 따위)은 비밀값
# 문맥이 아니기 때문이다. 이 워크플로 둘은 비밀값이 필요 없고, 비밀값을 쓰는 단계는 포크의 pull request에서 값이 비어
# 다르게 돈다. 대소문자는 가리지 않는다(대문자로 쓴 이름을 놓치지 않으려는 것이다). 글 전체에서 찾으므로 주석 안의 식도
# 잡는다: 글만 보고는 YAML 주석과 `run` 스크립트 안의 셸 주석을 가르기 어렵고, `run` 글의 `${{ }}`는 셸이 읽기 전에
# 값으로 바뀌므로 셸 주석 안에 있어도 쓰인 것이기 때문이다.
_SECRETS_CONTEXT = re.compile(r"\$\{\{\s*secrets\s*[.\[]", re.IGNORECASE)

# README.md의 워크플로 배지 그림 주소에서 워크플로 파일 이름을 뽑는다:
# .../actions/workflows/<파일>/badge.svg?branch=main
_BADGE_FILE = re.compile(r"actions/workflows/(?P<file>[^/\s)]+)/badge\.svg")


def raw_on(workflow: dict):
    """워크플로의 `on` 값을 해석된 그대로 돌려준다. 표가 아닐 수 있고(글자 하나, 목록), 없으면 None이다.

    PyYAML는 YAML 1.1을 따라 키 `on`을 불리언 True로 읽는다. 그래서 문자열 "on"과 True 둘 다 찾는다.
    """
    return workflow.get("on", workflow.get(True))


def triggers(workflow: dict) -> dict:
    """워크플로의 `on` 표(어느 사건에서 도는지).

    표가 아니면(예: `on: push`처럼 글자 하나) 아래 시험이 기대하는 꼴이 아니므로 실패시킨다.
    """
    on = raw_on(workflow)
    assert isinstance(on, dict), f"on이 사건별 표가 아니다: {on!r}"
    return on


def steps_of(workflow: dict) -> list[dict]:
    """워크플로의 모든 작업의 단계를 차례로 모은 목록. 재사용 워크플로를 부르는 작업은 steps가 없어 건너뛴다."""
    return [step for job in workflow["jobs"].values() for step in job.get("steps", [])]


def run_commands(workflow: dict) -> list[str]:
    """`run`이 있는 모든 단계의 명령(셸 글)을 워크플로에 나온 차례대로 모은 목록. 글은 YAML이 해석한 그대로다."""
    return [step["run"] for step in steps_of(workflow) if "run" in step]


def run_text(workflow: dict) -> str:
    """모든 단계의 `run` 글(셸 명령)을 줄바꿈으로 이은 글. 명령이 어느 단계에 있든 글자로 찾으려는 것이다."""
    return "\n".join(run_commands(workflow))


def load_workflow(name: str) -> tuple[str, dict]:
    """루트 워크플로 파일 하나를 (원문, YAML 해석 결과)로 읽는다. 파일이 없으면 FileNotFoundError로 실패한다."""
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def rule_violations(name: str, text: str) -> list[str]:
    """워크플로 글 하나가 권한·사건·비밀값·액션 고정 규칙을 어기는 곳을 한 줄씩 돌려준다. 어기지 않으면 빈 목록이다.

    보는 것(모두 모아서 알린다. 처음 걸리는 것에서 멈추면 고친 뒤에야 다음 위반이 보인다):
        - 맨 위 permissions가 `{"contents": "read"}` 하나다. 작업(job)에는 permissions가 없다.
        - `on`이 사건별 표이고 그 안에 `pull_request_target`과 `workflow_run`이 없다. 표가 아니면(글자 하나나 목록이면,
          또는 없으면) 어느 사건에서 도는지 이 검사가 모두 읽지 못하므로 그것도 위반으로 알린다. 예외로 죽지 않는다.
        - `actions/checkout@` 단계는 `with.persist-credentials`가 불리언 False다(글자 "false"는 받지 않는다).
        - `uses:` 줄은 모두 `_USES` 꼴이고, 참조는 40자리 커밋 SHA, 줄 끝 주석은 `v<숫자>.<숫자>.<숫자>`다.
        - `uses:` 줄이 하나 이상 있고, 줄로 읽은 개수가 YAML이 읽은 개수와 같다. 다르면 줄 검사가 못 보는 꼴
          (예: `- {uses: ...}`)로 쓴 액션이 있다는 뜻이라, 그 액션이 태그로 불려도 못 잡는다.
        - 글에 비밀값 문맥(`${{ secrets.…`)이 없다(`_SECRETS_CONTEXT`). 있으면 그 줄 번호와 줄을 알린다.

    입력: name은 알림 글에 붙이는 파일 이름, text는 워크플로 원문(UTF-8로 읽은 글).
    주의: text가 YAML로 읽히지 않거나 jobs 표가 없으면 예외가 그대로 나간다(규칙 위반이 아니라 깨진 파일이다). 비밀값
    문맥은 글 전체에서 찾으므로 주석에 적은 `${{ secrets.…` 꼴도 위반으로 알린다.
    """
    workflow = yaml.safe_load(text)
    problems: list[str] = []

    # 토큰 권한: 맨 위에서 읽기 하나로 정하고 작업마다 다시 넓히지 않는다.
    if workflow.get("permissions") != {"contents": "read"}:
        problems.append(
            f"{name}: 맨 위 permissions가 contents: read 하나가 아니다: {workflow.get('permissions')!r}"
        )

    # 사건: 바탕 저장소의 권한으로 도는 사건을 쓰지 않는다. `on`이 표가 아니면 사건 이름을 이 검사가 모두 읽지 못하므로
    # 그것도 위반이다. 예외를 내지 않고 알리는 것은 위반을 모아서 보여 주는 이 함수의 약속을 지키려는 것이다.
    on = raw_on(workflow)
    if not isinstance(on, dict):
        problems.append(f"{name}: on이 사건별 표가 아니다(어느 사건에서 도는지 검사할 수 없다): {on!r}")
    else:
        for event in _FORBIDDEN_EVENTS:
            if event in on:
                problems.append(
                    f"{name}: on에 {event} 사건이 있다(바탕 저장소의 권한으로 도는 사건은 쓰지 않는다)"
                )

    parsed_uses: list[str] = []
    for job_name, job in workflow["jobs"].items():
        if "permissions" in job:
            problems.append(f"{name}: 작업 {job_name}에 permissions가 있다(작업 단위로 권한을 넓히지 않는다)")
        if "uses" in job:  # 재사용 워크플로를 부르는 작업
            parsed_uses.append(job["uses"])
        for step in job.get("steps", []):
            if "uses" not in step:
                continue
            parsed_uses.append(step["uses"])
            if (
                step["uses"].startswith("actions/checkout@")
                and (step.get("with") or {}).get("persist-credentials") is not False
            ):
                problems.append(
                    f"{name}: 작업 {job_name}의 actions/checkout 단계에 persist-credentials: false가 없다"
                )

    # 액션 고정: `uses:` 줄을 글 그대로 한 줄씩 본다.
    uses_lines = [line for line in text.splitlines() if _USES_LINE.match(line)]
    if not uses_lines:
        problems.append(f"{name}: uses 줄이 하나도 없다(이 검사가 아무것도 보지 못했다)")
    if len(uses_lines) != len(parsed_uses):
        problems.append(
            f"{name}: 줄로 읽은 uses {len(uses_lines)}개와 YAML이 읽은 uses {len(parsed_uses)}개가 다르다"
            "(줄 검사가 못 보는 꼴로 쓴 uses가 있다)"
        )
    for line in uses_lines:
        found = _USES.match(line)
        if not found:
            problems.append(f"{name}: 읽을 수 없는 uses 줄: {line.strip()}")
            continue
        if not _COMMIT_SHA.fullmatch(found["ref"]):
            problems.append(
                f"{name}: 액션이 40자리 커밋 SHA가 아니라 {found['ref']!r}로 불린다: {line.strip()}"
            )
        if not (found["version"] and _VERSION.fullmatch(found["version"])):
            problems.append(f"{name}: 줄 끝에 v<숫자>.<숫자>.<숫자> 판 주석이 없다: {line.strip()}")

    # 비밀값 문맥: 글 전체에서 찾는다(찾는 꼴과 까닭은 _SECRETS_CONTEXT 위의 주석). 쓴 곳마다 줄 번호와 그 줄을 알린다.
    lines = text.split("\n")
    for hit in _SECRETS_CONTEXT.finditer(text):
        number = text.count("\n", 0, hit.start()) + 1
        problems.append(f"{name}: {number}번째 줄에 비밀값 문맥(secrets)이 있다: {lines[number - 1].strip()}")
    return problems


# 두 루트 워크플로 모두: 토큰은 읽기 전용이고 모든 액션은 커밋 SHA + 판 주석으로 부르며 checkout은 토큰을 남기지 않는다.
# 또 바탕 저장소의 권한으로 도는 사건(pull_request_target, workflow_run)과 비밀값 문맥(`${{ secrets.… }}`)을 쓰지 않는다.
# 시험 이름 뒤에 `[repo-checks.yml]`, `[e2e.yml]`처럼 파일마다 따로 보인다. 파일이 없으면 그 파일 쪽만 실패한다.
@pytest.mark.parametrize("name", ROOT_WORKFLOWS)
def test_root_workflows_pin_actions_and_keep_the_token_read_only(name):
    text, _ = load_workflow(name)
    problems = rule_violations(name, text)
    assert problems == [], "\n".join(problems)


# setup-uv 단계가 설치하는 uv는 0.13.4 이상이어야 한다. uv 0.13.4 미만은 기본으로 쓰는 루트 인증서 묶음(webpki-root-certs)에,
# 개인 키가 유출되어 발급 기관이 폐기한 중간 CA 인증서 여덟 개와 이어진 루트가 들어 있다. 그 키를 가진 쪽은 uv가 받아들이는
# 인증서를 아무 호스트 이름으로나 만들 수 있다(공개 권고 PYSEC-2026-4321 / GHSA-hq85-5cpj-mr62. 0.13.4가 그 루트를 묶음에서
# 뺐다). CI의 uv는 패키지를 내려받는 쪽이라 그 영향 안에 있다. `version`을 아예 적지 않으면 setup-uv가 최신 판을 받아 판이
# 실행마다 달라지므로, 정확한 판 하나가 적혀 있어야 한다. 구성 요소 워크플로(call-summary.yml 등)의 판은 그 구성 요소의 시험이
# 지킨다(call-summary는 tests/test_container.py).
MIN_UV_VERSION = (0, 13, 4)


@pytest.mark.parametrize("name", ROOT_WORKFLOWS)
def test_root_workflows_install_a_uv_release_without_the_revoked_root(name):
    _, workflow = load_workflow(name)
    versions = [
        (step.get("with") or {}).get("version")
        for step in steps_of(workflow)
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
    ]
    assert versions, f"{name}: astral-sh/setup-uv 단계가 없다(이 검사가 아무것도 보지 못했다)"
    for version in versions:
        assert isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version, re.ASCII), (
            f"{name}: setup-uv의 version이 정확한 판(x.y.z) 하나가 아니다: {version!r}"
        )
        assert tuple(int(part) for part in version.split(".")) >= MIN_UV_VERSION, (
            f"{name}: setup-uv가 uv {version}을 설치한다(폐기된 루트를 믿는 0.13.4 미만)"
        )


# repo-checks.yml에서 `run`이 있는 단계가 돌려야 하는 명령 전부, 워크플로에 나온 차례 그대로. 첫째가 tools/tests의 시험이고
# 나머지 셋이 루트 검사 도구다. `run` 글에 경로가 들어 있는지만 보면 명령 뒤에 `|| true`를 붙여 실패를 지우거나 `echo`로
# 바꾸거나 다른 단계를 더해도 통과해서, 검사를 돌리는 척만 하는 워크플로가 된다. 그래서 글자 그대로 견주고 이 목록 밖의
# `run` 단계도 받지 않는다. 명령을 일부러 바꿀 때(도구 판 올림, 검사 추가·제거)는 워크플로와 이 목록을 함께 고친다.
REPO_CHECKS_COMMANDS = [
    "uv run --no-project --with pytest==9.1.1 --with pyyaml==6.0.3 pytest tools/tests -q -p no:cacheprovider",
    "uv run --no-project tools/check_root_numbers.py",
    "uv run --no-project tools/check_links.py",
    "uv run --no-project tools/check_cross_deps.py",
]


# repo-checks.yml이 루트 검사를 모두 돌리는지. 어느 단계를 지워도 다른 시험이 깨지지 않으므로 글자로 고정한다.
def test_repo_checks_runs_every_root_check():
    _, workflow = load_workflow("repo-checks.yml")
    # 첫 화면의 배지(`repo-checks`)가 이 이름과 파일을 가리킨다(아래 배지 시험이 파일을, 이 줄이 이름을 지킨다).
    assert workflow.get("name") == "repo-checks"
    on = triggers(workflow)
    assert on["push"]["branches"] == ["main"]
    assert "pull_request" in on
    assert "workflow_dispatch" in on
    # 주기 실행은 저장소에 정기 실행을 만드는 지속 설정이라 넣지 않는다. 다시 돌리려면 수동 실행을 쓴다.
    assert "schedule" not in on
    # 경로 필터가 없다: 루트 수치의 출처가 구성 요소 README이고 링크·의존 선언도 구성 요소 안의 파일을 가리켜서, 어느
    # 폴더가 바뀌어도 이 검사가 깨질 수 있다.
    for event in ("push", "pull_request"):
        assert not {"paths", "paths-ignore"} & set(on[event] or {}), f"{event}에 경로 필터가 있다"

    # 전체 이력을 받는다(`fetch-depth: 0`). 기본값은 마지막 커밋 하나인데, 그러면 두 곳(두 파일의 시험 셋)이 CI에서만
    # 실패한다. 시험 하나는 test_check_cross_deps.py의 test_repository_dependencies_hold로, 이 저장소 자신의 선언으로
    # tools/check_cross_deps.py가 고정 사본의 원본 커밋을 이력에서 푼다. 시험 둘은 tools/tests/test_docs.py의
    # test_history_names_every_original_head_and_address(태그 archive/<이름>)와
    # test_history_names_the_move_and_merge_commits(HEAD에서 닿는 이동·병합 커밋)다. 이 단언이 두 파일의 주석("저장소 검사
    # 워크플로는 전체 이력을 받는다", "이 시험을 돌리는 CI는 전체 이력과 태그를 받아야 한다")이 기대는 약속을 지킨다.
    checkouts = [
        step for step in steps_of(workflow) if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert checkouts, "actions/checkout 단계가 없다"
    for step in checkouts:
        depth = (step.get("with") or {}).get("fetch-depth")
        # 정수 0만 받는다. 파이썬에서는 False == 0이 참이라 `== 0`만 쓰면 `fetch-depth: false`도 통과한다.
        assert type(depth) is int and depth == 0, (
            f"actions/checkout의 fetch-depth가 정수 0이 아니다: {depth!r}"
        )

    # 시험 하나와 검사 도구 셋을 모두, 정해 둔 명령 그대로 돈다(REPO_CHECKS_COMMANDS 위의 주석).
    assert run_commands(workflow) == REPO_CHECKS_COMMANDS, (
        "repo-checks.yml의 run 명령이 정해 둔 목록과 다르다"
    )

    # 검사가 실패하면 실행이 실패해야 한다. 그래서 어느 작업과 단계에도 `continue-on-error`(실패해도 통과로 센다)와 `if`가
    # 없다. 조건이 붙은 작업이나 단계는 어떤 사건에서 검사를 건너뛸 수 있고, 건너뛰어도 실행은 실패하지 않는다.
    # (e2e.yml에는 성공·실패와 상관없이 로그를 남기는 `if: always()` 단계가 있어서 이 단언은 repo-checks.yml에만 건다.)
    for job_name, job in workflow["jobs"].items():
        assert not {"continue-on-error", "if"} & set(job), f"작업 {job_name}에 continue-on-error나 if가 있다"
        for step in job.get("steps", []):
            label = step.get("name") or step.get("uses") or step.get("run")
            assert not {"continue-on-error", "if"} & set(step), (
                f"작업 {job_name}의 단계 {label!r}에 continue-on-error나 if가 있다"
            )


# e2e.yml이 두 오프라인 앱을 모두 띄우고, 통화 한 건을 돌린 뒤 리포트를 저장소의 예시와 견주는지.
def test_e2e_runs_both_offline_apps_and_compares_the_example():
    _, workflow = load_workflow("e2e.yml")
    on = triggers(workflow)
    assert on["push"]["branches"] == ["main"]
    assert "pull_request" in on
    assert "schedule" not in on
    # e2e/README.md가 "경로 필터가 없어 어느 폴더가 바뀌어도 돈다"고 말한다.
    for event in ("push", "pull_request"):
        assert not {"paths", "paths-ignore"} & set(on[event] or {}), f"{event}에 경로 필터가 있다"

    commands = run_text(workflow)
    for expected in (
        "support_agent.service.offline:create_offline_app",
        "call_summary.service:create_offline_app",
        "call-e2e --script calls/shop-cancel.json",
        "diff -u e2e/examples/shop-cancel",
    ):
        assert expected in commands, f"e2e.yml의 run에 {expected}가 없다"


# 첫 화면의 워크플로 배지가 가리키는 파일이 모두 있어야 한다. 없는 워크플로를 가리키면 화면에 상태가 나오지 않는데,
# 다른 시험은 그것을 잡지 못한다.
def test_readme_badges_point_to_existing_workflows():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    files = sorted({found["file"] for found in _BADGE_FILE.finditer(readme)})
    # 하나도 못 뽑으면 정규식이나 README의 배지 꼴이 바뀐 것이다. 빈 목록으로 조용히 통과하지 않게 실패시킨다.
    assert files, "README.md에서 워크플로 배지(actions/workflows/<파일>/badge.svg)를 하나도 찾지 못했다"
    # 폴더에 실제로 있는 이름과 글자 그대로 견준다. is_file()은 대소문자를 구분하지 않는 파일 시스템(Windows 기본값)에서
    # 대소문자가 틀린 이름도 통과시켜, 어느 PC에서 돌리느냐에 따라 결과가 달라진다.
    existing = {path.name for path in WORKFLOWS.iterdir() if path.is_file()}
    missing = [file for file in files if file not in existing]
    assert missing == [], (
        f"README.md의 배지가 가리키는데 {WORKFLOWS.relative_to(REPO).as_posix()}/에 없는 워크플로: {missing}"
    )


# 워크플로 폴더의 모든 파일이 어느 규칙을 받는지 정해져 있어야 한다. 위 규칙(권한·액션 고정·사건·비밀값)은 ROOT_WORKFLOWS의
# 파일에만 걸리므로, 새 워크플로를 더하고 어느 목록에도 넣지 않으면 그 파일은 규칙을 하나도 받지 않는데 다른 시험은 그것을
# 잡지 못한다. 그래서 폴더의 파일 이름을 구성 요소 다섯의 것과 ROOT_WORKFLOWS를 합친 목록과 글자 그대로 견주고, 어긋나면
# 실패시켜 새 파일을 어느 쪽에 둘지 사람이 정하게 한다. 목록에 있는 파일이 없어진 경우도 함께 잡는다(목록과 README의 배지가
# 낡았다는 뜻이다).
def test_every_workflow_file_is_guarded():
    existing = {path.name for path in WORKFLOWS.iterdir() if path.is_file()}
    known = set(COMPONENT_WORKFLOWS) | set(ROOT_WORKFLOWS)
    unlisted = sorted(existing - known)
    gone = sorted(known - existing)
    folder = WORKFLOWS.relative_to(REPO).as_posix()
    assert not unlisted and not gone, (
        f"{folder}/의 파일이 이 시험의 목록과 다르다. 목록에 없는 파일: {unlisted}, 목록에는 있는데 폴더에 없는 파일: {gone}.\n"
        "새 워크플로 파일이면 어느 쪽인지 정한다. 구성 요소에 속하지 않는 워크플로(루트 검사 같은 것)이면 ROOT_WORKFLOWS에\n"
        "넣어 위 규칙을 받게 하고, 구성 요소의 워크플로이면 그 구성 요소가 규칙을 지키게 한 뒤 COMPONENT_WORKFLOWS에 넣는다.\n"
        "지우거나 이름을 바꾼 것이면 두 목록과 README.md의 배지도 맞춰 고친다."
    )


# 규칙을 지키는 가장 작은 워크플로. 아래 시험이 이 글에서 한 곳씩 어긴 판을 만들어, rule_violations가 그 위반을
# 실제로 잡는지 본다. (이 시험이 없으면 검사 함수가 아무것도 못 잡게 고쳐져도 위 시험은 계속 통과한다.)
_SHA_REF = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
_PINNED_CHECKOUT = f"{_SHA_REF} # v7.0.1"
_CHECKOUT_STEP = f"      - uses: {_PINNED_CHECKOUT}\n        with:\n          persist-credentials: false\n"
_ON_TABLE = "on:\n  push:\n    branches: [main]\n"
_COMPLIANT = f"""\
name: sample
{_ON_TABLE}permissions:
  contents: read
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
{_CHECKOUT_STEP}      - run: echo ok
"""


def test_rule_check_passes_a_compliant_workflow():
    problems = rule_violations("sample.yml", _COMPLIANT)
    assert problems == [], "\n".join(problems)


# (바꿀 글, 새 글, 알림에 들어 있어야 하는 글, 시험 이름). 바꿀 글이 _COMPLIANT에 실제로 있는지도 시험이 본다.
@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        pytest.param(_PINNED_CHECKOUT, "actions/checkout@v7", "40자리 커밋 SHA", id="action-pinned-to-a-tag"),
        pytest.param(_PINNED_CHECKOUT, _SHA_REF, "판 주석", id="no-version-comment"),
        pytest.param(
            "  contents: read\n", "  contents: write\n", "contents: read 하나", id="token-can-write"
        ),
        pytest.param(
            "permissions:\n  contents: read\n", "", "contents: read 하나", id="no-top-level-permissions"
        ),
        pytest.param(
            "    runs-on: ubuntu-latest\n",
            "    runs-on: ubuntu-latest\n    permissions:\n      contents: write\n",
            "작업 checks에 permissions",
            id="job-level-permissions",
        ),
        pytest.param(
            "persist-credentials: false",
            "persist-credentials: true",
            "persist-credentials",
            id="credentials-kept",
        ),
        pytest.param(
            "        with:\n          persist-credentials: false\n",
            "",
            "persist-credentials",
            id="checkout-without-with",
        ),
        pytest.param(
            _CHECKOUT_STEP,
            '      - {uses: "actions/checkout@v7", with: {persist-credentials: false}}\n',
            "YAML이 읽은 uses",
            id="uses-hidden-from-the-line-scan",
        ),
        pytest.param(
            _ON_TABLE,
            _ON_TABLE + "  pull_request_target:\n",
            "pull_request_target 사건이 있다",
            id="event-pull-request-target",
        ),
        pytest.param(
            _ON_TABLE,
            _ON_TABLE + "  workflow_run:\n    workflows: [other]\n    types: [completed]\n",
            "workflow_run 사건이 있다",
            id="event-workflow-run",
        ),
        # `on`이 표가 아닌 꼴: 예외로 죽지 않고 위반으로 알려야 한다. 목록에 위험한 사건이 들어 있어도 표가 아니라는 알림이
        # 나온다(사건 이름은 표일 때만 읽는다).
        pytest.param(_ON_TABLE, "on: push\n", "사건별 표가 아니다", id="on-is-a-string"),
        pytest.param(_ON_TABLE, "on: [push, pull_request_target]\n", "사건별 표가 아니다", id="on-is-a-list"),
        pytest.param(_ON_TABLE, "", "사건별 표가 아니다", id="no-on"),
        # 비밀값 문맥: 입력 값, 공백 없는 꼴, 대괄호 꼴. 모두 `${{` 바로 뒤에 `secrets`가 온다.
        pytest.param(
            "          persist-credentials: false\n",
            "          persist-credentials: false\n          token: ${{ secrets.EXAMPLE }}\n",
            "비밀값 문맥",
            id="secrets-context-in-checkout-input",
        ),
        pytest.param(
            "      - run: echo ok\n",
            '      - run: echo "${{secrets.EXAMPLE}}"\n',
            "비밀값 문맥",
            id="secrets-context-without-spaces",
        ),
        pytest.param(
            "      - run: echo ok\n",
            "      - run: echo \"${{ secrets['EXAMPLE'] }}\"\n",
            "비밀값 문맥",
            id="secrets-context-with-brackets",
        ),
    ],
)
def test_rule_check_flags_each_kind_of_violation(old, new, expected):
    assert old in _COMPLIANT, "시험 자료가 바뀌어 고칠 글을 찾지 못했다"
    problems = rule_violations("sample.yml", _COMPLIANT.replace(old, new))
    assert any(expected in problem for problem in problems), problems


# 낱말 secrets만으로는 위반이 아니다. `run` 글이 파이썬 secrets 모듈을 부르는 경우이고, 같은 글에 `${{ }}` 식도 함께 있다.
# secrets는 식 바깥의 낱말이라 비밀값 문맥이 아니다. 비밀값 규칙의 정규식이 넓어져(예: `${{` 뒤 어디든 secrets가 있으면
# 건다) 이런 글을 잘못 잡으면 정상 워크플로가 막히므로 이 경우를 따로 지킨다.
def test_rule_check_does_not_mistake_the_python_secrets_module_for_the_secrets_context():
    step = (
        '      - run: echo "${{ github.ref }}" && python -c "import secrets; print(secrets.token_hex(8))"\n'
    )
    problems = rule_violations("sample.yml", _COMPLIANT.replace("      - run: echo ok\n", step))
    assert problems == [], "\n".join(problems)
