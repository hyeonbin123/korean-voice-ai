# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""문서와 코드에 적힌 커밋 해시 참조가 이 저장소의 이력과 맞는지 보는 검사 도구.

왜 있나
    이 저장소의 문서와 코드는 근거를 커밋 해시로 가리킨다("커밋 1234abc에서 규칙을 정했다" 같은 글).
    해시는 글자일 뿐이라서, 오타이거나, 다른 브랜치에만 있는 커밋이거나, 이력에서 사라진 커밋이어도 읽는
    사람은 알 수 없다. 이 도구는 추적 파일에서 해시 꼴 낱말을 뽑아 이 저장소의 git 이력으로 풀어 보고,
    풀리는데 HEAD의 조상이 아니거나 둘 이상에 맞는 것, 문서가 커밋이라고 밝혀 적었는데 풀리지 않는 것을
    문제로 알린다.

규칙 (같은 내용이 --help에도 있다)
    1. 대상은 HEAD의 추적 파일이다. 이름이 uv.lock·package-lock.json인 파일과 글이 아닌 파일(널 바이트가
       든 파일)은 뺀다. 작업 트리가 아니라 HEAD의 내용을 읽는다.
    2. 낱말은 7~40자 소문자 16진수다. a~f 글자가 하나도 없는 숫자뿐인 것은 문서가 커밋 참조로 적은 자리
       (규칙 4의 두 꼴)에 있을 때만 낱말로 본다. 날짜나 숫자 꼬리를 해시로 잘못 읽지 않으려는 것이고,
       참조라고 밝혀 적은 자리는 숫자뿐인 줄임 해시(앞 7자가 모두 숫자인 커밋)도 봐야 해서다. 앞뒤가
       영문자·숫자·밑줄이 아니어야 한다(ASCII 경계라서 `1234abc의`처럼 뒤에 한글 조사가 붙어도 뽑는다).
    3. (모든 대상 파일) 낱말이 이 저장소의 커밋 하나로 풀리면 그 커밋은 HEAD의 조상이어야 한다. 커밋 둘
       이상에 맞으면 모호해서 문제다. 어떤 커밋으로도 풀리지 않는 낱말은 이 규칙에서는 문제가 아니다.
    4. (.md 파일) 문서가 커밋 참조로 적은 낱말은 반드시 풀려야 한다. 커밋 참조로 적었다는 것은 같은 줄에서
       백틱 한 쌍 안이 통째로 그 낱말이거나, `커밋`·`commit`(대소문자 무시) 뒤에 공백·탭·백틱·여는 괄호만
       두고 그 낱말이 온다는 뜻이다. 풀리지 않으면 문제다. 다만 등록 파일의 [[external]]에 그 파일과 그
       낱말이 등록돼 있으면 통과한다.
    5. [[external]]이 가리키는 낱말이 그 파일에 더는 없으면(낡은 등록), 또는 그 낱말이 이 저장소의 커밋으로
       풀리면(잘못 등록) 문제다.

왜 낱말 전부를 '풀려야 한다'로 두지 않나
    추적 파일에는 커밋이 아닌 해시 꼴 낱말이 훨씬 많다(데이터 해시, 다이제스트의 앞부분, 다른 저장소의
    커밋, 모델·데이터 개정 번호, 시험용 가짜 해시). 숫자뿐인 글자열(날짜, 크기, 숫자 꼬리)은 그보다도 많아서
    참조라고 밝혀 적은 자리에 있을 때만 낱말로 본다(규칙 2). 전부 풀려야 한다고 하면 그 낱말을 모두
    등록해야 하고, 아무도 읽지 않는 거대한 목록이 된다. 그래서 풀리는 낱말은 어디서나 올바른지 보고(규칙 3),
    풀려야 한다고 요구하는 것은 문서가 스스로 커밋이라고 밝힌 자리로 좁힌다(규칙 4). 그렇게 좁혀도 남는
    것(다른 저장소의 커밋을 적은 문서)만 등록한다.

왜 HEAD의 내용을 읽나
    작업 트리를 읽으면 Windows의 줄바꿈 변환 설정과 아직 커밋하지 않은 편집에 따라 결과가 달라진다.
    `git ls-tree`·`git cat-file`로 HEAD의 내용을 읽으면 이 PC의 작업 폴더에서도 CI의 새 복제본에서도 같은
    바이트를 보므로 같은 결과가 나온다. 색인(`git ls-files`)도 스테이징만 한 변경 때문에 HEAD와 다를 수 있어
    쓰지 않는다. 다만 등록 파일은 작업 트리의 파일을 읽는다. 등록을 고치며 다시 돌려 볼 수 있게 하려는
    것이고, CI에서는 둘이 같다.

어떻게 푸나
    낱말마다 git에 묻지 않는다. `git rev-list --all`(브랜치·태그·원격 추적 브랜치 등 어느 ref에서든 닿는
    커밋)과 `git rev-list HEAD`의 합집합을 한 번 받아 앞 7자를 키로 한 사전을 만들고, 파이썬 안에서 접두로
    찾는다. 40자 해시가 낱말로 시작하는 커밋이 0개면 풀리지 않음, 1개면 그 커밋, 2개 이상이면 모호다.
    낱말은 아주 많아서 낱말마다 git을 부르면 느리고, 이름 붙은 객체까지 푸는 방식은 어느 ref에서도 닿지
    않는 '떠 있는 객체'(지운 브랜치의 커밋 등)에 흔들린다. 그런 객체는 이 PC의 로컬 저장소에는 있고 CI의
    새 복제본에는 없어서, 세면 두 곳의 결과가 갈린다. 조상 여부는 `git rev-list HEAD`의 집합으로 본다.

