"""`tools/check_lock_drift.py` 시험.

이 도구는 저장소가 추적하는 잠금 파일(uv.lock, package-lock.json)이 등록 파일(tools/locks.toml)에 적힌 갱신으로만
바뀌었는지 git 객체(blob과 이력)만 읽어 확인한다. 어긋나면 문제로 알리고(종료 코드 1), 읽지 못했는데 통과하는 길은
없어야 하므로 이력을 읽을 수 없는 경우는 문제가 아니라 '검사를 끝낼 수 없음'(종료 코드 2)으로 나눠 고정한다. 한 시험은
한 가지만 어긋나게 해서, 어느 검사가 어떤 문제를 냈는지 시험이 정확히 가리킬 수 있게 한다. 구역은 이 파일의 순서대로
아래와 같다.
    1. 통과와 등록하지 않은 변경: 맞게 등록하면 문제가 없고, 등록에 없는 변경과 잠금 파일은 알린다. 색인에만 있는 변경은 보지 않는다.
    2. 등록한 갱신의 내용: 날짜, 부모 수, changes의 세 꼴(화살표, `+`, `-`)이 실제 커밋과 같아야 한다.
    3. 이력과 등록의 어긋남: 순서, 모르는 커밋, 경로가 없는 커밋, 이력이 모자란 복제, 저장소 뿌리가 아닌 폴더.
    4. 잠금 읽기: lock_versions, 읽을 수 없는 잠금, package-lock.json, 작업 트리와 무관함, git 설정(log.follow)과 무관함.
    5. 등록 파일의 꼴: 읽을 수 없으면 멈추고, 항목의 꼴 오류는 그 항목의 문제로 알린다.
    6. 명령줄: 종료 코드와 출력 꼴, 파이프로 나가는 UTF-8 출력, 읽기만 한다는 것.
    7. 이 저장소의 실제 등록: 등록한 base가 합치기 전 저장소의 잠금과 같고, 이 저장소의 잠금 여덟이 등록과 맞는다.

시험용 저장소는 잠금 파일을 들인 커밋 → 판을 올린 커밋 → 무관한 커밋을 쌓아 만든다(build_world). git으로 저장소를 만드는
일이 시험 시간의 대부분이라, 같은 잠금 글로 만드는 저장소는 모듈 범위로 한 번만 만들어 두고(Prototypes) 시험마다 쓴다.
- make_world / world: 원본을 시험마다 복사해 준다. 저장소를 고치는 시험(커밋, 설정, 작업 트리)은 복사본에서 한다.
- share_world / shared_world: 원본을 그대로 나눠 쓴다. 저장소는 읽기만 하고, 등록 파일만 시험마다 임시 폴더에 써서
  --registry로 준다. 원본이 고쳐지면 모듈이 끝날 때 알아챈다.
커밋 시각은 환경 변수로 고정해 날짜 시험이 실행하는 날과 상관없고 복사본의 커밋 해시가 원본과 같다. 등록 파일은 시험마다
저장소의 실제 커밋 해시로 만든다. 이 저장소 자신의 등록(tools/locks.toml)과 잠금을 읽는 시험은 맨 끝 구역의 둘뿐이고, 그
둘은 저장소를 읽기만 한다.
"""

import copy
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

import check_lock_drift
import pytest
from check_lock_drift import check, load_registry, lock_versions, main
from conftest import REPO

# 이 파일은 <저장소>/tools/tests/에 있다. parents[1] = tools. 도구를 스크립트로 직접 돌리는 시험이 쓴다.
TOOLS = Path(__file__).resolve().parents[1]

# 시험 저장소의 첫 커밋(잠금을 들이는 커밋)의 시각.
FIRST_STAMP = "2026-03-01 09:00:00 +0000"

# 갱신 커밋의 (커밋 시각, 그 커밋에 기록된 시간대의 날짜). 첫 갱신은 일부러 UTC로는 3월 3일이 되는 -05:00 시간대로
# 만들었다. 도구가 UTC가 아니라 '커밋에 기록된 시간대의 날짜'를 읽는지 보려는 것이다.
UPDATE_STAMPS = [
    ("2026-03-02 23:30:00 -0500", "2026-03-02"),
    ("2026-03-05 09:00:00 +0900", "2026-03-05"),
    ("2026-03-08 09:00:00 +0000", "2026-03-08"),
]

# changes 한 건의 꼴이 틀렸을 때 문제 줄에 나오는 글(꼴 오류 시험이 공유한다).
CHANGES_SHAPE = (
    "changes - '<패키지> <옛 판> -> <새 판>', '+ <패키지> <판>', '- <패키지> <판>' 가운데 하나의 꼴이 아니다"
)


def write(root: Path, rel: str, text: str | bytes) -> Path:
    """root 아래 rel 경로에 text를 쓴다. 글이면 UTF-8(BOM 없음), 줄바꿈 LF이고 바이트면 그대로다. 폴더가 없으면 만든다."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8", newline="\n")
    return path


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    """repo 안에서 git을 부르고 표준 출력(앞뒤 공백 제외)을 돌려준다. 실패하면 CalledProcessError."""
    done = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=None if env is None else {**os.environ, **env},
    )
    return done.stdout.strip()


def init_repo(repo: Path) -> None:
    """빈 git 저장소를 만든다. conftest의 git_repo와 같은 설정이다.

    모듈 범위 고정물(Prototypes)은 함수 범위 고정물 git_repo를 쓸 수 없어 같은 설정을 여기에 둔다: 줄바꿈 변환을 끄고
    시험용 신원을 넣어 이 PC의 전역 git 설정과 상관없이 같은 결과가 나오게 하고, 서명을 끄고, 초기 브랜치를 main으로 한다.
    """
    git(repo, "init", "--quiet", "--initial-branch=main")
    for key, value in [
        ("core.autocrlf", "false"),
        ("user.name", "Test User"),
        ("user.email", "test@example.com"),
        ("commit.gpgsign", "false"),
    ]:
        git(repo, "config", key, value)


def commit(repo: Path, message: str, stamp: str, *paths: str) -> str:
    """paths를 스테이징해 stamp 시각으로 커밋하고, 그 커밋의 40자 해시를 돌려준다."""
    git(repo, "add", "--", *paths)
    git(
        repo,
        "commit",
        "--quiet",
        "-m",
        message,
        env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
    )
    return git(repo, "rev-parse", "HEAD")


def snapshot(repo: Path) -> dict[str, tuple[int, int]]:
    """repo 아래 모든 파일(.git 포함)의 (크기, 수정 시각). 시험 전후를 견줘 저장소가 고쳐졌는지 본다."""
    return {
        str(path.relative_to(repo)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(repo.rglob("*"))
        if path.is_file()
    }


def quoted(text: str) -> str:
    """TOML 기본 글로 감싼다(JSON 글 규칙은 TOML 기본 글과 같다)."""
    return json.dumps(text, ensure_ascii=False)


def uv_lock(*pairs: tuple[str, str], source: str = "https://pypi.org/simple") -> str:
    """uv.lock 꼴의 글. (이름, 판)마다 [[package]] 하나를 둔다. 도구가 읽는 것은 이름과 판뿐이다."""
    head = 'version = 1\nrevision = 5\nrequires-python = ">=3.11"\n'
    body = "".join(
        f'\n[[package]]\nname = "{name}"\nversion = "{version}"\nsource = {{ registry = "{source}" }}\n'
        for name, version in pairs
    )
    return head + body


def npm_lock(versions: dict[str, str]) -> str:
    """package-lock.json 꼴의 글. packages의 경로(키)마다 version 하나를 둔다. 뿌리는 빈 경로 ""다."""
    packages = {path: {"version": version} for path, version in versions.items()}
    return json.dumps({"name": "demo", "lockfileVersion": 3, "packages": packages}, indent=2) + "\n"


@dataclass
class Step:
    """등록할 갱신 하나: 갱신 커밋과, 그 커밋을 설명하는 등록 값."""

    commit: str
    date: str
    changes: list[str]
    why: str = "시험용 갱신"


def lock_toml(path: str, added: str, base: str, steps: list[Step], what: str = "시험용 잠금") -> str:
    """[[lock]] 하나(와 steps의 [[lock.update]]들)를 등록 파일 글로 만든다. steps는 옛것부터 적는다."""
    lines = [
        "[[lock]]",
        f"path = {quoted(path)}",
        f"added = {quoted(added)}",
        f"base = {quoted(base)}",
        f"what = {quoted(what)}",
    ]
    for step in steps:
        changes = ", ".join(quoted(change) for change in step.changes)
        lines += [
            "",
            "[[lock.update]]",
            f"commit = {quoted(step.commit)}",
            f"date = {quoted(step.date)}",
            f"changes = [{changes}]",
            f"why = {quoted(step.why)}",
        ]
    return "\n".join(lines) + "\n"


@dataclass
class World:
    """시험용 저장소 하나와, 그 저장소의 잠금 하나를 맞게 등록하는 데 필요한 값들."""

    repo: Path
    path: str  # 잠금 파일의 저장소 기준 경로
    added: str  # 잠금을 들인 커밋(40자)
    base: str  # 그 커밋에서의 blob(40자)
    steps: list[Step] = field(default_factory=list)
    # 등록 파일의 위치. 없으면 도구의 기본 위치(<저장소>/tools/locks.toml)다. 읽기 전용으로 나눠 쓰는 저장소는 시험마다 임시
    # 폴더의 파일을 쓴다.
    registry: Path | None = None
    before: list[str] = field(default_factory=list)  # 잠금을 들이기 전의 무관한 커밋들(옛것부터)

    def __post_init__(self) -> None:
        if self.registry is None:
            self.registry = self.repo / "tools" / "locks.toml"

    def toml(self, steps: list[Step] | None = None) -> str:
        """맞게 등록한 글. steps를 주면 갱신 목록만 그것으로 바꾼다."""
        return lock_toml(self.path, self.added, self.base, self.steps if steps is None else steps)

    def write_registry(self, text: str | bytes) -> None:
        write(self.registry.parent, self.registry.name, text)


def build_world(repo: Path, path: str, texts: list[str | bytes], *, before: int = 0) -> World:
    """texts[0]을 path에 들이는 커밋을 만들고, texts[1:]을 차례로 반영하는 갱신 커밋을 만든다.

    잠금을 들이기 전에 무관한 커밋을 before개 먼저 만들고, 갱신 커밋마다 뒤에 잠금과 무관한 커밋을 하나 더 둔다(그래서
    갱신의 부모가 늘 잠금 커밋은 아니고, HEAD도 갱신이 아니다). 갱신의 changes는 비워 둔다(시험이 맞게 정한다). 끝에 그 등록을
    작업 트리에 쓴다(커밋하지 않는다: 도구는 등록 파일을 작업 트리에서 읽는다).
    """
    earlier = []
    for index in range(before):
        write(repo, f"early-{index}.txt", f"early {index}\n")
        earlier.append(
            commit(repo, f"Add early file {index}", f"2026-02-{20 + index} 09:00:00 +0000", f"early-{index}.txt")
        )
    write(repo, path, texts[0])
    added = commit(repo, "Add the lock", FIRST_STAMP, path)
    base = git(repo, "rev-parse", f"{added}:{path}")
    world = World(repo=repo, path=path, added=added, base=base, before=earlier)
    for index, text in enumerate(texts[1:]):
        stamp, date = UPDATE_STAMPS[index]
        write(repo, path, text)
        update = commit(repo, f"Raise the lock {index + 1}", stamp, path)
        world.steps.append(Step(commit=update, date=date, changes=[]))
        write(repo, "notes.txt", f"note {index}\n")
        commit(repo, f"Add a note {index}", f"2026-03-{20 + index} 09:00:00 +0000", "notes.txt")
    world.write_registry(world.toml())
    return world


class Prototypes:
    """같은 잠금 글로 만든 시험 저장소를 한 번만 만들어 두는 곳(모듈 범위).

    저장소는 (경로, 잠금 글들, 앞선 커밋 수)로 정해지고 등록할 changes와는 상관이 없다(changes는 등록 파일에만 들어간다).
    그래서 같은 저장소를 여러 시험이 쓴다. 원본은 시험이 고치지 않는다: 고치는 시험은 복사본을 쓰고, 읽기만 하는 시험은
    원본을 나눠 쓴다. 만든 직후의 파일 목록(크기·수정 시각)을 적어 두었다가 모듈이 끝날 때 같은지 본다.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._worlds: dict[tuple, World] = {}
        self._snapshots: dict[tuple, dict[str, tuple[int, int]]] = {}

    def original(self, path: str, texts: list[str | bytes], *, before: int = 0) -> World:
        """(path, texts, before)로 만든 원본. 처음 부를 때만 만든다. 읽기 전용으로만 쓴다."""
        key = (path, tuple(texts), before)
        if key not in self._worlds:
            repo = self.root / f"original-{len(self._worlds)}"
            repo.mkdir()
            init_repo(repo)
            self._worlds[key] = build_world(repo, path, texts, before=before)
            self._snapshots[key] = snapshot(repo)
        return self._worlds[key]

    def assert_untouched(self) -> None:
        """모든 원본이 만든 직후와 같은지 본다. 다르면 어느 시험이 공유 원본을 고친 것이다."""
        for key, world in self._worlds.items():
            assert snapshot(world.repo) == self._snapshots[key], f"공유 원본이 시험 중에 고쳐졌다: {world.repo}"


