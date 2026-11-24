"""`tools/check_evidence.py` 시험.

이 도구는 추적 파일(HEAD의 내용)에 적힌 커밋 해시 참조가 이 저장소의 git 이력과 맞는지 본다. 7~40자
16진수 낱말을 뽑아 이력으로 풀어 보고, 풀리는데 HEAD의 조상이 아니거나 둘 이상에 맞으면(모호) 알리고,
문서(.md)가 커밋 참조라고 밝혀 적은 낱말이 풀리지 않으면 알린다. 다른 저장소의 해시는 등록 파일
(tools/evidence.toml)의 [[external]]로 면제하고, 낡거나 잘못된 등록도 알린다. 같은 등록 파일의 [[record]]가
가리키는 기록 파일(JSON)에 적힌 커밋 값과, [[pair]]에 등록한 '규칙 → 결과' 짝의 순서도 본다. 한 시험은 한
가지만 어긋나게 해서, 어느 규칙이 어떤 문제를 냈는지 시험이 정확히 가리킬 수 있게 한다. 아래 아홉 구역을 이
파일의 구역 순서대로 고정한다.
    1. 낱말 뽑기: 7~40자 소문자 16진수를 ASCII 경계로(뒤에 한글 조사가 붙어도) 줄 번호와 함께 뽑고, 문서가
       커밋 참조로 적었는지(백틱 한 쌍, `커밋`·`commit` 바로 뒤)도 함께 돌려준다. 백틱 쌍은 줄마다 맞추고, 한 줄에
       감싼 낱말이 수천 개여도 느려지지 않는다. a~f 글자가 하나도 없는 숫자뿐인 것은 그렇게 적은 자리에 있을
       때만 낱말이다(날짜나 숫자 꼬리를 해시로 읽지 않으려는 것이다).
    2. 이력으로 풀기: 앞부분이 같은 커밋을 찾고, 둘 이상이면 모호다.
    3. 규칙 3·4: 풀리는 낱말은 HEAD의 조상이어야 하고, 문서가 커밋 참조로 적은 낱말은 풀려야 한다.
    4. 규칙 5와 등록 파일: 등록은 그 파일의 그 낱말만 면제하고, 낡거나 잘못된 등록과 꼴이 틀린 항목은 알린다.
    5. 읽는 대상: HEAD의 내용만 읽고(작업 트리·색인에 흔들리지 않는다), 잠금 파일·글이 아닌 파일·기호 링크·
       서브모듈은 건너뛰고, UTF-8이 아닌 글도 멈추지 않는다. 어느 ref에서도 닿지 않는 커밋은 세지 않는다.
    6. 시작할 수 없음: 얕은 복제, git 실패, 저장소가 아님, 커밋 없음은 종료 2다(읽지 못했는데 통과하지 않는다).
    7. 명령줄: 종료 코드 0·1·2, 출력 꼴과 정렬, --report-only, 파이프로 나가는 UTF-8 출력, 도움말, 읽기 명령만 부름.
    8. 기록 파일의 커밋 값([[record]]): glob에 맞는 HEAD의 파일(.jsonl은 줄마다)에서 모든 깊이의 키를 찾아 센다.
       값이 커밋 꼴이고, 이 저장소의 커밋 하나로 풀리고, HEAD의 조상이어야 한다. 같은 객체에 git_tree가 있으면 그
       커밋의 구성 요소 폴더 트리와 같아야 한다. 맞는 파일이 없으면 낡은 등록이고, 등록한 키가 맞는 파일 어디에도 없으면
       그 키의 문제(오타이거나 낡은 등록)이며, 읽을 수 없는 파일은 종료 2다.
    9. 등록한 짝([[pair]]): 두 커밋이 풀리고 조상이며, 서로 다르고, 규칙이 결과의 조상이고, 커밋 시각이 거꾸로
       가지 않고(같은 초는 된다), where 문서에 두 해시의 앞 7자가 글자로 있어야 한다.

시험용 저장소는 임시 폴더에 빈 git 저장소를 만들고 커밋을 쌓아 꾸민다. 고정물 world는 main에 커밋 셋(first →
second → third)을 쌓고, 그 사이에 갈라진 side 브랜치에만 있는 커밋 하나(main에 합치지 않는다)를 둔다. second는
구성 요소 폴더 comp를 처음 만든다(기록 파일 시험이 그 폴더의 트리를 쓴다. first에는 comp가 없다). third의
문서와 코드는 앞선 두 커밋의 앞 7자를 적고 있어서 처음 상태에서는 문제가 없다. 이 저장소를 만드는 데 git을
스무 번쯤 부르므로, 원본을 모듈에서 한 번만 만들고(world_template) 시험마다 그 폴더를 복사해 쓴다. 저장소가
필요 없는 시험(낱말 뽑기, 풀이, 등록 파일의 꼴)은 world를 쓰지 않는다. 앞 7자가 모두 숫자인 해시는 참조 표시
없이 적으면 낱말이 아니므로, 시험이 표시 없이 문서에 적는 해시는 short()로 줄인 것만 쓴다(해시는 고를 수 없어
앞 7자가 숫자뿐인 진짜 커밋은 만들 수 없다. 그런 낱말이 풀리는 쪽은 가짜 커밋을 넣은 순수 함수로 본다). 등록
파일은 저장소 안 tools/evidence.toml에 추적하지 않는 파일로 쓴다(도구는 등록 파일만 작업 트리에서 읽고, 검사
대상은 HEAD에서 읽는다). 이 저장소 자신을 대상으로 하는 시험은 이 파일에 없다.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

import check_evidence
import pytest
from check_evidence import (
    Problem,
    Registry,
    build_prefix_index,
    check_references,
    find_tokens,
    judge_file,
    load_registry,
    main,
    resolve,
    scan_references,
)

# 이 파일은 <저장소>/tools/tests/에 있다. parents[1] = tools. 도구를 스크립트로 직접 돌리는 시험이 쓴다.
TOOLS = Path(__file__).resolve().parents[1]

# 어느 커밋의 앞부분도 아닌 7자 낱말. 시험 저장소의 커밋 해시는 만들 때마다 달라지므로, 이 낱말이 정말 어느
# 커밋의 앞부분도 아닌지는 쓰는 시험이 assert_not_a_commit_prefix로 확인한다.
FAKE = "1234abc"


def write(root: Path, rel: str, content: str | bytes) -> Path:
    """root 아래 rel 경로에 content를 쓴다. 글은 UTF-8(BOM 없음), 줄바꿈 LF. 폴더가 없으면 만든다."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="\n")
    return path


def git(repo: Path, *args: str) -> str:
    """repo 안에서 git을 부르고 표준 출력(앞뒤 공백 제외)을 돌려준다. 실패하면 CalledProcessError."""
    done = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return done.stdout.strip()


def commit_files(
    repo: Path, files: dict[str, str | bytes], message: str, *, date: str | None = None
) -> str:
    """files를 쓰고 그 파일만 스테이징해 커밋한 뒤, 새 커밋의 40자 해시를 돌려준다.

    date를 주면(예: 2026-01-02T03:04:05+0000) 작성 시각과 커밋 시각을 그 값으로 정한다. 커밋 시각이 같은 초이거나
    거꾸로 간 커밋을 만들 때 쓴다.
    """
    for rel, content in files.items():
        write(repo, rel, content)
    git(repo, "add", "--", *files)
    if date is None:
        git(repo, "commit", "--quiet", "-m", message)
    else:
        env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        subprocess.run(
            ["git", "commit", "--quiet", "-m", message], cwd=repo, check=True, capture_output=True, env=env
        )
    return git(repo, "rev-parse", "HEAD")


def commit_seconds(repo: Path, commit: str) -> int:
    """commit의 커밋 시각(초). 사용자 설정(서명 확인 줄)이 끼지 않게 --no-show-signature를 붙인다."""
    return int(git(repo, "show", "-s", "--no-show-signature", "--format=%ct", commit))


def short(commit: str, length: int = 7) -> str:
    """commit의 앞 length자를 돌려준다. 그 앞부분이 숫자뿐이면 a~f 글자가 나올 때까지 늘린다.

    숫자뿐인 글자열은 날짜나 숫자 꼬리와 구별되지 않아, 백틱 한 쌍 안이나 `커밋`·`commit` 바로 뒤 같은 참조
    표시가 없으면 낱말로 뽑지 않는다(규칙 2). 해시마다 앞부분이 달라 시험이 흔들리지 않도록, 시험이 문서에
    적는 해시는 표시가 있든 없든 늘 이 함수로 줄인다.
    """
    while length < len(commit) and commit[:length].isdigit():
        length += 1
    return commit[:length]


def assert_not_a_commit_prefix(repo: Path, word: str) -> None:
    """word가 이 저장소의 어느 커밋(떠 있는 객체까지)의 앞부분도 아님을 확인한다. 시험의 전제다."""
    commits = git(repo, "rev-list", "--all").split()
    assert not any(commit.startswith(word) for commit in commits), word


def external_entry(word: str, where: str, what: str = "다른 저장소의 커밋") -> str:
    """등록 파일의 [[external]] 항목 하나(뒤에 빈 줄)."""
    return f'[[external]]\nhash = "{word}"\nwhere = "{where}"\nwhat = "{what}"\n\n'


def record_rule(
    glob: str, keys: list[str], component: str = "comp", what: str = "기록 파일의 커밋 값"
) -> str:
    """등록 파일의 [[record]] 항목 하나(뒤에 빈 줄)."""
    names = ", ".join(f'"{key}"' for key in keys)
    return f'[[record]]\nglob = "{glob}"\nkeys = [{names}]\ncomponent = "{component}"\nwhat = "{what}"\n\n'


def pair_rule(
    pair_id: str, rule: str, result: str, where: str, what: str = "규칙 커밋 뒤에 잰 결과"
) -> str:
    """등록 파일의 [[pair]] 항목 하나(뒤에 빈 줄)."""
    return (
        f'[[pair]]\nid = "{pair_id}"\nrule = "{rule}"\nresult = "{result}"\n'
        f'where = "{where}"\nwhat = "{what}"\n\n'
    )


@dataclass
class World:
    """시험용 저장소 하나와 그 커밋들(40자 해시)."""

    repo: Path
    first: str  # main의 첫 커밋
    second: str  # main의 둘째 커밋. side 브랜치가 여기서 갈라진다.
    third: str  # main의 끝(HEAD). 문서와 코드가 first·second의 앞 7자를 적고 있다.
    side: str  # side 브랜치에만 있는 커밋(HEAD의 조상이 아니다)

    @property
    def registry_path(self) -> Path:
        """등록 파일 경로(<저장소>/tools/evidence.toml, 도구의 기본 위치와 같다)."""
        return self.repo / "tools" / "evidence.toml"

    def set_registry(self, text: str = "") -> Path:
        """등록 파일을 text로 쓴다(추적하지 않는다)."""
        return write(self.repo, "tools/evidence.toml", text)


def init_repo(path: Path) -> None:
    """path에 빈 git 저장소를 만든다. 설정은 conftest의 git_repo 고정물과 같다.

    world의 원본은 모듈 범위로 한 번만 만드는데 git_repo는 시험마다 새로 만드는 고정물이라 그대로 쓸 수 없어,
    같은 설정을 여기서 되풀이한다: 줄바꿈 변환 끔, 시험용 신원, 서명 끔, 초기 브랜치 main.
    """
    for args in (
        ("init", "--quiet", "--initial-branch=main"),
        ("config", "core.autocrlf", "false"),
        ("config", "user.name", "Test User"),
        ("config", "user.email", "test@example.com"),
        ("config", "commit.gpgsign", "false"),
    ):
        git(path, *args)


