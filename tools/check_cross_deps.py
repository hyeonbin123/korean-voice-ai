# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""구성 요소 사이의 의존을 선언 파일에 글자로 묶어 두고, 그 선언이 지금도 맞는지 보는 검사 도구.

왜 있나
    이 저장소의 구성 요소는 서로를 패키지로 설치해 쓰지 않는다. 그런데 몇 군데에서는 한 구성 요소의
    코드가 다른 구성 요소의 파일을 폴더 경로로 직접 쓴다(예: call-summary의 음성 조건 스크립트는
    support-agent의 환경과 소스에서 돈다). 이런 의존은 경로 계산 코드 속에 숨어 있어 눈에 띄지 않고,
    파일을 옮기거나 글을 고치면 조용히 끊긴다. 그렇다고 구성 요소의 코드와 시험을 고치면 기록된 측정을
    낸 실행(경로 계산)이나 시험 수집 수가 달라진다. 그래서 구성 요소는 그대로 두고, 의존을 이 도구의
    선언 파일(기본값 tools/cross-deps.toml)에 적어 두며 사람이 읽는 설명 문서(docs/architecture.md)와
    함께 검사한다.

선언 파일(TOML)
    doc            의존을 설명하는 문서의 경로(저장소 뿌리 기준, 슬래시 경로).
    [[dep]]        한 구성 요소가 다른 구성 요소의 파일을 쓰는 곳 하나.
        id, from, to, what
                   이름(검사 출력에 쓴다), 쓰는 구성 요소와 쓰이는 구성 요소(폴더 이름), 한 문장 설명.
        tracked    쓰이는 파일 가운데 git이 추적하는 것의 경로 목록(없으면 생략).
        local      git이 추적하지 않아 이 PC에만 있는 대상(가상환경, 학습 결과 폴더)의 경로 목록(없으면 생략).
        [[dep.code]]
            path, text
                   쓰는 쪽 코드 파일과, 그 파일에 글자 그대로 들어 있어야 하는 글. 하나 이상 있어야 한다.
    [[pinned]]     다른 구성 요소의 어느 커밋 시점 파일을 사본으로 고정해 쓰는 곳 하나.
        id, code   이름, 고정 상수(커밋·원본 경로·blob 해시)가 적힌 코드 파일.
        commit_pattern, source_pattern, blob_pattern
                   code 글에서 고정 커밋, 원본 경로, 원본 blob 해시를 뽑는 정규식. 괄호 묶음(캡처)이
                   정확히 하나여야 하고 파일 안에서 정확히 한 번 맞아야 한다. 정규식은 파일 전체 글에
                   건다(줄 단위 기준이 필요하면 (?m)을 앞에 둔다).

검사하는 것 (어긋날 때마다 문제 한 줄. 아래 순서로 본다)
    1. [[dep.code]]: path가 git 추적 파일이고 그 글에 text가 들어 있다. 경로 계산 코드가 바뀌면 설명 문서가
       틀리게 되므로, 글이 사라지면 실패해서 알려 준다.
    2. tracked의 각 경로가 `git ls-files --error-unmatch`를 통과한다. 디스크에만 있고 커밋하지 않은
       파일은 새로 받은 복제본에 없으므로 의존의 대상으로 삼을 수 없다.
    3. --local을 줄 때만: local의 각 경로가 디스크에 있다.
    4. [[pinned]]: code 파일이 추적 파일이고, 세 정규식이 각각 정확히 한 번 맞고, 뽑은 커밋과 blob이
       40자 소문자 16진수 해시이며(브랜치·태그 이름처럼 움직이는 값은 '고정'이 아니다), 그 커밋이 이
       저장소의 이력에 있고, `git rev-parse <커밋>:<원본 경로>`가 적힌 blob과 같다. 사본 파일 본문이 그
       blob과 같은지는 이 도구가 보지 않는다(사본을 쓰는 구성 요소의 시험이 본다). 여기서는 코드에 적힌
       고정 상수가 이 저장소의 이력과 맞는지만 본다.
    5. doc 문서가 위의 모든 쓰는 쪽 코드 경로, tracked 경로, 고정 코드 경로와 고정 커밋의 앞 7자를 글자로 적고
       있다(링크 `../<경로>` 꼴이면 된다).
    선언 파일 자체의 꼴 오류(모르는 키, 빠진 키, 빈 글, 깨진 정규식)도 문제로 알린다. 오타 때문에 선언이
    조용히 빠지거나 검사가 느슨해지는 일을 막으려는 것이다.

