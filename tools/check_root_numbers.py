# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""루트 문서에 옮겨 적은 수치가 구성 요소 기록 글자와 같은지 대조하는 검사 도구.

왜 있나
    첫 화면(README.md)과 docs/ 문서는 구성 요소 README에 기록된 대표 수치를 옮겨 적는다. 옮겨 적은 수는
    출처가 바뀌어도 저절로 따라 바뀌지 않으므로 한쪽만 고치면 첫 화면이 조용히 틀린 수를 말하게 된다.
    이 도구는 "이 수는 저 파일의 저 자리에서 왔다"를 선언 파일(기본값 root-numbers.toml)에 글자로 묶어 두고,
    실행할 때마다 두 쪽이 여전히 같은 수를 말하는지 다시 본다. 수를 계산하지는 않는다. 기록에 적힌 글자와
    루트 문서에 적힌 글자가 같은지만 본다. 반올림이나 부동소수 표기 차이가 끼어들지 않도록 비교는 모두
    정규화한 글자로 한다.

선언 파일(TOML)의 표 세 가지
    모르는 표는 읽는 단계에서 멈추고(DeclarationError), 표 안의 모르는 키·빠진 키·빈 글·꼴 오류는 그 선언의
    문제로 알린다. 오타 때문에 선언이 조용히 빠지거나 검사가 느슨해지는 일을 막으려는 것이다.

    [[number]]   구성 요소 기록에서 옮겨 온 수.
        where, section(선택)   루트 쪽 파일(저장소 뿌리 기준 상대 경로, '..'와 역슬래시 금지)과 그 파일의
                               제목 글('#' 없이). section을 주면 그 제목 아래 본문(같은 수준 이상의 다음
                               제목 전까지)만 본다. 코드 울타리 안의 '#' 줄은 제목이 아니다. 제목이 0개나
                               2개 이상이면 문제다.
        context                그 범위에 정확히 한 번 나오는 한 줄 글. 마지막 수가 value여야 하고, 그 수는
                               문서에 적힌 수 전체여야 한다(아래 '수 경계').
        condition              context가 든 같은 줄에 있어야 하는 조건 글. 수치에는 어떤 데이터·설정에서 잰
                               값인지 조건을 붙여 읽게 하려는 것이다.
        source, source_section(선택), source_context
                               구성 요소 기록 파일 쪽의 같은 검사(정확히 한 번, 마지막 수가 value이고 수 경계도
                               같다).
        value                  쉼표 없이 적은 수 글자(`-?\\d+(\\.\\d+)?`). 글의 "2,160"은 "2160"으로 적는다.
    [[snapshot]] 구성 요소 기록 파일에 없는 수(예: CI에서 센 테스트 수).
        where, section, context, value
                               위와 같다. 다만 section은 필수이고 source 쪽 검사는 없다.
        as_of                  YYYY-MM-DD. 그 수가 어느 시점의 수인지를 뜻한다(CI에서 센 수는 실행한 날, 날짜로 닫은
                               범위를 센 수는 그 범위의 끝 날). 그 절 본문에 이 날짜 글이 있어야 한다(어느 시점의
                               수인지 글에 남기려고).
        evidence               근거 한 줄(어느 실행의 어느 작업에서 셌는지). 비어 있으면 안 된다.
    [[coverage]] 선언 없이 끼어든 수를 잡는다.
        where, section(선택)   이 범위(section이 없으면 파일 전체)에서 '%'나 '%p'가 바로(공백 하나까지)
                               뒤따르는 수는 모두 같은 where의 number·snapshot 선언이 가리키는 context
                               자리 안에 있어야 한다. 수 전체(부호 포함)가 그 자리 안에 들어야 덮인 것으로
                               본다. 코드 울타리와 인라인 코드 안의 수도 센다. 선언의 section은 달라도 된다
                               (파일 전체 coverage 하나와 절마다 section을 준 선언을 함께 쓸 수 있다).

수 경계 (context와 source_context의 마지막 수)
    context가 문서에 적힌 수의 일부만 담으면, 한 번 나오고 마지막 수가 value와 같아 보여도 통과시키지 않는다.
    문서에는 1.96이라고 적혀 있는데 context가 1.9에서 끝나거나, 문서에는 -2.0이라고 적혀 있는데 context가 부호를
    빼고 2.0부터 시작하면 'not a whole number in the document' 문제로 알린다. 그러니 마지막 수는 이어지는 소수점
    아래와 천 단위 쉼표 부분, 빼기 부호(ASCII 하이픈과 U+2212)까지 context에 담아야 한다. 더하기 부호는 있어도
    없어도 같은 수로 본다(정규화한 글자가 같다). 루트 쪽 context와 기록 쪽 source_context에 똑같이 적용한다.