@pytest.fixture(scope="module")
def world_template(tmp_path_factory) -> World:
    """위 머리말의 고정물 원본을 모듈에서 한 번만 만든다. HEAD는 main의 끝(third)이다.

    이 저장소를 만드는 데 git을 스무 번쯤 부르므로 시험마다 만들면 이 파일만 몇 분이 걸린다. 그래서 한 번
    만들어 두고, 시험이 쓰는 world는 이 원본을 통째로 복사한 것이다. 원본은 시험이 고치지 않는다.
    """
    repo = tmp_path_factory.mktemp("world-template")
    init_repo(repo)
    first = commit_files(repo, {"src/app.py": "VALUE = 1\n"}, "Add the app module")
    # second는 구성 요소 폴더 comp를 처음 만든다. first에는 comp가 없다(기록 파일의 git_tree 시험이 쓴다).
    second = commit_files(
        repo, {"src/app.py": "VALUE = 2\n", "comp/code.py": "VALUE = 2\n"}, "Change the value"
    )
    # side 브랜치는 second에서 갈라져 커밋 하나를 갖고, main에 합치지 않는다. 그래서 이 커밋은 이 저장소의
    # 커밋이면서 HEAD의 조상이 아니다.
    git(repo, "switch", "--quiet", "--create", "side")
    side = commit_files(repo, {"side.txt": "only on the side branch\n"}, "Add a side file")
    git(repo, "switch", "--quiet", "main")
    third = commit_files(
        repo,
        {
            "src/app.py": f"# 근거: {short(first)}\nVALUE = 2\n",
            "docs/notes.md": (
                "# 기록\n"
                "\n"
                f"- 처음 값은 커밋 `{short(first)}`에서 정했다.\n"
                f"- 바꾼 값은 {short(second)}의 결과다.\n"
            ),
        },
        "Cite the earlier commits",
    )
    return World(repo=repo, first=first, second=second, third=third, side=side)


@pytest.fixture
def world(world_template: World, tmp_path: Path) -> World:
    """시험마다 새로 쓰는 고정물: 원본 저장소를 tmp_path 안으로 복사한다(견본 훅 파일은 빼고 복사한다)."""
    repo = tmp_path / "repo"
    shutil.copytree(world_template.repo, repo, ignore=shutil.ignore_patterns("*.sample"))
    return replace(world_template, repo=repo)


def problems_of(world: World, registry_text: str = "") -> list[Problem]:
    """등록 파일을 registry_text로 쓰고 읽어, 고정물의 HEAD를 검사한 문제들."""
    registry = load_registry(world.set_registry(registry_text), display="tools/evidence.toml")
    return check_references(world.repo, registry)


def records_of(world: World, registry_text: str) -> list[Problem]:
    """등록 파일을 registry_text로 쓰고 읽어, 고정물의 HEAD에 [[record]] 검사를 한 문제들."""
    registry = load_registry(world.set_registry(registry_text), display="tools/evidence.toml")
    return check_evidence.check_records(world.repo, registry)


def pairs_of(world: World, registry_text: str) -> list[Problem]:
    """등록 파일을 registry_text로 쓰고 읽어, 고정물의 HEAD에 [[pair]] 검사를 한 문제들."""
    registry = load_registry(world.set_registry(registry_text), display="tools/evidence.toml")
    return check_evidence.check_pairs(world.repo, registry)


def parse_registry(folder: Path, text: str) -> Registry:
    """등록 파일을 folder에 text로 쓰고 읽는다. 저장소 없이 등록 파일의 꼴만 볼 때 쓴다."""
    return load_registry(write(folder, "evidence.toml", text), display="tools/evidence.toml")


def places(problems: list[Problem]) -> list[tuple[str, str, int]]:
    """문제들을 (종류, 파일, 줄)로 줄여 본다."""
    return [(problem.kind, problem.path, problem.line) for problem in problems]


# ---------------------------------------------------------------------------------------------
# 1. 낱말 뽑기
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "words"),
    [
        pytest.param("abcdef0", ["abcdef0"], id="7자는 하한"),
        pytest.param("abcdef", [], id="6자는 모자란다"),
        pytest.param("a" * 40, ["a" * 40], id="40자는 상한"),
        pytest.param("a" * 41, [], id="41자부터는 더 긴 글자열의 일부"),
        pytest.param("12345678", [], id="참조 표시 없는 숫자뿐인 글자열은 낱말이 아니다"),
        pytest.param("날짜 20261124 기준", [], id="날짜 같은 숫자뿐인 글자열"),
        pytest.param("`12345678`", ["12345678"], id="백틱 통째로 든 숫자뿐인 글자열은 낱말이다"),
        pytest.param("커밋 12345678", ["12345678"], id="커밋 뒤의 숫자뿐인 글자열은 낱말이다"),
        pytest.param("commit 12345678", ["12345678"], id="commit 뒤의 숫자뿐인 글자열은 낱말이다"),
        pytest.param("`1234567`과 1234567", ["1234567"], id="숫자뿐인 낱말은 표시가 달린 것만 뽑는다"),
        pytest.param("1234567a", ["1234567a"], id="숫자 사이에 a~f 하나면 된다"),
        pytest.param("ABCDEF0", [], id="대문자는 뽑지 않는다"),
        pytest.param("abcdef0g", [], id="16진수가 아닌 영문자가 붙은 글자열의 일부"),
        pytest.param("_abcdef0", [], id="앞 밑줄은 낱말 글자"),
        pytest.param("abcdef0_x", [], id="뒤 밑줄은 낱말 글자"),
        pytest.param("v-abcdef0.py", ["abcdef0"], id="하이픈과 점은 경계"),
        pytest.param("한글abcdef0의 결과", ["abcdef0"], id="앞뒤에 한글이 붙어도 뽑는다"),
        pytest.param("abcdef0 1234abc", ["abcdef0", "1234abc"], id="한 줄에 둘"),
    ],
)
def test_find_tokens_picks_hex_words_with_ascii_boundaries(text, words):
    assert [word for _, word, _ in find_tokens(text)] == words


def test_find_tokens_counts_lines_by_newline_only():
    # 줄 번호는 \n으로 센다. 줄 끝의 CR은 낱말 글자가 아니라 낱말을 막지 않는다.
    text = "첫 줄\r\n둘째 abcdef0\r\n\r\n넷째 `1234abc` 와 커밋 2345bcd\n"
    assert find_tokens(text) == [
        (2, "abcdef0", False),
        (4, "1234abc", True),
        (4, "2345bcd", True),
    ]


# 문서가 커밋 참조로 적은 자리인지 가르는 글 24가지. 글 속의 `1234abc`가 시험할 낱말이고, 둘째 값은 그 낱말을 커밋
# 참조로 적었다고 보는지다. 낱말이 a~f 글자가 든 꼴(아래 첫째 시험)과 숫자뿐인 꼴(둘째 시험)에 같은 표를 쓴다.
CLAIM_CASES = [
    # 백틱 한 쌍 안이 통째로 그 낱말이면 커밋 참조로 적은 것이다.
    pytest.param("`1234abc`", True, id="백틱 한 쌍"),
    pytest.param("`1234abc`의 결과", True, id="백틱 뒤에 한글"),
    pytest.param("``1234abc``", True, id="백틱 둘로 감싼 쌍"),
    pytest.param("`1234abc 외`", False, id="백틱 안에 다른 글자가 함께 있다"),
    pytest.param("`외 1234abc`", False, id="백틱 안 앞에 다른 글자"),
    pytest.param("`x`1234abc`y`", False, id="이웃한 백틱이 서로 다른 쌍에 속한다"),
    # 커밋·commit(대소문자 무시) 뒤에 공백·탭·백틱·여는 괄호만 두고 오면 커밋 참조로 적은 것이다.
    pytest.param("커밋 1234abc에서", True, id="커밋 뒤"),
    pytest.param("commit 1234abc", True, id="commit 뒤"),
    pytest.param("Commit 1234abc", True, id="Commit"),
    pytest.param("COMMIT 1234abc", True, id="COMMIT"),
    pytest.param("커밋 `1234abc`", True, id="커밋 뒤의 백틱"),
    pytest.param("커밋(1234abc)", True, id="커밋 뒤의 여는 괄호"),
    pytest.param("(commit 1234abc)", True, id="괄호 안의 commit"),
    pytest.param("커밋1234abc", True, id="사이에 아무것도 없어도 된다"),
    pytest.param("커밋 \t 1234abc", True, id="공백과 탭 여러 개"),
    pytest.param("commits 1234abc", False, id="commits는 아니다"),
    pytest.param("committed 1234abc", False, id="committed는 아니다"),
    pytest.param("recommit 1234abc", False, id="앞 글자가 영문자면 아니다"),
    pytest.param("커밋: 1234abc", False, id="쌍점은 사이에 올 수 없다"),
    pytest.param("커밋들 1234abc", False, id="커밋들은 아니다"),
    pytest.param("SHA-256 1234abc…", False, id="다른 낱말 뒤"),
    pytest.param("https://example.com/org/repo/commit/1234abc", False, id="주소 안의 commit"),
    pytest.param("1234abc", False, id="아무 표시도 없다"),
    pytest.param("커밋\n1234abc", False, id="줄을 넘어서는 보지 않는다"),
]


@pytest.mark.parametrize(("text", "claimed"), CLAIM_CASES)
def test_find_tokens_tells_whether_the_document_claims_a_commit(text, claimed):
    found = find_tokens(text)
    assert [word for _, word, _ in found] == ["1234abc"]
    assert found[0][2] is claimed


@pytest.mark.parametrize(("text", "claimed"), CLAIM_CASES)
def test_find_tokens_takes_a_digit_only_word_only_where_it_is_claimed(text, claimed):
    # a~f 글자가 하나도 없는 숫자뿐인 낱말은 같은 표에서 참조로 적은 자리일 때만 낱말이다. 그 밖에는 날짜나 숫자
    # 꼬리일 수 있어 버린다. 낱말로 뽑힌 것의 셋째 값은 늘 참이다.
    found = find_tokens(text.replace("1234abc", "1234567"))
    assert found == ([(1, "1234567", True)] if claimed else [])


def test_backtick_pairs_are_judged_line_by_line():
    # 백틱 쌍은 줄마다 따로 맞춘다. 앞 줄의 쌍이 다음 줄의 판정으로 새어 들어오면 안 된다: 아래 첫째 줄과 둘째 줄은 낱말이
    # 줄 안의 같은 자리에 있고 양옆이 모두 백틱이지만, 첫째 줄에서만 백틱 쌍의 안쪽이다.
    text = (
        "``1234abc``\n"  # 백틱 둘로 감싼 쌍
        "``1234abc`\n"  # 닫는 백틱 줄이 짧아 쌍이 아니다
        "`x` `1234abc`\n"  # 앞의 쌍과 이 낱말의 쌍이 따로다
        "`1234abc` `x`1234abc`y`\n"  # 첫 낱말은 쌍 안이고 둘째 낱말은 이웃한 두 쌍 사이다
    )
    assert find_tokens(text) == [
        (1, "1234abc", True),
        (2, "1234abc", False),
        (3, "1234abc", True),
        (4, "1234abc", True),
        (4, "1234abc", False),
    ]


def test_many_backticked_words_on_one_line_stay_fast():
    # 한 줄에 백틱으로 감싼 낱말이 수천 개여도 느려지지 않는다. 감싼 낱말마다 그 줄 전체의 백틱 쌍을 다시 찾으면 줄 길이에
    # 낱말 수를 곱한 만큼 걸린다(8000개가 든 줄 하나, 약 8만 자에 이 PC에서 25초쯤). 줄마다 한 번만 찾으면 0.02초쯤이다.
    # 상한은 느린 PC에서도 헛실패하지 않게 넉넉히(고친 코드의 백 배쯤) 잡았고, 고치기 전 코드는 그 상한을 크게 넘는다.
    words = [f"a{number:06x}" for number in range(8000)]
    text = " ".join(f"`{word}`" for word in words) + "\n"
    started = time.perf_counter()
    found = find_tokens(text)
    elapsed = time.perf_counter() - started
    assert found == [(1, word, True) for word in words]
    assert elapsed < 2.0, f"{len(words)}개가 든 한 줄을 뽑는 데 {elapsed:.1f}초 걸렸다"


# ---------------------------------------------------------------------------------------------
# 2. 이력으로 풀기
# ---------------------------------------------------------------------------------------------