종료 코드와 출력
    0 = 모두 통과, 1 = 문제가 있음, 2 = 검사를 시작할 수 없음(선언 파일이 없거나 읽을 수 없음, TOML 문법 오류,
    저장소 폴더가 아니거나 git 저장소가 아님, git을 실행할 수 없음). 문제는 한 줄에 하나씩 쓰고 마지막 줄은
    `선언 N개, 문제 M개`다(N은 [[dep]] 수와 [[pinned]] 수의 합). 판정은 끝 줄 글자가 아니라 종료 코드로 한다.

실행
    uv run --no-project tools/check_cross_deps.py [--repo <저장소>] [--deps <toml>] [--local]
    --local 없이는 저장소 안의 것(추적 파일, 이력)만 보므로 새로 받은 복제본이나 CI에서도 돌릴 수 있다.
    다만 고정 사본의 원본 커밋을 이력에서 풀기 때문에 전체 이력이 있어야 한다(CI 체크아웃은
    `fetch-depth: 0`, 얕은 복제는 `git fetch --unshallow`).

이 도구는 읽기만 한다. git은 읽기 명령(--no-optional-locks)만 부르고, 선언 파일과 문서를 고치지 않는다.
"""

import argparse
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

# 이 파일은 <저장소>/tools/check_cross_deps.py에 있다. parents[0] = tools, parents[1] = 저장소 뿌리.
DEFAULT_REPO = Path(__file__).resolve().parents[1]
DEFAULT_DEPS_FILE = "tools/cross-deps.toml"

# 선언 표마다 받는 키. 여기에 없는 키는 오타일 가능성이 커서 조용히 무시하지 않고 문제로 알린다.
TOP_KEYS = ("doc", "dep", "pinned")
DEP_KEYS = ("id", "from", "to", "what", "tracked", "local", "code")
CODE_KEYS = ("path", "text")
PINNED_KEYS = ("id", "code", "commit_pattern", "source_pattern", "blob_pattern")

# 고정 커밋과 blob으로 받아들이는 꼴: 40자 소문자 16진수(SHA-1 전체 해시). 줄임 해시나 브랜치·태그
# 이름은 시간이 지나면 다른 객체를 가리킬 수 있어 '고정'이 아니다. 뽑은 글을 git 인자로 넘기기 전에 이
# 꼴만 통과시키므로, 정규식이 넓어도 옵션처럼 읽히는 글(`-`로 시작하는 글)이 git에 닿지 않는다.
_FULL_HASH = re.compile(r"[0-9a-f]{40}", re.ASCII)


@dataclass(frozen=True)
class CodeRef:
    """쓰는 쪽 코드에서 의존을 드러내는 글 한 곳: 파일 경로와, 그 파일에 들어 있어야 하는 글."""

    path: str
    text: str


@dataclass(frozen=True)
class Dep:
    """한 구성 요소가 다른 구성 요소의 파일을 쓰는 곳 하나([[dep]]).

    from_은 TOML 키 `from`이다(파이썬 예약어라 뒤에 밑줄을 붙였다).
    """

    id: str
    from_: str
    to: str
    what: str
    code: tuple[CodeRef, ...]
    tracked: tuple[str, ...] = ()
    local: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pinned:
    """다른 구성 요소의 어느 커밋 시점 파일을 사본으로 고정한 곳 하나([[pinned]])."""

    id: str
    code: str
    commit_pattern: str
    source_pattern: str
    blob_pattern: str


@dataclass(frozen=True)
class Spec:
    """선언 파일을 읽은 결과.

    problems는 읽는 단계에서 찾은 꼴 오류(모르는 키, 빈 글, 깨진 정규식 등)다. 꼴이 맞지 않아 객체로
    만들 수 없는 선언은 deps·pinned에서 빠지지만, 그 이유가 여기 남아 check가 문제로 알린다(조용히
    빠지지 않는다). doc은 비어 있을 수 있고(꼴 오류), 그러면 check는 문서 검사만 건너뛴다.
    """

    doc: str
    deps: tuple[Dep, ...]
    pinned: tuple[Pinned, ...]
    problems: tuple[str, ...] = ()


# ---------------------------------------------------------------------------------------------
# 선언 파일 읽기
# ---------------------------------------------------------------------------------------------


def _unknown_keys(table: dict, allowed: tuple[str, ...], where: str, problems: list[str]) -> None:
    """table에 allowed에 없는 키가 있으면 키마다 문제를 적는다."""
    for key in table:
        if key not in allowed:
            problems.append(f"{where}: {key} - 모르는 키(오타일 수 있다)")


def _text_of(table: dict, key: str, where: str, problems: list[str]) -> str | None:
    """table[key]가 비어 있지 않은 글이면 그 글을 돌려주고, 아니면 이유를 problems에 적고 None을 돌려준다.

    공백뿐인 글도 비었다고 본다. 빈 text는 어떤 파일에도 들어 있어 검사가 아무것도 보지 않게 되기 때문이다.
    """
    if key not in table:
        problems.append(f"{where}: {key} - 없다")
        return None
    value = table[key]
    if not isinstance(value, str):
        problems.append(f"{where}: {key} - 글이어야 한다")
        return None
    if not value.strip():
        problems.append(f"{where}: {key} - 비어 있다")
        return None
    return value


def _texts_of(table: dict, key: str, where: str, problems: list[str]) -> tuple[str, ...]:
    """table[key]를 글의 목록으로 읽는다.

    키가 없으면 빈 목록이다. 꼴이 틀리거나 빈 글이 들어 있으면 이유를 problems에 적는다.
    """
    if key not in table:
        return ()
    value = table[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        problems.append(f"{where}: {key} - 글의 목록이어야 한다")
        return ()
    kept = []
    for item in value:
        if item.strip():
            kept.append(item)
        else:
            problems.append(f"{where}: {key} - 빈 글이 들어 있다")
    return tuple(kept)


def _tables(raw: dict, key: str, where: str, problems: list[str]) -> list[dict]:
    """raw[key]를 TOML 표의 배열([[key]])로 읽는다. 키가 없으면 빈 목록, 꼴이 틀리면 문제로 적고 빈 목록."""
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        problems.append(f"{where}: {key} - [[{key}]] 표의 배열이어야 한다")
        return []
    return value


def _parse_codes(raw: object, where: str, problems: list[str]) -> tuple[CodeRef, ...]:
    """[[dep.code]] 배열을 읽는다. 하나도 없으면 문제다(쓰는 쪽 코드가 없는 의존은 아무것도 묶지 못한다)."""
    if raw is None or raw == []:
        problems.append(f"{where}: code - 쓰는 쪽 코드([[dep.code]])가 하나도 없다")
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        problems.append(f"{where}: code - [[dep.code]] 표의 배열이어야 한다")
        return ()
    refs = []
    for number, entry in enumerate(raw, 1):
        label = f"{where} code {number}번째"
        _unknown_keys(entry, CODE_KEYS, label, problems)
        path = _text_of(entry, "path", label, problems)
        text = _text_of(entry, "text", label, problems)
        if path is not None and text is not None:
            refs.append(CodeRef(path=path, text=text))
    return tuple(refs)


def _parse_dep(item: dict, number: int, problems: list[str]) -> Dep | None:
    """[[dep]] 표 하나를 읽는다.

    필요한 글이 없거나 쓰는 쪽 코드가 하나도 남지 않으면 None을 돌려주고, 이유는 problems에 적는다.
    """
    where = f"[[dep]] {number}번째"
    _unknown_keys(item, DEP_KEYS, where, problems)
    dep_id = _text_of(item, "id", where, problems)
    if dep_id is not None:
        where = f"{where} ({dep_id})"
    from_ = _text_of(item, "from", where, problems)
    to = _text_of(item, "to", where, problems)
    what = _text_of(item, "what", where, problems)
    tracked = _texts_of(item, "tracked", where, problems)
    local = _texts_of(item, "local", where, problems)
    code = _parse_codes(item.get("code"), where, problems)
    if dep_id is None or from_ is None or to is None or what is None or not code:
        return None
    return Dep(id=dep_id, from_=from_, to=to, what=what, code=code, tracked=tracked, local=local)


def _parse_pinned(item: dict, number: int, problems: list[str]) -> Pinned | None:
    """[[pinned]] 표 하나를 읽는다. 정규식은 컴파일되고 괄호 묶음이 정확히 하나여야 한다. 아니면 None."""
    where = f"[[pinned]] {number}번째"
    _unknown_keys(item, PINNED_KEYS, where, problems)
    pin_id = _text_of(item, "id", where, problems)
    if pin_id is not None:
        where = f"{where} ({pin_id})"
    code = _text_of(item, "code", where, problems)
    patterns: dict[str, str] = {}
    for key in ("commit_pattern", "source_pattern", "blob_pattern"):
        value = _text_of(item, key, where, problems)
        if value is None:
            continue
        try:
            compiled = re.compile(value)
        except re.error as error:
            problems.append(f"{where}: {key} - 정규식이 깨졌다: {error}")
            continue
        if compiled.groups != 1:
            problems.append(
                f"{where}: {key} - 괄호 묶음(캡처)이 정확히 하나여야 한다(지금 {compiled.groups}개)"
            )
            continue
        patterns[key] = value
    if pin_id is None or code is None or len(patterns) != 3:
        return None
    return Pinned(
        id=pin_id,
        code=code,
        commit_pattern=patterns["commit_pattern"],
        source_pattern=patterns["source_pattern"],
        blob_pattern=patterns["blob_pattern"],
    )


def _parse(raw: dict) -> Spec:
    """TOML을 읽은 dict를 Spec으로 바꾼다. 꼴 오류는 던지지 않고 Spec.problems에 모은다."""
    problems: list[str] = []
    _unknown_keys(raw, TOP_KEYS, "선언 파일", problems)
    doc = _text_of(raw, "doc", "선언 파일", problems) or ""
    deps = []
    for number, item in enumerate(_tables(raw, "dep", "선언 파일", problems), 1):
        dep = _parse_dep(item, number, problems)
        if dep is not None:
            deps.append(dep)
    pinned = []
    for number, item in enumerate(_tables(raw, "pinned", "선언 파일", problems), 1):
        pin = _parse_pinned(item, number, problems)
        if pin is not None:
            pinned.append(pin)
    return Spec(doc=doc, deps=tuple(deps), pinned=tuple(pinned), problems=tuple(problems))


def load(path: Path) -> Spec:
    """선언 파일(TOML)을 읽어 Spec으로 돌려준다.

    파일이 없거나 읽을 수 없으면 OSError, TOML 문법이나 인코딩이 틀리면 ValueError(tomllib.TOMLDecodeError,
    UnicodeDecodeError)가 그대로 나간다. main이 둘 다 종료 코드 2(검사를 시작할 수 없음)로 바꾼다. 표 안의 꼴
    오류(모르는 키, 빈 글 등)는 던지지 않고 Spec.problems에 담는다.
    """
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    return _parse(raw)


# ---------------------------------------------------------------------------------------------
# 검사
# ---------------------------------------------------------------------------------------------


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """repo에서 git 읽기 명령을 부른다. --no-optional-locks로 색인 잠금 파일을 만들지 않는다.

    git 실행 파일이 없으면 OSError가 나간다. 종료 코드가 0이 아닌 것은 호출한 쪽이 판단한다(check=False).
    """
    return subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class _Probe:
    """저장소 하나에 대한 git·파일 읽기를 모은 도우미. 같은 경로를 되풀이해 묻지 않도록 결과를 기억한다."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self._tracked: dict[str, bool] = {}
        self._texts: dict[str, tuple[str | None, str | None]] = {}
        self._shallow: bool | None = None

    def git(self, *args: str) -> tuple[int, str]:
        """(종료 코드, 앞뒤 공백을 뗀 표준 출력)."""
        done = _run(self.repo, *args)
        return done.returncode, done.stdout.strip()

    def tracked(self, path: str) -> bool:
        """path를 git이 추적하는지(색인에 있는지). `git ls-files --error-unmatch`가 성공하면 참이다."""
        if path not in self._tracked:
            code, _ = self.git("ls-files", "--error-unmatch", "--", path)
            self._tracked[path] = code == 0
        return self._tracked[path]

    def read_tracked(self, path: str) -> tuple[str | None, str | None]:
        """추적 파일의 글을 읽는다. (글, None) 또는 (None, 문제 설명).

        UTF-8로 읽고 맨 앞의 BOM은 뗀다. 깨진 바이트는 대체 글자로 바꿔 읽기가 멈추지 않게 한다.
        """
        if path not in self._texts:
            self._texts[path] = self._read_tracked(path)
        return self._texts[path]

    def _read_tracked(self, path: str) -> tuple[str | None, str | None]:
        if not self.tracked(path):
            return None, "추적 파일이 아니다(git ls-files --error-unmatch 실패)"
        try:
            data = (self.repo / path).read_bytes()
        except OSError as error:
            return None, f"읽을 수 없다({type(error).__name__})"
        return data.decode("utf-8-sig", errors="replace"), None

    def is_shallow(self) -> bool:
        """이 저장소가 얕은 복제(이력 일부만 받음)인지."""
        if self._shallow is None:
            code, out = self.git("rev-parse", "--is-shallow-repository")
            self._shallow = code == 0 and out == "true"
        return self._shallow


