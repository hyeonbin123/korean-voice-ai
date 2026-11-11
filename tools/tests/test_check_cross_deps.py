"""`tools/check_cross_deps.py` 시험.

이 도구는 구성 요소 사이의 의존(한 구성 요소의 코드가 다른 구성 요소의 파일을 쓰는 곳)을 선언 파일
(tools/cross-deps.toml)에 글자로 묶어 두고, 그 선언이 지금도 맞는지 git 저장소를 읽어 확인한다. 어긋날 때마다
문제로 알리고 조용히 건너뛰지 않는다. 한 시험은 한 가지만 어긋나게 해서, 어느 검사가 어떤 문제를 냈는지
시험이 정확히 가리킬 수 있게 한다. 아래 여덟 구역을 이 파일의 구역 순서대로 고정한다.
    1. 통과: 쓰는 쪽 코드에 선언한 글이 있고, 대상 파일을 git이 추적하고, 설명 문서가 그 경로들을 적고 있으면
       문제가 없다.
    2. 쓰는 쪽 코드와 추적 여부: 선언한 글이 코드에서 사라지거나, 대상·코드 파일이 추적에서 빠지면 알린다.
    3. 로컬에만 있는 대상(환경 폴더, 모델 폴더)은 --local을 줄 때만 본다.
    4. 설명 문서: 쓰는 쪽 코드·대상·고정 코드 경로와 고정 커밋의 앞 7자 가운데 하나라도 빠지면 알린다.
    5. 고정 사본: 코드에 적힌 커밋·경로·blob이 이 저장소의 이력과 맞는지 본다. 이력이 모자라거나 값이
       틀리면 알린다.
    6. 선언 파일의 꼴: 모르는 키, 빈 글, 깨진 정규식은 조용히 넘기지 않고 문제로 알린다.
    7. 명령줄: 종료 코드 0(통과) / 1(문제) / 2(검사를 시작할 수 없음)와 출력 꼴, 파이프로 나가는 UTF-8 출력.
    8. 이 저장소의 실제 선언이 지금도 맞는다.

시험용 저장소는 conftest의 git_repo(tmp_path 안의 빈 저장소)에 글 몇 개를 커밋해 만든다. 먼저 src/v.py를
커밋해 '이른 커밋'을 만들고(고정 사본의 원본), 그 뒤에 쓰는 쪽 코드 a/code.py, 대상 b/data.json, 고정
상수를 가진 a/pin.py, 설명 문서 docs/architecture.md, 선언 파일을 커밋한다. 이 저장소의 실제 선언을 읽는
시험은 test_repository_dependencies_hold 하나뿐이고, 나머지는 모두 위 고정물만 읽는다.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from check_cross_deps import check, load, main
from conftest import REPO

# 이 파일은 <저장소>/tools/tests/에 있다. parents[1] = tools. 도구를 스크립트로 직접 돌리는 시험이 쓴다.
TOOLS = Path(__file__).resolve().parents[1]

# 고정물의 선언 파일. 의존 하나(a가 b의 데이터 파일을 읽는다)와 고정 사본 하나(a/pin.py의 상수)를 담는다.
# local의 b/.venv는 일부러 만들지 않는 폴더라, --local을 줄 때만 문제가 되는 대상을 흉내 낸다.
DECLARATION = """doc = "docs/architecture.md"

[[dep]]
id = "a-reads-b"
from = "a"
to = "b"
what = "a의 코드가 b의 데이터 파일을 읽는다"
tracked = ["b/data.json"]
local = ["b/.venv"]
  [[dep.code]]
  path = "a/code.py"
  text = "../b/data.json"