def test_resolve_matches_the_start_of_a_hash_only():
    commit = "abcdef0" + "1" * 33  # 40자. 긴 16진 글자열을 소스에 그대로 적지 않고 코드로 만든다.
    inner = "1" * 7 + "bcdef01" + "2" * 26  # 가운데에 같은 글자가 있을 뿐 앞부분은 다르다
    by_prefix = build_prefix_index([commit, inner])
    assert resolve("abcdef0", by_prefix) == (commit,)
    assert resolve("abcdef01", by_prefix) == (commit,)
    assert resolve(commit, by_prefix) == (commit,)  # 40자 전체
    assert resolve("bcdef01", by_prefix) == ()  # 가운데 글자는 앞부분이 아니다
    assert resolve("abcdef02", by_prefix) == ()  # 앞 7자는 같지만 더 긴 앞부분이 다르다


def test_ambiguous_prefix_is_a_problem():
    # 진짜 해시 충돌은 만들 수 없으므로 앞 7자가 같은 가짜 커밋 둘을 코드로 만들어 순수 함수에 넣는다.
    shared = "abcdef0"
    left, right = shared + "1" * 33, shared + "2" * 33
    by_prefix = build_prefix_index([right, left])
    assert resolve(shared, by_prefix) == (left, right)  # 어느 순서로 넣어도 같은 차례
    assert resolve(shared + "1", by_prefix) == (left,)  # 더 길게 적으면 하나로 좁혀진다

    problems, references = judge_file(
        "docs/a.md",
        [(3, shared, False)],
        by_prefix=by_prefix,
        ancestors=frozenset([left, right]),
        registered=frozenset(),
        registry_source="tools/evidence.toml",
    )
    assert references == 1
    assert places(problems) == [("reference", "docs/a.md", 3)]
    assert "모호" in str(problems[0]) and shared in str(problems[0])
    # 하나로 좁혀지는 낱말은 모호하지 않다. 그 커밋이 조상이면 문제가 없다.
    problems, references = judge_file(
        "docs/a.md",
        [(3, shared + "1", False)],
        by_prefix=by_prefix,
        ancestors=frozenset([left]),
        registered=frozenset(),
        registry_source="tools/evidence.toml",
    )
    assert (problems, references) == ([], 1)


def test_digit_only_hash_that_resolves_is_judged_like_any_other():
    # 앞 7자가 모두 숫자인 진짜 커밋은 시험에서 만들 수 없다(해시는 고를 수 없다). 그래서 그런 앞부분을 가진 가짜
    # 커밋 둘을 코드로 만들어 순수 함수에 넣는다. 풀리는 낱말은 조상이면 세고 문제가 없고, 조상이 아니면 어느
    # 파일에서든 문제다. 풀리지 않는 낱말은 .md에서만 문제다.
    ancestor, other = "1234567" + "8" * 33, "7654321" + "9" * 33
    judged = {
        "by_prefix": build_prefix_index([ancestor, other]),
        "ancestors": frozenset([ancestor]),
        "registered": frozenset(),
        "registry_source": "tools/evidence.toml",
    }
    assert judge_file("docs/a.md", [(1, "1234567", True)], **judged) == ([], 1)

    problems, references = judge_file("src/app.py", [(2, "7654321", True)], **judged)
    assert references == 1
    assert places(problems) == [("reference", "src/app.py", 2)]
    assert "조상이 아니다" in str(problems[0])

    assert judge_file("src/app.py", [(3, "1111111", True)], **judged) == ([], 0)
    problems, references = judge_file("docs/a.md", [(3, "1111111", True)], **judged)
    assert references == 1
    assert places(problems) == [("reference", "docs/a.md", 3)]


# ---------------------------------------------------------------------------------------------
# 3. 규칙 3·4: 조상이어야 하고, 커밋 참조로 적었으면 풀려야 한다
# ---------------------------------------------------------------------------------------------


def test_the_untouched_world_has_no_problems_and_three_references(world):
    # 고정물의 처음 상태: src/app.py의 first, docs/notes.md의 first(백틱)와 second. 모두 조상으로 풀린다.
    report = scan_references(world.repo, load_registry(world.set_registry("")))
    assert report.problems == ()
    assert report.references == 3


@pytest.mark.parametrize("length", [7, 12, 40])
def test_resolving_hash_must_be_an_ancestor(world, length):
    assert problems_of(world) == []
    commit_files(
        world.repo, {"docs/a.md": f"- 앞 갈래: {short(world.first, length)}\n"}, "Cite an ancestor"
    )
    assert problems_of(world) == []  # first는 HEAD의 조상이다

    commit_files(
        world.repo, {"docs/b.md": f"- 다른 갈래: {short(world.side, length)}\n"}, "Cite the side commit"
    )
    problems = problems_of(world)
    assert places(problems) == [("reference", "docs/b.md", 1)]
    # side 커밋은 이 저장소의 커밋이지만 HEAD에서 닿지 않는다. 이유에 그 말이 있고 낱말도 적혀 있다.
    assert short(world.side, length) in str(problems[0])
    assert "조상이 아니다" in str(problems[0])


def test_claimed_hash_must_resolve(world):
    assert_not_a_commit_prefix(world.repo, FAKE)
    commit_files(
        world.repo,
        {
            "docs/a.md": f"- 근거: `{FAKE}`\n",
            # 같은 낱말을 코드 주석에 적으면 풀리지 않아도 문제가 아니다(규칙 3만 적용). 커밋 참조라고 밝혀
            # 적은 꼴이어도 규칙 4는 .md 파일에만 건다.
            "src/note.py": f"# 근거: {FAKE}\n# 커밋 {FAKE}에서 정했다\n",
        },
        "Cite an unknown hash",
    )
    problems = problems_of(world)
    assert places(problems) == [("reference", "docs/a.md", 1)]
    assert FAKE in str(problems[0])
    assert "풀리지 않는다" in str(problems[0])
    # 다음에 할 일이 보인다: 다른 저장소의 해시면 등록 파일에 등록한다.
    assert "tools/evidence.toml" in str(problems[0]) and "[[external]]" in str(problems[0])


def test_digit_only_hash_counts_only_where_it_is_claimed(world):
    # 문서가 커밋 참조라고 밝혀 적은 자리(백틱 통째, 커밋 뒤)의 숫자뿐인 낱말은 낱말이다. 날짜나 크기 같은 수는 그런
    # 표시가 없어 낱말이 아니다.
    for word in ("1234567", "7654321", "20261124"):
        assert_not_a_commit_prefix(world.repo, word)
    text = (
        "- 날짜는 20261124이다.\n"
        "- 크기는 1234567바이트다.\n"
        "- 근거: `1234567`\n"
        "- 근거: 커밋 7654321에서 정했다.\n"
    )
    commit_files(world.repo, {"docs/a.md": text}, "Cite digit-only words")
    report = scan_references(world.repo, load_registry(world.set_registry("")))
    # 표시 없는 두 수(1·2줄)는 문제도 아니고 세지도 않는다. 표시를 단 둘(3·4줄)은 풀리지 않아 규칙 4의 문제다.
    assert places(list(report.problems)) == [("reference", "docs/a.md", 3), ("reference", "docs/a.md", 4)]
    assert "1234567" in str(report.problems[0]) and "7654321" in str(report.problems[1])
    assert report.references == 3 + 2  # 처음 상태의 셋 + 표시를 단 둘
    # 등록하면 그 파일에서 통과한다. 등록한 낱말만이다.
    problems = problems_of(world, external_entry("1234567", "docs/a.md"))
    assert places(problems) == [("reference", "docs/a.md", 4)]


def test_commit_word_claims_the_next_token(world):
    assert_not_a_commit_prefix(world.repo, FAKE)
    text = f"커밋 {FAKE}에서 정했다\ncommit {FAKE}\nSHA-256 {FAKE}…\n"
    commit_files(world.repo, {"docs/a.md": text}, "Cite with the commit word")
    # 커밋·commit 바로 뒤의 낱말만 커밋 참조다. SHA-256 뒤의 같은 낱말은 아니다.
    assert places(problems_of(world)) == [
        ("reference", "docs/a.md", 1),
        ("reference", "docs/a.md", 2),
    ]


def test_hash_followed_by_korean_particle_is_found(world):
    # 파이썬 \b는 한글도 낱말 글자로 보므로, 해시 바로 뒤에 조사가 붙은 참조를 놓치기 쉽다.
    first, side = short(world.first), short(world.side)
    text = f"커밋 `{first}`의 결과\n{side}의 일부\n"
    assert find_tokens(text) == [(1, first, True), (2, side, False)]
    commit_files(world.repo, {"docs/a.md": text}, "Cite with Korean particles")
    # 앞의 것은 조상으로 풀려 문제가 없고, 뒤의 것(백틱 없음)은 규칙 3으로 잡힌다.
    assert places(problems_of(world)) == [("reference", "docs/a.md", 2)]


def test_unreachable_commits_are_not_counted(world):
    # 임시 브랜치에 커밋 하나를 만들고 그 브랜치를 지워 어느 ref에서도 닿지 않게 한다. 객체는 남는다. 이 PC의
    # 로컬 저장소에는 이런 떠 있는 객체가 있고 CI의 새 복제본에는 없으므로, 둘의 결과가 같아야 한다.
    git(world.repo, "switch", "--quiet", "--create", "scratch")
    floating = commit_files(world.repo, {"floating.txt": "never merged\n"}, "A commit that floats")
    git(world.repo, "switch", "--quiet", "main")
    git(world.repo, "branch", "--quiet", "-D", "scratch")
    assert git(world.repo, "cat-file", "-t", floating) == "commit"  # 객체는 아직 있다
    assert floating not in git(world.repo, "rev-list", "--all").split()  # 어느 ref에서도 닿지 않는다

    cited = short(floating)
    commit_files(world.repo, {"docs/a.md": f"- 근거: {cited}\n"}, "Mention the floating commit")
    assert problems_of(world) == []  # 풀리지 않는 낱말이라 규칙 3에 걸리지 않는다
    commit_files(world.repo, {"docs/a.md": f"- 근거: `{cited}`\n"}, "Claim the floating commit")
    problems = problems_of(world)
    assert places(problems) == [("reference", "docs/a.md", 1)]  # 규칙 4: 풀려야 하는데 풀리지 않는다
    assert "풀리지 않는다" in str(problems[0])


def test_summary_counts_the_occurrences_that_rules_three_and_four_touched(world, capsys):
    assert_not_a_commit_prefix(world.repo, FAKE)
    assert_not_a_commit_prefix(world.repo, "2345bcd")
    assert_not_a_commit_prefix(world.repo, "3456cde")
    first, side = short(world.first), short(world.side)
    text = (
        f"- 등록한 외부 해시: `{FAKE}`\n"  # 풀리지 않지만 커밋 참조로 적었다: 센다(등록돼 통과)
        "- 등록하지 않은 외부 해시: `2345bcd`\n"  # 센다(문제)
        "- 낱말만 있다: 3456cde\n"  # 풀리지 않고 커밋 참조도 아니다: 세지 않는다
        f"- 이 저장소의 커밋: {first}\n"  # 풀린다: 센다
        f"- 같은 낱말이 또: {first}\n"  # 출현마다 센다
        f"- 다른 갈래: {side}\n"  # 풀리지만 조상이 아니다: 센다(문제)
    )
    commit_files(world.repo, {"docs/c.md": text}, "Add a mixed document")
    world.set_registry(external_entry(FAKE, "docs/c.md"))
    assert main(["--repo", str(world.repo)]) == 1
    lines = capsys.readouterr().out.splitlines()
    # 처음 상태의 3개 + 이 문서의 5개(등록 통과 1, 등록 없는 문제 1, 풀림 둘, 조상 아님 1). 이 등록 파일에는
    # [[record]]와 [[pair]]가 없어 기록 값과 짝은 0이다.
    assert lines[-1] == "참조 8개, 기록 값 0개, 짝 0개, 문제 2개"
    assert len(lines) == 3  # 문제 둘과 끝 줄