def _check_pinned(pin: Pinned, probe: _Probe) -> tuple[list[str], str | None]:
    """고정 사본 하나를 검사한다. (문제 목록, 코드에서 뽑은 40자 고정 커밋 또는 None).

    고정 커밋은 이 저장소 이력에서 풀리지 않아도 40자 해시 꼴이면 돌려준다: 설명 문서가 그 앞 7자를 적고
    있는지는 별개의 검사라서다. 커밋을 풀지 못하면 원본 blob은 견줄 수 없으므로 blob 문제를 더 내지
    않는다.
    """
    text, reason = probe.read_tracked(pin.code)
    if text is None:
        return [f"{pin.id}: 고정 코드 {pin.code}: {reason}"], None

    problems: list[str] = []
    values: dict[str, str] = {}
    for key, pattern in (
        ("commit_pattern", pin.commit_pattern),
        ("source_pattern", pin.source_pattern),
        ("blob_pattern", pin.blob_pattern),
    ):
        found = [match.group(1) for match in re.finditer(pattern, text)]
        if len(found) == 1:
            values[key] = found[0]
        else:
            problems.append(
                f"{pin.id}: {key} - {pin.code}에서 {len(found)}번 맞았다(정확히 한 번이어야 한다)"
            )

    commit = values.get("commit_pattern")
    source = values.get("source_pattern")
    blob = values.get("blob_pattern")

    commit_ok = False
    if commit is not None:
        if not _FULL_HASH.fullmatch(commit):
            problems.append(f"{pin.id}: commit_pattern - 40자 소문자 16진수 해시가 아니다: {commit}")
            commit = None
        else:
            code, _ = probe.git("cat-file", "-e", f"{commit}^{{commit}}")
            commit_ok = code == 0
            if not commit_ok:
                hint = (
                    " (얕은 복제라 이력이 모자랄 수 있다: 전체 이력을 받아야 한다)"
                    if probe.is_shallow()
                    else ""
                )
                problems.append(f"{pin.id}: 커밋을 풀 수 없음: {commit}{hint}")

    if blob is not None and not _FULL_HASH.fullmatch(blob):
        problems.append(f"{pin.id}: blob_pattern - 40자 소문자 16진수 해시가 아니다: {blob}")
        blob = None

    if commit is not None and commit_ok and source is not None and blob is not None:
        code, actual = probe.git("rev-parse", "--verify", "--quiet", f"{commit}:{source}")
        if code != 0 or not actual:
            problems.append(f"{pin.id}: 고정 사본의 원본을 풀 수 없음: {commit[:7]}:{source}")
        elif actual != blob:
            problems.append(
                f"{pin.id}: blob이 다르다: 코드에 적힌 값 {blob}, {commit[:7]}:{source}의 값 {actual}"
            )

    return problems, commit