등록 파일(TOML, 기본값 tools/evidence.toml)
    [[external]]   문서가 커밋 참조처럼 적었지만 이 저장소의 커밋이 아닌 해시(다른 저장소의 커밋 등) 하나.
                   규칙 4만 면제한다.
        hash       문서에 적힌 낱말 그대로(7~40자 소문자 16진수). 앞부분만 같아서는 통하지 않는다.
        where      그 낱말이 적힌 파일(저장소 뿌리 기준 `/` 경로). HEAD의 트리에 있는 검사 대상 파일이어야
                   하고, 그 파일에서만 통한다.
        what       무엇의 해시인지 한 줄.
    [[record]], [[pair]]
                   이 도구는 두 표가 표의 배열인지만 본다. 항목 안의 키는 아직 정하지 않았다.
    그 밖의 꼭대기 표나 키는 받지 않는다(종료 코드 2). 항목의 모르는 키, 빠진 키, 빈 글, 꼴이 틀린 값은
    조용히 넘기지 않고 그 항목의 문제로 알린다(오타 때문에 면제가 조용히 빠지거나 느슨해지는 일을 막으려는
    것이다).

출력과 종료 코드
    문제는 한 줄에 하나씩 `<종류> <파일>:<줄>: <낱말>: <이유>`로 쓴다(종류는 reference, external, record,
    pair). 등록 항목 자체의 문제는 `external <등록 파일>: [[external]] <번호>번째: <키 또는 낱말> - <이유>`다.
    문제는 파일 경로·줄 번호 순으로 정렬해 실행마다 같은 순서로 낸다. 끝 줄은
    `참조 N개, 기록 값 R개, 짝 P개, 문제 M개`이고, --report-only를 주면 그 뒤에 `보고만: …` 줄이 하나 더
    붙는다. N은 규칙 3·4가 실제로 걸린 낱말 출현 수다(이 저장소의 커밋으로 풀리거나 모호한 출현과, .md에서
    문서가 커밋 참조로 적었는데 풀리지 않은 출현. 후자는 등록돼 통과한 것과 문제인 것을 모두 센다).
    기록 값 R과 짝 P는 이 도구가 아직 세지 않아 늘 0이다.
    0 = 문제 없음(--report-only면 문제가 있어도 0), 1 = 문제 있음, 2 = 검사를 시작하거나 끝낼 수 없음
    (등록 파일이 없거나 읽을 수 없음, TOML 문법 오류, 모르는 꼭대기 표, 저장소 폴더가 아니거나 git 저장소가
    아님, git을 실행할 수 없음, git 읽기 명령의 실패, 얕은 복제라 이력이 모자람, HEAD가 없음). --report-only를
    줘도 2는 2다(읽지 못했는데 통과하지 않게). 판정은 끝 줄 글자가 아니라 종료 코드로 한다.

실행
    uv run --no-project tools/check_evidence.py [--repo <저장소>] [--registry <toml>] [--report-only]
    이력이 모자라면 풀리지 않는 낱말이 늘어 '증거가 틀림'으로 잘못 알리게 된다. 그래서 얕은 복제는 종료
    코드 2와 안내로 끝낸다(CI 체크아웃은 `fetch-depth: 0`, 얕은 복제는 `git fetch --unshallow`).