# ---------------------------------------------------------------------------------------------
# 4. 규칙 5와 등록 파일
# ---------------------------------------------------------------------------------------------


def test_external_registration_passes_and_is_scoped_to_its_file(world):
    assert_not_a_commit_prefix(world.repo, FAKE)
    assert_not_a_commit_prefix(world.repo, "2345bcd")
    commit_files(
        world.repo,
        {
            "docs/a.md": f"- 근거: `{FAKE}`\n- 다른 낱말: `2345bcd`\n",
            "docs/b.md": f"- 근거: `{FAKE}`\n",
        },
        "Cite the same word in two documents",
    )
    problems = problems_of(world, external_entry(FAKE, "docs/a.md"))
    # a.md의 등록한 낱말은 통과하고, b.md의 같은 낱말과 a.md의 다른 낱말은 그대로 문제다.
    assert places(problems) == [("reference", "docs/a.md", 2), ("reference", "docs/b.md", 1)]


def test_external_registration_needs_the_exact_word(world):
    assert_not_a_commit_prefix(world.repo, FAKE + "d")
    commit_files(world.repo, {"docs/a.md": f"- 근거: `{FAKE}d`\n"}, "Cite a longer word")
    # 등록한 글자(7자)가 문서의 낱말(8자)의 앞부분일 뿐이면 통하지 않는다. 등록은 그 파일에 없는 낱말이라
    # 낡은 등록이기도 하다.
    problems = problems_of(world, external_entry(FAKE, "docs/a.md"))
    assert places(problems) == [("reference", "docs/a.md", 1), ("external", "tools/evidence.toml", 0)]
    assert "낡은 등록" in str(problems[1])


def test_stale_or_wrong_external_is_a_problem(world):
    assert_not_a_commit_prefix(world.repo, FAKE)
    assert_not_a_commit_prefix(world.repo, "2345bcd")
    commit_files(world.repo, {"docs/a.md": f"- 근거: `{FAKE}`\n"}, "Cite an unknown hash")
    # 낡은 등록: 그 파일에 없는 낱말을 등록했다.
    stale = problems_of(world, external_entry(FAKE, "docs/a.md") + external_entry("2345bcd", "docs/a.md"))
    assert places(stale) == [("external", "tools/evidence.toml", 0)]
    assert "[[external]] 2번째" in str(stale[0])
    assert "2345bcd" in str(stale[0]) and "낡은 등록" in str(stale[0])
    # 잘못 등록: 이 저장소의 커밋으로 풀리는 낱말(docs/notes.md에 실제로 있다)을 등록했다. 앞의 올바른 등록은
    # 그대로 둬서 a.md의 낱말이 새 문제를 만들지 않게 한다.
    wrong = problems_of(
        world, external_entry(FAKE, "docs/a.md") + external_entry(short(world.first), "docs/notes.md")
    )
    assert places(wrong) == [("external", "tools/evidence.toml", 0)]
    assert "[[external]] 2번째" in str(wrong[0])
    assert short(world.first) in str(wrong[0]) and "이 저장소의 커밋으로 풀린다" in str(wrong[0])


def test_a_digit_only_external_is_stale_unless_it_is_claimed_in_its_file(world):
    assert_not_a_commit_prefix(world.repo, "1234567")
    commit_files(
        world.repo,
        {"docs/a.md": "- 크기는 1234567바이트다.\n", "docs/b.md": "- 근거: `1234567`\n"},
        "Write the same digits with and without a mark",
    )
    # 표시 없이 적힌 숫자뿐인 값은 그 파일에서 낱말로 뽑히지 않으므로 등록이 낡았다고 알리고, 이유에 그 까닭이 보인다.
    # 표시를 달아 적은 파일의 등록은 통과한다.
    problems = problems_of(
        world, external_entry("1234567", "docs/a.md") + external_entry("1234567", "docs/b.md")
    )
    assert places(problems) == [("external", "tools/evidence.toml", 0)]
    assert "[[external]] 1번째" in str(problems[0])
    assert "낡은 등록" in str(problems[0]) and "커밋 참조로 적힌 자리" in str(problems[0])


def test_where_must_name_a_scanned_file_in_head(world):
    assert_not_a_commit_prefix(world.repo, FAKE)
    commit_files(
        world.repo,
        {"uv.lock": f"{FAKE}\n", "data.bin": b"\x00" + FAKE.encode() + b"\n"},
        "Add a lock file and a binary file",
    )
    registry = (
        external_entry(FAKE, "docs/없는파일.md")
        + external_entry(FAKE, "uv.lock")
        + external_entry(FAKE, "data.bin")
    )
    problems = problems_of(world, registry)
    assert [problem.line for problem in problems] == [0, 0, 0]
    assert "[[external]] 1번째" in str(problems[0]) and "트리에 없다" in str(problems[0])
    assert "[[external]] 2번째" in str(problems[1]) and "검사 대상이 아닌" in str(problems[1])
    assert "[[external]] 3번째" in str(problems[2]) and "검사 대상이 아닌" in str(problems[2])


def test_duplicate_external_registration_is_a_problem(world):
    assert_not_a_commit_prefix(world.repo, FAKE)
    commit_files(world.repo, {"docs/a.md": f"- 근거: `{FAKE}`\n"}, "Cite an unknown hash")
    entry = external_entry(FAKE, "docs/a.md")
    problems = problems_of(world, entry + entry)
    assert places(problems) == [("external", "tools/evidence.toml", 0)]
    assert "[[external]] 2번째" in str(problems[0]) and "1번째" in str(problems[0])


def test_registry_errors(world, capsys):
    base = ["--repo", str(world.repo)]
    # 등록 파일을 읽을 수 없으면 종료 2다: TOML 문법 오류와 모르는 꼭대기 표. --report-only여도 같다.
    for text, expected in (
        ("[[external\n", "evidence.toml"),
        ('[[extern]]\nhash = "1234abc"\n', "extern"),
        ('hash = "1234abc"\n', "hash"),
    ):
        world.set_registry(text)
        for extra in ([], ["--report-only"]):
            assert main([*base, *extra]) == 2
            captured = capsys.readouterr()
            assert expected in captured.err
            assert captured.out == ""
    # 등록 파일이 없는 것도 같다.
    world.registry_path.unlink()
    assert main(base) == 2
    assert "evidence.toml" in capsys.readouterr().err

    # 항목 하나의 꼴 오류(빠진 키, 16진수가 아닌 hash)는 시작하지 못할 일이 아니라 그 항목의 문제다(종료 1).
    for text, key in (
        ('[[external]]\nhash = "1234abc"\nwhere = "docs/notes.md"\n', "what"),
        ('[[external]]\nhash = "xyz1234"\nwhere = "docs/notes.md"\nwhat = "x"\n', "hash"),
    ):
        world.set_registry(text)
        assert main(base) == 1
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].startswith(f"external tools/evidence.toml: [[external]] 1번째: {key} - ")
        assert lines[-1].endswith("문제 1개")


@pytest.mark.parametrize(
    ("entry", "key"),
    [
        pytest.param('where = "docs/notes.md"\nwhat = "x"\n', "hash", id="hash가 없다"),
        pytest.param('hash = "1234abc"\nwhat = "x"\n', "where", id="where가 없다"),
        pytest.param('hash = "1234abc"\nwhere = "docs/notes.md"\n', "what", id="what이 없다"),
        pytest.param('hash = "xyz1234"\nwhere = "docs/notes.md"\nwhat = "x"\n', "hash", id="16진수가 아니다"),
        pytest.param('hash = "1234ab"\nwhere = "docs/notes.md"\nwhat = "x"\n', "hash", id="6자는 모자란다"),
        pytest.param('hash = "1234ABC"\nwhere = "docs/notes.md"\nwhat = "x"\n', "hash", id="대문자"),
        pytest.param(f'hash = "{"a" * 41}"\nwhere = "docs/notes.md"\nwhat = "x"\n', "hash", id="41자"),
        pytest.param('hash = ""\nwhere = "docs/notes.md"\nwhat = "x"\n', "hash", id="빈 hash"),
        pytest.param('hash = "1234abc"\nwhere = "  "\nwhat = "x"\n', "where", id="공백뿐인 where"),
        pytest.param('hash = "1234abc"\nwhere = "docs/notes.md"\nwhat = ""\n', "what", id="빈 what"),
        pytest.param('hash = 1234\nwhere = "docs/notes.md"\nwhat = "x"\n', "hash", id="글이 아닌 hash"),
        pytest.param(
            'hash = "1234abc"\nwhere = "docs/notes.md"\nwhat = "x"\nwaht = "오타"\n', "waht", id="모르는 키"
        ),
    ],
)
def test_malformed_external_entries_are_problems_of_that_entry(tmp_path, entry, key):
    # 등록 파일의 꼴만 보는 시험이라 저장소가 필요 없다(검사에 실리는 것은 test_registry_errors가 본다).
    registry = parse_registry(tmp_path, "[[external]]\n" + entry)
    problems = [problem for problem in registry.problems if problem.kind == "external"]
    assert len(problems) >= 1
    assert all("[[external]] 1번째" in str(problem) for problem in problems)
    assert any(f"{key} -" in str(problem) for problem in problems)


def test_tables_that_are_not_arrays_of_tables_are_problems(tmp_path):
    for key in ("external", "record", "pair"):
        registry = parse_registry(tmp_path, f'{key} = "x"\n')
        assert places(list(registry.problems)) == [(key, "tools/evidence.toml", 0)]
        assert f"[[{key}]] 표의 배열이어야 한다" in str(registry.problems[0])
    # record와 pair는 받는 꼭대기 표다(모르는 표가 아니다). 꼴이 맞는 항목은 그대로 읽힌다.
    text = (
        record_rule("comp/reports/*/manifest.json", ["git_commit"])
        + pair_rule("first-pair", "1234abc", "2345bcd", "docs/a.md")
        + pair_rule("second-pair", "1234abc", "3456cde", "docs/a.md")
    )
    registry = parse_registry(tmp_path, text)
    assert registry.problems == ()
    assert (len(registry.records), len(registry.pairs), registry.pair_total) == (1, 2, 2)


def test_registry_problems_keep_their_order_in_the_file(world):
    # 항목 번호는 문자열이 아니라 숫자로 정렬된다(10번째가 2번째보다 앞서지 않는다).
    entries = "".join(external_entry(f"{n:07d}", "src/app.py") for n in range(1, 11))
    problems = problems_of(world, entries)
    assert len(problems) == 10  # 모두 그 파일에 없는 낱말이라 낡은 등록이다
    for number, problem in enumerate(problems, 1):
        assert f"[[external]] {number}번째: " in str(problem)


# ---------------------------------------------------------------------------------------------
# 5. 읽는 대상
# ---------------------------------------------------------------------------------------------


def test_lock_files_and_binary_files_are_not_read(world):
    bad = f"- 다른 갈래: {short(world.side)}\n"
    commit_files(
        world.repo,
        {
            "uv.lock": bad,
            "sub/package-lock.json": bad,
            "e2e/uv.lock": bad,
            "data.bin": b"\x00\x01" + bad.encode("utf-8"),
        },
        "Add lock files and a binary file",
    )
    report = scan_references(world.repo, load_registry(world.set_registry("")))
    assert report.problems == ()
    assert report.references == 3  # 처음 상태의 세 참조뿐이다. 건너뛴 파일 안의 낱말은 세지도 않는다.
    # 대조: 같은 글을 보통 글 파일에 쓰면 잡히고 센다. 위 파일들이 건너뛰어진 것이지 글이 무해한 것이 아니다.
    commit_files(world.repo, {"control.txt": bad}, "Add the same text to a plain file")
    report = scan_references(world.repo, load_registry(world.set_registry("")))
    assert places(list(report.problems)) == [("reference", "control.txt", 1)]
    assert report.references == 4