수 읽기와 제목 나누기 규칙은 call-summary/src/call_summary/compare.py의 같은 일을 하는 코드를 복제했다. 같은
꼴의 글(표와 문장 속 수, 마크다운 제목)을 같은 방법으로 읽으려는 것이다. 수를 읽는 정규식(_NUMBER)과 제목
정규식(_HEADING)은 그 코드와 글자까지 같고, number_tokens는 같은 규칙이다(정규화를 _token으로 나눠 두었다).
절 본문을 자르는 section_body도 같은 방법이되, 코드 울타리를 여닫는 판정은 더 엄밀하다(fence_mask): 닫는 줄은
열 때와 같은 글자를 열 때 이상 길게 쓰고 뒤에 공백만 올 수 있으며, 줄 머리에서 인라인 코드를 쓴 줄은 울타리로
읽지 않는다. compare.py는 줄이 세 글자(백틱이나 물결표)로 시작하면 열고, 열 때와 같은 세 글자로 시작하는 줄에서
닫는다. 이 도구는 의존성 없는 한 장짜리 스크립트라 어느 구성 요소의 코드나 환경도 가져오지 않는다(구성 요소의
환경을 건드리지 않으려고). 그래서 규칙을 가져다 쓰는 대신 복제했고, 복제한 자리마다 출처 줄을 적었다.
tools/tests/test_check_root_numbers.py의 test_number_tokens_follow_the_call_summary_rule과
test_number_tokens_skip_names_and_read_signs_like_call_summary가 수 읽기의 같은 예를,
test_code_fence_hash_lines_are_not_headings가 울타리 규칙의 차이를 고정한다. 규칙을 바꿀 때는 두 쪽을 함께 본다.

종료 코드와 출력
    0 = 모두 통과, 1 = 선언 문제나 불일치, 2 = 선언 파일을 읽을 수 없음(없음, TOML 문법 오류, 모르는 표).
    문제는 한 줄에 하나씩 `<where>[<section>] <context 앞 40자>: <문제>`로 쓰고, 마지막 줄은
    `선언 N개, 문제 M개`다(N은 [[number]], [[snapshot]], [[coverage]] 선언을 모두 더한 수). 판정은 끝 줄 글자가
    아니라 종료 코드로 한다.

실행
    uv run --no-project tools/check_root_numbers.py [--repo <저장소>] [--numbers <toml>]