이 도구는 읽기만 한다. git은 읽기 명령(--no-optional-locks)만 부르고, 등록 파일과 저장소의 어떤 파일도
고치지 않는다.
"""

import argparse
import re
import subprocess
import sys
import tomllib
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# 이 파일은 <저장소>/tools/check_evidence.py에 있다. parents[0] = tools, parents[1] = 저장소 뿌리.
DEFAULT_REPO = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = "tools/evidence.toml"

# 등록 파일이 받는 꼭대기 표와, [[external]] 항목이 받는 키. 여기에 없는 것은 오타일 가능성이 커서 조용히
# 무시하지 않는다(꼭대기 표는 읽을 수 없는 파일로, 항목의 키는 그 항목의 문제로 알린다).
TOP_KEYS = ("external", "record", "pair")
EXTERNAL_KEYS = ("hash", "where", "what")
# [[external]]의 hash가 받는 꼴: 낱말(아래 _WORD)과 같은 7~40자 소문자 16진수. 이 꼴이어도 그 파일에 적힌 낱말과
# 글자가 같아야 등록이 통한다(앞부분만 같은 것은 통하지 않는다).
_EXTERNAL_HASH = re.compile(r"[0-9a-f]{7,40}")

# 규칙 2의 낱말 후보: 7~40자 소문자 16진수. 앞뒤가 ASCII 영문자·숫자·밑줄이 아니어야 한다. 파이썬의 \b는 한글도
# 낱말 글자로 보므로(`139cb8a의`의 뒤가 경계로 안 잡힌다) 쓰지 않고 ASCII 경계를 직접 적는다. 이 정규식은 숫자뿐인
# 글자열도 맞히는데, 그것을 낱말로 칠지는 find_tokens가 정한다(참조 표시가 달린 것만 낱말로 본다).
_WORD = re.compile(r"(?<![0-9A-Za-z_])[0-9a-f]{7,40}(?![0-9A-Za-z_])")
# 백틱 한 쌍(코드 조각)을 찾는 정규식. 여는 백틱 줄(길이 N)은 같은 길이의 닫는 백틱 줄을 만날 때까지다(백틱
# 둘로 감싼 조각도 한 쌍이다). 앞뒤에 백틱이 더 붙은 줄은 다른 길이의 줄이라 짝이 되지 않는다. 가운데 글(2번
# 묶음)이 낱말과 정확히 같은 조각만 '통째로 그 낱말'로 본다.
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
# 커밋·commit 바로 뒤에 올 수 있는 글자: 공백, 탭, 백틱, 여는 괄호.
_SEPARATORS = " \t`("
_COMMIT_WORDS = ("커밋", "commit")
# 낱말을 커밋 참조로 적은 것으로 보려면 낱말 바로 앞 글자가 이 가운데 하나여야 한다: 백틱이거나, 커밋·commit 뒤에
# 둔 구분 글자이거나, 사이에 아무것도 없을 때 그 말의 마지막 글자다. 숫자뿐인 낱말을 줄 번호를 세거나 줄을 훑기
# 전에 싸게 거르는 데 쓴다(앞 글자가 이 가운데 하나라고 해서 참조로 적은 것이라는 뜻은 아니다).
_CLAIM_PREFIX_CHARS = frozenset(_SEPARATORS) | {word[-1] for word in _COMMIT_WORDS}

# 이 이름의 파일은 해시 꼴 글자열이 가득한 잠금 파일이라 읽지 않는다.
SKIPPED_NAMES = frozenset({"uv.lock", "package-lock.json"})

# 풀이 사전의 키 길이. 낱말의 최소 길이(7)와 같다.
PREFIX_LENGTH = 7

# 블롭을 `git cat-file --batch`로 읽을 때 한 번에 묶는 크기. 한 번에 다 읽으면 저장소 전체 크기만큼 메모리를
# 쓰므로 일정한 크기로 나눈다(블롭 하나가 이보다 크면 그 하나가 한 묶음이다).
MAX_BATCH_BYTES = 32 * 1024 * 1024
MAX_BATCH_BLOBS = 1000


class CannotCheck(Exception):
    """검사를 시작하거나 끝낼 수 없음(종료 코드 2)을 알린다. 메시지는 사람이 읽는 한국어 이유다."""


class RegistryError(ValueError):
    """등록 파일을 읽을 수 없음을 알린다(예: 모르는 꼭대기 표). ValueError라서 TOML 문법 오류와 같이 묶인다."""


@dataclass(frozen=True)
class Problem:
    """문제 한 줄.

    kind는 reference(규칙 3·4: 파일 안의 낱말) 또는 등록 파일의 표 이름(external, record, pair)이다.
    path는 문제가 난 파일이고(등록 항목의 문제는 등록 파일), line은 그 파일 안의 줄 번호다(없으면 0).
    order는 같은 파일 안에서 정렬 순서를 정하는 번호로, 등록 항목의 문제에서 항목 번호를 담는다(문자열로
    정렬하면 10번째가 2번째보다 앞서므로 숫자로 둔다). message는 줄 끝까지의 설명이다.
    """

    kind: str
    path: str
    message: str
    line: int = 0
    order: int = 0

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{self.kind} {where}: {self.message}"


@dataclass(frozen=True)
class External:
    """다른 저장소의 해시를 문서가 커밋 참조처럼 적은 곳 하나([[external]]). number는 등록 파일의 몇 번째 항목인지."""

    hash: str
    where: str
    what: str
    number: int


@dataclass(frozen=True)
class Registry:
    """등록 파일을 읽은 결과.

    externals는 꼴이 맞는 [[external]] 항목이다. 꼴이 틀린 항목은 여기서 빠지지만 그 이유가 problems에
    남아 검사가 문제로 알린다(조용히 빠지지 않는다). records와 pairs는 [[record]]·[[pair]] 표를 있는 그대로
    담는다(항목 안의 키는 아직 보지 않는다). source는 문제 줄에 쓰는 등록 파일 이름이다.
    """

    externals: tuple[External, ...] = ()
    records: tuple[dict, ...] = ()
    pairs: tuple[dict, ...] = ()
    problems: tuple[Problem, ...] = ()
    source: str = DEFAULT_REGISTRY


@dataclass(frozen=True)
class ReferenceReport:
    """check_references의 자세한 결과. problems는 정렬된 문제들, references는 끝 줄의 `참조 N개`의 N이다."""

    problems: tuple[Problem, ...]
    references: int


# ---------------------------------------------------------------------------------------------
# 등록 파일 읽기
# ---------------------------------------------------------------------------------------------


def _entry_problem(kind: str, source: str, number: int, key: str, reason: str) -> Problem:
    """등록 항목의 문제. `[[<종류>]] <번호>번째: <키 또는 낱말> - <이유>`(cross-deps 선언 오류와 같은 말투)."""
    return Problem(kind, source, f"[[{kind}]] {number}번째: {key} - {reason}", order=number)


def _tables(raw: dict, kind: str, source: str, problems: list[Problem]) -> list[dict]:
    """raw[kind]를 TOML 표의 배열([[kind]])로 읽는다. 없으면 빈 목록, 꼴이 틀리면 문제로 적고 빈 목록."""
    value = raw.get(kind, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        problems.append(Problem(kind, source, f"등록 파일: {kind} - [[{kind}]] 표의 배열이어야 한다"))
        return []
    return value


def _text_of(table: dict, key: str) -> tuple[str | None, str | None]:
    """table[key]가 비어 있지 않은 글이면 (글, None), 아니면 (None, 이유)를 돌려준다.

    공백뿐인 글도 비었다고 본다. 빈 where나 what은 아무것도 뜻하지 않는 등록이 되기 때문이다.
    """
    if key not in table:
        return None, "없다"
    value = table[key]
    if not isinstance(value, str):
        return None, "글이어야 한다"
    if not value.strip():
        return None, "비어 있다"
    return value, None


def _parse_externals(items: list[dict], source: str, problems: list[Problem]) -> list[External]:
    """[[external]] 항목들을 읽는다. 꼴이 틀린 항목은 이유를 problems에 적고 결과에서 뺀다.

    모르는 키는 문제로 알리되 항목은 남긴다(필요한 키가 모두 맞으면 쓸모가 있고, 오타 하나로 면제가 통째로
    사라져 문제가 불어나는 것을 막으려는 것이다). 같은 (hash, where)를 두 번 등록하면 뒤의 것이 문제다.
    """
    externals: list[External] = []
    seen: dict[tuple[str, str], int] = {}
    for number, item in enumerate(items, 1):
        for key in item:
            if key not in EXTERNAL_KEYS:
                problems.append(_entry_problem("external", source, number, key, "모르는 키(오타일 수 있다)"))
        values: dict[str, str] = {}
        for key in EXTERNAL_KEYS:
            value, reason = _text_of(item, key)
            if value is not None and key == "hash" and not _EXTERNAL_HASH.fullmatch(value):
                value, reason = None, "7~40자 소문자 16진수가 아니다"
            if value is None:
                problems.append(_entry_problem("external", source, number, key, reason or ""))
            else:
                values[key] = value
        if len(values) != len(EXTERNAL_KEYS):
            continue
        pair = (values["hash"], values["where"])
        if pair in seen:
            reason = f"{seen[pair]}번째와 같은 hash·where를 또 등록했다"
            problems.append(_entry_problem("external", source, number, "hash·where", reason))
            continue
        seen[pair] = number
        externals.append(External(values["hash"], values["where"], values["what"], number))
    return externals


def load_registry(path: Path, display: str | None = None) -> Registry:
    """등록 파일(TOML)을 읽어 Registry로 돌려준다.

    display는 문제 줄에 쓸 등록 파일 이름이다(기본값은 path의 `/` 경로). 파일이 없거나 읽을 수 없으면
    OSError, TOML 문법이나 인코딩이 틀리면 ValueError(tomllib.TOMLDecodeError, UnicodeDecodeError), 모르는
    꼭대기 표가 있으면 RegistryError(ValueError)가 그대로 나간다. main이 모두 종료 코드 2로 바꾼다. 표 안의
    꼴 오류(모르는 키, 빠진 키, 빈 글, 16진수가 아닌 hash 등)는 던지지 않고 Registry.problems에 담는다.
    주석만 있는 파일은 빈 사전이라 빈 등록이다.
    """
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    source = display if display is not None else path.as_posix()
    unknown = [key for key in raw if key not in TOP_KEYS]
    if unknown:
        raise RegistryError(f"모르는 꼭대기 표나 키: {', '.join(unknown)} (받는 것: {', '.join(TOP_KEYS)})")
    problems: list[Problem] = []
    externals = _parse_externals(_tables(raw, "external", source, problems), source, problems)
    records = _tables(raw, "record", source, problems)
    pairs = _tables(raw, "pair", source, problems)
    return Registry(
        externals=tuple(externals),
        records=tuple(records),
        pairs=tuple(pairs),
        problems=tuple(problems),
        source=source,
    )


# ---------------------------------------------------------------------------------------------
# 낱말 뽑기
# ---------------------------------------------------------------------------------------------


def _follows_commit_word(text: str, start: int, line_start: int) -> bool:
    """text[start] 앞에 `커밋` 또는 `commit`이 (공백·탭·백틱·여는 괄호만 사이에 두고) 붙어 있는지.

    같은 줄 안에서만 본다(line_start는 그 줄이 시작하는 자리). commit 바로 앞 글자가 ASCII 영문자이면
    `recommit`처럼 다른 낱말의 일부라서 아니다. `commits`, `SHA-256`, 주소 안의 `/commit/`도 사이에 올 수
    없는 글자(s, -, /)가 끼어 있어 아니다. 낱말 앞의 긴 글을 통째로 훑지 않고 거꾸로 몇 글자만 본다(한 줄이
    아주 긴 파일에서도 선형 시간으로 끝나게 하려는 것이다).
    """
    i = start
    while i > line_start and text[i - 1] in _SEPARATORS:
        i -= 1
    for word in _COMMIT_WORDS:
        begin = i - len(word)
        if begin >= line_start and text[begin:i].lower() == word:
            before = text[begin - 1] if begin > line_start else ""
            if not (before.isascii() and before.isalpha()):
                return True
    return False


def _claimed(text: str, start: int, end: int, line_start: int) -> bool:
    """text[start:end]의 낱말을 문서가 커밋 참조로 적었는지(규칙 4가 말하는 두 꼴 가운데 하나인지)."""
    # 백틱 한 쌍 안이 통째로 그 낱말이다. 낱말 바로 앞뒤가 백틱일 때만 그 줄의 백틱 짝을 따져 본다(대부분의
    # 낱말은 그렇지 않으므로 줄을 매번 훑지 않는다). 이웃한 백틱이 서로 다른 쌍에 속하는 `x`1234abc`y`는
    # 짝을 맞춰 보면 낱말이 어느 쌍의 안쪽도 아니다.
    if start > line_start and text[start - 1] == "`" and text.startswith("`", end):
        line_end = text.find("\n", end)
        if line_end == -1:
            line_end = len(text)
        wanted = (start - line_start, end - line_start)
        if any(span.span(2) == wanted for span in _CODE_SPAN.finditer(text[line_start:line_end])):
            return True
    return _follows_commit_word(text, start, line_start)


def find_tokens(text: str) -> list[tuple[int, str, bool]]:
    """text에서 해시 꼴 낱말(규칙 2)을 모두 뽑아 (줄 번호, 낱말, 문서가 커밋 참조로 적었는가) 목록으로 돌려준다.

    줄 번호는 1부터 `\\n`으로 센다(줄 끝의 CR은 낱말 글자가 아니라 낱말을 막지 않는다). 셋째 값은 한 줄
    안에서만 보며, 어느 파일에서나 계산한다(규칙 4는 .md 파일에만 건다). 참이 되는 꼴은 둘이다.
      - 백틱 한 쌍 안이 통째로 그 낱말이다(백틱 안에 다른 글자가 함께 있으면 아니다).
      - `커밋` 또는 `commit`(대소문자 무시, 바로 앞 글자가 ASCII 영문자가 아닐 것) 뒤에 공백·탭·백틱·여는
        괄호만 0개 이상 두고 그 낱말이 온다.
    파일 전체에 정규식을 한 번 걸고 줄 번호는 지나온 줄바꿈만 이어서 센다(낱말이 수십만 개여도 한 번에
    끝낸다).

    a~f 글자가 하나도 없는 숫자뿐인 글자열(날짜, 크기, 숫자 꼬리)은 해시가 아닌 수일 수 있어서, 위 두 꼴로
    적은 것(셋째 값이 참인 것)만 낱말로 낸다. 그 밖의 숫자뿐인 글자열은 버린다. 참조라고 밝혀 적은 자리는
    앞 7자가 모두 숫자인 커밋의 줄임 해시도 봐야 해서 숫자뿐이어도 낱말로 본다. 숫자뿐인 글자열이 아주 많은
    파일에서도 느려지지 않도록, 바로 앞 글자가 참조 표시가 될 수 없는 것이면 줄 번호를 세기 전에 버린다.
    """
    found: list[tuple[int, str, bool]] = []
    line = 1
    line_start = 0
    counted_to = 0
    for match in _WORD.finditer(text):
        word = match.group()
        start, end = match.span()
        digits_only = word.isdigit()
        if digits_only and text[start - 1 : start] not in _CLAIM_PREFIX_CHARS:
            continue  # start가 0이면 빈 글이라 여기서도 걸러진다
        newlines = text.count("\n", counted_to, start)
        if newlines:
            line += newlines
            line_start = text.rfind("\n", counted_to, start) + 1
        counted_to = start
        claimed = _claimed(text, start, end, line_start)
        if digits_only and not claimed:
            continue
        found.append((line, word, claimed))
    return found


# ---------------------------------------------------------------------------------------------
# 이력으로 풀기와 판정
# ---------------------------------------------------------------------------------------------


def build_prefix_index(commits: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """커밋 해시들을 앞 7자를 키로 묶은 사전으로 만든다. 같은 앞 7자의 커밋은 해시 순으로 한 묶음이다."""
    grouped: dict[str, list[str]] = {}
    for commit in sorted(set(commits)):
        grouped.setdefault(commit[:PREFIX_LENGTH], []).append(commit)
    return {prefix: tuple(group) for prefix, group in grouped.items()}


def resolve(word: str, by_prefix: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """word로 시작하는 커밋 해시들. 0개면 풀리지 않음, 1개면 그 커밋, 2개 이상이면 모호다.

    word는 PREFIX_LENGTH(7)자 이상이어야 한다(낱말이 그렇다). 접두만 보고 가운데 글자는 보지 않는다.
    """
    return tuple(commit for commit in by_prefix.get(word[:PREFIX_LENGTH], ()) if commit.startswith(word))


def _short_list(commits: Sequence[str]) -> str:
    """문제 줄에 보일 커밋 목록: 앞 12자씩, 다섯 개까지."""
    shown = ", ".join(commit[:12] for commit in commits[:5])
    return shown + (" …" if len(commits) > 5 else "")


def judge_file(
    path: str,
    words: Sequence[tuple[int, str, bool]],
    *,
    by_prefix: Mapping[str, Sequence[str]],
    ancestors: Collection[str],
    registered: Collection[str] = frozenset(),
    registry_source: str = DEFAULT_REGISTRY,
) -> tuple[list[Problem], int]:
    """파일 하나의 낱말들(find_tokens의 결과)에 규칙 3·4를 걸어 (문제들, 센 출현 수)를 돌려준다.

    ancestors는 HEAD에서 닿는 커밋들, registered는 이 파일에 대해 [[external]]로 등록된 낱말들이다. 규칙은
    다음과 같다.
      - 이 저장소의 커밋으로 풀리거나 모호하면(어느 파일이든) 센다. 모호하거나 HEAD의 조상이 아니면 문제다.
      - 풀리지 않는데 .md 파일이고 문서가 커밋 참조로 적었으면 센다. 등록된 낱말이면 통과, 아니면 문제다.
      - 그 밖의 풀리지 않는 낱말은 세지 않고 문제도 아니다.
    """
    problems: list[Problem] = []
    counted = 0
    is_markdown = path.endswith(".md")
    for line, word, claimed in words:
        matches = resolve(word, by_prefix)
        if matches:
            counted += 1
            if len(matches) > 1:
                reason = f"커밋 둘 이상에 맞는다(모호): {_short_list(matches)}"
            elif matches[0] not in ancestors:
                reason = "이 저장소의 커밋이지만 HEAD의 조상이 아니다(다른 브랜치에만 있거나 이력에서 빠진 커밋일 수 있다)"
            else:
                continue
            problems.append(Problem("reference", path, f"{word}: {reason}", line=line))
        elif is_markdown and claimed:
            counted += 1
            if word not in registered:
                reason = (
                    "문서가 커밋 참조로 적었는데 이 저장소의 커밋으로 풀리지 않는다"
                    f" — 다른 저장소의 해시면 {registry_source}의 [[external]]에 등록한다"
                )
                problems.append(Problem("reference", path, f"{word}: {reason}", line=line))
    return problems, counted


# ---------------------------------------------------------------------------------------------
# git 읽기
# ---------------------------------------------------------------------------------------------


def _run(repo: Path, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    """repo에서 git 읽기 명령을 부른다. --no-optional-locks로 색인 잠금 파일을 만들지 않는다.

    종료 코드가 0이 아닌 것은 호출한 쪽이 판단한다(check=False). git 실행 파일이 없으면 CannotCheck다.
    출력은 바이트로 받는다(파일 내용과 경로를 글자 변환 없이 다루려는 것이다). 넘길 입력이 없으면 표준 입력을
    비워 둔다(DEVNULL): 부모의 터미널 입력을 물려받아 git이 입력을 기다리며 멈추는 일이 없게 하려는 것이다.
    """
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", "-C", str(repo), *args],
            input=stdin,
            stdin=None if stdin is not None else subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise CannotCheck(f"git을 실행할 수 없다: {type(error).__name__}: {error}") from error


def _first_line(data: bytes) -> str:
    """git이 표준 오류에 쓴 글의 첫 줄(없으면 빈 글)."""
    lines = data.decode("utf-8", errors="replace").strip().splitlines()
    return lines[0] if lines else ""


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    """_run과 같지만 종료 코드가 0이 아니면 CannotCheck다. 읽지 못한 것을 빈 결과로 넘기지 않는다."""
    done = _run(repo, *args, stdin=stdin)
    if done.returncode != 0:
        reason = _first_line(done.stderr)
        raise CannotCheck(
            f"git {args[0]} 실패(종료 코드 {done.returncode})" + (f": {reason}" if reason else "")
        )
    return done.stdout


def _require_history(repo: Path) -> None:
    """repo에서 이력을 믿고 읽을 수 있는지 확인한다. 아니면 이유를 담아 CannotCheck를 올린다.

    git 저장소가 아닌 폴더에서는 모든 질문이 실패하므로 먼저 확인하고, 얕은 복제는 이력이 모자라 풀리지 않는
    낱말이 늘어나므로(증거가 틀린 것처럼 보이게 된다) 검사하지 않는다. HEAD가 없으면 비교할 이력이 없다.
    """
    if not repo.is_dir():
        raise CannotCheck(f"저장소 폴더가 아니다: {repo}")
    done = _run(repo, "rev-parse", "--git-dir")
    if done.returncode != 0:
        reason = _first_line(done.stderr)
        raise CannotCheck(f"git 저장소가 아니다: {repo}" + (f": {reason}" if reason else ""))
    if _git(repo, "rev-parse", "--is-shallow-repository").decode("ascii").strip() == "true":
        raise CannotCheck(
            "얕은 복제라 이력이 모자라 낱말을 풀 수 없다. 전체 이력을 받은 뒤 다시 돌린다"
            "(git fetch --unshallow, CI 체크아웃은 fetch-depth: 0)"
        )
    if _run(repo, "rev-parse", "--verify", "--quiet", "HEAD^{commit}").returncode != 0:
        raise CannotCheck("HEAD가 없다(커밋이 하나도 없는 저장소)")


def _hashes(data: bytes) -> list[str]:
    """`git rev-list`의 출력(줄마다 해시 하나)을 해시 목록으로 읽는다."""
    return data.decode("ascii").split()


@dataclass(frozen=True)
class _Blob:
    """HEAD의 트리에 있는 일반 파일 하나."""

    path: str
    oid: str
    size: int


def _head_blobs(repo: Path) -> list[_Blob]:
    """HEAD의 트리에서 일반 파일(모드 100644·100755의 blob)을 모두 돌려준다.

    `--full-tree`라서 repo가 저장소 뿌리의 하위 폴더여도 저장소 전체를 본다. 기호 링크(120000)와
    서브모듈(160000)은 내용이 파일 글이 아니라서 건너뛴다. 색인(`git ls-files`)이 아니라 HEAD의 트리를 읽는
    까닭은 모듈 설명에 있다. -z라서 경로가 따옴표나 이스케이프 없이 UTF-8 그대로 온다.
    """
    raw = _git(repo, "ls-tree", "-r", "-l", "-z", "--full-tree", "HEAD")
    blobs: list[_Blob] = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        meta, tab, path = entry.partition(b"\t")
        fields = meta.split()
        if not tab or len(fields) != 4:
            raise CannotCheck("git ls-tree의 출력을 읽을 수 없다")
        mode, kind, oid, size = fields
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            continue
        blobs.append(_Blob(path.decode("utf-8", errors="replace"), oid.decode("ascii"), int(size)))
    return blobs


def _batches(sized: Sequence[tuple[str, int]]) -> Iterator[list[str]]:
    """(객체 해시, 크기) 목록을 MAX_BATCH_BYTES·MAX_BATCH_BLOBS를 넘지 않는 묶음으로 나눠 해시 목록을 낸다."""
    batch: list[str] = []
    total = 0
    for oid, size in sized:
        if batch and (total + size > MAX_BATCH_BYTES or len(batch) >= MAX_BATCH_BLOBS):
            yield batch
            batch, total = [], 0
        batch.append(oid)
        total += size
    if batch:
        yield batch


def _read_blobs(repo: Path, oids: Sequence[str]) -> Iterator[tuple[str, bytes]]:
    """`git cat-file --batch`로 블롭들의 내용을 한꺼번에 읽어 (객체 해시, 내용)을 차례로 낸다.

    출력은 객체마다 `<해시> blob <크기>\\n<내용>\\n`이다. 내용은 저장된 바이트 그대로다(줄바꿈 변환 없음).
    요청한 차례와 다르거나 객체가 없으면(`<해시> missing`) 읽지 못한 것이므로 CannotCheck다.
    """
    request = "".join(f"{oid}\n" for oid in oids).encode("ascii")
    out = _git(repo, "cat-file", "--batch", "--buffer", stdin=request)
    position = 0
    for oid in oids:
        newline = out.find(b"\n", position)
        header = out[position:newline].split() if newline >= 0 else []
        if len(header) != 3 or header[0] != oid.encode("ascii") or header[1] != b"blob":
            raise CannotCheck(f"git cat-file의 출력을 읽을 수 없다: {oid}")
        size = int(header[2])
        begin = newline + 1
        end = begin + size
        if end >= len(out) or out[end : end + 1] != b"\n":
            raise CannotCheck(f"git cat-file의 출력이 모자라다: {oid}")
        yield oid, out[begin:end]
        position = end + 1


# ---------------------------------------------------------------------------------------------
# 검사
# ---------------------------------------------------------------------------------------------


def _check_externals(
    registry: Registry,
    by_prefix: Mapping[str, Sequence[str]],
    tree_paths: Collection[str],
    scanned_paths: Collection[str],
    words_by_path: Mapping[str, Collection[str]],
) -> list[Problem]:
    """규칙 5: 등록한 항목이 아직 쓸모 있고 올바른지 본다.

    where는 HEAD의 트리에 있는 검사 대상 파일이어야 하고, 그 파일에 hash 낱말이 글자 그대로 있어야 한다
    (낡은 등록이 아니다). 그리고 그 낱말이 이 저장소의 커밋으로 풀리면 다른 저장소의 해시가 아니므로
    잘못 등록이다. 앞의 세 가지는 서로 배타적이고 마지막은 독립이다.
    """
    problems: list[Problem] = []
    source = registry.source
    for entry in registry.externals:
        if entry.where not in tree_paths:
            reason = f"{entry.where}: HEAD의 트리에 없다(저장소 뿌리 기준 / 경로로 적는다)"
            problems.append(_entry_problem("external", source, entry.number, "where", reason))
        elif entry.where not in scanned_paths:
            reason = f"{entry.where}: 검사 대상이 아닌 파일이다(잠금 파일이거나 글이 아니다)"
            problems.append(_entry_problem("external", source, entry.number, "where", reason))
        elif entry.hash not in words_by_path.get(entry.where, ()):
            if entry.hash.isdigit():
                # 숫자뿐인 값은 참조 표시가 달린 자리에서만 낱말로 뽑히므로, 표시 없이 적힌 값에 건 등록은 쓸모가 없다.
                reason = (
                    f"{entry.where}에 이 낱말이 없다(낡은 등록이거나, 숫자뿐인 값이라 그 파일에서 커밋 참조로 적힌 자리"
                    "(백틱 한 쌍 안, 또는 `커밋`·`commit` 바로 뒤)에 있지 않다)"
                )
            else:
                reason = f"{entry.where}에 이 낱말이 없다(낡은 등록이다)"
            problems.append(_entry_problem("external", source, entry.number, entry.hash, reason))
        matches = resolve(entry.hash, by_prefix)
        if matches:
            reason = (
                f"이 저장소의 커밋으로 풀린다({_short_list(matches)}): "
                "다른 저장소의 해시가 아니므로 잘못 등록이다. 등록을 지운다"
            )
            problems.append(_entry_problem("external", source, entry.number, entry.hash, reason))
    return problems


def _sort_key(problem: Problem) -> tuple[str, int, int, str, str]:
    """문제를 파일 경로, 줄 번호, 등록 항목 번호 순으로 정렬하는 키(실행마다 같은 순서)."""
    return (problem.path, problem.line, problem.order, problem.kind, problem.message)


def scan_references(repo: Path, registry: Registry) -> ReferenceReport:
    """repo의 HEAD를 읽어 규칙 3·4·5를 걸고 (정렬된 문제들, 센 출현 수)를 돌려준다. 읽기만 한다.

    registry.problems(등록 파일의 꼴 오류)도 문제에 싣는다. 검사를 시작하거나 끝낼 수 없으면(폴더나 git
    저장소가 아님, 얕은 복제, HEAD 없음, git 실패) 빈 결과를 돌려주지 않고 CannotCheck를 올린다.
    """
    _require_history(repo)
    ancestors = frozenset(_hashes(_git(repo, "rev-list", "HEAD")))
    everything = ancestors.union(_hashes(_git(repo, "rev-list", "--all")))
    by_prefix = build_prefix_index(everything)

    registered: dict[str, set[str]] = {}
    for entry in registry.externals:
        registered.setdefault(entry.where, set()).add(entry.hash)

    blobs = _head_blobs(repo)
    tree_paths = {blob.path for blob in blobs}
    # 같은 내용의 파일(같은 객체)은 한 번만 읽고 경로마다 판정한다. 잠금 파일은 읽지 않는다.
    paths_by_oid: dict[str, list[str]] = {}
    sizes: dict[str, int] = {}
    for blob in blobs:
        if blob.path.rsplit("/", 1)[-1] in SKIPPED_NAMES:
            continue
        paths_by_oid.setdefault(blob.oid, []).append(blob.path)
        sizes[blob.oid] = blob.size

    problems: list[Problem] = list(registry.problems)
    references = 0
    scanned_paths: set[str] = set()
    words_by_path: dict[str, set[str]] = {}
    for oids in _batches(list(sizes.items())):
        for oid, data in _read_blobs(repo, oids):
            if b"\0" in data:
                continue  # 글이 아닌 파일
            # UTF-8이 아닌 바이트는 대체 글자로 바꾼다. 낱말은 ASCII뿐이고 깨진 바이트는 낱말 글자가 아닌
            # 글자가 되므로 낱말이 생기거나 쪼개지지 않는다(원래도 ASCII가 아닌 바이트는 낱말 경계였다).
            words = find_tokens(data.decode("utf-8", errors="replace"))
            for path in paths_by_oid[oid]:
                scanned_paths.add(path)
                if path in registered:
                    words_by_path[path] = {word for _, word, _ in words}
                found, counted = judge_file(
                    path,
                    words,
                    by_prefix=by_prefix,
                    ancestors=ancestors,
                    registered=registered.get(path, frozenset()),
                    registry_source=registry.source,
                )
                problems += found
                references += counted
    problems += _check_externals(registry, by_prefix, tree_paths, scanned_paths, words_by_path)
    return ReferenceReport(problems=tuple(sorted(problems, key=_sort_key)), references=references)


def check_references(repo: Path, registry: Registry) -> list[Problem]:
    """repo의 HEAD에 적힌 커밋 해시 참조를 검사하고 문제를 정렬해 돌려준다. 통과면 빈 목록. 읽기만 한다.

    scan_references와 같고 센 출현 수는 돌려주지 않는다. 검사를 시작하거나 끝낼 수 없으면 CannotCheck다.
    """
    return list(scan_references(repo, registry).problems)


# ---------------------------------------------------------------------------------------------
# 명령줄
# ---------------------------------------------------------------------------------------------


def _use_utf8_output() -> None:
    """표준 출력·오류를 UTF-8로 다시 연다. 인코딩할 수 없는 글자는 \\uXXXX로 바꿔 죽지 않게 한다.

    한국어 Windows(코드 페이지 949)의 파이썬은 출력이 파이프나 파일이면 cp949로 써서 한글 출력이 깨지고,
    cp949에 없는 글자가 파일 이름에 있으면 UnicodeEncodeError로 죽는다. Linux CI는 이미 UTF-8이라 바뀌는
    것이 없다.

    모듈을 가져올 때가 아니라 main이 시작할 때 한다: 시험이 출력을 가로채는 중에 import만으로 표준
    출력을 바꾸지 않으려는 것이다. reconfigure가 없는 스트림(가로채기용 객체)이거나 이미 닫혔으면 건너뛴다.
    출력 인코딩은 보조 수단이라 실패해도 검사 자체를 막지 않는다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            continue


