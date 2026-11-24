"""`tools/check_evidence.py` 시험.

이 도구는 추적 파일(HEAD의 내용)에 적힌 커밋 해시 참조가 이 저장소의 git 이력과 맞는지 본다. 7~40자
16진수 낱말을 뽑아 이력으로 풀어 보고, 풀리는데 HEAD의 조상이 아니거나 둘 이상에 맞으면(모호) 알리고,
문서(.md)가 커밋 참조라고 밝혀 적은 낱말이 풀리지 않으면 알린다. 다른 저장소의 해시는 등록 파일
(tools/evidence.toml)의 [[external]]로 면제하고, 낡거나 잘못된 등록도 알린다. 한 시험은 한 가지만
어긋나게 해서, 어느 규칙이 어떤 문제를 냈는지 시험이 정확히 가리킬 수 있게 한다. 아래 일곱 구역을 이 파일의
구역 순서대로 고정한다.
    1. 낱말 뽑기: 7~40자 소문자 16진수를 ASCII 경계로(뒤에 한글 조사가 붙어도) 줄 번호와 함께 뽑고, 문서가
       커밋 참조로 적었는지(백틱 한 쌍, `커밋`·`commit` 바로 뒤)도 함께 돌려준다. a~f 글자가 하나도 없는
       숫자뿐인 것은 그렇게 적은 자리에 있을 때만 낱말이다(날짜나 숫자 꼬리를 해시로 읽지 않으려는 것이다).
    2. 이력으로 풀기: 앞부분이 같은 커밋을 찾고, 둘 이상이면 모호다.
    3. 규칙 3·4: 풀리는 낱말은 HEAD의 조상이어야 하고, 문서가 커밋 참조로 적은 낱말은 풀려야 한다.
    4. 규칙 5와 등록 파일: 등록은 그 파일의 그 낱말만 면제하고, 낡거나 잘못된 등록과 꼴이 틀린 항목은 알린다.
    5. 읽는 대상: HEAD의 내용만 읽고(작업 트리·색인에 흔들리지 않는다), 잠금 파일·글이 아닌 파일·기호 링크·
       서브모듈은 건너뛰고, UTF-8이 아닌 글도 멈추지 않는다. 어느 ref에서도 닿지 않는 커밋은 세지 않는다.
    6. 시작할 수 없음: 얕은 복제, git 실패, 저장소가 아님, 커밋 없음은 종료 2다(읽지 못했는데 통과하지 않는다).
    7. 명령줄: 종료 코드 0·1·2, 출력 꼴과 정렬, --report-only, 파이프로 나가는 UTF-8 출력, 도움말, 읽기 명령만 부름.

시험용 저장소는 임시 폴더에 빈 git 저장소를 만들고 커밋을 쌓아 꾸민다. 고정물 world는 main에 커밋 셋(first →
second → third)을 쌓고, 그 사이에 갈라진 side 브랜치에만 있는 커밋 하나(main에 합치지 않는다)를 둔다. third의
문서와 코드는 앞선 두 커밋의 앞 7자를 적고 있어서 처음 상태에서는 문제가 없다. 이 저장소를 만드는 데 git을
스무 번쯤 부르므로, 원본을 모듈에서 한 번만 만들고(world_template) 시험마다 그 폴더를 복사해 쓴다. 저장소가
필요 없는 시험(낱말 뽑기, 풀이, 등록 파일의 꼴)은 world를 쓰지 않는다. 앞 7자가 모두 숫자인 해시는 참조 표시
없이 적으면 낱말이 아니므로, 시험이 표시 없이 문서에 적는 해시는 short()로 줄인 것만 쓴다(해시는 고를 수 없어
앞 7자가 숫자뿐인 진짜 커밋은 만들 수 없다. 그런 낱말이 풀리는 쪽은 가짜 커밋을 넣은 순수 함수로 본다). 등록
파일은 저장소 안 tools/evidence.toml에 추적하지 않는 파일로 쓴다(도구는 등록 파일만 작업 트리에서 읽고, 검사
대상은 HEAD에서 읽는다). 이 저장소 자신을 대상으로 하는 시험은 이 파일에 없다.
"""

import os
import shutil
import subprocess
import sys
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


def commit_files(repo: Path, files: dict[str, str | bytes], message: str) -> str:
    """files를 쓰고 그 파일만 스테이징해 커밋한 뒤, 새 커밋의 40자 해시를 돌려준다."""
    for rel, content in files.items():
        write(repo, rel, content)
    git(repo, "add", "--", *files)
    git(repo, "commit", "--quiet", "-m", message)
    return git(repo, "rev-parse", "HEAD")


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
    second = commit_files(repo, {"src/app.py": "VALUE = 2\n"}, "Change the value")
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
    # 처음 상태의 3개 + 이 문서의 5개(등록 통과 1, 등록 없는 문제 1, 풀림 둘, 조상 아님 1). 기록 값·짝은 이
    # 도구가 아직 세지 않는다.
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
    # record와 pair는 받는 꼭대기 표다(모르는 표가 아니다). 항목 안의 키는 여기서 보지 않는다.
    registry = parse_registry(tmp_path, "[[record]]\n[[pair]]\n[[pair]]\n")
    assert registry.problems == ()
    assert (len(registry.records), len(registry.pairs)) == (1, 2)


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
        "종료 코드",
        "git fetch --unshallow",
    ):
        assert needle in text, needle


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