def test_worktree_edits_do_not_matter(world):
    side = short(world.side)
    commit_files(world.repo, {"docs/a.md": f"- 근거: {short(world.first)}\n"}, "Cite an ancestor")
    assert problems_of(world) == []
    # 커밋하지 않은 변경은 모두 HEAD가 아니라서 결과를 바꾸지 못한다: 작업 트리의 문서를 틀리게 고치고, 다른
    # 문서는 지우고, 추적하지 않는 새 파일을 만들고, 한 파일은 스테이징만 한다.
    write(world.repo, "docs/a.md", f"- 근거: {side}\n")
    (world.repo / "docs" / "notes.md").unlink()
    write(world.repo, "docs/new.md", f"- 근거: `{FAKE}`\n")
    write(world.repo, "docs/staged.md", f"- 근거: {side}\n")
    git(world.repo, "add", "--", "docs/staged.md")
    assert problems_of(world) == []


def test_uncommitted_fixes_do_not_hide_a_problem_in_head(world):
    # 거꾸로: HEAD의 문서가 틀렸다면, 작업 트리에서 고치고 스테이징까지 했어도 HEAD의 문제가 그대로 나온다.
    commit_files(world.repo, {"docs/bad.md": f"- 근거: {short(world.side)}\n"}, "Cite the side commit")
    assert places(problems_of(world)) == [("reference", "docs/bad.md", 1)]
    write(world.repo, "docs/bad.md", f"- 근거: {short(world.first)}\n")
    assert places(problems_of(world)) == [("reference", "docs/bad.md", 1)]
    git(world.repo, "add", "--", "docs/bad.md")
    assert places(problems_of(world)) == [("reference", "docs/bad.md", 1)]


def test_symlinks_and_submodule_entries_are_skipped(world):
    side = short(world.side)
    # 기호 링크의 blob에는 링크가 가리키는 경로 글이 든다. 일반 파일로 읽으면 그 글의 낱말이 잡힐 것이다.
    target = write(world.repo, "link-target.txt", f"{side}\n")
    blob = git(world.repo, "hash-object", "-w", str(target))
    target.unlink()
    git(world.repo, "update-index", "--add", "--cacheinfo", f"120000,{blob},docs/link")
    git(world.repo, "update-index", "--add", "--cacheinfo", f"160000,{world.second},vendor/sub")
    git(world.repo, "commit", "--quiet", "-m", "Add a symlink entry and a submodule entry")
    # 전제: 두 항목이 실제로 그 모드로 트리에 들어갔다.
    listing = git(world.repo, "ls-tree", "-r", "HEAD")
    assert f"120000 blob {blob}\tdocs/link" in listing
    assert f"160000 commit {world.second}\tvendor/sub" in listing
    assert problems_of(world) == []
    commit_files(world.repo, {"docs/plain.txt": f"{side}\n"}, "Add the same text to a plain file")
    assert places(problems_of(world)) == [("reference", "docs/plain.txt", 1)]


def test_non_utf8_text_does_not_stop_the_scan(world):
    # UTF-8이 아닌 바이트는 대체 글자로 바뀐다. 낱말은 ASCII뿐이라 낱말이 생기거나 쪼개지지 않고, 깨진 바이트
    # 바로 옆의 낱말도 경계로 본다.
    side = short(world.side).encode("ascii")
    content = b"caf\xe9 \xff\xfe " + side + b"\xe9\n" + b"\xe9" + side + b"\n"
    commit_files(world.repo, {"data/latin1.txt": content}, "Add a Latin-1 file")
    assert places(problems_of(world)) == [
        ("reference", "data/latin1.txt", 1),
        ("reference", "data/latin1.txt", 2),
    ]


def test_korean_file_names_are_reported_as_they_are(world):
    commit_files(world.repo, {"docs/기록 문서.md": f"- 다른 갈래: {short(world.side)}\n"}, "Add a document")
    problems = problems_of(world)
    assert places(problems) == [("reference", "docs/기록 문서.md", 1)]
    assert str(problems[0]).startswith("reference docs/기록 문서.md:1: ")


# ---------------------------------------------------------------------------------------------
# 6. 시작할 수 없음
# ---------------------------------------------------------------------------------------------


def test_shallow_clone_is_reported_as_missing_history(world, tmp_path_factory, capsys):
    # CI의 기본 체크아웃처럼 마지막 커밋만 받은 복제본에서는 이력이 모자라 낱말이 풀리지 않는다. 그것을 '증거가
    # 틀림'으로 알리면 안 되고, 검사할 수 없다고 알려야 한다. 로컬 경로를 그대로 주면 깊이가 무시되므로
    # file:// 주소로 복제한다.
    registry = world.set_registry("")
    clone = tmp_path_factory.mktemp("shallow") / "clone"
    subprocess.run(
        ["git", "clone", "--quiet", "--depth", "1"]
        + ["-c", "core.autocrlf=false", world.repo.as_uri(), str(clone)],
        check=True,
        capture_output=True,
    )
    assert git(clone, "rev-parse", "--is-shallow-repository") == "true"  # 전제: 정말 얕은 복제다
    for extra in ([], ["--report-only"]):
        assert main(["--repo", str(clone), "--registry", str(registry), *extra]) == 2
        captured = capsys.readouterr()
        assert "git fetch --unshallow" in captured.err
        assert captured.out == ""


def test_git_failure_stops_the_check(world, tmp_path_factory, capsys):
    # 읽지 못했는데 0으로 통과하면 안 된다. 폴더가 아니거나 git 저장소가 아니면 종료 2다.
    registry = world.set_registry("")
    plain = tmp_path_factory.mktemp("not-a-repo")
    for extra in ([], ["--report-only"]):
        assert main(["--repo", str(plain), "--registry", str(registry), *extra]) == 2
        captured = capsys.readouterr()
        assert "git 저장소가 아니다" in captured.err
        assert captured.out == ""
        assert main(["--repo", str(plain / "없는폴더"), "--registry", str(registry), *extra]) == 2
        captured = capsys.readouterr()
        assert "저장소 폴더가 아니다" in captured.err
        assert captured.out == ""


@pytest.mark.parametrize("subcommand", ["rev-list", "ls-tree", "cat-file"])
def test_a_failing_git_read_stops_the_check(world, monkeypatch, capsys, subcommand):
    # 검사 도중 git 읽기 명령이 실패하면(종료 코드가 0이 아니면) 빈 결과로 넘기지 않고 종료 2로 끝낸다.
    world.set_registry("")
    real_run = check_evidence._run

    def failing(repo, *args, **kwargs):
        if args and args[0] == subcommand:
            return subprocess.CompletedProcess(args, 128, stdout=b"", stderr=b"fatal: simulated failure\n")
        return real_run(repo, *args, **kwargs)

    monkeypatch.setattr(check_evidence, "_run", failing)
    assert main(["--repo", str(world.repo), "--report-only"]) == 2
    captured = capsys.readouterr()
    assert subcommand in captured.err and "simulated failure" in captured.err
    assert captured.out == ""


def test_missing_git_executable_stops_the_check(world, monkeypatch, capsys):
    world.set_registry("")

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(check_evidence.subprocess, "run", no_git)
    assert main(["--repo", str(world.repo)]) == 2
    captured = capsys.readouterr()
    assert "git을 실행할 수 없다" in captured.err
    assert captured.out == ""


def test_a_repository_without_commits_cannot_be_checked(git_repo, tmp_path_factory, capsys):
    registry = write(tmp_path_factory.mktemp("registry"), "evidence.toml", "")
    assert main(["--repo", str(git_repo), "--registry", str(registry), "--report-only"]) == 2
    captured = capsys.readouterr()
    assert "HEAD" in captured.err
    assert captured.out == ""


# ---------------------------------------------------------------------------------------------
# 7. 명령줄
# ---------------------------------------------------------------------------------------------