def _check_doc(doc: str, repo: Path, needed: dict[str, str]) -> list[str]:
    """설명 문서 doc에 needed의 글(경로, 커밋 앞 7자)이 모두 적혀 있는지 본다. needed는 글 → 필요한 이유."""
    if not doc:
        return []  # doc 키의 꼴 오류는 Spec.problems가 이미 알렸다
    try:
        text = (repo / doc).read_bytes().decode("utf-8-sig", errors="replace")
    except OSError as error:
        return [f"문서 {doc}: 읽을 수 없다({type(error).__name__})"]
    return [
        f"문서 {doc}: 적혀 있어야 할 글이 없다: {needle} ({reason})"
        for needle, reason in needed.items()
        if needle not in text
    ]


def check(spec: Spec, repo: Path, *, local: bool) -> list[str]:
    """선언 spec이 repo(git 저장소 뿌리)에서 지금도 맞는지 보고, 문제를 한 줄씩 돌려준다. 통과면 빈 목록.

    local이 참이면 git이 추적하지 않는 대상(Dep.local)이 디스크에 있는지도 본다. 거짓이면 저장소 안의
    것만 본다. 먼저 선언 파일 자체의 꼴 오류(Spec.problems)를 싣고, 이어 의존, 고정 사본, 설명 문서
    순서로 검사한다.
    """
    probe = _Probe(repo)
    problems = list(spec.problems)
    # 설명 문서에 글자로 적혀 있어야 하는 것 → 필요한 이유. 같은 글이 여러 곳에서 필요하면 처음 이유만 둔다.
    needed: dict[str, str] = {}

    for dep in spec.deps:
        for ref in dep.code:
            text, reason = probe.read_tracked(ref.path)
            if text is None:
                problems.append(f"{dep.id}: 쓰는 쪽 코드 {ref.path}: {reason}")
            elif ref.text not in text:
                problems.append(f"{dep.id}: 쓰는 쪽 코드 {ref.path}: 선언한 글이 없다: {ref.text}")
            needed.setdefault(ref.path, f"{dep.id}의 쓰는 쪽 코드")
        for path in dep.tracked:
            if not probe.tracked(path):
                problems.append(
                    f"{dep.id}: 대상 {path}: 추적 파일이 아니다(git ls-files --error-unmatch 실패)"
                )
            needed.setdefault(path, f"{dep.id}의 대상")
        if local:
            for path in dep.local:
                if not (repo / path).exists():
                    problems.append(f"{dep.id}: 로컬 대상 {path}: 없다(--local)")

    for pin in spec.pinned:
        found, commit = _check_pinned(pin, probe)
        problems += found
        needed.setdefault(pin.code, f"{pin.id}의 고정 코드")
        if commit is not None:
            needed.setdefault(commit[:7], f"{pin.id}의 고정 커밋 앞 7자")

    problems += _check_doc(spec.doc, repo, needed)
    return problems