@pytest.fixture(scope="module")
def prototypes(tmp_path_factory):
    store = Prototypes(tmp_path_factory.mktemp("prototypes"))
    yield store
    store.assert_untouched()


def apply_changes(world: World, changes: list[list[str]]) -> None:
    """world의 갱신마다 등록할 changes를 정한다(갱신 수와 같아야 한다)."""
    assert len(changes) == len(world.steps), "갱신 수와 changes 수가 다르다"
    for step, listed in zip(world.steps, changes, strict=True):
        step.changes = list(listed)


@pytest.fixture
def make_world(prototypes, tmp_path):
    """원본을 복사해 시험이 마음껏 고칠 수 있는 저장소를 주는 함수. 복사본의 등록 파일은 <복사본>/tools/locks.toml이다.

    .git/hooks는 복사하지 않는다(git이 없어도 되는 폴더이고 파일이 많아 복사가 느리다).
    """
    count = 0

    def make(path: str, texts: list[str | bytes], changes: list[list[str]], *, before: int = 0) -> World:
        nonlocal count
        original = prototypes.original(path, texts, before=before)
        destination = tmp_path / f"repo-{count}"
        count += 1
        shutil.copytree(original.repo, destination, ignore=shutil.ignore_patterns("hooks"))
        world = copy.deepcopy(original)
        world.repo = destination
        world.registry = destination / "tools" / "locks.toml"
        apply_changes(world, changes)
        world.write_registry(world.toml())
        return world

    return make


@pytest.fixture
def share_world(prototypes, tmp_path):
    """원본을 그대로 나눠 쓰는 저장소를 주는 함수. 저장소를 고치면 안 된다. 등록 파일은 시험의 임시 폴더에 쓴다."""
    count = 0

    def share(path: str, texts: list[str | bytes], changes: list[list[str]], *, before: int = 0) -> World:
        nonlocal count
        world = copy.deepcopy(prototypes.original(path, texts, before=before))
        world.registry = tmp_path / f"locks-{count}.toml"
        count += 1
        apply_changes(world, changes)
        world.write_registry(world.toml())
        return world

    return share


def standard_texts() -> list[str | bytes]:
    """기본 고정물의 잠금 글: 패키지 둘을 들이고, alpha의 판만 올린다."""
    return [
        uv_lock(("alpha", "1.0.0"), ("beta", "2.0.0")),
        uv_lock(("alpha", "1.1.0"), ("beta", "2.0.0")),
    ]


STANDARD = ("comp/uv.lock", standard_texts(), [["alpha 1.0.0 -> 1.1.0"]])


@pytest.fixture
def world(make_world) -> World:
    """comp/uv.lock을 들인 커밋 → alpha 1.0.0 -> 1.1.0 갱신 → 무관한 커밋. 갱신을 맞게 등록한 복사본."""
    return make_world(*STANDARD)


@pytest.fixture
def shared_world(share_world) -> World:
    """위와 같은 저장소를 읽기 전용으로 나눠 쓴다. 등록 파일만 임시 폴더에 있다."""
    return share_world(*STANDARD)


def args_for(world: World) -> list[str]:
    """도구에 줄 인자: 저장소와 등록 파일."""
    return ["--repo", str(world.repo), "--registry", str(world.registry)]


def run_check(world: World) -> list[str]:
    """world의 등록 파일을 읽어 검사한 문제 줄들."""
    return check(world.repo, load_registry(world.registry))


def run_check_with(world: World, steps: list[Step]) -> list[str]:
    """등록의 갱신 목록을 steps로 바꿔 쓴 뒤 검사한 문제 줄들."""
    world.write_registry(world.toml(steps=steps))
    return run_check(world)


def without_changes(world: World) -> list[Step]:
    """world의 갱신을 changes만 비워 돌려준다."""
    return [replace(step, changes=[]) for step in world.steps]


# ---------------------------------------------------------------------------------------------
# 1. 통과와 등록하지 않은 변경
# ---------------------------------------------------------------------------------------------


def test_registered_history_passes(world, capsys):
    assert run_check(world) == []
    # 등록 파일을 주지 않으면 <저장소>/tools/locks.toml을 읽는다.
    assert main(["--repo", str(world.repo)]) == 0
    assert capsys.readouterr().out.splitlines() == ["잠금 1개, 문제 0개"]
    # 서명 확인 출력을 켠 PC(log.showSignature)에서도 같다. 서명된 커밋은 이 시험이 만들지 않는다(서명 도구에 기대게 되므로).
    # 서명하지 않은 커밋은 그 설정에서도 출력이 달라지지 않아, 여기서 보는 것은 설정이 도구의 git 호출을 깨지 않는다는 것뿐이다.
    git(world.repo, "config", "log.showSignature", "true")
    assert run_check(world) == []


def test_unregistered_change_is_a_problem(shared_world, capsys):
    # 갱신 등록을 뺀다. 그 커밋은 잠금 경로의 이력에 있지만 등록에 없다.
    shared_world.write_registry(shared_world.toml(steps=[]))
    problems = run_check(shared_world)
    update = shared_world.steps[0].commit
    assert any(
        problem.startswith("comp/uv.lock: ") and "등록하지 않은 변경 커밋" in problem and update[:7] in problem
        for problem in problems
    )
    assert main(args_for(shared_world)) == 1
    assert capsys.readouterr().out.splitlines()[-1].startswith("잠금 1개, 문제 ")