[[pinned]]
id = "v-copy"
code = "a/pin.py"
commit_pattern = 'PINNED_COMMIT = "([0-9a-f]{40})"'
source_pattern = 'PINNED_SOURCE = "([^"]+)"'
blob_pattern = 'PINNED_BLOB = "([0-9a-f]{40})"'
"""


def write(root: Path, rel: str, text: str) -> Path:
    """root 아래 rel 경로에 text를 UTF-8(BOM 없음), 줄바꿈 LF로 쓴다. 폴더가 없으면 만든다."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def read(root: Path, rel: str) -> str:
    """root 아래 rel 파일을 UTF-8로 읽는다."""
    return (root / rel).read_text(encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    """repo 안에서 git을 부르고 표준 출력(앞뒤 공백 제외)을 돌려준다. 실패하면 CalledProcessError."""
    done = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return done.stdout.strip()


def architecture_doc(early: str) -> str:
    """고정물의 설명 문서.

    쓰는 쪽 코드, 대상, 고정 코드 세 경로와 이른 커밋의 앞 7자를 글로 적는다(문서 검사가 이 넷을 본다).
    """
    return (
        "# 구조\n"
        "\n"
        "- [a/code.py](../a/code.py)가 [b/data.json](../b/data.json)을 읽는다.\n"
        f"- 고정 사본은 [a/pin.py](../a/pin.py)가 가리키는 커밋 {early[:7]}의 src/v.py다.\n"
    )


@dataclass
class World:
    """시험용 저장소 하나와, 시험이 값을 바꿔 쓰는 해시 둘."""

    repo: Path
    early: str  # 이른 커밋의 40자 해시(고정 사본의 원본 커밋)
    blob: str  # 그 커밋 시점 src/v.py의 blob 해시(a/pin.py의 PINNED_BLOB이 가리키는 값)

    @property
    def deps(self) -> Path:
        """선언 파일 경로(<저장소>/tools/cross-deps.toml, 도구의 기본 위치와 같다)."""
        return self.repo / "tools" / "cross-deps.toml"


@pytest.fixture
def world(git_repo: Path) -> World:
    """위 머리말의 고정물을 만든다. 이른 커밋 하나 뒤에 나머지 파일을 한 커밋으로 넣는다."""
    write(git_repo, "src/v.py", "VALUE = 1\n")
    git(git_repo, "add", "--", "src/v.py")
    git(git_repo, "commit", "--quiet", "-m", "Add the pinned source")
    early = git(git_repo, "rev-parse", "HEAD")
    blob = git(git_repo, "rev-parse", f"{early}:src/v.py")

    write(git_repo, "a/code.py", 'DATA = "../b/data.json"\n')
    write(git_repo, "b/data.json", '{"k": 1}\n')
    write(
        git_repo,
        "a/pin.py",
        f'PINNED_COMMIT = "{early}"\nPINNED_SOURCE = "src/v.py"\nPINNED_BLOB = "{blob}"\n',
    )
    write(git_repo, "docs/architecture.md", architecture_doc(early))
    write(git_repo, "tools/cross-deps.toml", DECLARATION)
    git(
        git_repo,
        "add",
        "--",
        "a/code.py",
        "b/data.json",
        "a/pin.py",
        "docs/architecture.md",
        "tools/cross-deps.toml",
    )
    git(git_repo, "commit", "--quiet", "-m", "Add the callers, the target and the document")
    return World(repo=git_repo, early=early, blob=blob)


def problems_of(world: World, *, local: bool = False) -> list[str]:
    """고정물의 선언 파일을 읽어 검사한 문제 줄들."""
    return check(load(world.deps), world.repo, local=local)


# ---------------------------------------------------------------------------------------------
# 1. 통과
# ---------------------------------------------------------------------------------------------


def test_dependencies_pass_when_code_tracked_files_and_doc_agree(world):
    assert problems_of(world) == []


# ---------------------------------------------------------------------------------------------
# 2. 쓰는 쪽 코드와 추적 여부
# ---------------------------------------------------------------------------------------------


def test_changed_path_text_is_reported(world):
    # 경로 계산 코드가 바뀌면 문서가 틀리게 되므로, 선언한 글이 코드에서 사라지면 알려야 한다.
    write(world.repo, "a/code.py", 'DATA = "../b/other.json"\n')
    problems = problems_of(world)
    assert len(problems) == 1
    assert "a/code.py" in problems[0]
    assert "../b/data.json" in problems[0]


def test_untracked_target_is_reported(world):
    # 디스크에는 있지만 add도 commit도 하지 않은 대상. 새로 받은 복제본에는 없으므로 문제다.
    write(world.repo, "b/extra.json", "{}\n")
    write(
        world.repo,
        "tools/cross-deps.toml",
        DECLARATION.replace('tracked = ["b/data.json"]', 'tracked = ["b/data.json", "b/extra.json"]'),
    )
    # 문서는 대상 경로를 적고 있어야 하므로 새 대상도 문서에 적어, 추적 여부만 어긋나게 한다.
    write(world.repo, "docs/architecture.md", read(world.repo, "docs/architecture.md") + "- b/extra.json\n")
    problems = problems_of(world)
    assert len(problems) == 1
    assert "b/extra.json" in problems[0]


@pytest.mark.parametrize("path", ["a/code.py", "a/pin.py"])
def test_untracked_code_file_is_reported(world, path):
    # 쓰는 쪽 코드(의존의 코드와 고정 코드)도 추적 파일이어야 한다. 디스크에만 있는 파일을 근거로 삼지 않는다.
    git(world.repo, "rm", "--cached", "--quiet", "--", path)
    problems = problems_of(world)
    assert len(problems) == 1
    assert path in problems[0]


# ---------------------------------------------------------------------------------------------
# 3. 로컬에만 있는 대상
# ---------------------------------------------------------------------------------------------


def test_local_targets_are_checked_only_with_local(world):
    assert problems_of(world, local=False) == []
    problems = problems_of(world, local=True)
    assert len(problems) == 1
    assert "b/.venv" in problems[0]
    (world.repo / "b" / ".venv").mkdir()
    assert problems_of(world, local=True) == []


# ---------------------------------------------------------------------------------------------
# 4. 설명 문서
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["a/code.py", "b/data.json", "a/pin.py", "early"])
def test_doc_must_name_each_code_and_tracked_path(world, name):
    # 문서는 쓰는 쪽 코드 경로, 추적 대상 경로, 고정 코드 경로, 고정 커밋의 앞 7자를 모두 적어야 한다.
    needle = world.early[:7] if name == "early" else name
    doc = read(world.repo, "docs/architecture.md")
    assert needle in doc
    write(world.repo, "docs/architecture.md", doc.replace(needle, ""))
    problems = problems_of(world)
    assert len(problems) == 1
    assert needle in problems[0]