def test_report_only_exits_zero_but_prints_the_problems(world, capsys):
    world.set_registry("")
    commit_files(world.repo, {"docs/b.md": f"- 다른 갈래: {short(world.side)}\n"}, "Cite the side commit")
    base = ["--repo", str(world.repo)]

    assert main(base) == 1
    plain = capsys.readouterr().out.splitlines()
    assert len(plain) == 2
    assert plain[0].startswith("reference docs/b.md:1: ")
    assert plain[1] == "참조 4개, 기록 값 0개, 짝 0개, 문제 1개"

    # --report-only는 문제가 있어도 종료 코드를 0으로 만들 뿐, 같은 줄을 모두 출력하고 끝에 한 줄을 더한다.
    assert main([*base, "--report-only"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[:-1] == plain
    assert lines[-1] == "보고만: 문제가 있어도 종료 코드는 0이다"


def test_main_exit_codes_when_nothing_is_wrong(world, capsys):
    world.set_registry("")
    assert main(["--repo", str(world.repo)]) == 0
    assert capsys.readouterr().out.splitlines() == ["참조 3개, 기록 값 0개, 짝 0개, 문제 0개"]
    assert main(["--repo", str(world.repo), "--report-only"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "참조 3개, 기록 값 0개, 짝 0개, 문제 0개",
        "보고만: 문제가 있어도 종료 코드는 0이다",
    ]


def test_problems_are_sorted_by_path_then_line(world):
    side = short(world.side)
    # 일부러 파일 이름과 줄 번호를 거꾸로 만든다.
    commit_files(
        world.repo,
        {
            "docs/z.md": f"첫 줄\n- {side}\n\n\n- {side}\n",
            "docs/a.md": f"\n\n- {side}\n",
            "README.md": f"- {side}\n",
        },
        "Cite the side commit in three files",
    )
    problems = problems_of(world, external_entry("2345bcd", "docs/a.md"))
    assert places(problems) == [
        ("reference", "README.md", 1),
        ("reference", "docs/a.md", 3),
        ("reference", "docs/z.md", 2),
        ("reference", "docs/z.md", 5),
        ("external", "tools/evidence.toml", 0),
    ]


def test_output_is_utf8_when_piped(world):
    # 한국어 Windows의 파이썬은 파이프로 나가는 출력을 cp949로 쓴다. 어느 PC에서나 같은 조건이 되도록 그 인코딩을
    # 환경 변수로 정해 두고, 도구가 시작할 때 UTF-8로 다시 여는지 본다. 파일 이름에 cp949로 쓸 수 없는 글자(빼기
    # 기호)를 넣어, 다시 열지 않으면 출력 도중에 죽는 것도 함께 잡는다.
    name = "docs/차이−기록.md"
    commit_files(world.repo, {name: f"- 다른 갈래: {short(world.side)}\n"}, "Cite the side commit")
    registry = world.set_registry("")
    env = {key: value for key, value in os.environ.items() if key != "PYTHONUTF8"}
    env["PYTHONIOENCODING"] = "cp949"
    done = subprocess.run(
        [sys.executable, str(TOOLS / "check_evidence.py")]
        + ["--repo", str(world.repo), "--registry", str(registry)],
        capture_output=True,
        env=env,
        check=False,  # 종료 코드는 아래에서 직접 확인한다
    )
    assert done.returncode == 1, done.stderr.decode("utf-8", errors="replace")
    lines = done.stdout.decode("utf-8").splitlines()
    assert lines[0].startswith(f"reference {name}:1: ")
    assert "조상이 아니다" in lines[0]
    assert lines[-1] == "참조 4개, 기록 값 0개, 짝 0개, 문제 1개"


def test_help_is_korean_and_lists_the_rules_and_exit_codes(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0
    text = capsys.readouterr().out
    for needle in (
        "--repo",
        "--registry",
        "--report-only",
        "HEAD",
        "uv.lock",
        "package-lock.json",
        "숫자뿐",
        "조상",
        "모호",
        "백틱",
        "[[external]]",
        "낡은 등록",
        "잘못 등록",
        "[[record]]",
        "git_tree",
        "어디에도 한 번도 안 나오면",  # 등록한 키가 맞는 파일 어디에도 없으면 그 키의 문제라는 말
        "[[pair]]",
        "종료 코드",
        "git fetch --unshallow",
    ):
        assert needle in text, needle
    # 기록 값과 짝 검사가 생겼으니 '표의 배열인지만 본다'는 옛 말이 남아 있으면 안 된다.
    assert "배열인지만" not in text


def test_only_read_commands_are_run(world, monkeypatch):
    # 이 도구는 읽기만 한다. 부르는 git 명령은 모두 `git --no-optional-locks -C <저장소>`로 시작하는 읽기 명령이다.
    world.set_registry("")
    status_before = git(world.repo, "status", "--porcelain")
    calls: list[list[str]] = []
    real_run = subprocess.run

    def spy(command, *args, **kwargs):
        calls.append(list(command))
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(check_evidence.subprocess, "run", spy)
    assert main(["--repo", str(world.repo)]) == 0
    monkeypatch.undo()  # 아래 확인에서 부르는 git이 calls에 섞이지 않게 한다
    assert calls
    allowed = {"rev-parse", "rev-list", "ls-tree", "cat-file"}
    for command in calls:
        assert command[:4] == ["git", "--no-optional-locks", "-C", str(world.repo)], command
        assert command[4] in allowed, command
    # 저장소와 등록 파일은 고쳐지지 않았다.
    assert git(world.repo, "status", "--porcelain") == status_before
    assert git(world.repo, "rev-parse", "HEAD") == world.third


def test_empty_registry_object_checks_the_world_too(world):
    # 등록 파일 없이 Registry()를 바로 넘겨도 같은 결과다(함수로 부르는 쪽을 위한 기본값).
    assert check_references(world.repo, Registry()) == []


# ---------------------------------------------------------------------------------------------
# 8. 기록 파일의 커밋 값([[record]])
# ---------------------------------------------------------------------------------------------

MANIFEST = "comp/reports/run1/manifest.json"
MANIFEST_GLOB = "comp/reports/*/manifest.json"


def write_manifest(world: World, **fields) -> str:
    """MANIFEST를 fields의 JSON으로 쓰고 커밋한다. 새 커밋의 해시를 돌려준다."""
    return commit_files(world.repo, {MANIFEST: json.dumps(fields)}, "Write the manifest")


def test_record_commit_must_be_an_ancestor(world):
    # 여러 경우를 한 번에 커밋하고 한 번에 검사한다(경우마다 폴더 하나, 이름이 폴더 이름이다).
    assert_not_a_commit_prefix(world.repo, FAKE)
    second = world.second
    # 이름 → (값, 문제 줄에 적힐 값 모양, 문제 이유에 있어야 할 말). 문제가 아닌 것은 None이다.
    cases = {
        "full": (second, None, None),
        "short": (second[:7], None, None),  # 줄임 해시도 풀린다
        "side": (world.side, world.side, "조상이 아니다"),
        "unknown": ("unknown", "unknown", "16진수"),
        "dirty": (second + "+dirty", second + "+dirty", "16진수"),
        "empty": ("", '""', "16진수"),
        "fake": (FAKE, FAKE, "풀리지 않는다"),
        "null": (None, "null", "글이 아니다"),  # 값이 글이 아니면 그 자리에 JSON 꼴을 적는다
        "number": (12345678, "12345678", "글이 아니다"),
        "list": (["x"], '["x"]', "글이 아니다"),
    }
    files = {
        f"comp/reports/{name}/manifest.json": json.dumps({"git_commit": value, "official": True})
        for name, (value, _, _) in cases.items()
    }
    commit_files(world.repo, files, "Write the manifests")
    problems = records_of(world, record_rule(MANIFEST_GLOB, ["git_commit"]))

    expected = {name: case for name, case in cases.items() if case[1] is not None}
    assert places(problems) == sorted(
        ("record", f"comp/reports/{name}/manifest.json", 0) for name in expected
    )
    for problem in problems:
        name = problem.path.split("/")[2]
        _, shown, reason = expected[name]
        assert str(problem).startswith(f"record {problem.path}: git_commit: {shown}: "), name
        assert reason in str(problem), name


def test_record_keys_are_found_at_any_depth_and_in_jsonl(world, capsys):
    # 값 셋: json 하나(깊이 셋, 줄임 해시, 맨 앞에 BOM)와 jsonl 둘(줄 끝 CR, 공백뿐인 줄). 등록한 키가 아닌 것은 세지 않는다.
    nested = {"a": {"b": [{"commit": world.second[:7], "other_commit": "unknown"}]}}
    rows = [{"meta": {"asr": {"commit": world.second}}}, {"commit": world.second, "n": 1}]
    commit_files(
        world.repo,
        {
            "comp/reports/a/data.json": b"\xef\xbb\xbf" + json.dumps(nested).encode("utf-8"),
            "comp/reports/b/rows.jsonl": (
                json.dumps(rows[0]) + "\r\n \r\n" + json.dumps(rows[1]) + "\r\n"
            ).encode("utf-8"),
        },
        "Write record files",
    )
    world.set_registry(record_rule("comp/reports/*/*", ["commit"]))
    assert main(["--repo", str(world.repo)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1].split(", ")[1:] == ["기록 값 3개", "짝 0개", "문제 0개"]


def test_record_problem_line_has_the_line_number_for_jsonl(world):
    rows = [{"commit": world.second}, {"x": 1}, {"commit": "unknown"}]
    commit_files(
        world.repo,
        {"comp/reports/b/rows.jsonl": "".join(json.dumps(row) + "\n" for row in rows)},
        "Write a record file",
    )
    problems = records_of(world, record_rule("comp/reports/*/*.jsonl", ["commit"]))
    assert places(problems) == [("record", "comp/reports/b/rows.jsonl", 3)]
    assert str(problems[0]).startswith("record comp/reports/b/rows.jsonl:3: commit: unknown: ")


def test_record_key_missing_from_some_files_is_not_a_problem(world):
    # 파일 단위로는 너그럽다: glob에 걸린 파일 가운데 그 키가 없는 파일이 섞여 있는 것은 문제가 아니고 값으로 세지도
    # 않는다. 키가 든 파일이 하나라도 있으면 된다.
    commit_files(
        world.repo,
        {
            "comp/reports/a/manifest.json": json.dumps({"git_commit": world.second}),
            "comp/reports/b/manifest.json": json.dumps({"official": True}),
        },
        "Write record files",
    )
    registry = load_registry(
        world.set_registry(record_rule(MANIFEST_GLOB, ["git_commit"])), display="tools/evidence.toml"
    )
    report = check_evidence.scan_records(world.repo, registry)
    assert report.problems == ()
    assert report.values == 1


def test_record_key_found_in_no_file_is_a_problem(world, capsys):
    # 규칙 단위로는 엄격하다: 등록한 키가 glob에 맞는 파일 전체에서 한 번도 안 나오면 키 이름의 오타이거나 낡은 등록이다.
    # 이것을 알리지 않으면 그 항목은 아무것도 검사하지 않은 채 종료 0으로 끝난다.
    commit_files(
        world.repo,
        {
            "comp/reports/a/manifest.json": json.dumps({"git_commit": world.second}),
            "comp/reports/b/manifest.json": json.dumps({"git_commit": world.first, "official": True}),
        },
        "Write record files",
    )
    # 키 둘 가운데 하나만 오타이면 그 키만 문제이고, 맞는 키의 값은 그대로 센다.
    registry = load_registry(
        world.set_registry(record_rule(MANIFEST_GLOB, ["git_commit", "git_comit"])),
        display="tools/evidence.toml",
    )
    report = check_evidence.scan_records(world.repo, registry)
    assert report.values == 2
    assert [str(problem) for problem in report.problems] == [
        "record tools/evidence.toml: [[record]] 1번째: keys - git_comit: "
        "glob에 맞는 파일 2개 어디에도 이 키가 없다(오타이거나 낡은 등록이다)"
    ]
    # 키가 모두 오타이면 키마다 하나씩 알리고(같은 키를 두 번 적어도 한 번만), 검사는 종료 1이다. 센 값은 없다.
    world.set_registry(record_rule(MANIFEST_GLOB, ["git_comit", "commit_git", "git_comit"]))
    assert main(["--repo", str(world.repo)]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3
    assert "keys - commit_git: " in lines[0] and "keys - git_comit: " in lines[1]
    assert lines[-1].split(", ")[1:] == ["기록 값 0개", "짝 0개", "문제 2개"]


def test_record_tree_must_match_the_component_tree(world):
    registry = record_rule(MANIFEST_GLOB, ["git_commit"])
    tree = git(world.repo, "rev-parse", f"{world.second}:comp")
    write_manifest(world, git_commit=world.second, git_tree=tree)
    assert records_of(world, registry) == []

    other = "0" * 40
    write_manifest(world, git_commit=world.second, git_tree=other)
    problems = records_of(world, registry)
    assert places(problems) == [("record", MANIFEST, 0)]
    assert str(problems[0]).startswith(f"record {MANIFEST}: git_tree: {other}: ")
    assert tree in str(problems[0]) and "comp" in str(problems[0])


@pytest.mark.parametrize(
    ("tree", "shown"),
    [pytest.param(None, "null", id="null"), pytest.param(12345678, "12345678", id="숫자")],
)
def test_record_tree_that_is_not_a_string_is_a_problem(world, tree, shown):
    write_manifest(world, git_commit=world.second, git_tree=tree)
    problems = records_of(world, record_rule(MANIFEST_GLOB, ["git_commit"]))
    assert places(problems) == [("record", MANIFEST, 0)]
    assert str(problems[0]).startswith(f"record {MANIFEST}: git_tree: {shown}: ")
    assert "글이 아니다" in str(problems[0])


def test_record_tree_of_a_commit_without_the_folder_is_a_problem(world):
    # first에는 comp 폴더가 없다(합치기 전 커밋과 같다). 그 커밋의 comp 트리를 적었다고 할 수는 없다.
    assert git(world.repo, "cat-file", "-t", f"{world.second}:comp") == "tree"
    write_manifest(world, git_commit=world.first, git_tree="0" * 40)
    problems = records_of(world, record_rule(MANIFEST_GLOB, ["git_commit"]))
    assert places(problems) == [("record", MANIFEST, 0)]
    assert "그 커밋에 이 폴더가 없다" in str(problems[0])


def test_record_tree_is_not_compared_when_the_commit_is_already_a_problem(world):
    write_manifest(world, git_commit=world.side, git_tree="0" * 40)
    problems = records_of(world, record_rule(MANIFEST_GLOB, ["git_commit"]))
    assert places(problems) == [("record", MANIFEST, 0)]  # 문제를 두 번 내지 않는다
    assert "git_commit" in str(problems[0]) and "조상이 아니다" in str(problems[0])


def test_record_tree_is_compared_for_each_registered_key_of_the_same_object(world):
    tree = git(world.repo, "rev-parse", f"{world.second}:comp")
    write_manifest(
        world, git_commit=world.second, source_commit=world.first, git_tree=tree, other={"git_commit": "x"}
    )
    registry = load_registry(
        world.set_registry(record_rule(MANIFEST_GLOB, ["git_commit", "source_commit"])),
        display="tools/evidence.toml",
    )
    report = check_evidence.scan_records(world.repo, registry)
    # 값은 셋이다: 맨 위 객체의 git_commit·source_commit, 안쪽 객체(other)의 git_commit. 맨 위 객체의 git_commit은
    # 트리가 맞고, source_commit(first)에는 comp 폴더가 없어 문제다. 안쪽 객체는 git_tree를 함께 가지지 않아 트리를
    # 견주지 않지만, 값 x가 커밋 꼴이 아니라 문제다.
    assert report.values == 3
    texts = [str(problem) for problem in report.problems]
    assert len(texts) == 2
    assert any(": git_commit: x: " in text and "16진수" in text for text in texts)
    assert any(
        ": git_tree: " in text and "source_commit" in text and "그 커밋에 이 폴더가 없다" in text for text in texts
    )


def test_record_component_must_be_a_top_level_folder(world):
    write_manifest(world, git_commit=world.second, git_tree="0" * 40)
    problems = records_of(world, record_rule(MANIFEST_GLOB, ["git_commit"], component="nothing"))
    # 폴더 이름이 틀린 것은 그 항목의 문제 하나다. 값마다 트리를 견주며 같은 말을 되풀이하지 않는다.
    assert places(problems) == [("record", "tools/evidence.toml", 0)]
    assert "[[record]] 1번째: component" in str(problems[0])


def test_record_glob_without_files_is_a_problem(world):
    # 맞는 파일이 없으면 낡은 등록이라는 문제 하나뿐이다. 키가 어디에도 없다는 문제를 키마다 겹쳐 내지 않는다.
    problems = records_of(world, record_rule("comp/nothing/*.json", ["git_commit", "git_comit"]))
    assert places(problems) == [("record", "tools/evidence.toml", 0)]
    assert "[[record]] 1번째: glob" in str(problems[0]) and "낡은 등록" in str(problems[0])


def test_record_glob_star_does_not_cross_folders(world):
    matches = check_evidence.glob_matches
    assert matches(MANIFEST_GLOB, "comp/reports/a/manifest.json")
    assert not matches(MANIFEST_GLOB, "comp/reports/a/b/manifest.json")  # *는 폴더 하나다
    assert not matches(MANIFEST_GLOB, "comp/reports/manifest.json")
    assert not matches(MANIFEST_GLOB, "comp/reports/a/manifest.jsonl")
    assert matches("comp/reports/*.json", "comp/reports/x.json")
    assert not matches("comp/reports/*.json", "comp/reports/a/x.json")
    assert matches("comp/reports/dev-*-itn.jsonl", "comp/reports/dev-asr-v3-l-itn.jsonl")
    assert not matches("comp/reports/*.JSON", "comp/reports/x.json")  # 대소문자를 가린다
    # 한 폴더 더 깊은 파일은 읽지도 않는다. 깨진 JSON이어도 검사가 멈추지 않는다.
    commit_files(
        world.repo,
        {MANIFEST: json.dumps({"git_commit": world.second}), "comp/reports/a/b/manifest.json": "{broken"},
        "Write a nested record file",
    )
    assert records_of(world, record_rule(MANIFEST_GLOB, ["git_commit"])) == []


@pytest.mark.parametrize(
    ("rel", "content", "where"),
    [
        pytest.param(
            "comp/reports/a/broken.json",
            b'{"git_commit": ',
            "comp/reports/a/broken.json",
            id="깨진 JSON",
        ),
        pytest.param(
            "comp/reports/a/rows.jsonl",
            b'{"git_commit": "x"}\n{"git_commit": \n',
            "comp/reports/a/rows.jsonl:2",
            id="jsonl의 깨진 줄",
        ),
        pytest.param(
            "comp/reports/a/latin1.json",
            b'{"git_commit": "\xe9"}',
            "comp/reports/a/latin1.json",
            id="UTF-8이 아님",
        ),
    ],
)
def test_unreadable_record_file_stops_the_check(world, capsys, rel, content, where):
    # 읽지 못한 기록을 건너뛴 채 통과하면 안 된다. 문제로 세지 않고 종료 2로 멈추며, 어느 파일(jsonl이면 몇째 줄)인지 알린다.
    commit_files(world.repo, {rel: content}, "Write an unreadable record file")
    world.set_registry(record_rule("comp/reports/*/*", ["git_commit"]))
    for extra in ([], ["--report-only"]):
        assert main(["--repo", str(world.repo), *extra]) == 2
        captured = capsys.readouterr()
        assert where in captured.err
        assert captured.out == ""


def test_record_git_calls_do_not_grow_with_the_number_of_values(world, monkeypatch):
    # 값·파일·(커밋, 폴더) 쌍이 늘어도 git 호출 수는 늘지 않는다. 기록 파일마다 글이 다르고(블롭이 서로 다르다) 적힌 커밋도
    # 여럿이라(서로 다른 쌍이 여럿이다), 고유 파일마다 따로 읽거나 쌍마다 따로 묻는 퇴행도 호출 수를 늘려서 걸린다.
    # 파일이 모두 같은 글이면 블롭도 쌍도 하나뿐이라 그런 퇴행이 숨는다.
    commits = [world.second]
    for number in range(3):  # second 말고도 comp 폴더가 있고 트리가 서로 다른 커밋을 셋 더 만든다
        change = {f"comp/extra{number}.txt": f"{number}\n"}
        commits.append(commit_files(world.repo, change, f"Change comp {number}"))
    trees = {commit: git(world.repo, "rev-parse", f"{commit}:comp") for commit in commits}
    assert len(set(trees.values())) == len(commits)  # 전제: 쌍마다 트리가 다르다
    registry = record_rule(MANIFEST_GLOB, ["git_commit"])

    def git_calls() -> int:
        calls: list[list[str]] = []
        real_run = subprocess.run

        def spy(command, *args, **kwargs):
            calls.append(list(command))
            return real_run(command, *args, **kwargs)

        monkeypatch.setattr(check_evidence.subprocess, "run", spy)
        try:
            assert records_of(world, registry) == []
        finally:
            monkeypatch.undo()
        return len(calls)

    def write_manifests(count: int, usable: list[str]) -> None:
        # 파일마다 글이 다르다("n"이 다르다). 적힌 커밋은 usable을 돌아가며 쓰고, git_tree는 그 커밋의 것이다.
        files = {}
        for number in range(count):
            commit = usable[number % len(usable)]
            manifest = {"git_commit": commit, "git_tree": trees[commit], "n": number}
            files[f"comp/reports/run{number}/manifest.json"] = json.dumps(manifest)
        assert len(set(files.values())) == count  # 전제: 블롭이 파일마다 다르다
        commit_files(world.repo, files, f"Write {count} manifests")

    write_manifests(3, commits[:1])  # 값 3개, 블롭 3개, 쌍 1개
    few = git_calls()
    write_manifests(12, commits)  # 값 12개, 블롭 12개, 쌍 4개
    assert git_calls() == few  # 값마다·블롭마다·쌍마다 git을 따로 부르지 않는다(묶어서 한 번씩만 묻는다)


# ---------------------------------------------------------------------------------------------
# 9. 등록한 짝([[pair]])
# ---------------------------------------------------------------------------------------------

PAIR_DOC = "docs/pairs.md"


def write_pair_doc(world: World, *commits: str) -> None:
    """PAIR_DOC에 commits의 앞 7자를 한 줄씩 적어 커밋한다(where 문서의 글자 찾기를 통과시키는 글)."""
    text = "# 짝 기록\n\n" + "".join(f"- 커밋 {commit[:7]}에서 정했다.\n" for commit in commits)
    commit_files(world.repo, {PAIR_DOC: text}, "Write the pair document")


def test_pair_order_holds(world):
    # 여러 짝을 한 번에 등록해 한 번에 검사한다(짝의 id가 경우 이름이다).
    write_pair_doc(world, world.first, world.second, world.third, world.side)
    assert_not_a_commit_prefix(world.repo, FAKE)
    first, second, third, side = world.first, world.second, world.third, world.side
    cases = {
        "forward": (first, third),
        "short-forward": (first[:7], third[:7]),  # 앞 7자로 적어도 같다
        "adjacent": (second, third),
        "reverse": (third, first),  # 결과가 규칙보다 앞선 커밋이다
        "same": (third, third),
        "side-rule": (side, third),  # side 커밋은 HEAD의 조상이 아니다. 어느 쪽인지 말에 적는다.
        "side-result": (first, side),
        "both-side": (side, side),  # 둘 다 걸리면 둘 다 알린다
        "unknown-rule": (FAKE, third),
    }
    registry = "".join(pair_rule(name, rule, result, PAIR_DOC) for name, (rule, result) in cases.items())
    problems = pairs_of(world, registry)

    by_name: dict[str, list[str]] = {}
    for problem in problems:
        assert (problem.kind, problem.path, problem.line) == ("pair", PAIR_DOC, 0)
        name = problem.message.split(": ", 1)[0]
        assert str(problem).startswith(f"pair {PAIR_DOC}: {name}: ")
        by_name.setdefault(name, []).append(str(problem))
    assert set(by_name) == {"reverse", "same", "side-rule", "side-result", "both-side", "unknown-rule"}

    assert len(by_name["reverse"]) == 1 and "규칙 커밋이 결과 커밋의 조상이 아니다" in by_name["reverse"][0]
    assert len(by_name["same"]) == 1 and "서로 다른 커밋" in by_name["same"][0]
    assert len(by_name["side-rule"]) == 1
    assert "규칙 커밋" in by_name["side-rule"][0] and "HEAD의 조상이 아니다" in by_name["side-rule"][0]
    assert len(by_name["side-result"]) == 1
    assert "결과 커밋" in by_name["side-result"][0] and "HEAD의 조상이 아니다" in by_name["side-result"][0]
    assert len(by_name["both-side"]) == 2
    assert len(by_name["unknown-rule"]) == 1
    assert "규칙 커밋" in by_name["unknown-rule"][0] and "풀리지 않는다" in by_name["unknown-rule"][0]


def test_pair_must_be_written_in_its_document(world):
    write_pair_doc(world, world.first)  # 결과(third)의 앞 7자가 문서에 없다
    registry = pair_rule("written", world.first, world.third, PAIR_DOC)
    problems = pairs_of(world, registry)
    assert places(problems) == [("pair", PAIR_DOC, 0)]
    assert "결과 커밋" in str(problems[0]) and world.third[:7] in str(problems[0])

    write_pair_doc(world, world.third)  # 이번에는 규칙(first)이 없다
    problems = pairs_of(world, registry)
    assert places(problems) == [("pair", PAIR_DOC, 0)]
    assert "규칙 커밋" in str(problems[0]) and world.first[:7] in str(problems[0])

    commit_files(world.repo, {PAIR_DOC: "# 비었다\n"}, "Empty the pair document")
    assert len(pairs_of(world, registry)) == 2  # 없는 쪽마다 문제다

    # 문서가 HEAD의 트리에 없으면 그것도 문제다.
    missing = pairs_of(world, pair_rule("written", world.first, world.third, "docs/없는문서.md"))
    assert places(missing) == [("pair", "docs/없는문서.md", 0)]
    assert "HEAD의 트리에 없다" in str(missing[0])


def test_pair_with_equal_commit_seconds_passes(world):
    date = "2026-01-02T03:04:05+0000"
    rule = commit_files(world.repo, {"comp/a.txt": "1\n"}, "The rule", date=date)
    result = commit_files(world.repo, {"comp/b.txt": "2\n"}, "The result", date=date)
    assert commit_seconds(world.repo, rule) == commit_seconds(world.repo, result)  # 전제: 같은 초다
    write_pair_doc(world, rule, result)
    assert pairs_of(world, pair_rule("same-second", rule, result, PAIR_DOC)) == []  # <=라서 통과한다


def test_pair_commit_time_must_not_go_backwards(world):
    rule = commit_files(world.repo, {"comp/a.txt": "1\n"}, "The rule", date="2026-01-02T03:04:05+0000")
    result = commit_files(world.repo, {"comp/b.txt": "2\n"}, "The result", date="2026-01-02T03:04:04+0000")
    assert commit_seconds(world.repo, rule) == commit_seconds(world.repo, result) + 1  # 전제: 결과가 1초 이르다
    write_pair_doc(world, rule, result)
    problems = pairs_of(world, pair_rule("clock", rule, result, PAIR_DOC))
    assert places(problems) == [("pair", PAIR_DOC, 0)]
    assert "시각" in str(problems[0]) and "clock" in str(problems[0])


def test_pair_ids_must_be_unique(tmp_path):
    text = (
        pair_rule("same", "1234abc", "2345bcd", "docs/a.md")
        + pair_rule("other", "1234abc", "3456cde", "docs/a.md")
        + pair_rule("same", "1234abc", "4567def", "docs/a.md")
    )
    registry = parse_registry(tmp_path, text)
    assert places(list(registry.problems)) == [("pair", "tools/evidence.toml", 0)]
    assert "[[pair]] 3번째" in str(registry.problems[0]) and "id" in str(registry.problems[0])
    assert [pair.id for pair in registry.pairs] == ["same", "other"]  # 겹친 뒤의 것은 등록에서 빠진다
    assert registry.pair_total == 3  # 끝 줄의 짝 수는 등록한 항목 수다(꼴 오류인 것도 센다)


def test_pair_git_failure_stops_the_check(world, monkeypatch, capsys):
    # merge-base --is-ancestor는 조상이 아니면 1이다. 그 밖의 종료 코드는 읽지 못한 것이라 종료 2다.
    write_pair_doc(world, world.first, world.third)
    world.set_registry(pair_rule("order", world.first, world.third, PAIR_DOC))
    real_run = check_evidence._run

    def failing(repo, *args, **kwargs):
        if args and args[0] == "merge-base":
            return subprocess.CompletedProcess(args, 128, stdout=b"", stderr=b"fatal: simulated failure\n")
        return real_run(repo, *args, **kwargs)

    monkeypatch.setattr(check_evidence, "_run", failing)
    assert main(["--repo", str(world.repo), "--report-only"]) == 2
    captured = capsys.readouterr()
    assert "merge-base" in captured.err and "simulated failure" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("which", ["tree lookup", "commit times"])
def test_a_failing_git_read_in_the_record_and_pair_checks_stops_the_check(world, monkeypatch, capsys, which):
    # 기록 값의 트리 조회나 짝의 커밋 시각 읽기가 실패해도 빈 결과로 넘기지 않고 종료 2로 끝낸다. 두 읽기만 겨냥하려고,
    # 트리 조회는 `cat-file --batch-check`로, 커밋 시각은 커밋 해시만 넣은 `cat-file --batch`로 알아본다(글을 읽는
    # 첫 검사의 `cat-file --batch`는 파일 객체 해시를 넣으므로 지나간다).
    tree = git(world.repo, "rev-parse", f"{world.second}:comp")
    write_manifest(world, git_commit=world.second, git_tree=tree)
    write_pair_doc(world, world.first, world.third)
    world.set_registry(
        record_rule(MANIFEST_GLOB, ["git_commit"]) + pair_rule("order", world.first, world.third, PAIR_DOC)
    )
    commits = {world.first, world.third}
    real_run = check_evidence._run
    targeted = []

    def failing(repo, *args, **kwargs):
        sent = kwargs.get("stdin")
        names = sent.decode("ascii").split() if sent else []
        if args and args[0] == "cat-file":
            hit = "--batch-check" in args if which == "tree lookup" else bool(names) and set(names) <= commits
            if hit:
                targeted.append(args)
                failure = b"fatal: simulated failure\n"
                return subprocess.CompletedProcess(args, 128, stdout=b"", stderr=failure)
        return real_run(repo, *args, **kwargs)

    monkeypatch.setattr(check_evidence, "_run", failing)
    assert main(["--repo", str(world.repo), "--report-only"]) == 2
    captured = capsys.readouterr()
    assert targeted  # 겨냥한 읽기가 실제로 불렸다
    assert "simulated failure" in captured.err
    assert captured.out == ""


def test_commit_value_problem_reasons():
    problem = check_evidence.commit_value_problem
    first, second, other = "abcdef0" + "1" * 33, "abcdef0" + "2" * 33, "1234567" + "8" * 33
    by_prefix = build_prefix_index([first, second, other])
    ancestors = frozenset([first, other])
    assert problem(first, by_prefix, ancestors) == (None, first)
    assert problem("abcdef01", by_prefix, ancestors) == (None, first)  # 더 길게 적으면 하나로 좁혀진다
    reason, commit = problem("abcdef0", by_prefix, ancestors)
    assert commit is None and "모호" in reason
    reason, commit = problem("abcdef02", by_prefix, ancestors)
    assert commit is None and "조상이 아니다" in reason
    reason, commit = problem("bbbbbbb", by_prefix, ancestors)
    assert commit is None and "풀리지 않는다" in reason
    for value in ("unknown", "", "ABCDEF0", "abcdef", "a" * 41, first + "+dirty"):
        reason, commit = problem(value, by_prefix, ancestors)
        assert commit is None and "16진수" in reason, value
    for value in (None, 12345678, ["x"], {"a": 1}, True):
        reason, commit = problem(value, by_prefix, ancestors)
        assert commit is None and "글이 아니다" in reason, value


def test_digit_only_commit_values_are_accepted(tmp_path):
    # 등록 값과 기록 값은 숫자뿐이어도 꼴이 맞다(a~f 글자 조건은 글에서 낱말을 뽑을 때만 쓴다). 앞 7자가 숫자뿐인 진짜
    # 커밋은 시험에서 만들 수 없으므로, 풀이는 가짜 커밋을 넣은 순수 함수로 본다.
    registry = parse_registry(tmp_path, pair_rule("digits", "1234567", "7654321", "docs/a.md"))
    assert registry.problems == ()
    assert (registry.pairs[0].rule, registry.pairs[0].result) == ("1234567", "7654321")
    ancestor, other = "1234567" + "8" * 33, "7654321" + "9" * 33
    by_prefix = build_prefix_index([ancestor, other])
    problem = check_evidence.commit_value_problem
    assert problem("1234567", by_prefix, frozenset([ancestor])) == (None, ancestor)
    reason, commit = problem("7654321", by_prefix, frozenset([ancestor]))
    assert commit is None and "조상이 아니다" in reason


def test_record_and_pair_checks_only_run_read_commands(world, monkeypatch):
    tree = git(world.repo, "rev-parse", f"{world.second}:comp")
    write_manifest(world, git_commit=world.second, git_tree=tree)
    write_pair_doc(world, world.first, world.third)
    world.set_registry(
        record_rule(MANIFEST_GLOB, ["git_commit"]) + pair_rule("order", world.first, world.third, PAIR_DOC)
    )
    status_before = git(world.repo, "status", "--porcelain")
    head_before = git(world.repo, "rev-parse", "HEAD")
    calls: list[list[str]] = []
    real_run = subprocess.run

    def spy(command, *args, **kwargs):
        calls.append(list(command))
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(check_evidence.subprocess, "run", spy)
    assert main(["--repo", str(world.repo)]) == 0
    monkeypatch.undo()
    allowed = {"rev-parse", "rev-list", "ls-tree", "cat-file", "merge-base"}
    assert {command[4] for command in calls} >= {"merge-base", "cat-file"}  # 두 검사가 실제로 돌았다
    for command in calls:
        assert command[:4] == ["git", "--no-optional-locks", "-C", str(world.repo)], command
        assert command[4] in allowed, command
    assert git(world.repo, "status", "--porcelain") == status_before
    assert git(world.repo, "rev-parse", "HEAD") == head_before


def test_summary_counts_record_values_and_registered_pairs(world, capsys):
    # 끝 줄의 기록 값은 찾은 값(문제인 값 포함), 짝은 등록한 [[pair]] 항목 수(꼴 오류인 항목 포함)다.
    write_manifest(world, git_commit=world.second, other_commit="unknown", git_tree=None)
    write_pair_doc(world, world.first, world.third)
    world.set_registry(
        record_rule(MANIFEST_GLOB, ["git_commit", "other_commit"])
        + pair_rule("good", world.first, world.third, PAIR_DOC)
        + pair_rule("reverse", world.third, world.first, PAIR_DOC)
        + '[[pair]]\nid = "broken"\n'
    )
    assert main(["--repo", str(world.repo)]) == 1
    lines = capsys.readouterr().out.splitlines()
    # 기록 값은 둘(git_commit은 커밋이 맞고, other_commit은 unknown이라 문제). git_tree가 null이라 맞는 커밋 쪽의
    # 트리 비교도 문제 하나를 더 낸다: 기록 문제 둘. 짝은 셋을 등록했다: reverse는 순서가 틀려 문제 하나, broken은 빠진
    # 키 넷(rule, result, where, what)이 문제 넷: 짝 문제 다섯. 합쳐 문제 일곱.
    kinds = [line.split()[0] for line in lines[:-1]]
    assert kinds.count("record") == 2
    assert kinds.count("pair") == 5
    assert lines[-1].split(", ")[1:] == ["기록 값 2개", "짝 3개", "문제 7개"]


# 꼴 시험용 [[record]]·[[pair]] 항목의 맞는 바탕. 시험은 여기서 한 키만 고치거나 빼서 그 항목의 문제를 본다.
RECORD_BASE = {"glob": '"c/*.json"', "keys": '["a"]', "component": '"c"', "what": '"x"'}
PAIR_BASE = {"id": '"p"', "rule": '"1234abc"', "result": '"2345bcd"', "where": '"d.md"', "what": '"x"'}


def entry_toml(base: dict[str, str], **changes: str | None) -> str:
    """base에서 changes만 바꾼 항목 본문(TOML 줄들). 값은 TOML 값 글이고, None이면 그 키를 뺀다. 새 키는 끝에 붙는다."""
    fields = {**base, **changes}
    return "".join(f"{key} = {value}\n" for key, value in fields.items() if value is not None)


@pytest.mark.parametrize(
    ("changes", "key"),
    [
        pytest.param({"glob": None}, "glob", id="glob이 없다"),
        pytest.param({"keys": None}, "keys", id="keys가 없다"),
        pytest.param({"component": None}, "component", id="component가 없다"),
        pytest.param({"what": None}, "what", id="what이 없다"),
        pytest.param({"keys": "[]"}, "keys", id="빈 keys"),
        pytest.param({"keys": '[""]'}, "keys", id="빈 키 이름"),
        pytest.param({"keys": '"a"'}, "keys", id="목록이 아닌 keys"),
        pytest.param({"keys": "[1]"}, "keys", id="글이 아닌 키 이름"),
        pytest.param({"glob": '"c/**/x.json"'}, "glob", id="**"),
        pytest.param({"glob": '"c\\\\x.json"'}, "glob", id="역슬래시"),
        pytest.param({"glob": '"/c/x.json"'}, "glob", id="맨 앞의 /"),
        pytest.param({"glob": '"c//x.json"'}, "glob", id="빈 조각"),
        pytest.param({"glob": '"c/x/"'}, "glob", id="끝의 /"),
        pytest.param({"component": '"c/d"'}, "component", id="폴더가 둘"),
        pytest.param({"what": '""'}, "what", id="빈 what"),
        pytest.param({"waht": '"오타"'}, "waht", id="모르는 키"),
    ],
)
def test_malformed_record_entries_are_problems_of_that_entry(tmp_path, changes, key):
    registry = parse_registry(tmp_path, "[[record]]\n" + entry_toml(RECORD_BASE, **changes))
    problems = [problem for problem in registry.problems if problem.kind == "record"]
    assert len(problems) >= 1
    assert all("[[record]] 1번째" in str(problem) for problem in problems)
    assert any(f"{key} -" in str(problem) for problem in problems)


@pytest.mark.parametrize(
    ("changes", "key"),
    [
        pytest.param({"id": None}, "id", id="id가 없다"),
        pytest.param({"rule": None}, "rule", id="rule이 없다"),
        pytest.param({"result": None}, "result", id="result가 없다"),
        pytest.param({"where": None}, "where", id="where가 없다"),
        pytest.param({"what": None}, "what", id="what이 없다"),
        pytest.param({"id": '""'}, "id", id="빈 id"),
        pytest.param({"rule": '"xyz1234"'}, "rule", id="16진수가 아닌 rule"),
        pytest.param({"rule": '"1234ab"'}, "rule", id="6자 rule"),
        pytest.param({"result": '"2345BCD"'}, "result", id="대문자 result"),
        pytest.param({"rule": "1234567"}, "rule", id="글이 아닌 rule"),
        pytest.param({"waht": '"오타"'}, "waht", id="모르는 키"),
    ],
)
def test_malformed_pair_entries_are_problems_of_that_entry(tmp_path, changes, key):
    registry = parse_registry(tmp_path, "[[pair]]\n" + entry_toml(PAIR_BASE, **changes))
    problems = [problem for problem in registry.problems if problem.kind == "pair"]
    assert len(problems) >= 1
    assert all("[[pair]] 1번째" in str(problem) for problem in problems)
    assert any(f"{key} -" in str(problem) for problem in problems)
    assert registry.pair_total == 1  # 꼴이 틀린 항목도 등록한 항목이라 센다