def test_unregistered_change_after_the_last_registered_update_is_a_problem(share_world):
    # 갱신 둘 가운데 뒤의 것만 빠졌다. 등록한 마지막 상태와 HEAD의 잠금이 다르다는 것도 알려야 한다.
    texts: list[str | bytes] = [
        uv_lock(("alpha", "1.0.0"), ("beta", "2.0.0")),
        uv_lock(("alpha", "1.1.0"), ("beta", "2.0.0")),
        uv_lock(("alpha", "1.1.0"), ("beta", "2.1.0")),
    ]
    world = share_world("comp/uv.lock", texts, [["alpha 1.0.0 -> 1.1.0"], ["beta 2.0.0 -> 2.1.0"]])
    assert run_check(world) == []
    problems = run_check_with(world, world.steps[:1])
    missing = world.steps[1].commit[:7]
    assert any(missing in problem and "등록하지 않은 변경 커밋" in problem for problem in problems)
    assert any("HEAD의 잠금" in problem for problem in problems)


@pytest.mark.parametrize("changed_on", ["pull-request-side", "main-side"])
def test_merge_commit_checkout_of_a_pull_request_passes(git_repo, changed_on):
    # pull_request 이벤트의 CI 체크아웃은 PR 머리가 아니라 기준 브랜치와 PR 머리를 합친 병합 커밋이다. 그 병합 커밋의 잠금은
    # 바꾼 쪽 부모와 같으므로 이력은 바꾼 쪽만 따라가고, 병합 커밋 자신은 갱신으로 보이지 않아 등록한 이력과 그대로 맞아야
    # 한다. 잠금을 바꾼 쪽이 PR 쪽인 경우와 기준 브랜치 쪽인 경우를 모두 본다.
    path = "comp/uv.lock"
    write(git_repo, path, uv_lock(("alpha", "1.0.0"), ("beta", "2.0.0")))
    added = commit(git_repo, "Add the lock", FIRST_STAMP, path)
    base = git(git_repo, "rev-parse", f"{added}:{path}")
    raised = uv_lock(("alpha", "1.1.0"), ("beta", "2.0.0"))
    stamp = "2026-03-02 09:00:00 +0000"

    def raise_lock() -> str:
        write(git_repo, path, raised)
        return commit(git_repo, "Raise alpha", stamp, path)

    def other_work(name: str) -> None:
        write(git_repo, f"{name}.txt", f"{name}\n")
        commit(git_repo, f"Work on {name}", "2026-03-03 09:00:00 +0000", f"{name}.txt")

    git(git_repo, "switch", "--quiet", "-c", "pr")
    pr_update = raise_lock() if changed_on == "pull-request-side" else None
    if pr_update is None:
        other_work("pr")
    git(git_repo, "switch", "--quiet", "main")
    main_update = raise_lock() if changed_on == "main-side" else None
    if main_update is None:
        other_work("main")
    update = pr_update or main_update
    merge_stamp = "2026-03-04 09:00:00 +0000"
    merge_env = {"GIT_AUTHOR_DATE": merge_stamp, "GIT_COMMITTER_DATE": merge_stamp}
    git(git_repo, "merge", "--quiet", "--no-ff", "-m", "Merge the pull request", "pr", env=merge_env)
    assert len(git(git_repo, "show", "-s", "--format=%P", "HEAD").split()) == 2  # HEAD가 병합 커밋이어야 시험이 된다
    world = World(repo=git_repo, path=path, added=added, base=base)
    world.steps.append(Step(commit=update, date="2026-03-02", changes=["alpha 1.0.0 -> 1.1.0"]))
    world.write_registry(world.toml())
    assert run_check(world) == []
    # 갱신 등록을 빼면 그 커밋이 등록하지 않은 변경으로 잡힌다(병합 커밋을 갱신으로 세는 것이 아니다).
    problems = run_check_with(world, [])
    assert any(update[:7] in problem and "등록하지 않은 변경 커밋" in problem for problem in problems)


def test_wrong_base_is_a_problem(shared_world):
    wrong = "0" * 40  # blob 해시 꼴이지만 그 커밋의 값이 아니다
    shared_world.write_registry(shared_world.toml().replace(shared_world.base, wrong))
    problems = run_check(shared_world)
    assert len(problems) == 1
    assert problems[0].startswith("comp/uv.lock: base가 다르다")
    assert wrong in problems[0]
    assert shared_world.base in problems[0]


@pytest.mark.parametrize("lock_path", ["other/uv.lock", "other/package-lock.json"])
def test_unregistered_lock_file_is_a_problem(world, lock_path):
    content = uv_lock(("gamma", "3.0.0")) if lock_path.endswith("uv.lock") else npm_lock({"": "1"})
    write(world.repo, lock_path, content)
    commit(world.repo, "Add another lock", "2026-03-10 09:00:00 +0000", lock_path)
    problems = run_check(world)
    assert len(problems) == 1
    assert problems[0].startswith(f"{lock_path}: 등록하지 않은 잠금 파일")


def test_files_with_other_names_are_not_lock_files(world):
    # 이름이 uv.lock이나 package-lock.json과 정확히 같은 파일만 잠금이다. 닮은 이름은 등록을 요구하지 않는다.
    names = ["docs/uv.lock.md", "other/package-lock.json.bak", "notes/my-uv.lock", "x/Uv.lock"]
    for rel in names:
        write(world.repo, rel, "내용\n")
    commit(world.repo, "Add look-alikes", "2026-03-10 09:00:00 +0000", *names)
    assert run_check(world) == []


def test_staged_but_uncommitted_changes_to_locks_are_not_seen(world):
    # 도구는 색인이 아니라 HEAD의 트리를 읽는다. 스테이징만 하고 커밋하지 않은 새 잠금은 아직 이 저장소의 것이 아니고, 색인에서만
    # 뺀 등록된 잠금은 HEAD에 그대로 있다.
    write(world.repo, "other/uv.lock", uv_lock(("gamma", "3.0.0")))
    git(world.repo, "add", "--", "other/uv.lock")
    assert "other/uv.lock" in git(world.repo, "diff", "--cached", "--name-only")  # 스테이징만 됐다
    assert run_check(world) == []
    git(world.repo, "rm", "--cached", "--quiet", "--", world.path)
    assert world.path in git(world.repo, "diff", "--cached", "--name-only")  # 색인에서 빠졌다(HEAD에는 있다)
    assert run_check(world) == []


@pytest.mark.parametrize("how", ["never-existed", "deleted-later"])
def test_registered_path_that_is_not_tracked_is_a_problem(world, how):
    if how == "never-existed":
        ghost = "ghost/uv.lock"
        world.write_registry(world.toml() + "\n" + lock_toml(ghost, world.added, world.base, []))
    else:
        ghost = world.path
        git(world.repo, "rm", "--quiet", "--", world.path)
        git(world.repo, "commit", "--quiet", "-m", "Drop the lock")
    problems = run_check(world)
    assert len(problems) == 1
    assert problems[0].startswith(f"{ghost}: ")
    assert "HEAD에서 추적되지 않는" in problems[0]


def test_registering_the_same_path_twice_is_a_problem(shared_world):
    shared_world.write_registry(shared_world.toml() + "\n" + shared_world.toml())
    problems = run_check(shared_world)
    assert len(problems) == 1
    assert "path - 1번째 항목이 이미 등록한 경로다" in problems[0]


def test_two_locks_may_share_the_commit_that_added_them(git_repo, capsys):
    # 구성 요소를 옮겨 들인 커밋 하나가 잠금 둘을 함께 들일 수 있다(같은 added를 두 항목이 쓴다).
    write(git_repo, "comp/uv.lock", uv_lock(("alpha", "1.0.0")))
    write(git_repo, "comp/web/package-lock.json", npm_lock({"": "1"}))
    both = commit(git_repo, "Add both locks", FIRST_STAMP, "comp/uv.lock", "comp/web/package-lock.json")
    first = lock_toml("comp/uv.lock", both, git(git_repo, "rev-parse", f"{both}:comp/uv.lock"), [])
    second_blob = git(git_repo, "rev-parse", f"{both}:comp/web/package-lock.json")
    second = lock_toml("comp/web/package-lock.json", both, second_blob, [])
    write(git_repo, "tools/locks.toml", first + "\n" + second)
    assert main(["--repo", str(git_repo)]) == 0
    assert capsys.readouterr().out.splitlines() == ["잠금 2개, 문제 0개"]


def test_path_with_glob_characters_is_read_literally(git_repo):
    # 폴더 이름 a[1]은 glob으로 읽으면 a1과도 맞는다. 이력은 글자 그대로의 경로로 읽어야 두 잠금의 이력이 섞이지 않는다.
    write(git_repo, "a1/uv.lock", uv_lock(("alpha", "1.0.0")))
    first = commit(git_repo, "Add a1", FIRST_STAMP, "a1/uv.lock")
    write(git_repo, "a[1]/uv.lock", uv_lock(("beta", "2.0.0")))
    second = commit(git_repo, "Add a[1]", "2026-03-02 09:00:00 +0000", ":(literal)a[1]/uv.lock")
    entries = [
        lock_toml(path, added, git(git_repo, "rev-parse", f"{added}:{path}"), [])
        for path, added in [("a1/uv.lock", first), ("a[1]/uv.lock", second)]
    ]
    write(git_repo, "tools/locks.toml", "\n".join(entries))
    assert check(git_repo, load_registry(git_repo / "tools" / "locks.toml")) == []