def test_missing_doc_is_reported_once(world):
    (world.repo / "docs" / "architecture.md").unlink()
    problems = problems_of(world)
    assert len(problems) == 1
    assert "docs/architecture.md" in problems[0]


# ---------------------------------------------------------------------------------------------
# 5. 고정 사본
# ---------------------------------------------------------------------------------------------


def test_pinned_blob_must_equal_the_tree_of_its_commit(world):
    other = "0" * 40  # blob 해시 꼴이지만 그 커밋 트리의 값이 아니다
    write(world.repo, "a/pin.py", read(world.repo, "a/pin.py").replace(world.blob, other))
    problems = problems_of(world)
    assert len(problems) == 1
    assert "blob" in problems[0]
    assert other in problems[0]
    assert world.blob in problems[0]


def test_unknown_pinned_commit_is_reported(world):
    missing = "1" * 40  # 해시 꼴이지만 이 저장소에 없는 커밋
    write(world.repo, "a/pin.py", read(world.repo, "a/pin.py").replace(world.early, missing))
    problems = problems_of(world)
    assert any("커밋을 풀 수 없음" in problem and missing in problem for problem in problems)
    # 커밋을 풀지 못하면 원본 blob은 견줄 수 없으므로 blob 문제를 더 내지 않는다.
    assert not any("blob" in problem for problem in problems)
    # 이력이 모자란 것이 아니라 값이 틀린 경우이므로 얕은 복제 안내는 붙지 않는다.
    assert not any("얕은" in problem for problem in problems)