# ---------------------------------------------------------------------------------------------
# 명령줄
# ---------------------------------------------------------------------------------------------


def _use_utf8_output() -> None:
    """표준 출력·오류를 UTF-8로 다시 연다. 인코딩할 수 없는 글자는 \\uXXXX로 바꿔 죽지 않게 한다.

    한국어 Windows(코드 페이지 949)의 파이썬은 출력이 파이프나 파일이면 cp949로 써서 한글 출력이 깨진다.
    Linux CI는 이미 UTF-8이라 바뀌는 것이 없다.

    모듈을 가져올 때가 아니라 main이 시작할 때 한다: 시험이 출력을 가로채는 중에 import만으로 표준
    출력을 바꾸지 않으려는 것이다. reconfigure가 없는 스트림(가로채기용 객체)이거나 이미 닫혔으면
    건너뛴다. 출력 인코딩은 보조 수단이라 실패해도 검사 자체를 막지 않는다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            continue


def _cannot_start(repo: Path) -> str | None:
    """repo에서 git 검사를 시작할 수 없으면 이유를, 시작할 수 있으면 None을 돌려준다.

    git 저장소가 아닌 폴더에서는 모든 추적 여부 질문이 실패해 문제가 줄줄이 나오고, 어디가 틀렸는지
    보이지 않는다. 그래서 검사에 들어가기 전에 한 번 확인해 '시작할 수 없음'으로 알린다.
    """
    if not repo.is_dir():
        return f"저장소 폴더가 아니다: {repo}"
    try:
        done = _run(repo, "rev-parse", "--is-inside-work-tree")
    except OSError as error:
        return f"git을 실행할 수 없다: {type(error).__name__}: {error}"
    if done.returncode != 0 or done.stdout.strip() != "true":
        lines = done.stderr.strip().splitlines()
        reason = f": {lines[0]}" if lines else ""
        return f"git 저장소가 아니다: {repo}{reason}"
    return None


def _build_parser() -> argparse.ArgumentParser:
    """명령줄 인자 해석기. 도움말은 한국어다."""
    parser = argparse.ArgumentParser(
        prog="check_cross_deps.py",
        add_help=False,  # 기본 -h 설명이 영어라서 아래에서 한국어 설명으로 직접 더한다
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "구성 요소 사이의 의존 선언이 지금도 맞는지 본다.\n"
            "\n"
            "선언 파일(기본값: <저장소>/tools/cross-deps.toml)의 [[dep]]마다 쓰는 쪽 코드에 선언한 글이\n"
            "아직 있는지, 대상 파일을 git이 추적하는지 보고, [[pinned]]마다 코드에 적힌 고정 커밋·원본\n"
            "경로·blob이 이 저장소의 이력과 맞는지 본다. 선언이 가리키는 경로와 고정 커밋의 앞 7자를\n"
            "설명 문서(선언 파일의 doc)가 적고 있는지도 본다.\n"
            "\n"
            "이 도구는 읽기만 한다. 선언 파일과 문서를 고치지 않는다."
        ),
        epilog=(
            "종료 코드: 0 = 모두 통과, 1 = 문제가 있음(한 줄씩 출력), 2 = 검사를 시작할 수 없음(선언 파일이\n"
            "없거나 읽을 수 없음, 저장소 폴더가 아니거나 git 저장소가 아님, git을 실행할 수 없음).\n"
            "출력의 끝 줄은 '선언 N개, 문제 M개'이며, 통과 여부는 끝 줄 글자가 아니라 종료 코드로 판정한다.\n"
            "\n"
            "고정 사본의 원본 커밋을 이력에서 풀기 때문에 전체 이력이 필요하다\n"
            "(얕은 복제에서는 git fetch --unshallow).\n"
            "\n"
            "예: uv run --no-project tools/check_cross_deps.py\n"
            "    uv run --no-project tools/check_cross_deps.py --local"
        ),
    )
    parser.add_argument("-h", "--help", action="help", help="이 도움말을 보여 주고 끝낸다")
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        metavar="<저장소>",
        help="경로의 기준이 되는 git 저장소 뿌리 (기본값: 이 파일에서 두 단계 위 폴더)",
    )
    parser.add_argument(
        "--deps",
        type=Path,
        default=None,
        metavar="<toml>",
        help="선언 파일 (기본값: <저장소>/tools/cross-deps.toml)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help=(
            "git이 추적하지 않아 이 PC에만 있는 대상(가상환경, 학습 결과 폴더)이 있는지도 본다. "
            "주지 않으면 저장소 안의 것만 보므로 CI에서도 돌릴 수 있다"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """선언을 읽어 검사하고 문제를 출력한다. 종료 코드는 0(통과), 1(문제), 2(검사를 시작할 수 없음)."""
    _use_utf8_output()
    args = _build_parser().parse_args(argv)
    repo = args.repo if args.repo is not None else DEFAULT_REPO
    deps = args.deps if args.deps is not None else repo / DEFAULT_DEPS_FILE
    try:
        spec = load(deps)
    except (OSError, ValueError) as error:
        # ValueError에는 tomllib.TOMLDecodeError(문법 오류)와 UnicodeDecodeError(UTF-8이 아님)가 든다.
        print(f"선언 파일을 읽을 수 없다: {deps}: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    reason = _cannot_start(repo)
    if reason is not None:
        print(f"검사를 시작할 수 없다: {reason}", file=sys.stderr)
        return 2
    problems = check(spec, repo, local=args.local)
    for problem in problems:
        print(problem)
    print(f"선언 {len(spec.deps) + len(spec.pinned)}개, 문제 {len(problems)}개")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