def test_problems_are_sorted_by_path(world, capsys):
    for rel in ["zz/uv.lock", "aa/uv.lock"]:
        write(world.repo, rel, uv_lock(("gamma", "3.0.0")))
    commit(world.repo, "Add two locks", "2026-03-10 09:00:00 +0000", "zz/uv.lock", "aa/uv.lock")
    world.write_registry(world.toml().replace(world.base, "0" * 40))
    problems = run_check(world)
    assert [problem.split(":", 1)[0] for problem in problems] == ["aa/uv.lock", "comp/uv.lock", "zz/uv.lock"]
    assert main(args_for(world)) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[:-1] == problems
    assert lines[-1] == "잠금 1개, 문제 3개"


def test_header_only_registry_matches_a_repository_without_locks(git_repo, capsys):
    # 머리 주석만 있는 등록 파일은 빈 등록이다. 추적되는 잠금이 없는 저장소에서는 통과한다.
    write(git_repo, "README.md", "읽을거리\n")
    commit(git_repo, "Add a readme", FIRST_STAMP, "README.md")
    write(git_repo, "tools/locks.toml", "# 주석만 있는 등록 파일\n")
    assert main(["--repo", str(git_repo)]) == 0
    assert capsys.readouterr().out.splitlines() == ["잠금 0개, 문제 0개"]
    # 같은 빈 등록으로 잠금이 있는 저장소를 보면 그 잠금은 등록하지 않은 것이다.
    write(git_repo, "comp/uv.lock", uv_lock(("alpha", "1.0.0")))
    commit(git_repo, "Add a lock", "2026-03-02 09:00:00 +0000", "comp/uv.lock")
    assert main(["--repo", str(git_repo)]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("comp/uv.lock: 등록하지 않은 잠금 파일")
    assert lines[-1] == "잠금 0개, 문제 1개"


# ---------------------------------------------------------------------------------------------
# 2. 등록한 갱신의 내용
# ---------------------------------------------------------------------------------------------


BOTH_BUMPED: list[str | bytes] = [
    uv_lock(("alpha", "1.0.0"), ("beta", "2.0.0")),
    uv_lock(("alpha", "1.1.0"), ("beta", "2.1.0")),
]


def test_extra_version_change_under_a_registered_commit_is_a_problem(share_world):
    # 그 커밋은 패키지 둘의 판을 바꿨는데 등록은 하나만 적었다.
    world = share_world("comp/uv.lock", BOTH_BUMPED, [["alpha 1.0.0 -> 1.1.0"]])
    problems = run_check(world)
    assert len(problems) == 1
    assert world.steps[0].commit[:7] in problems[0]
    assert "등록에 없는 실제 차이 beta 2.0.0 -> 2.1.0" in problems[0]


def test_registered_change_that_did_not_happen_is_a_problem(shared_world):
    shared_world.steps[0].changes = ["alpha 1.0.0 -> 1.1.0", "beta 2.0.0 -> 2.1.0"]
    shared_world.write_registry(shared_world.toml())
    problems = run_check(shared_world)
    assert len(problems) == 1
    assert "등록에만 있는 차이 beta 2.0.0 -> 2.1.0" in problems[0]


def test_registered_changes_may_be_listed_in_any_order(share_world):
    changes = [["beta 2.0.0 -> 2.1.0", "alpha 1.0.0 -> 1.1.0"]]
    assert run_check(share_world("comp/uv.lock", BOTH_BUMPED, changes)) == []


def test_same_change_listed_twice_does_not_pass_as_one(shared_world):
    shared_world.steps[0].changes = ["alpha 1.0.0 -> 1.1.0", "alpha 1.0.0 -> 1.1.0"]
    shared_world.write_registry(shared_world.toml())
    problems = run_check(shared_world)
    assert len(problems) == 1
    assert "등록에만 있는 차이 alpha 1.0.0 -> 1.1.0" in problems[0]


def test_wrong_version_in_a_registered_change_is_a_problem(shared_world):
    # 옛 판은 맞고 새 판만 틀렸다. 없어진 쪽은 같고 생긴 쪽만 달라서, 문제 줄은 생긴 판 둘을 `+` 꼴로 보인다.
    shared_world.steps[0].changes = ["alpha 1.0.0 -> 1.1.1"]
    shared_world.write_registry(shared_world.toml())
    problems = run_check(shared_world)
    assert len(problems) == 1
    assert "등록에 없는 실제 차이 + alpha 1.1.0" in problems[0]  # 실제로 생긴 판
    assert "등록에만 있는 차이 + alpha 1.1.1" in problems[0]  # 등록에만 있는 판


def test_new_package_is_registered_with_a_plus_line(share_world):
    texts: list[str | bytes] = [
        uv_lock(("alpha", "1.0.0"), ("beta", "2.0.0")),
        uv_lock(("alpha", "1.0.0"), ("beta", "2.0.0"), ("gamma", "3.0.0")),
    ]
    world = share_world("comp/uv.lock", texts, [["+ gamma 3.0.0"]])
    assert run_check(world) == []
    # 빼면 문제이고, 문제 줄의 글은 그대로 changes에 옮겨 적을 수 있는 꼴이다.
    problems = run_check_with(world, without_changes(world))
    assert len(problems) == 1
    assert "등록에 없는 실제 차이 + gamma 3.0.0" in problems[0]


def test_removed_package_is_registered_with_a_minus_line(share_world):
    texts: list[str | bytes] = [uv_lock(("alpha", "1.0.0"), ("beta", "2.0.0")), uv_lock(("alpha", "1.0.0"))]
    world = share_world("comp/uv.lock", texts, [["- beta 2.0.0"]])
    assert run_check(world) == []
    problems = run_check_with(world, without_changes(world))
    assert len(problems) == 1
    assert "등록에 없는 실제 차이 - beta 2.0.0" in problems[0]


def test_plus_line_that_did_not_happen_is_a_problem(shared_world):
    shared_world.steps[0].changes = ["alpha 1.0.0 -> 1.1.0", "+ gamma 3.0.0"]
    shared_world.write_registry(shared_world.toml())
    problems = run_check(shared_world)
    assert len(problems) == 1
    assert "등록에만 있는 차이 + gamma 3.0.0" in problems[0]


def test_minus_and_plus_lines_mean_the_same_as_one_arrow(shared_world):
    shared_world.steps[0].changes = ["- alpha 1.0.0", "+ alpha 1.1.0"]
    shared_world.write_registry(shared_world.toml())
    assert run_check(shared_world) == []


def test_two_versions_of_one_name_changed_together_are_written_as_two_arrows(share_world):
    # uv.lock에는 같은 이름이 판 둘로 나올 수 있다(환경마다 다른 판). 둘이 함께 바뀐 갱신은 화살표 두 건으로 적는다. 견주는 것은
    # 없어진 쌍과 생긴 쌍 각각의 모음이라 어느 짝으로 적어도 같은 뜻이다.
    texts: list[str | bytes] = [
        uv_lock(("numpy", "1.26.4"), ("numpy", "2.2.0"), ("beta", "2.0.0")),
        uv_lock(("numpy", "1.26.5"), ("numpy", "2.2.1"), ("beta", "2.0.0")),
    ]
    for listed in (
        ["numpy 1.26.4 -> 1.26.5", "numpy 2.2.0 -> 2.2.1"],
        ["numpy 1.26.4 -> 2.2.1", "numpy 2.2.0 -> 1.26.5"],
    ):
        assert run_check(share_world("comp/uv.lock", texts, [listed])) == []
    # 등록하지 않으면, 한 이름에 쌍이 여럿이라 짝을 정할 수 없는 차이는 `-`와 `+`로 보인다.
    world = share_world("comp/uv.lock", texts, [[]])
    problems = run_check(world)
    assert len(problems) == 1
    for line in ["- numpy 1.26.4", "- numpy 2.2.0", "+ numpy 1.26.5", "+ numpy 2.2.1"]:
        assert line in problems[0]


def test_bumping_only_one_of_two_versions_of_a_name_is_one_arrow(share_world):
    # 실제 voice-translator 잠금처럼 같은 이름이 판 둘로 나오는 잠금에서 한쪽 판만 올린 갱신은 화살표 한 건이다.
    texts: list[str | bytes] = [
        uv_lock(("numpy", "1.26.4"), ("numpy", "2.2.0"), ("beta", "2.0.0")),
        uv_lock(("numpy", "1.26.4"), ("numpy", "2.2.1"), ("beta", "2.0.0")),
    ]
    world = share_world("comp/uv.lock", texts, [["numpy 2.2.0 -> 2.2.1"]])
    assert run_check(world) == []
    problems = run_check_with(world, without_changes(world))
    assert len(problems) == 1
    assert "등록에 없는 실제 차이 numpy 2.2.0 -> 2.2.1" in problems[0]


def test_difference_with_a_versionless_entry_cannot_be_registered(share_world):
    # version이 없는 [[package]](빈 판)는 changes의 어느 꼴로도 적을 수 없다. 그 이름을 견주지 않고 까닭을 밝혀 문제로 둔다.
    # 적을 수 없는 건을 적으라는 안내(`+ root 0.1.0` 같은)가 나오면 안 된다.
    before = 'version = 1\n\n[[package]]\nname = "root"\nsource = { virtual = "." }\n'
    after = 'version = 1\n\n[[package]]\nname = "root"\nversion = "0.1.0"\nsource = { virtual = "." }\n'
    world = share_world("comp/uv.lock", [before, after], [[]])
    problems = run_check(world)
    assert len(problems) == 1
    assert "판이 없는 항목이 낀 이름은 changes에 적을 수 없다 root" in problems[0]
    assert "+ root" not in problems[0] and "- root" not in problems[0]


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (
            [("alpha", "1.0.0"), ("beta", "2.0.0")],
            [("alpha", "1.0.0"), ("beta", "2.0.0"), ("gamma", "3.0.0")],
            ["+ gamma 3.0.0"],
        ),
        ([("alpha", "1.0.0"), ("beta", "2.0.0")], [("alpha", "1.0.0")], ["- beta 2.0.0"]),
        (
            [("alpha", "1.0.0"), ("alpha", "1.5.0")],
            [("alpha", "1.1.0"), ("alpha", "1.6.0")],
            ["- alpha 1.0.0", "- alpha 1.5.0", "+ alpha 1.1.0", "+ alpha 1.6.0"],
        ),
    ],
    ids=["new-package", "removed-package", "several-versions-of-one-name"],
)
def test_unregistered_difference_is_shown_in_the_form_it_can_be_registered_in(share_world, before, after, expected):
    # 등록하지 않은 차이는 문제이고, 문제 줄에는 그대로 changes에 옮겨 적을 수 있는 글이 보인다(새로 들어옴·빠짐은 `+`·`-`).
    world = share_world("comp/uv.lock", [uv_lock(*before), uv_lock(*after)], [[]])
    problems = run_check(world)
    assert len(problems) == 1
    assert "등록에 없는 실제 차이" in problems[0]
    for line in expected:
        assert line in problems[0]