def _display_path(path: Path, repo: Path) -> str:
    """등록 파일 이름을 문제 줄에 쓸 꼴로 만든다. 저장소 안이면 뿌리 기준 `/` 경로, 밖이면 받은 경로 그대로."""
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def _build_parser() -> argparse.ArgumentParser:
    """명령줄 인자 해석기. 도움말은 한국어다."""
    parser = argparse.ArgumentParser(
        prog="check_evidence.py",
        add_help=False,  # 기본 -h 설명이 영어라서 아래에서 한국어 설명으로 직접 더한다
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "문서와 코드에 적힌 커밋 해시 참조가 이 저장소의 이력과 맞는지 본다.\n"
            "\n"
            "HEAD의 추적 파일에서 7~40자 소문자 16진수 낱말을 뽑아 이 저장소의 커밋으로 풀어 보고, 아래\n"
            "규칙 다섯으로 문제를 알린다.\n"
            "  1. 대상은 HEAD의 추적 파일이다. uv.lock·package-lock.json과 글이 아닌 파일(널 바이트가 든\n"
            "     파일)은 뺀다. 작업 트리가 아니라 HEAD의 내용을 읽는다.\n"
            "  2. 낱말은 7~40자 소문자 16진수다. a~f 글자가 하나도 없는 숫자뿐인 것은 규칙 4의 두 꼴로 적은\n"
            "     자리에 있을 때만 낱말로 본다(날짜나 숫자 꼬리를 해시로 잘못 읽지 않으려는 것이고, 참조라고\n"
            "     밝혀 적은 자리는 앞 7자가 모두 숫자인 커밋의 줄임 해시도 봐야 해서다). 앞뒤가 영문자·숫자·\n"
            "     밑줄이 아니어야 한다(뒤에 한글 조사가 붙어도 뽑는다).\n"
            "  3. (모든 대상 파일) 이 저장소의 커밋 하나로 풀리는 낱말은 그 커밋이 HEAD의 조상이어야 한다.\n"
            "     커밋 둘 이상에 맞으면 모호해서 문제다. 어떤 커밋으로도 풀리지 않는 낱말은 이 규칙에서는\n"
            "     문제가 아니다.\n"
            "  4. (.md 파일) 문서가 커밋 참조로 적은 낱말(같은 줄에서 백틱 한 쌍 안이 통째로 그 낱말이거나,\n"
            "     `커밋`·`commit` 바로 뒤에 온 낱말)은 반드시 풀려야 한다. 풀리지 않으면 문제다. 등록 파일의\n"
            "     [[external]]에 그 파일과 그 낱말이 등록돼 있으면 통과한다.\n"
            "  5. [[external]]이 가리키는 낱말이 그 파일에 더는 없으면(낡은 등록), 또는 그 낱말이 이\n"
            "     저장소의 커밋으로 풀리면(잘못 등록) 문제다.\n"
            "\n"
            "이 도구는 읽기만 한다. 등록 파일과 저장소의 어떤 파일도 고치지 않는다."
        ),
        epilog=(
            "등록 파일의 표: [[external]](hash, where, what)은 다른 저장소의 해시를 문서가 커밋 참조처럼 적은\n"
            "곳 하나를 그 파일에서만 통하게 등록한다. [[record]]·[[pair]]는 표의 배열인지만 본다.\n"
            "\n"
            "출력: 문제마다 한 줄 `<종류> <파일>:<줄>: <낱말>: <이유>`(종류는 reference, external, record,\n"
            "pair), 끝 줄 `참조 N개, 기록 값 R개, 짝 P개, 문제 M개`. --report-only를 주면 그 뒤에 `보고만`\n"
            "줄이 붙는다.\n"
            "\n"
            "종료 코드: 0 = 문제 없음(--report-only면 문제가 있어도 0), 1 = 문제 있음, 2 = 검사를 시작하거나\n"
            "끝낼 수 없음(등록 파일이 없거나 읽을 수 없음, TOML 문법 오류, 모르는 꼭대기 표, 저장소 폴더가\n"
            "아니거나 git 저장소가 아님, git 실행 불가나 읽기 실패, 얕은 복제, HEAD 없음). --report-only여도\n"
            "2는 2다. 통과 여부는 끝 줄 글자가 아니라 종료 코드로 판정한다.\n"
            "\n"
            "이력이 모자라면 풀리지 않는 낱말이 늘어 증거가 틀린 것처럼 보이므로 전체 이력이 필요하다\n"
            "(얕은 복제에서는 git fetch --unshallow, CI 체크아웃은 fetch-depth: 0).\n"
            "\n"
            "예: uv run --no-project tools/check_evidence.py\n"
            "    uv run --no-project tools/check_evidence.py --report-only"
        ),
    )
    parser.add_argument("-h", "--help", action="help", help="이 도움말을 보여 주고 끝낸다")
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        metavar="<저장소>",
        help="검사할 git 저장소 뿌리 (기본값: 이 파일에서 두 단계 위 폴더)",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        metavar="<toml>",
        help="등록 파일 (기본값: <저장소>/tools/evidence.toml). 검사 대상과 달리 작업 트리의 파일을 읽는다",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help=(
            "문제가 있어도 종료 코드를 0으로 끝내고 끝에 한 줄을 더한다. 문제를 모아 보기만 할 때 쓴다. "
            "검사를 시작하거나 끝낼 수 없는 경우(종료 코드 2)는 이 옵션으로도 바뀌지 않는다"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """등록 파일을 읽어 HEAD의 해시 참조를 검사하고 문제를 출력한다. 종료 코드는 0(통과), 1(문제), 2(시작·완료 불가)."""
    _use_utf8_output()
    args = _build_parser().parse_args(argv)
    repo = args.repo if args.repo is not None else DEFAULT_REPO
    registry_path = args.registry if args.registry is not None else repo / DEFAULT_REGISTRY
    try:
        registry = load_registry(registry_path, display=_display_path(registry_path, repo))
    except (OSError, ValueError) as error:
        # ValueError에는 tomllib.TOMLDecodeError(문법 오류), UnicodeDecodeError(UTF-8이 아님), RegistryError가 든다.
        print(f"등록 파일을 읽을 수 없다: {registry_path}: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    try:
        report = scan_references(repo, registry)
    except CannotCheck as error:
        print(f"검사를 시작하거나 끝낼 수 없다: {error}", file=sys.stderr)
        return 2
    for problem in report.problems:
        print(problem)
    # 기록 값과 짝은 이 도구가 아직 검사하지 않으므로 세지 않는다(늘 0).
    print(f"참조 {report.references}개, 기록 값 0개, 짝 0개, 문제 {len(report.problems)}개")
    if args.report_only:
        print("보고만: 문제가 있어도 종료 코드는 0이다")
        return 0
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