def test_missing_commit_in_a_shallow_clone_gets_a_hint(world, tmp_path_factory):
    # CI의 기본 체크아웃처럼 마지막 커밋만 받은 복제본에는 이른 커밋이 없다. 값이 틀린 것이 아니라 이력이
    # 모자란 것이라는 단서를 문제에 붙여, 전체 이력을 받으면 된다는 것을 알려야 한다.
    clone = tmp_path_factory.mktemp("shallow") / "clone"
    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--depth",
            "1",
            "-c",
            "core.autocrlf=false",
            world.repo.as_uri(),
            str(clone),
        ],
        check=True,
        capture_output=True,
    )
    problems = check(load(clone / "tools" / "cross-deps.toml"), clone, local=False)
    assert any("커밋을 풀 수 없음" in problem and "얕은" in problem for problem in problems)


def test_pinned_commit_must_be_a_full_hash(world):
    # 브랜치나 태그 이름은 움직이므로 '고정'이 아니다. 정규식이 넓어도 40자 해시가 아니면 문제로 알린다.
    text = DECLARATION.replace(
        """commit_pattern = 'PINNED_COMMIT = "([0-9a-f]{40})"'""",
        """commit_pattern = 'PINNED_COMMIT = "([^"]+)"'""",
    )
    write(world.repo, "tools/cross-deps.toml", text)
    write(world.repo, "a/pin.py", read(world.repo, "a/pin.py").replace(world.early, "main"))
    problems = problems_of(world)
    assert any("main" in problem and "40자" in problem for problem in problems)


@pytest.mark.parametrize(
    ("case", "pattern"),
    [("missing", "source_pattern"), ("twice", "blob_pattern")],
)
def test_pinned_patterns_must_match_exactly_once(world, case, pattern):
    pin = read(world.repo, "a/pin.py")
    if case == "missing":
        pin = pin.replace('PINNED_SOURCE = "src/v.py"\n', "")
    else:
        pin += f'PINNED_BLOB = "{world.blob}"\n'
    write(world.repo, "a/pin.py", pin)
    problems = problems_of(world)
    assert len(problems) == 1
    assert pattern in problems[0]


# ---------------------------------------------------------------------------------------------
# 6. 선언 파일의 꼴
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        # 모르는 키(오타). 조용히 무시하면 검사가 느슨해진 줄 모른다.
        ('what = "a의 코드가 b의 데이터 파일을 읽는다"', 'what = "x"\nwaht = "오타"', "waht"),
        ('doc = "docs/architecture.md"', 'doc = "docs/architecture.md"\ndokc = "오타"', "dokc"),
        # 빈 글. 빈 text는 어떤 코드에도 들어 있어 검사가 아무것도 보지 않게 된다.
        ('text = "../b/data.json"', 'text = ""', "text"),
        ('tracked = ["b/data.json"]', 'tracked = ["b/data.json", ""]', "tracked"),
        # 깨진 정규식, 괄호 묶음이 없는 정규식.
        ("""commit_pattern = 'PINNED_COMMIT = "([0-9a-f]{40})"'""", "commit_pattern = '('", "commit_pattern"),
        (
            """blob_pattern = 'PINNED_BLOB = "([0-9a-f]{40})"'""",
            "blob_pattern = 'PINNED_BLOB'",
            "blob_pattern",
        ),
        # 쓰는 쪽 코드가 하나도 없는 의존, 표가 아닌 값.
        ('  [[dep.code]]\n  path = "a/code.py"\n  text = "../b/data.json"\n', "", "code"),
        ('tracked = ["b/data.json"]', 'tracked = "b/data.json"', "tracked"),
    ],
)
def test_malformed_declarations_are_reported(world, old, new, expected):
    text = DECLARATION.replace(old, new)
    assert text != DECLARATION  # 시험이 바꾸려는 줄이 실제로 있는지
    write(world.repo, "tools/cross-deps.toml", text)
    problems = problems_of(world)
    assert any(expected in problem for problem in problems)