def test_update_without_a_version_change_is_registered_with_empty_changes(share_world):
    # 판 말고 주소만 바뀐 갱신. 판 변경이 없으므로 changes는 빈 목록이다. 등록하지 않으면 이력 검사가 잡는다.
    texts: list[str | bytes] = [
        uv_lock(("alpha", "1.0.0"), source="https://pypi.org/simple"),
        uv_lock(("alpha", "1.0.0"), source="https://mirror.example/simple"),
    ]
    world = share_world("comp/uv.lock", texts, [[]])
    assert run_check(world) == []
    problems = run_check_with(world, [])
    assert any(world.steps[0].commit[:7] in problem for problem in problems)


def test_update_date_must_match_the_commit(shared_world):
    # 그 커밋의 시각은 -05:00 시간대의 3월 2일 23:30이다. UTC로는 3월 3일이지만 도구는 기록된 시간대의 날짜를 본다.
    assert shared_world.steps[0].date == "2026-03-02"
    assert run_check(shared_world) == []
    shared_world.write_registry(shared_world.toml().replace('date = "2026-03-02"', 'date = "2026-03-03"'))
    problems = run_check(shared_world)
    assert len(problems) == 1
    assert shared_world.steps[0].commit[:7] in problems[0]
    assert "date가 커밋 날짜와 다르다" in problems[0]
    assert "2026-03-03" in problems[0] and "2026-03-02" in problems[0]


def test_update_commit_that_is_a_merge_is_a_problem(git_repo):
    # 병합 커밋이 잠금을 바꾸면(두 부모 어느 쪽과도 다른 잠금) 이력에는 갱신으로 보이지만, 부모가 둘이라 판 차이를 어느
    # 부모와 견줄지 정할 수 없다. 병합 커밋으로 잠금을 바꾸지 않는다.
    write(git_repo, "comp/uv.lock", uv_lock(("alpha", "1.0.0"), ("beta", "2.0.0")))
    added = commit(git_repo, "Add the lock", FIRST_STAMP, "comp/uv.lock")
    base = git(git_repo, "rev-parse", f"{added}:comp/uv.lock")
    git(git_repo, "switch", "--quiet", "-c", "side")
    write(git_repo, "side.txt", "side\n")
    commit(git_repo, "Side work", "2026-03-02 09:00:00 +0000", "side.txt")
    git(git_repo, "switch", "--quiet", "main")
    write(git_repo, "main.txt", "main\n")
    commit(git_repo, "Main work", "2026-03-03 09:00:00 +0000", "main.txt")
    git(git_repo, "merge", "--quiet", "--no-ff", "--no-commit", "side")
    write(git_repo, "comp/uv.lock", uv_lock(("alpha", "1.1.0"), ("beta", "2.0.0")))
    stamp = "2026-03-04 09:00:00 +0000"
    merge = commit(git_repo, "Merge and raise alpha", stamp, "comp/uv.lock")
    assert len(git(git_repo, "show", "-s", "--format=%P", merge).split()) == 2
    world = World(repo=git_repo, path="comp/uv.lock", added=added, base=base)
    world.steps.append(Step(commit=merge, date="2026-03-04", changes=["alpha 1.0.0 -> 1.1.0"]))
    world.write_registry(world.toml())
    problems = run_check(world)
    assert len(problems) == 1
    assert merge[:7] in problems[0]
    assert "병합 커밋" in problems[0]


def test_update_commit_without_a_parent_is_a_problem(shared_world):
    # 뿌리 커밋(부모 없음)을 갱신으로 등록하면, 무엇과 견줄지 정할 수 없다.
    root = Step(commit=shared_world.added, date="2026-03-01", changes=[])
    problems = run_check_with(shared_world, [root])
    assert any(shared_world.added[:7] in problem and "뿌리 커밋" in problem for problem in problems)


# ---------------------------------------------------------------------------------------------
# 3. 이력과 등록의 어긋남
# ---------------------------------------------------------------------------------------------


def test_updates_must_be_registered_oldest_first(share_world):
    texts: list[str | bytes] = [
        uv_lock(("alpha", "1.0.0"), ("beta", "2.0.0")),
        uv_lock(("alpha", "1.1.0"), ("beta", "2.0.0")),
        uv_lock(("alpha", "1.1.0"), ("beta", "2.1.0")),
    ]
    world = share_world("comp/uv.lock", texts, [["alpha 1.0.0 -> 1.1.0"], ["beta 2.0.0 -> 2.1.0"]])
    assert run_check(world) == []
    problems = run_check_with(world, list(reversed(world.steps)))
    assert any("순서" in problem for problem in problems)


def test_registered_commit_that_did_not_change_the_path_is_a_problem(shared_world):
    # 잠금을 바꾸지 않은 커밋(시험 저장소의 무관한 마지막 커밋)을 갱신으로 등록했다.
    note = git(shared_world.repo, "rev-parse", "HEAD")
    assert note not in (shared_world.added, shared_world.steps[0].commit)
    date = git(shared_world.repo, "show", "-s", "--format=%cs", note)
    problems = run_check_with(shared_world, [*shared_world.steps, Step(commit=note, date=date, changes=[])])
    assert any("등록했지만 이 경로를 바꾸지 않은 커밋" in problem and note[:7] in problem for problem in problems)


@pytest.mark.parametrize("which", ["added", "commit"])
def test_unknown_commit_in_the_registry_is_a_problem(shared_world, capsys, which):
    # 이 저장소에 없는 40자 해시(형식은 맞지만 어느 커밋도 아님). 멈추지 않고 그 항목의 문제로 알린다.
    unknown = "a" * 40
    real = shared_world.added if which == "added" else shared_world.steps[0].commit
    shared_world.write_registry(shared_world.toml().replace(real, unknown))
    assert main(args_for(shared_world)) == 1
    out = capsys.readouterr().out
    assert any(
        line.startswith("comp/uv.lock: ") and unknown[:7] in line and "커밋으로 풀 수 없다" in line
        for line in out.splitlines()
    ), out


@pytest.mark.parametrize("case", ["added", "update", "update-parent"])
def test_registered_commit_without_the_path_is_a_problem(share_world, case):
    # 등록한 커밋은 이 저장소에 있지만 그 커밋(또는 갱신의 부모)에 잠금 경로가 없다. git은 '없다'고 답하므로 멈추지 않고 그
    # 항목의 문제로 알린다(예상하지 못한 git 실패와 다르다).
    world = share_world(*STANDARD, before=2)
    first, second = (
        world.before
    )  # 잠금을 들이기 전의 커밋 둘(옛것부터). 둘째의 부모가 첫째이고, 잠금을 들인 커밋의 부모가 둘째다.
    path = world.path
    if case == "added":
        world.added = first
        world.write_registry(world.toml())
        expected = f"added {first[:7]}: 그 커밋에 {path} 파일이 없다"
    elif case == "update":
        step = Step(commit=second, date=git(world.repo, "show", "-s", "--format=%cs", second), changes=[])
        world.write_registry(world.toml(steps=[step]))
        expected = f"갱신 {second[:7]}: 그 커밋에 {path} 파일이 없다"
    else:
        added_date = git(world.repo, "show", "-s", "--format=%cs", world.added)
        step = Step(commit=world.added, date=added_date, changes=[])
        world.write_registry(world.toml(steps=[step]))
        expected = f"갱신 {world.added[:7]}: 부모 {second[:7]}에 {path} 파일이 없다"
    assert f"{path}: {expected}" in run_check(world)