이 도구는 읽기만 한다. 선언 파일이나 문서를 고치지 않는다.
"""

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath

# 이 파일은 <저장소>/tools/check_root_numbers.py에 있다. parents[0] = tools, parents[1] = 저장소 뿌리.
DEFAULT_REPO = Path(__file__).resolve().parents[1]
DEFAULT_NUMBERS_FILE = "root-numbers.toml"

# 선언 표마다 받는 키. 여기에 없는 키는 오타일 가능성이 커서 조용히 무시하지 않고 문제로 알린다.
NUMBER_REQUIRED = ("where", "context", "condition", "source", "source_context", "value")
NUMBER_OPTIONAL = ("section", "source_section")
SNAPSHOT_REQUIRED = ("where", "section", "context", "value", "as_of", "evidence")
SNAPSHOT_OPTIONAL = ()
COVERAGE_REQUIRED = ("where",)
COVERAGE_OPTIONAL = ("section",)

# [복제] 아래 _NUMBER, _HEADING과 number_tokens는 call-summary/src/call_summary/compare.py의
# _NUMBER(213-215행), _HEADING(218행), number_tokens(221행)와 같은 규칙이다(이 파일 머리말 참고).
#
# 글 속의 숫자 하나. 앞에 부호(ASCII 하이픈, 유니코드 빼기 U+2212, 더하기)가 붙을 수 있고 천 단위 쉼표와
# 소수점을 받는다. 영문자·숫자·밑줄·점 바로 뒤의 숫자(모델 이름 "Qwen3"·"q8_0", 판 "v2")와 영문자·숫자
# 바로 앞의 숫자("4B", "14B", "1.5b")는 값이 아니라 이름의 일부라 읽지 않는다. 뒤의 "\.\d" 막기는 "1.5b"가
# 되돌아가 "1"만 숫자로 잡히는 것을 막는다. 한글은 막지 않는다: "49.5이고"처럼 한국어 문장에서는 조사가
# 숫자에 바로 붙는다.
_NUMBER = re.compile(
    r"(?<![0-9A-Za-z_.])([+\-\u2212]?)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![0-9A-Za-z]|\.\d)"
)
# Markdown 제목 줄(# 1~6개 + 공백 + 제목, 끝의 닫는 #은 뺀다). 코드 울타리 안의 줄은 제목이 아니다.
_HEADING = re.compile(r"(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")

# 코드 울타리를 여는·닫는 줄 후보. 들여쓰기는 몇 칸이든 받는다(목록 안에서 들여쓴 울타리가 있다).
# 같은 글자(` 또는 ~) 세 개 이상이 이어진 다음에 나머지 글(정보 글)이 온다.
_FENCE = re.compile(r"[ \t]*(`{3,}|~{3,})(.*)")
# 수 바로 뒤의 퍼센트: 공백은 하나까지 받고, 뒤따르는 p는 "%p"(퍼센트포인트) 꼴을 같이 잡으려는 것이다.
_PERCENT_TAIL = re.compile(r" ?%p?")
# value는 쉼표 없는 수 글자, as_of는 YYYY-MM-DD 꼴. \d가 다른 나라 숫자까지 받지 않도록 ASCII로 한정한다.
_VALUE = re.compile(r"-?\d+(\.\d+)?", re.ASCII)
_AS_OF = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)


class DeclarationError(ValueError):
    """선언 파일을 해석할 수 없을 때(모르는 꼭대기 표, 표가 [[이름]] 배열이 아님 등).

    main은 이를 종료 코드 2로 바꾼다. 선언 하나의 꼴 오류(Problem)와 달리 파일 전체를 믿을 수 없다는 뜻이다.
    """


@dataclass
class Declarations:
    """선언 파일에서 읽은 선언들. 각 항목은 TOML 표 하나를 그대로 담은 dict다."""

    numbers: list[dict] = field(default_factory=list)  # [[number]]
    snapshots: list[dict] = field(default_factory=list)  # [[snapshot]]
    coverage: list[dict] = field(default_factory=list)  # [[coverage]]


@dataclass
class Problem:
    """검사가 찾은 문제 하나.

    where, section, context: 문제가 난 선언을 가리킨다(선언에 없거나 글이 아니면 where는 "?", 나머지는 비움).
    message: 무엇이 어긋났는지. 한 줄이다.
    """

    where: str
    section: str | None
    context: str
    message: str

    def __str__(self) -> str:
        """`<where>[<section>] <context 앞 40자>: <문제>` 한 줄. context가 비면 그 칸을 뺀다."""
        head = self.where + (f"[{self.section}]" if self.section else "")
        snippet = re.sub(r"[\r\n]", " ", self.context[:40])
        return f"{head} {snippet}: {self.message}" if snippet else f"{head}: {self.message}"


def _token(match: re.Match) -> str:
    """_NUMBER 일치 하나를 정규화한 글로 바꾼다: 빼기 기호는 "-", 더하기 기호와 천 단위 쉼표는 없앰,
    0의 부호는 뺌("−0.0" → "0.0"). 소수 자리 수는 글에 적힌 그대로 둔다("0"과 "0.0"은 다르다)."""
    digits = match.group(2).replace(",", "")
    negative = match.group(1) in ("-", "\u2212") and float(digits) != 0
    return ("-" if negative else "") + digits


def number_tokens(text: str) -> list[str]:
    """글 속 숫자들을 나온 순서대로 정규화한 글로 돌려준다(규칙은 _token과 같다).

    call-summary/src/call_summary/compare.py:221의 number_tokens와 같은 규칙이다.
    """
    return [_token(m) for m in _NUMBER.finditer(text)]


def fence_mask(text: str) -> list[bool]:
    """줄마다 코드 울타리 안이면 True인 목록을 돌려준다(줄 나누기는 text.splitlines()와 같아 길이가 같다).

    울타리를 여는 줄, 안쪽 줄, 닫는 줄이 모두 True다. 울타리는 같은 글자(` 또는 ~) 세 개 이상으로 열고,
    닫는 줄은 같은 글자를 열 때보다 짧지 않게 쓰며 그 뒤에 공백만 있어야 한다(CommonMark의 닫는 울타리
    규칙). 그래서 백틱 4개로 연 울타리 속의 백틱 3개짜리 줄은 닫지 못한다. 백틱 울타리의 정보 글에 백틱이
    들면(```코드``` 처럼 줄 앞머리에서 인라인 코드를 쓴 줄) 울타리가 아니다. 닫히지 않은 울타리는 글 끝까지
    이어진다. 들여쓰기는 몇 칸이든 받는다(목록 안에 들여쓴 울타리가 있어서, 3칸까지만 받는 CommonMark보다
    느슨하다).

    section_body가 코드 속 '# 주석' 줄을 제목으로 읽지 않으려고 쓴다. 같은 tools 폴더의 다른 도구(링크
    검사 등)도 울타리 안의 글을 건너뛸 때 이 함수를 가져다 쓸 수 있게 공개 함수로 둔다. 울타리 해석을 한
    벌만 두려는 것이다. call-summary의 같은 일(compare.py:307의 _section_body)은 닫는 줄을 "같은 글자 세
    개로 시작하는 줄"로 단순하게 읽는데, 이 함수는 그 규칙과 보통의 글에서 같은 답을 내고 위 두 경우만 더
    정확히 가른다.
    """
    mask: list[bool] = []
    opener: tuple[str, int] | None = None  # 열려 있는 울타리의 (글자, 길이). 닫혀 있으면 None.
    for line in text.splitlines():
        found = _FENCE.match(line)
        run = found.group(1) if found else ""
        rest = found.group(2) if found else ""
        if opener is not None:
            mask.append(True)
            if run and run[0] == opener[0] and len(run) >= opener[1] and not rest.strip():
                opener = None
        elif run and not (run[0] == "`" and "`" in rest):
            mask.append(True)
            opener = (run[0], len(run))
        else:
            mask.append(False)
    return mask


def _section_lines(text: str, section: str) -> tuple[list[str], int, int, int]:
    """section 제목의 본문이 차지하는 줄 범위를 찾는다. (줄 목록, 본문 첫 줄, 본문 끝 줄(미포함), 제목 수).

    본문은 그 제목 다음 줄부터 같은 수준 이상(# 개수가 같거나 적은)의 다음 제목 전까지다. 코드 울타리 안의
    줄은 제목 후보가 아니다. 제목이 정확히 하나가 아니면 범위는 의미가 없고 제목 수만 쓴다.
    """
    lines = text.splitlines()
    mask = fence_mask(text)
    heads: list[tuple[int, int, str]] = []  # (줄 번호, 수준, 제목 글)
    for i, line in enumerate(lines):
        if mask[i]:
            continue
        if m := _HEADING.match(line):
            heads.append((i, len(m.group(1)), m.group(2)))
    hits = [h for h in heads if h[2] == section]
    if len(hits) != 1:
        return lines, 0, 0, len(hits)
    start, level, _ = hits[0]
    end = next((i for i, lv, _ in heads if i > start and lv <= level), len(lines))
    return lines, start + 1, end, 1


def section_body(text: str, section: str | None) -> tuple[str | None, int]:
    """section 제목 아래의 글(다음 같은 수준 이상의 제목 전까지)과 그 제목이 나온 수를 돌려준다.

    section이 None이면 파일 전체와 1이다. 제목이 없거나 둘 이상이면 (None, 나온 수)다. 줄은 "\\n"으로 다시
    이어 붙인다. call-summary/src/call_summary/compare.py:307의 _section_body와 같은 규칙이다(울타리 해석은
    fence_mask 참고).
    """
    if section is None:
        return "\n".join(text.splitlines()), 1
    lines, first, last, hits = _section_lines(text, section)
    if hits != 1:
        return None, hits
    return "\n".join(lines[first:last]), 1


def _section_span(text: str, section: str | None) -> tuple[tuple[int, int] | None, int]:
    """section_body와 같은 범위를 text 안의 글자 위치 (시작, 끝)으로 돌려준다. 제목이 정확히 하나가 아니면
    (None, 제목 수).

    context가 파일 안 어디에 있는지(coverage가 자리를 비교한다)까지 알아야 해서 본문 글 대신 위치로 다룬다.
    """
    if section is None:
        return (0, len(text)), 1
    _, first, last, hits = _section_lines(text, section)
    if hits != 1:
        return None, hits
    starts = [0]  # 줄마다 시작 위치. 마지막 항목은 글 끝이다.
    for chunk in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(chunk))
    return (starts[first], starts[last]), 1


def load_declarations(path: Path) -> Declarations:
    """선언 파일(TOML)을 읽어 Declarations로 돌려준다.

    표는 [[number]], [[snapshot]], [[coverage]] 세 가지뿐이다. 다른 꼭대기 표가 있으면(오타 등) 그 표의 선언이
    조용히 빠지지 않도록 DeclarationError로 멈춘다. 파일을 못 읽거나 TOML 문법이 틀리면 OSError나
    tomllib.TOMLDecodeError가 그대로 나온다(main이 모두 종료 코드 2로 바꾼다).
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)
    extra = sorted(set(data) - {"number", "snapshot", "coverage"})
    if extra:
        raise DeclarationError(
            f"unknown top-level table(s) {', '.join(extra)}; declarations are [[number]], [[snapshot]] "
            "and [[coverage]]"
        )
    tables: dict[str, list[dict]] = {}
    for name in ("number", "snapshot", "coverage"):
        items = data.get(name, [])
        if not isinstance(items, list) or not all(isinstance(d, dict) for d in items):
            raise DeclarationError(f"'{name}' must be an array of tables ([[{name}]])")
        tables[name] = items
    return Declarations(tables["number"], tables["snapshot"], tables["coverage"])


def _path_problem(rel: str) -> str | None:
    """루트 쪽·기록 쪽 파일 경로가 저장소 뿌리 기준 상대 경로 꼴인지 본다. 어긋나면 이유 글, 아니면 None.

    역슬래시는 Windows에서만 풀리고 CI(Linux)에서는 깨지므로 막고, 절대 경로·드라이브 꼴·'..'는 저장소 밖을
    읽게 되므로 막는다.
    """
    if "\\" in rel:
        return "must use '/' separators, not backslashes"
    posix = PurePosixPath(rel)
    if posix.is_absolute() or PureWindowsPath(rel).drive:
        return "must be a path relative to the repository root"
    if ".." in posix.parts:
        return "must not contain '..'"
    return None


def _real_date(text: str) -> bool:
    """YYYY-MM-DD 꼴이고 달력에 있는 날짜인지(2026-13-45 같은 글은 아님)."""
    if not _AS_OF.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _form_problems(decl: dict, required: tuple[str, ...], optional: tuple[str, ...]) -> list[str]:
    """선언 하나의 꼴을 검사한다(대조 전에): 빠진 키, 모르는 키, 비었거나 글이 아닌 값, 키별 꼴.

    하나라도 있으면 그 선언은 대조하지 않고 이 문제들만 알린다(꼴이 틀린 선언으로 대조하면 엉뚱한 문제가
    따라 나오기 때문이다).
    """
    problems = []
    missing = [key for key in required if key not in decl]
    unknown = sorted(set(decl) - set(required) - set(optional))
    if missing:
        problems.append(f"missing key(s): {', '.join(missing)}")
    if unknown:
        problems.append(f"unknown key(s): {', '.join(unknown)}")
    for key in (*required, *optional):
        if key not in decl:
            continue
        value = decl[key]
        if not (isinstance(value, str) and value.strip()):
            problems.append(f"{key} must be a non-empty string")
        elif key in ("where", "source") and (reason := _path_problem(value)):
            problems.append(f"{key} {reason}")
        elif key in ("context", "source_context", "condition") and ("\n" in value or "\r" in value):
            problems.append(f"{key} must be a single line")
        elif key == "value" and not _VALUE.fullmatch(value):
            problems.append(
                f'value must be a number written without thousands separators, such as "1.96" or "-2.0" '
                f"(got {value!r})"
            )
        elif key == "as_of" and not _real_date(value):
            problems.append(f"as_of must be a real date written YYYY-MM-DD (got {value!r})")
    return problems


class _Docs:
    """저장소 안 문서를 한 번만 읽어 두는 캐시. 읽지 못한 파일은 (None, 이유 글)로 기억한다.

    UTF-8로 읽고, 줄바꿈은 읽으면서 "\\n"으로 통일된다. 앞의 BOM(U+FEFF)은 버린다(utf-8-sig): 첫 줄이 제목인
    문서에서 BOM이 제목 앞 글자로 남아 그 제목이 제목으로 읽히지 않는 일을 막으려는 것이다.
    """

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self._cache: dict[str, tuple[str | None, str | None]] = {}

    def read(self, rel: str) -> tuple[str | None, str | None]:
        if rel not in self._cache:
            try:
                self._cache[rel] = ((self.repo / rel).read_text(encoding="utf-8-sig"), None)
            except (OSError, UnicodeDecodeError) as e:
                self._cache[rel] = (None, f"cannot read {rel}: {type(e).__name__}: {_reason(e)}")
        return self._cache[rel]


def _reason(error: Exception) -> str:
    """오류에서 이유 글만 뽑는다. OSError의 기본 글에는 절대 경로가 들어 있어 strerror만 쓴다."""
    return getattr(error, "strerror", None) or str(error)


@dataclass
class _Located:
    """파일 안에서 context를 찾은 결과.

    text: 파일 글(못 읽었으면 None).
    scope: 절 본문(section이 없으면 파일 전체)의 글자 범위(절을 못 찾았으면 None).
    pos: context가 정확히 한 번 나온 자리(아니면 None).
    problems: 찾는 중에 알게 된 문제 글.
    """

    text: str | None = None
    scope: tuple[int, int] | None = None
    pos: int | None = None
    problems: list[str] = field(default_factory=list)


def _find_all(haystack: str, needle: str) -> list[int]:
    """needle이 나오는 자리를 모두 찾는다. 겹치는 자리도 센다("정확히 한 번"을 느슨하게 세지 않으려고)."""
    found = []
    i = haystack.find(needle)
    while i != -1:
        found.append(i)
        i = haystack.find(needle, i + 1)
    return found


def _line_around(text: str, start: int, end: int | None = None) -> tuple[int, str]:
    """text에서 start 자리가 든 줄을 찾아 (줄이 시작하는 위치, 줄 글)을 돌려준다.

    줄은 "\\n"으로 나뉜다(_Docs.read가 읽으면서 줄바꿈을 "\\n"으로 통일한다). 줄 끝은 end 자리(주지 않으면
    start) 뒤의 첫 "\\n"이고, 그런 줄바꿈이 없으면 글 끝까지다(줄바꿈 없이 끝나는 글의 마지막 줄). 돌려주는 줄
    글에는 줄바꿈이 들지 않는다. start와 end는 같은 줄에 있다고 본다: 수와 context는 한 줄 안에 있다.
    """
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", start if end is None else end)
    return line_start, text[line_start : len(text) if line_end == -1 else line_end]


def _locate(
    docs: _Docs,
    rel: str,
    section: str | None,
    context: str,
    section_key: str,
    context_key: str,
    role: str = "",
) -> _Located:
    """rel 파일의 section 본문에서 context를 찾는다. section_key·context_key는 문제 글에 쓸 선언 키 이름
    (루트 쪽은 "section"·"context", 기록 쪽은 "source_section"·"source_context")이고, role은 읽기 실패 글 뒤에
    붙일 말이다."""
    loc = _Located()
    text, error = docs.read(rel)
    if text is None:
        loc.problems.append(f"{error}{role}")
        return loc
    loc.text = text
    scope, hits = _section_span(text, section)
    if scope is None:
        loc.problems.append(f"{section_key} {section!r} found {hits} times in {rel} (must be exactly once)")
        return loc
    loc.scope = scope
    found = _find_all(text[scope[0] : scope[1]], context)
    if len(found) != 1:
        place = rel + (f" section {section!r}" if section else "")
        loc.problems.append(f"{context_key} found {len(found)} times in {place} (must be exactly once)")
        return loc
    loc.pos = scope[0] + found[0]
    return loc


def _value_problems(context_key: str, context: str, value: str) -> list[str]:
    """context의 마지막 수가 선언한 value와 같은 글자인지 본다(선언만으로 알 수 있는 검사)."""
    tokens = number_tokens(context)
    if not tokens:
        return [f"{context_key} has no number, so it cannot show the declared value {value}"]
    if tokens[-1] != value:
        return [f"{context_key} ends with number {tokens[-1]}, not the declared value {value}"]
    return []


def _boundary_problems(context_key: str, text: str, pos: int, context: str) -> list[str]:
    """context가 문서에서 찾은 자리의 마지막 수가 문서가 말하는 수 그대로인지 본다.

    context가 문서에 적힌 수의 중간에서 끝나거나(문서는 1.96인데 context는 1.9까지) 부호를 빼고 시작하면,
    부분 일치로 한 번 나오고 마지막 수도 value와 같아 보이지만 문서의 수는 다르다. 그래서 context의 마지막
    수가 있는 자리에서 문서를 같은 규칙(_NUMBER)으로 다시 읽어, 같은 자리에 같은 정규화 글의 수가 있는지
    확인한다. (소수점·천 단위 쉼표가 이어지는 경우도 문서의 수가 더 길어서 걸린다. 더하기 기호 유무는
    정규화 글이 같아 문제가 아니다.)
    """
    in_context = list(_NUMBER.finditer(context))
    if not in_context:
        return []  # 수가 없는 context는 _value_problems가 이미 알린다
    last = in_context[-1]
    want = (pos + last.start(2), pos + last.end(2))  # 수의 숫자 부분이 문서에서 차지해야 하는 자리
    line_start, line = _line_around(text, want[0], want[1])
    for m in _NUMBER.finditer(line):
        if (line_start + m.start(2), line_start + m.end(2)) == want and _token(m) == _token(last):
            return []
    return [
        f"the last number of {context_key} ({_token(last)}) is not a whole number in the document: "
        "the text there continues the number or changes its sign"
    ]


def _problem(decl: dict, message: str) -> Problem:
    """선언 하나에 대한 문제를 만든다. 선언에 where·section·context가 없거나 글이 아니어도 죽지 않는다."""
    where, section, context = decl.get("where"), decl.get("section"), decl.get("context")
    return Problem(
        where if isinstance(where, str) and where else "?",
        section if isinstance(section, str) and section else None,
        context if isinstance(context, str) else "",
        message,
    )


def _check_number(decl: dict, index: int, docs: _Docs, spans: list[tuple[str, int, int]]) -> list[Problem]:
    """[[number]] 선언 하나를 대조한다: 루트 쪽 검사, 조건 검사, 기록 쪽 검사.

    루트 쪽에서 context를 찾은 자리는 spans에 더한다(coverage가 쓴다).
    """
    form = _form_problems(decl, NUMBER_REQUIRED, NUMBER_OPTIONAL)
    if form:
        return [_problem(decl, f"[[number]] #{index}: {m}") for m in form]
    messages: list[str] = []

    where, context, value = decl["where"], decl["context"], decl["value"]
    root = _locate(docs, where, decl.get("section"), context, "section", "context")
    messages += root.problems
    messages += _value_problems("context", context, value)
    if root.pos is not None and root.text is not None:
        messages += _boundary_problems("context", root.text, root.pos, context)
        spans.append((where, root.pos, root.pos + len(context)))
        _, line = _line_around(root.text, root.pos)
        if decl["condition"] not in line:
            messages.append(f"condition {decl['condition']!r} is not on the same line as the context")

    source_context = decl["source_context"]
    source = _locate(
        docs,
        decl["source"],
        decl.get("source_section"),
        source_context,
        "source_section",
        "source_context",
        " (source)",
    )
    messages += source.problems
    messages += _value_problems("source_context", source_context, value)
    if source.pos is not None and source.text is not None:
        messages += _boundary_problems("source_context", source.text, source.pos, source_context)
    return [_problem(decl, m) for m in messages]


def _check_snapshot(decl: dict, index: int, docs: _Docs, spans: list[tuple[str, int, int]]) -> list[Problem]:
    """[[snapshot]] 선언 하나를 대조한다: context 위치, 마지막 수, 그 절 본문에 as_of 날짜 글."""
    form = _form_problems(decl, SNAPSHOT_REQUIRED, SNAPSHOT_OPTIONAL)
    if form:
        return [_problem(decl, f"[[snapshot]] #{index}: {m}") for m in form]
    where, section, context = decl["where"], decl["section"], decl["context"]
    loc = _locate(docs, where, section, context, "section", "context")
    messages = list(loc.problems)
    messages += _value_problems("context", context, decl["value"])
    if loc.pos is not None and loc.text is not None:
        messages += _boundary_problems("context", loc.text, loc.pos, context)
        spans.append((where, loc.pos, loc.pos + len(context)))
    if loc.text is not None and loc.scope is not None:
        # context를 못 찾았더라도 날짜 글은 따로 본다(문제를 한꺼번에 보여 주려고).
        body = loc.text[loc.scope[0] : loc.scope[1]]
        if decl["as_of"] not in body:
            messages.append(f"as_of {decl['as_of']} does not appear in section {section!r} of {where}")
    return [_problem(decl, m) for m in messages]


def _check_coverage(decl: dict, index: int, docs: _Docs, spans: list[tuple[str, int, int]]) -> list[Problem]:
    """[[coverage]] 선언 하나를 대조한다: 범위 안의 '%' 수가 모두 선언된 context 자리 안에 드는지.

    수의 숫자 부분(부호 포함, '%'는 뺀 것)이 선언의 context 등장 구간에 완전히 들어야 덮인 것으로 본다.
    context가 "CER 1.96"처럼 수에서 끝나고 글에는 "1.96%"가 있어도 덮이는 이유다.
    """
    form = _form_problems(decl, COVERAGE_REQUIRED, COVERAGE_OPTIONAL)
    if form:
        return [_problem(decl, f"[[coverage]] #{index}: {m}") for m in form]
    rel, section = decl["where"], decl.get("section")
    text, error = docs.read(rel)
    if text is None:
        return [_problem(decl, error or f"cannot read {rel}")]
    scope, hits = _section_span(text, section)
    if scope is None:
        return [_problem(decl, f"section {section!r} found {hits} times in {rel} (must be exactly once)")]
    begin, finish = scope
    # 같은 where의 number·snapshot 선언 가운데 context 자리가 이 범위 안에 드는 것만 덮개로 쓴다.
    covers = [(s, e) for where, s, e in spans if where == rel and begin <= s and e <= finish]
    body = text[begin:finish]
    problems = []
    for m in _NUMBER.finditer(body):
        tail = _PERCENT_TAIL.match(body, m.end())
        if tail is None:
            continue
        start, end = begin + m.start(), begin + m.end()
        if any(s <= start and end <= e for s, e in covers):
            continue
        line_no = text.count("\n", 0, start) + 1
        line = _line_around(text, start, end)[1].strip()
        shown = body[m.start() : tail.end()]  # 문서에 적힌 그대로(부호와 % 또는 %p 포함)
        problems.append(
            Problem(
                rel,
                section,
                line,
                f"undeclared percentage {shown} on line {line_no}: "
                f"it is not inside the context of any number or snapshot declaration for {rel}",
            )
        )
    return problems


def check(decls: Declarations, repo: Path) -> list[Problem]:
    """선언을 모두 대조해 문제 목록을 돌려준다(문제가 없으면 빈 목록).

    순서는 number, snapshot, coverage다. coverage가 앞의 둘이 찾은 context 자리를 쓰기 때문이다. 선언
    하나의 문제가 다른 선언의 검사를 막지 않는다(파일이 없거나 짝이 안 맞아도 나머지는 계속 본다). repo는
    where·source 경로의 기준 폴더다.
    """
    docs = _Docs(Path(repo))
    spans: list[tuple[str, int, int]] = []  # (where, 시작, 끝): 선언이 가리키는 루트 문서 안의 자리
    problems: list[Problem] = []
    for i, decl in enumerate(decls.numbers, 1):
        problems += _check_number(decl, i, docs, spans)
    for i, decl in enumerate(decls.snapshots, 1):
        problems += _check_snapshot(decl, i, docs, spans)
    for i, decl in enumerate(decls.coverage, 1):
        problems += _check_coverage(decl, i, docs, spans)
    return problems


def _use_utf8_output() -> None:
    """표준 출력·오류를 UTF-8로 다시 연다. 인코딩할 수 없는 글자는 \\uXXXX로 바꿔 죽지 않게 한다.

    한국어 Windows(코드 페이지 949)의 파이썬은 출력이 파이프나 파일이면 cp949로 써서 한글 출력이 깨지고,
    cp949에 없는 글자(유니코드 빼기 U+2212 등)를 찍으면 UnicodeEncodeError로 죽는다(call-summary의 커밋
    0ea5791이 같은 원인이다). Linux CI는 이미 UTF-8이라 바뀌는 것이 없다.

    모듈을 가져올 때가 아니라 main이 시작할 때 한다: 시험이 출력을 가로채는 중에 import만으로 표준 출력을
    바꾸지 않으려는 것이다. reconfigure가 없는 스트림(가로채기용 객체)이거나 이미 닫혔으면 건너뛴다. 출력
    인코딩은 보조 수단이라 실패해도 검사 자체를 막지 않는다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            continue


def _build_parser() -> argparse.ArgumentParser:
    """명령줄 인자 해석기. 도움말은 한국어다."""
    parser = argparse.ArgumentParser(
        prog="check_root_numbers.py",
        add_help=False,  # 기본 -h 설명이 영어라서 아래에서 한국어 설명으로 직접 더한다
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "루트 문서(첫 화면 README.md, docs/)에 옮겨 적은 수치가 구성 요소 기록 글자와 같은지 대조한다.\n"
            "\n"
            "선언 파일(기본값: <저장소>/root-numbers.toml)의 [[number]] 선언은 '루트 문서의 이 줄 글'과\n"
            "'구성 요소 기록 파일의 이 줄 글'을 짝지어 두 쪽의 마지막 수가 같은 값인지, 수에 붙이기로 한\n"
            "조건 글이 같은 줄에 있는지 본다. [[snapshot]] 선언은 구성 요소 기록에 없는 수(예: CI에서 센\n"
            "테스트 수)를 날짜와 근거와 함께 본다. [[coverage]] 선언은 선언 없이 끼어든 퍼센트 수를 잡는다.\n"
            "\n"
            "이 도구는 읽기만 한다. 선언 파일과 문서를 고치지 않는다."
        ),
        epilog=(
            "종료 코드: 0 = 모두 통과, 1 = 선언 문제나 불일치(문제를 한 줄씩 출력), 2 = 선언 파일을 읽을 수\n"
            "없음(없음, TOML 문법 오류, 모르는 표). 출력의 끝 줄은 '선언 N개, 문제 M개'이며, 통과 여부는 끝\n"
            "줄 글자가 아니라 종료 코드로 판정한다.\n"
            "\n"
            "예: uv run --no-project tools/check_root_numbers.py\n"
            "    uv run --no-project tools/check_root_numbers.py --repo <저장소> --numbers <toml>"
        ),
    )
    parser.add_argument("-h", "--help", action="help", help="이 도움말을 보여 주고 끝낸다")
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        metavar="<저장소>",
        help="where·source 경로의 기준이 되는 저장소 뿌리 (기본값: 이 파일에서 두 단계 위 폴더)",
    )
    parser.add_argument(
        "--numbers",
        type=Path,
        default=None,
        metavar="<toml>",
        help="선언 파일 (기본값: <저장소>/root-numbers.toml)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """선언 파일을 읽어 대조하고 문제를 출력한다. 종료 코드는 0(통과), 1(문제), 2(선언 파일을 못 읽음)."""
    _use_utf8_output()
    args = _build_parser().parse_args(argv)
    repo = args.repo if args.repo is not None else DEFAULT_REPO
    numbers = args.numbers if args.numbers is not None else repo / DEFAULT_NUMBERS_FILE
    try:
        decls = load_declarations(numbers)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, DeclarationError) as e:
        print(f"선언 파일을 읽을 수 없다: {numbers}: {type(e).__name__}: {_reason(e)}", file=sys.stderr)
        return 2
    problems = check(decls, repo)
    for problem in problems:
        print(problem)
    total = len(decls.numbers) + len(decls.snapshots) + len(decls.coverage)
    print(f"선언 {total}개, 문제 {len(problems)}개")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