# ---------------------------------------------------------------------------------------------
# 7. 명령줄
# ---------------------------------------------------------------------------------------------


def test_main_exit_codes(world, capsys):
    base = ["--repo", str(world.repo)]

    # 선언 파일을 주지 않으면 <저장소>/tools/cross-deps.toml을 읽는다. 선언은 의존 하나와 고정 사본 하나다.
    assert main(base) == 0
    assert capsys.readouterr().out.splitlines() == ["선언 2개, 문제 0개"]

    write(world.repo, "a/code.py", 'DATA = "../b/other.json"\n')
    assert main(base) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert "a/code.py" in lines[0]
    assert lines[1] == "선언 2개, 문제 1개"

    assert main([*base, "--deps", str(world.repo / "없는선언.toml")]) == 2
    captured = capsys.readouterr()
    assert "없는선언.toml" in captured.err
    assert captured.out == ""


def test_main_local_flag_checks_local_targets(world, capsys):
    base = ["--repo", str(world.repo)]
    assert main(base) == 0
    capsys.readouterr()  # 앞 호출의 출력을 비운다

    assert main([*base, "--local"]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert "b/.venv" in lines[0]

    (world.repo / "b" / ".venv").mkdir()
    assert main([*base, "--local"]) == 0


def test_main_refuses_to_start_when_the_declaration_or_repository_cannot_be_read(
    world, tmp_path_factory, capsys
):
    # TOML 문법 오류는 문제가 아니라 시작할 수 없음이다(어느 선언도 믿을 수 없다).
    broken = write(world.repo, "tools/broken.toml", "doc = [\n")
    assert main(["--repo", str(world.repo), "--deps", str(broken)]) == 2
    assert "broken.toml" in capsys.readouterr().err

    # git 저장소가 아닌 폴더는 추적 여부를 물을 수 없으므로, 문제를 잔뜩 내지 않고 시작할 수 없다고 알린다.
    plain = tmp_path_factory.mktemp("not-a-repo")
    assert main(["--repo", str(plain), "--deps", str(world.deps)]) == 2
    captured = capsys.readouterr()
    assert "git" in captured.err
    assert captured.out == ""

    # 없는 폴더도 같다.
    assert main(["--repo", str(plain / "없는폴더"), "--deps", str(world.deps)]) == 2
    assert capsys.readouterr().out == ""


def test_script_prints_utf8_even_when_output_is_piped(world):
    # 한국어 Windows의 파이썬은 파이프로 나가는 출력을 cp949로 쓴다. 도구가 시작할 때 UTF-8로 다시
    # 여는지 본다.
    write(world.repo, "a/code.py", 'DATA = "../b/other.json"\n')
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    done = subprocess.run(
        [sys.executable, str(TOOLS / "check_cross_deps.py"), "--repo", str(world.repo)],
        capture_output=True,
        env=env,
    )
    assert done.returncode == 1, done.stderr.decode("utf-8", errors="replace")
    lines = done.stdout.decode("utf-8").splitlines()
    assert "a/code.py" in lines[0]
    assert lines[-1] == "선언 2개, 문제 1개"


# ---------------------------------------------------------------------------------------------
# 8. 이 저장소의 실제 선언
# ---------------------------------------------------------------------------------------------


def test_repository_dependencies_hold():
    # 이 저장소 자신의 선언이 지금도 맞는지 본다. 고정 사본의 원본 커밋을 이력에서 풀기 때문에 얕은
    # 체크아웃에서는 실패한다(건너뛰지 않는다): 저장소 검사 워크플로는 전체 이력을 받는다.
    assert check(load(REPO / "tools" / "cross-deps.toml"), REPO, local=False) == []