def test_shallow_clone_is_reported_as_missing_history(shared_world, tmp_path_factory, capsys):
    # CI의 기본 체크아웃처럼 마지막 커밋만 받은 복제본에서는 잠금의 이력이 잘려 '등록이 틀림'으로 보일 수 있다. 그것은
    # 틀린 등록이 아니라 모자란 이력이므로, 문제가 아니라 검사를 끝낼 수 없음(종료 코드 2)과 안내로 알린다.
    # 로컬 경로를 그대로 주면 깊이가 무시되므로 file 주소로 복제한다.
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
            shared_world.repo.as_uri(),
            str(clone),
        ],
        check=True,
        capture_output=True,
    )
    assert git(clone, "rev-parse", "--is-shallow-repository") == "true"  # 얕지 않으면 이 시험은 아무것도 보지 못한다
    assert main(["--repo", str(clone), "--registry", str(shared_world.registry)]) == 2
    captured = capsys.readouterr()
    assert "git fetch --unshallow" in captured.err
    assert captured.out == ""
    # 같은 등록은 전체 이력이 있는 원본에서는 통과한다. 위의 2는 등록이 아니라 이력이 모자라서다.
    assert main(args_for(shared_world)) == 0


def test_repository_without_commits_cannot_be_checked(git_repo, capsys):
    write(git_repo, "tools/locks.toml", "# 비어 있다\n")
    assert main(["--repo", str(git_repo)]) == 2
    captured = capsys.readouterr()
    assert "HEAD" in captured.err
    assert captured.out == ""


def test_repo_must_be_the_repository_root(shared_world, tmp_path, capsys):
    # --repo에 안쪽 폴더를 주면 git은 그 폴더를 작업 트리 안이라고 답하지만 경로를 그 폴더 기준으로 읽는다. 그러면 트리 목록이
    # 달라져, 등록이 비어 있을 때 잠금이 있는데도 조용히 통과한다. 뿌리가 아니면 검사를 시작하지 않는다.
    empty = write(tmp_path, "empty.toml", "# 비어 있다\n")
    assert (
        main(["--repo", str(shared_world.repo), "--registry", str(empty)]) == 1
    )  # 뿌리에서는 등록하지 않은 잠금이 보인다
    capsys.readouterr()
    inner = shared_world.repo / "comp"
    for registry in (empty, shared_world.registry):
        assert main(["--repo", str(inner), "--registry", str(registry)]) == 2
        captured = capsys.readouterr()
        assert "저장소 뿌리" in captured.err
        assert captured.out == ""


# ---------------------------------------------------------------------------------------------
# 4. 잠금 읽기
# ---------------------------------------------------------------------------------------------


def test_lock_versions_counts_name_and_version_pairs():
    pairs = [("alpha", "1.0.0"), ("alpha", "2.0.0"), ("beta", "1.0.0"), ("beta", "1.0.0")]
    data = uv_lock(*pairs).encode("utf-8")
    # 같은 이름이 서로 다른 판으로 여러 번 나올 수 있고, 같은 (이름, 판)도 출처가 다르면 여러 번 나올 수 있다.
    assert lock_versions(data, "uv.lock") == Counter(
        {("alpha", "1.0.0"): 1, ("alpha", "2.0.0"): 1, ("beta", "1.0.0"): 2}
    )
    # 이름은 파일 이름이거나 경로여도 된다(마지막 낱말을 본다).
    assert lock_versions(data, "comp/uv.lock") == lock_versions(data, "uv.lock")


def test_lock_versions_counts_a_package_without_version_as_empty():
    data = b'version = 1\n\n[[package]]\nname = "root"\nsource = { virtual = "." }\n'
    assert lock_versions(data, "uv.lock") == Counter({("root", ""): 1})


def test_lock_versions_of_package_lock_uses_paths_and_skips_entries_without_version():
    data = json.dumps(
        {
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "demo", "version": "0.1.0"},
                "node_modules/a": {"version": "1.0.0"},
                "node_modules/linked": {"resolved": "../x", "link": True},
            },
        }
    ).encode("utf-8")
    # 뿌리(빈 경로)는 등록에 적을 수 있도록 .으로 센다. 판이 없는 항목(링크)은 세지 않는다.
    assert lock_versions(data, "package-lock.json") == Counter({(".", "0.1.0"): 1, ("node_modules/a", "1.0.0"): 1})


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"\xff\xfe\x00 not utf-8", "uv.lock"),
        (b"not = [valid", "uv.lock"),
        (b"version = 1\n", "uv.lock"),
        (b'version = 1\n\n[[package]]\nversion = "1.0.0"\n', "uv.lock"),
        (b'version = 1\n\n[[package]]\nname = "a"\nversion = 3\n', "uv.lock"),
        (b"{", "package-lock.json"),
        (b"[]", "package-lock.json"),
        (b'{"lockfileVersion": 1, "dependencies": {}}', "package-lock.json"),
        (b'{"packages": {"": {"version": 1}}}', "package-lock.json"),
        (b"x", "poetry.lock"),
    ],
    ids=[
        "not-utf8",
        "toml-syntax",
        "no-package",
        "package-without-name",
        "version-not-text",
        "json-syntax",
        "json-not-object",
        "no-packages-object",
        "json-version-not-text",
        "unknown-file-name",
    ],
)
def test_lock_versions_refuses_what_it_cannot_read(data, name):
    # 읽지 못한 잠금을 '판 변경 없음'으로 읽으면 변경이 조용히 사라진다. 모두 ValueError로 멈춘다.
    with pytest.raises(ValueError):
        lock_versions(data, name)


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        ("comp/uv.lock", "not = [valid"),
        ("comp/uv.lock", b"\xff\xfe\x00 not utf-8"),
        ("web/package-lock.json", "{"),
    ],
    ids=["toml-syntax", "not-utf8", "json-syntax"],
)
def test_unreadable_lock_is_a_problem_of_that_entry(share_world, capsys, path, bad):
    # 풀리지 않거나 문법이 깨진 잠금은 검사를 멈추지 않고 그 항목의 문제로 알린다(종료 코드 1).
    good = uv_lock(("alpha", "1.0.0")) if path.endswith("uv.lock") else npm_lock({"": "1"})
    world = share_world(path, [good, bad], [[]])
    problems = run_check(world)
    assert len(problems) == 1
    assert "읽을 수 없다" in problems[0] and world.steps[0].commit[:7] in problems[0]
    assert main(args_for(world)) == 1
    capsys.readouterr()


def npm_world(share_world, changes: list[str], *, root_after: str = "0.1.0") -> World:
    """package-lock.json의 판 하나를 올리는 갱신(left-pad 1.3.0 -> 1.3.1)을 둔 저장소."""
    before = {"": "0.1.0", "node_modules/left-pad": "1.3.0", "node_modules/chalk": "5.0.0"}
    after = {"": root_after, "node_modules/left-pad": "1.3.1", "node_modules/chalk": "5.0.0"}
    texts: list[str | bytes] = [npm_lock(before), npm_lock(after)]
    return share_world("web/package-lock.json", texts, [changes])


def test_package_lock_json_is_read_too(share_world):
    world = npm_world(share_world, ["node_modules/left-pad 1.3.0 -> 1.3.1"])
    assert run_check(world) == []
    # 판 변경을 빠뜨리면 같은 규칙으로 문제다.
    problems = run_check_with(world, without_changes(world))
    assert len(problems) == 1
    assert "등록에 없는 실제 차이 node_modules/left-pad 1.3.0 -> 1.3.1" in problems[0]


def test_package_lock_json_root_version_change_is_written_with_a_dot(share_world):
    world = npm_world(share_world, [], root_after="0.2.0")
    problems = run_check(world)
    assert len(problems) == 1
    assert ". 0.1.0 -> 0.2.0" in problems[0]
    world.steps[0].changes = ["node_modules/left-pad 1.3.0 -> 1.3.1", ". 0.1.0 -> 0.2.0"]
    world.write_registry(world.toml())
    assert run_check(world) == []


def test_worktree_line_endings_do_not_matter(world):
    # Windows에서 줄바꿈 변환을 켠 채 받은 복제본의 작업 트리 잠금은 CRLF일 수 있다. 도구는 작업 트리가 아니라 HEAD의
    # blob을 읽으므로 결과가 같다.
    lock = world.repo / world.path
    lock.write_bytes(lock.read_bytes().replace(b"\n", b"\r\n"))
    assert b"\r\n" in lock.read_bytes()
    assert run_check(world) == []
    # 아직 커밋하지 않은 판 변경도 보지 않는다.
    write(world.repo, world.path, uv_lock(("alpha", "9.9.9")))
    assert run_check(world) == []


def test_log_follow_setting_does_not_change_the_history(git_repo):
    # git 설정 log.follow=true는 경로 하나를 준 git log가 이름을 따라가게 한다. 이 도구의 핵심 결정('이름 따라가기 없음')을 그
    # 설정이 뒤집으면, 폴더를 옮긴 잠금의 이력이 옮기기 전의 옛 경로(다른 구성 요소의 이력일 수 있다)까지 이어져 거짓으로
    # 실패한다. 설정이 켜져 있어도 결과가 같아야 한다.
    write(git_repo, "old/uv.lock", uv_lock(("alpha", "1.0.0"), ("beta", "2.0.0")))
    commit(git_repo, "Add the lock in the old folder", FIRST_STAMP, "old/uv.lock")
    (git_repo / "new").mkdir()
    git(git_repo, "mv", "old/uv.lock", "new/uv.lock")
    moved = commit(git_repo, "Move the lock", "2026-03-02 09:00:00 +0000", "new/uv.lock")
    base = git(git_repo, "rev-parse", f"{moved}:new/uv.lock")
    world = World(repo=git_repo, path="new/uv.lock", added=moved, base=base)  # 옮긴 커밋을 added로 맞게 등록한다
    world.write_registry(world.toml())
    assert run_check(world) == []
    git(git_repo, "config", "log.follow", "true")
    # 전제: 그 설정에서는 맨 git log가 옮기기 전의 커밋까지 따라간다(그래서 설정이 도구의 결과를 바꿀 수 있다).
    assert len(git(git_repo, "log", "--format=%H", "--", "new/uv.lock").split()) >= 2
    assert run_check(world) == []


# ---------------------------------------------------------------------------------------------
# 5. 등록 파일의 꼴
# ---------------------------------------------------------------------------------------------


def _replace(old: str, new: str = ""):
    """등록 글에서 old를 new로 바꾸는 편집. old가 글에 없으면 시험이 아무것도 바꾸지 못한 것이므로 실패시킨다."""

    def edit(world: World, text: str) -> str | bytes:
        assert old in text, old
        return text.replace(old, new)

    return edit


def _replace_value(old_of, new: str):
    """등록 글에서 world의 값(old_of(world))을 new로 바꾸는 편집."""

    def edit(world: World, text: str) -> str | bytes:
        old = old_of(world)
        assert old in text, old
        return text.replace(old, new)

    return edit


def _drop_updates_and_add_scalar(world: World, text: str) -> str | bytes:
    """갱신 표를 모두 떼고 [[lock]] 안에 update = 3(표의 배열이 아닌 값)을 둔다."""
    return text.split("\n[[lock.update]]")[0] + "update = 3\n"


# (편집, 기대하는 종료 코드, 기대하는 글). 종료 코드 2면 글은 표준 오류에, 1이면 문제 줄에 있어야 한다.
REGISTRY_CASES = [
    # 읽을 수 없는 등록 파일은 검사를 시작할 수 없다(종료 코드 2).
    pytest.param(lambda w, t: "lock = [", 2, "등록 파일을 읽을 수 없다", id="toml-syntax"),
    pytest.param(lambda w, t: b"\xff\xfe\x00 not utf-8", 2, "등록 파일을 읽을 수 없다", id="not-utf8"),
    pytest.param(lambda w, t: t + "\n[[lcok]]\nx = 1\n", 2, "lcok", id="unknown-top-level-table"),
    pytest.param(lambda w, t: "lock = 5\n", 2, "등록 파일을 읽을 수 없다", id="lock-is-not-a-table-array"),
    # 항목 안의 꼴 오류는 그 항목의 문제다(종료 코드 1). 오타 때문에 등록이 조용히 빠지거나 느슨해지면 안 된다.
    pytest.param(_replace('what = "시험용 잠금"\n'), 1, "what - 없다", id="missing-what"),
    pytest.param(_replace('what = "시험용 잠금"', 'what = "  "'), 1, "what - 비어 있다", id="blank-what"),
    pytest.param(_replace('what = "시험용 잠금"', "what = 3"), 1, "what - 글이어야 한다", id="what-is-not-text"),
    pytest.param(
        _replace('what = "시험용 잠금"', 'what = "시험용 잠금"\nwaht = "오타"'),
        1,
        "waht - 모르는 키",
        id="unknown-key",
    ),
    pytest.param(
        _replace('why = "시험용 갱신"', 'why = "시험용 갱신"\nwyh = "오타"'),
        1,
        "wyh - 모르는 키",
        id="unknown-update-key",
    ),
    pytest.param(_replace('why = "시험용 갱신"\n'), 1, "why - 없다", id="missing-why"),
    pytest.param(_replace('why = "시험용 갱신"', 'why = ""'), 1, "why - 비어 있다", id="blank-why"),
    pytest.param(_replace('path = "comp/uv.lock"\n'), 1, "path - 없다", id="missing-path"),
    pytest.param(
        _replace('path = "comp/uv.lock"', 'path = "comp/Cargo.lock"'),
        1,
        "path - 이름이 uv.lock이나 package-lock.json이어야 한다",
        id="path-is-not-a-lock-name",
    ),
    pytest.param(
        _replace_value(lambda w: f'added = "{w.added}"', 'added = "abc1234"'),
        1,
        "added - 40자 소문자 16진수",
        id="added-is-not-a-full-hash",
    ),
    pytest.param(
        _replace_value(lambda w: f'base = "{w.base}"', 'base = "' + "A" * 40 + '"'),
        1,
        "base - 40자 소문자 16진수",
        id="base-is-uppercase",
    ),
    pytest.param(
        _replace_value(lambda w: f'commit = "{w.steps[0].commit}"', 'commit = "main"'),
        1,
        "commit - 40자 소문자 16진수",
        id="commit-is-a-branch-name",
    ),
    pytest.param(
        _replace('date = "2026-03-02"', 'date = "2026/03/02"'),
        1,
        "date - YYYY-MM-DD 꼴이 아니다",
        id="date-with-slashes",
    ),
    pytest.param(
        _replace('date = "2026-03-02"', "date = 2026-03-02"),
        1,
        "date - 따옴표로 감싼 YYYY-MM-DD",
        id="date-without-quotes",
    ),
    pytest.param(_replace('changes = ["alpha 1.0.0 -> 1.1.0"]\n'), 1, "changes - 없다", id="missing-changes"),
    pytest.param(
        _replace('changes = ["alpha 1.0.0 -> 1.1.0"]', 'changes = "alpha 1.0.0 -> 1.1.0"'),
        1,
        "changes - 글의 목록이어야 한다",
        id="changes-is-not-a-list",
    ),
    pytest.param(
        _replace('"alpha 1.0.0 -> 1.1.0"', '"alpha 1.0.0 => 1.1.0"'), 1, CHANGES_SHAPE, id="changes-item-without-arrow"
    ),
    pytest.param(
        _replace('"alpha 1.0.0 -> 1.1.0"', '"alpha  1.0.0 -> 1.1.0"'),
        1,
        CHANGES_SHAPE,
        id="changes-item-with-two-spaces",
    ),
    pytest.param(
        _replace('"alpha 1.0.0 -> 1.1.0"', '"+ alpha"'), 1, CHANGES_SHAPE, id="changes-plus-without-a-version"
    ),
    pytest.param(
        _replace('"alpha 1.0.0 -> 1.1.0"', '"- alpha 1.0.0 extra"'),
        1,
        CHANGES_SHAPE,
        id="changes-minus-with-an-extra-word",
    ),
    pytest.param(
        _replace('"alpha 1.0.0 -> 1.1.0"', '""'), 1, "changes - 빈 글이 들어 있다", id="changes-item-is-empty"
    ),
    pytest.param(
        _drop_updates_and_add_scalar,
        1,
        "update - [[lock.update]] 표의 배열이어야 한다",
        id="update-is-not-a-table-array",
    ),
]


@pytest.mark.parametrize(("edit", "code", "needle"), REGISTRY_CASES)
def test_registry_errors(shared_world, capsys, edit, code, needle):
    text = shared_world.toml()
    edited = edit(shared_world, text)
    assert edited != text  # 시험이 바꾸려는 곳이 실제로 있는지
    shared_world.write_registry(edited)
    assert main(args_for(shared_world)) == code
    captured = capsys.readouterr()
    if code == 2:
        # 읽지 못했으면 문제 목록도 끝 줄도 내지 않고 이유만 표준 오류로 알린다.
        assert needle in captured.err
        assert captured.out == ""
    else:
        lines = captured.out.splitlines()
        assert any(needle in line for line in lines[:-1]), captured.out
        assert lines[-1].startswith("잠금 ")


def test_missing_registry_file_stops_the_check(shared_world, capsys):
    absent = shared_world.repo / "없는등록.toml"
    assert main(["--repo", str(shared_world.repo), "--registry", str(absent)]) == 2
    captured = capsys.readouterr()
    assert "없는등록.toml" in captured.err
    assert captured.out == ""


def test_malformed_entry_is_named_with_the_registry_file_and_its_number(shared_world, capsys):
    shared_world.write_registry(shared_world.toml().replace('what = "시험용 잠금"\n', ""))
    assert main(args_for(shared_world)) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        f"{shared_world.registry}: [[lock]] 1번째: what - 없다",
        "잠금 1개, 문제 1개",
    ]
    # 갱신 표 안의 오류는 몇 번째 갱신인지까지 적는다.
    shared_world.write_registry(shared_world.toml().replace('why = "시험용 갱신"\n', ""))
    assert main(args_for(shared_world)) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"{shared_world.registry}: [[lock]] 1번째 update 1번째: why - 없다"


def test_malformed_entry_is_not_checked_against_git(shared_world):
    # 꼴이 틀린 항목의 값은 믿을 수 없으므로 git과 견주지 않는다. 그래도 그 경로는 등록된 것으로 센다(같은 잠금을
    # '등록하지 않은 잠금'으로 한 번 더 알리지 않는다).
    edited = shared_world.toml().replace('what = "시험용 잠금"\n', "").replace(shared_world.base, "0" * 40)
    shared_world.write_registry(edited)
    problems = run_check(shared_world)
    assert len(problems) == 1
    assert "what - 없다" in problems[0]


# ---------------------------------------------------------------------------------------------
# 6. 명령줄
# ---------------------------------------------------------------------------------------------


def test_git_failure_stops_the_check(shared_world, tmp_path_factory, capsys):
    # git 저장소가 아닌 폴더는 읽을 수 없다. 문제 목록이 아니라 시작할 수 없다고 알리고 종료 코드 2로 끝낸다.
    plain = tmp_path_factory.mktemp("not-a-repo")
    assert main(["--repo", str(plain), "--registry", str(shared_world.registry)]) == 2
    captured = capsys.readouterr()
    assert "git" in captured.err
    assert captured.out == ""
    # 없는 폴더도 같다.
    assert main(["--repo", str(plain / "없는폴더"), "--registry", str(shared_world.registry)]) == 2
    assert capsys.readouterr().out == ""


def _subcommand(args: tuple[str, ...]) -> tuple[str, ...]:
    """git 인자에서 앞의 전역 설정(`-c 이름=값`)을 떼고 하위 명령부터의 인자를 돌려준다."""
    rest = list(args)
    while rest[:1] == ["-c"]:
        rest = rest[2:]
    return tuple(rest)


@pytest.mark.parametrize(
    "failing",
    [("ls-tree",), ("log",), ("show",), ("cat-file",), ("rev-parse", "--verify")],
    ids=["ls-tree", "log", "show", "cat-file", "rev-parse-verify"],
)
def test_unexpected_git_failure_exits_2_instead_of_passing(shared_world, capsys, monkeypatch, failing):
    # git이 '모른다'(종료 코드 1)가 아니라 예상하지 못한 방식으로 실패하면, 읽지 못한 것을 통과로 두지 않고 종료 코드 2로
    # 끝낸다. 맞게 등록한 저장소라 실패를 끼우지 않으면 0이다.
    real = check_lock_drift._run

    def fail(repo, *args):
        if _subcommand(args)[: len(failing)] == failing:
            return subprocess.CompletedProcess(list(args), 128, stdout=b"", stderr=b"fatal: boom\n")
        return real(repo, *args)

    assert main(args_for(shared_world)) == 0
    capsys.readouterr()
    monkeypatch.setattr(check_lock_drift, "_run", fail)
    assert main(args_for(shared_world)) == 2
    captured = capsys.readouterr()
    assert "fatal: boom" in captured.err
    assert captured.out == ""


def test_help_is_in_korean_and_lists_the_rules(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0
    out = capsys.readouterr().out
    for needle in [
        "--repo",
        "--registry",
        "종료 코드",
        "blob",
        "이름 따라가기",
        "얕은 복제",
        "저장소 뿌리",
        "'+ <패키지> <판>'",
    ]:
        assert needle in out, needle


def test_check_does_not_write_to_the_repository(shared_world):
    # 읽기만 하는 도구다. 저장소의 파일(작업 트리와 .git)을 고치거나 만들지 않는다. 등록 파일은 저장소 밖에 있다.
    before = snapshot(shared_world.repo)
    assert main(args_for(shared_world)) == 0
    assert snapshot(shared_world.repo) == before
    shared_world.write_registry(shared_world.toml(steps=[]))
    assert main(args_for(shared_world)) == 1
    assert snapshot(shared_world.repo) == before


def test_output_is_utf8_when_piped(shared_world):
    # 한국어 Windows의 파이썬은 파이프로 나가는 출력을 cp949로 쓴다. 어느 PC에서나 같은 조건이 되도록 그 인코딩을 환경 변수로
    # 정해 두고, 도구가 시작할 때 UTF-8로 다시 여는지 본다. 문제 줄에 cp949로 쓸 수 없는 글자(빼기 기호)를 넣어, 다시 열지
    # 않으면 출력 도중에 죽는 것도 함께 잡는다.
    minus = "−"
    shared_world.steps[0].date = f"2026{minus}03{minus}02"  # YYYY-MM-DD 꼴이 아니라 그 값이 문제 줄에 그대로 나온다
    shared_world.write_registry(shared_world.toml())
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUTF8"}
    env["PYTHONIOENCODING"] = "cp949"
    done = subprocess.run(
        [sys.executable, str(TOOLS / "check_lock_drift.py"), *args_for(shared_world)],
        capture_output=True,
        env=env,
        check=False,  # 종료 코드는 아래에서 직접 확인한다
    )
    assert done.returncode == 1, done.stderr.decode("utf-8", errors="replace")
    lines = done.stdout.decode("utf-8").splitlines()
    assert lines[0].endswith(f"date - YYYY-MM-DD 꼴이 아니다: 2026{minus}03{minus}02")
    assert lines[-1] == "잠금 1개, 문제 1개"


# ---------------------------------------------------------------------------------------------
# 7. 이 저장소의 실제 등록
# ---------------------------------------------------------------------------------------------
#
# 아래 두 시험은 시험용 저장소가 아니라 이 저장소 자신(tools/locks.toml과 HEAD의 이력)을 읽고, 읽기만 한다. 태그 archive/<이름>과
# 전체 이력이 있어야 해서, 얕은 체크아웃이나 태그를 받지 않은 체크아웃에서는 건너뛰지 않고 실패한다(tools/tests/test_docs.py의
# 실제 저장소 시험과 같은 관습: 읽지 못했는데 통과하는 길을 두지 않는다). 이 시험을 돌리는 CI는 전체 이력과 태그를 받는다
# (actions/checkout의 fetch-depth: 0).

# 등록한 잠금 → (합치기 전 저장소의 이름, 그 저장소 안의 옛 경로). 이름은 태그 archive/<이름>과 같다: 그 태그가 합친 시점의 그
# 저장소 마지막 커밋이다. 구성 요소 다섯의 잠금 여섯이다. e2e/uv.lock과 evaluation/asr/uv.lock은 이 저장소에서 처음 만든
# 잠금이라 합치기 전 저장소가 없어 이 표에 없다.
ORIGINAL_LOCKS = {
    "whisper-ko-ft/uv.lock": ("whisper-ko-ft", "uv.lock"),
    "stt-scratch/uv.lock": ("stt-scratch", "uv.lock"),
    "call-summary/uv.lock": ("call-summary", "uv.lock"),
    "support-agent/uv.lock": ("support-agent", "uv.lock"),
    "voice-translator/backend/uv.lock": ("voice-translator", "backend/uv.lock"),
    "voice-translator/frontend/package-lock.json": ("voice-translator", "frontend/package-lock.json"),
}


def test_registry_bases_are_the_original_locks():
    # 폴더째 옮겨 들인 잠금은 합치기 전 저장소의 것과 한 바이트도 다르면 안 된다. 등록한 base(들일 때의 blob)가 태그 archive/<이름>에서
    # 옛 경로로 읽은 blob과 같으면 그렇다(도구의 규칙 2가 added 커밋에서의 blob이 base와 같음을 보므로, 둘을 이으면 옮긴 커밋의
    # 잠금이 옛 저장소의 잠금과 같다). 등록은 이 저장소의 실제 tools/locks.toml을 읽어 쓰고 값을 여기 다시 적지 않는다.
    registered = {lock.path: lock for lock in load_registry(REPO / "tools" / "locks.toml")}
    for path, (name, old_path) in ORIGINAL_LOCKS.items():
        assert path in registered, f"tools/locks.toml에 {path}가 없다"
        try:
            original = git(REPO, "rev-parse", f"archive/{name}:{old_path}")
        except subprocess.CalledProcessError as error:
            pytest.fail(
                f"archive/{name}:{old_path}를 읽을 수 없다. 태그와 전체 이력이 있어야 한다"
                f"(얕은 복제는 git fetch --unshallow, 태그는 git fetch --tags): {error.stderr.strip()}"
            )
        assert registered[path].base == original, (
            f"{path}의 base {registered[path].base}가 archive/{name}:{old_path}의 {original}와 다르다"
        )


def test_repository_locks_match_the_registry(capsys):
    # 이 저장소의 HEAD에서 추적되는 잠금 여덟이 등록과 맞는다: 등록하지 않은 잠금이나 변경이 없고, 등록한 갱신의 판 변경이
    # 실제와 같다. 인자 없이 도구를 돌릴 때와 같은 검사다(기본 저장소 뿌리와 기본 등록). 이력을 읽을 수 없으면 종료 코드 2가
    # 나와 이 시험이 실패한다. 새 잠금을 등록하면 아래 개수도 함께 고친다.
    code = main(["--repo", str(REPO)])
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert captured.out.splitlines()[-1] == "잠금 8개, 문제 0개"
