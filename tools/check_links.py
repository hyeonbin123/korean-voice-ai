# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""루트 문서(README.md, docs/*.md, e2e/README.md)의 상대 링크가 끊기지 않았는지 보는 검사 도구.

왜 있나
    첫 화면과 docs/ 문서는 저장소 안의 다른 문서·파일·제목·줄을 링크로 가리킨다. 파일을 옮기거나 제목을 고치면
    링크가 조용히 끊긴다. 또 Windows에서 쓴 경로(역슬래시, 드라이브 글자, file: 주소)는 글쓴이의 PC에서는 열려도
    저장소를 받은 다른 사람에게는 열리지 않는다. 이 도구는 그런 링크를 문서를 올리기 전에 잡는다. 읽기만 하며
    문서를 고치지 않는다.

찾는 링크 (코드 울타리와 인라인 코드 안의 글은 링크로 읽지 않는다)
    인라인 링크·그림   [글](대상)  ![그림](대상)  [글](대상 "제목")
                       그림을 링크로 감싼 [![그림](a.png)](b.md)는 안쪽(a.png)과 바깥(b.md)을 모두 본다.
    참조 정의          [이름]: 대상
                       각주 정의([^1]: ...)와, 대상 뒤에 글이 더 이어지는 줄은 정의가 아니라 글이다.

대상 하나의 판정 (링크 하나에 문제는 하나만 알린다. 아래 순서에서 처음 걸리는 것)
    1. 드라이브 글자로 시작하거나, file: 로 시작하거나, 역슬래시가 든 대상은 대상 파일이 있어도 문제다. 이런 꼴은
       글쓴이의 Windows PC에서만 열린다. 역슬래시를 퍼센트 인코딩해 적은 경로도 같다. 2번(스킴 건너뛰기)보다 먼저
       본다: 드라이브 글자 한 자와 쌍점도 스킴처럼 생겨서, 먼저 거르지 않으면 바깥 주소로 오해해 건너뛰게 된다.
    2. https:·mailto: 같은 스킴이나 //로 시작하는 바깥 주소는 보지 않는다(링크 개수에는 들어간다).
    3. '#제목'처럼 앵커만 있으면 같은 문서의 제목을 본다. 그 밖에는 '#' 앞(경로)과 뒤(앵커)를 나눠 각각 퍼센트
       해독한 뒤 경로를 문서가 있는 폴더 기준으로 푼다. 저장소 밖을 가리키거나(슬래시로 시작하는 경로 포함) 대상이
       없으면 문제다. 폴더도 대상이 될 수 있다.
    4. 앵커가 있으면: 'L<줄>'이나 'L<시작>-L<끝>' 꼴은 대상 파일에 그 줄이 있어야 하고(줄은 1부터), 그 밖의 앵커는
       대상이 .md 문서이고 그 문서의 제목에서 만든 slug 가운데 하나여야 한다.

제목 slug (github_slug, heading_slugs)
    GitHub가 제목 앵커를 만드는 방식(github-slugger)을 따라 만든다: 인라인 코드의 백틱을 떼고, [글](주소)는 글만
    남기고, **를 떼고, 소문자로 바꾸고, 유니코드 범주가 글자(L)·결합 기호(M)·숫자(N)인 글자와 '-'·'_'·공백만 남기고,
    공백 하나마다 '-'로 바꾼다. 같은 slug가 또 나오면 '-1', '-2'를 붙인다. 코드 울타리 안의 '#' 줄은 제목이 아니다.
    이 규칙이 만든 slug가 실제 GitHub 화면의 앵커와 같은지는 이 도구가 증명하지 못한다. GitHub 화면에서 링크를
    눌러 보는 확인이 따로 필요하다.

보지 않는 것
    - 바깥 주소(https 등)가 열리는지.
    - HTML 태그(<a href>, <img src>)의 주소. HTML 주석 안의 마크다운 링크는 오히려 링크로 읽는다.
    - 주소 끝의 쿼리 문자열(?로 시작하는 부분). 파일 이름의 일부로 읽으므로 그런 상대 링크는 대상이 없다고 알린다.
    - 들여쓴 코드 블록, 밑줄 강조(_글_), 밑줄 줄로 만든 제목(=== 또는 ---). 제목은 '#'으로 시작하는 줄만 읽는다.
    - 파일 이름의 대소문자. 대소문자를 구분하지 않는 파일 시스템(Windows 기본값)에서는 대소문자가 틀린 경로도
      통과한다. 구분하는 환경(Linux)에서 돌리면 잡힌다.
    - 괄호가 든 상대 경로. 대상은 첫 `)`에서 끝나므로 `docs/b_(1).md`는 `docs/b_(1`로 읽혀 대상이 없다고
      알린다(괄호를 %28·%29로 적으면 본다).
    - 공백이 든 `<대상>`. `[글](<docs/my file.md>)`는 링크로 잡히지 않아 파일이 없어도 조용히 통과한다(공백을
      %20으로 적으면 본다).
    - 직접 쓴 HTML 앵커(`<a id="x"></a>` 뒤의 `[글](#x)`). 앵커는 제목에서 만든 slug만 알기 때문에 '제목 앵커가
      없다'고 알린다.

코드 울타리를 해석하는 규칙은 같은 폴더의 check_root_numbers.fence_mask를 가져다 쓴다. 울타리 해석을 두 벌 두지
않으려는 것이다. 이 도구는 의존성 없는 한 장짜리 스크립트지만 이 한 가지는 같은 폴더의 도구에 기대므로, tools/
폴더째 두고 실행한다.

종료 코드와 출력
    0 = 모두 통과, 1 = 끊긴 링크가 있음, 2 = 검사를 시작하거나 끝낼 수 없음(인자로 준 파일이 없거나 저장소 밖에
    있음, 저장소 폴더가 아님, 파일을 안 줬는데 기본 문서가 하나도 없음, 검사할 문서나 링크가 가리키는 파일을
    읽다가 실패함). 문서가 하나도 없는 것을 통과로 보지 않는 까닭은 저장소 위치를 잘못 준 실수가 초록색 통과로
    보이지 않게 하려는 것이다. 파일을 읽지 못한 때도 같다: 끊긴 링크가 없다는 0도, 있다는 1도 아니다.
    끊긴 링크마다 `<파일>:<줄>: <대상>: <이유>` 한 줄을 쓴다. 파일은 저장소 뿌리 기준 슬래시 경로, 줄은 대상이
    적힌 줄, 대상은 문서에 적힌 그대로다. 마지막 줄은 `링크 N개, 끊김 M개`다. N은 찾은 링크 전부(바깥 주소 포함),
    M은 문제를 알린 링크 수다. 판정은 끝 줄 글자가 아니라 종료 코드로 한다.

실행
    uv run --no-project tools/check_links.py [--repo <저장소>] [파일 ...]
    파일을 주지 않으면 README.md, docs/*.md(이름순), e2e/README.md 가운데 있는 것을 검사한다.
"""

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

from check_root_numbers import fence_mask

# 이 파일은 <저장소>/tools/check_links.py에 있다. parents[0] = tools, parents[1] = 저장소 뿌리.
DEFAULT_REPO = Path(__file__).resolve().parents[1]

# 인라인 링크·그림의 대상: `](` 바로 뒤. 앞쪽 `[글`을 정규식에 넣지 않고 `](`만 기준으로 삼는 까닭은 그림을 링크로
# 감싼 `[![그림](a.png)](b.md)`에서 바깥 대상 b.md도 잡으려는 것이다. `[글]` 쪽까지 정규식으로 잡으면 안쪽 그림의
# 닫는 대괄호에서 일치가 끝나 바깥 대상이 남는다. 역슬래시로 이스케이프한 `\]`는 링크 글을 닫지 못한다.
# 대상은 공백·`)`·`>`가 아닌 글자들이고 `<...>`로 감싸도 된다. 뒤에 큰따옴표나 작은따옴표 제목이 올 수 있다.
_INLINE_TARGET = re.compile(r"""(?<!\\)\]\(\s*<?([^)\s>]+)>?(?:\s+(?:"[^"]*"|'[^']*'))?\s*\)""")

# 참조 정의 `[이름]: 대상`. 줄 머리(공백 세 칸까지)에서 시작하고, 대상 뒤에는 제목(선택)과 줄 끝만 올 수 있다. 그래서
# `[참고]: 이 값은 ...`처럼 대괄호 말머리 뒤에 글이 이어지는 줄은 정의가 아니다. `[^1]: ...` 각주 정의도 정의가 아니라서
# `[` 바로 뒤의 `^`는 막는다. 대상은 같은 줄이나 바로 다음 줄에 올 수 있다(줄바꿈은 한 번까지).
_REFERENCE_DEFINITION = re.compile(
    r"""^ {0,3}\[(?!\^)[^\]\n]+\]:[ \t]*\n?[ \t]*<?([^\s>]+)>?(?:[ \t]+(?:"[^"\n]*"|'[^'\n]*'))?[ \t]*$""",
    re.MULTILINE,
)

# 인라인 코드: 같은 개수의 백틱 묶음이 열고 닫는다(CommonMark). 닫는 묶음은 열 때와 정확히 같은 개수여야 하므로
# 앞뒤가 백틱이 아닌지 본다. 짝이 없는 백틱은 그냥 글자다. 빈 줄을 넘어 짝을 찾지 않는다(문단 하나 안에서만):
# 짝 없는 백틱 하나가 뒤쪽 문단까지 코드로 삼켜 그 사이의 링크를 놓치는 일을 막으려는 것이다.
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(?:(?!\n[ \t]*\n).)*?(?<!`)\1(?!`)", re.DOTALL)

# Markdown 제목 줄: 줄 머리의 공백 세 칸까지 허용(네 칸이면 들여쓴 코드), '#' 1~6개, 공백, 제목 글, 닫는 '#'(앞에 공백이
# 있어야 닫는 표시. "C#"의 '#'은 제목 글이다). '#' 뒤에 공백이 없는 "#해시태그"는 제목이 아니다. 글이 없는 제목은
# group(2)가 None이거나 비어 있다.
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
# 제목 글 속의 [글](주소): slug를 만들 때 글만 남기려고 찾는다.
_HEADING_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")

# 대상이 드라이브 글자로 시작하는 꼴(글자 하나, 쌍점, 슬래시나 역슬래시). 스킴 판정보다 앞서 본다.
_DRIVE = re.compile(r"[A-Za-z]:[\\/]")
# 바깥 주소의 스킴(https:, mailto: 같은 것).
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
# 줄 앵커: L<줄> 또는 L<시작>-L<끝>. \d가 다른 나라 숫자까지 받지 않도록 ASCII로 한정한다.
_LINE_ANCHOR = re.compile(r"L(\d+)(?:-L(\d+))?", re.ASCII)

# 이 PC에서만 열리는 꼴의 문제 이유. 같은 이유를 여러 자리에서 쓰므로 한 곳에 둔다.
_DRIVE_PROBLEM = "드라이브 글자로 시작하는 경로는 이 PC에서만 열린다(저장소 안 상대 경로로 쓴다)"
_FILE_URL_PROBLEM = "file: 주소는 이 PC에서만 열린다(저장소 안 상대 경로로 쓴다)"
_BACKSLASH_PROBLEM = "역슬래시가 든 경로는 Windows에서만 열린다(슬래시로 쓴다)"


def _use_utf8_output() -> None:
    """표준 출력·오류를 UTF-8로 다시 연다. 인코딩할 수 없는 글자는 \\uXXXX로 바꿔 죽지 않게 한다.

    한국어 Windows(코드 페이지 949)의 파이썬은 출력이 파이프나 파일이면 cp949로 써서 한글 출력이 깨진다.
    Linux CI는 이미 UTF-8이라 바뀌는 것이 없다. check_root_numbers의 같은 이름 함수와 같은 일을 하며, 비공개
    함수를 다른 도구에서 가져오지 않으려고 복제했다.

    모듈을 가져올 때가 아니라 main이 시작할 때 한다: 시험이 출력을 가로채는 중에 import만으로 표준 출력을
    바꾸지 않으려는 것이다. reconfigure가 없는 스트림(가로채기용 객체)이거나 이미 닫혔으면 건너뛴다. 출력 인코딩은
    보조 수단이라 실패해도 검사 자체를 막지 않는다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            continue


def github_slug(heading: str) -> str:
    """제목 글 하나를 GitHub 제목 앵커(slug)로 바꾼다. 같은 제목이 또 나올 때 붙는 번호는 heading_slugs가 붙인다.

    순서(github-slugger를 따른다): 인라인 코드의 백틱을 뗀다 → [글](주소)를 글만 남긴다 → **를 뗀다 → 소문자로
    바꾼다 → 유니코드 범주가 글자(L)·결합 기호(M)·숫자(N)인 글자와 '-'·'_'·공백만 남긴다 → 공백 하나마다 '-'로
    바꾼다. 그래서 "A & B"는 공백 두 개가 남아 "a--b"가 된다. 밑줄 강조(_글_)는 해석하지 않아 밑줄이 그대로 남는다.
    """
    text = heading.replace("`", "")
    text = _HEADING_LINK.sub(r"\1", text)
    text = text.replace("**", "")
    text = text.lower()
    kept = [ch for ch in text if ch in "-_ " or unicodedata.category(ch)[0] in "LMN"]
    return "".join(kept).replace(" ", "-")


def heading_slugs(markdown: str) -> set[str]:
    """마크다운 글의 모든 제목에서 만든 slug 모음. 같은 slug가 또 나오면 '-1', '-2'를 붙인다.

    번호 붙이기는 github-slugger와 같은 방법이다: 이미 쓴 slug와 겹치면 처음 slug에 붙는 번호를 올려 가며 빈 slug를
    찾는다. 그래서 제목 "결과"가 두 번 나온 뒤에 제목 "결과-1"이 따로 있으면 그 제목은 "결과-1-1"이 된다. 코드 울타리
    안의 줄은 제목이 아니고(fence_mask), 글이 없는 제목은 앵커를 만들지 않는다. 줄 나누기는 str.splitlines()다.
    """
    mask = fence_mask(markdown)
    used: dict[str, int] = {}  # 이미 쓴 slug → (처음 slug일 때) 마지막으로 붙인 번호
    slugs: set[str] = set()
    for index, line in enumerate(markdown.splitlines()):
        if mask[index]:
            continue
        found = _HEADING.match(line)
        if found is None:
            continue
        title = (found.group(2) or "").strip()
        if not title:
            continue
        base = github_slug(title)
        slug = base
        while slug in used:
            used[base] += 1
            slug = f"{base}-{used[base]}"
        used[slug] = 0
        slugs.add(slug)
    return slugs


def _mask_code(markdown: str) -> str:
    """코드 울타리 줄과 인라인 코드를 지운 글을 돌려준다. 줄 수와 줄바꿈 위치는 그대로다.

    울타리 줄은 빈 줄로, 인라인 코드는 같은 길이의 공백으로 바꾼다. 그래야 지운 글에서 찾은 위치로 원래 글의 줄
    번호를 그대로 셀 수 있다. 울타리 해석은 fence_mask를 쓴다(줄 나누기가 같다).
    """
    lines = markdown.splitlines()
    fenced = fence_mask(markdown)
    text = "\n".join("" if fenced[index] else line for index, line in enumerate(lines))
    return _CODE_SPAN.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), text)


def iter_links(markdown: str) -> list[tuple[int, str]]:
    """마크다운 글에서 링크 대상을 모두 찾아 (줄 번호, 대상) 목록으로 돌려준다. 위치 순서다.

    인라인 링크·그림·참조 정의를 찾고 코드(울타리, 인라인)는 건너뛴다. 줄 번호는 1부터이고 대상이 적힌 줄이다.
    대상은 글에 적힌 그대로(퍼센트 해독 전, 앵커 포함)이며 감싼 <>와 제목은 뺀다. 바깥 주소도 포함한다.
    """
    masked = _mask_code(markdown)
    found = [
        (match.start(1), match.group(1))
        for pattern in (_INLINE_TARGET, _REFERENCE_DEFINITION)
        for match in pattern.finditer(masked)
    ]
    found.sort()
    return [(masked.count("\n", 0, position) + 1, target) for position, target in found]


def default_files(repo: Path) -> list[Path]:
    """파일을 따로 주지 않았을 때 검사할 문서: README.md, docs/*.md(이름순), e2e/README.md 가운데 있는 것.

    docs의 하위 폴더는 보지 않는다. docs/*.md는 나열 결과를 그대로 쓰지 않고 이름순으로 정렬한다. 나열 순서는
    파일 시스템이 정하고 파이썬도 보장하지 않으므로, 정렬하지 않으면 같은 저장소의 문제 줄 순서가 환경마다 달라질
    수 있다.

    인자 없이 이 도구를 부르면 이 목록이 곧 검사 범위이고 문제 줄의 순서다. 범위나 순서를 바꾸면 인자 없이 도구를
    돌리는 곳의 결과가 달라지므로, 바꿀 때는 그런 호출도 함께 본다.
    """
    files = [repo / "README.md"]
    docs = repo / "docs"
    if docs.is_dir():
        files += sorted(docs.glob("*.md"), key=lambda path: path.name)
    files.append(repo / "e2e" / "README.md")
    return [path for path in files if path.is_file()]


def _read_text(path: Path) -> str:
    """마크다운 파일을 UTF-8로 읽는다. 맨 앞의 BOM은 떼고, 깨진 바이트는 대체 글자로 바꿔 읽기가 멈추지 않게 한다."""
    return path.read_bytes().decode("utf-8-sig", errors="replace")


def _line_count(path: Path) -> int:
    """파일의 줄 수. 줄바꿈(\\n)으로 나누고, 마지막 줄바꿈 뒤의 빈 칸은 줄로 세지 않는다. 빈 파일은 0이다.

    글로 읽지 않고 바이트로 센다: 글자 해석 때문에 줄 수가 달라지거나(이진 파일), str.splitlines()가 \\x0c 같은
    글자에서 줄을 더 나누는 일을 피하려는 것이다.
    """
    data = path.read_bytes()
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def _slugs_of(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    """문서의 제목 slug 모음. 한 번 검사하는 동안 같은 문서를 다시 읽지 않도록 cache에 담아 둔다."""
    if path not in cache:
        cache[path] = heading_slugs(_read_text(path))
    return cache[path]


def _line_anchor_problem(path: Path, anchor: str, found: re.Match) -> str | None:
    """줄 앵커(L<줄> 또는 L<시작>-L<끝>)가 가리키는 줄이 파일에 있는지 본다. 문제 없으면 None."""
    if not path.is_file():
        return "줄 앵커는 파일에만 붙일 수 있다"
    first = int(found.group(1))
    last = int(found.group(2) or first)
    if min(first, last) < 1:
        return "줄 번호는 1부터다"
    total = _line_count(path)
    if max(first, last) > total:
        return f"파일이 {total}줄뿐이라 {anchor} 줄이 없다"
    return None


def _judge(repo: Path, md: Path, target: str, cache: dict[Path, set[str]]) -> str | None:
    """링크 대상 하나를 판정한다. 문제가 없으면 None, 있으면 한 줄짜리 이유를 돌려준다.

    repo와 md는 이미 resolve한 절대 경로다(md는 문서 파일). 판정 순서와 까닭은 이 파일 머리말의 '대상 하나의 판정'.
    """
    # 1. 이 PC에서만 열리는 꼴은 대상 파일이 있어도 문제다. 스킴 건너뛰기(2)보다 먼저 본다.
    if _DRIVE.match(target):
        return _DRIVE_PROBLEM
    if target.lower().startswith("file:"):
        return _FILE_URL_PROBLEM
    if "\\" in target:
        return _BACKSLASH_PROBLEM
    # 2. 바깥 주소는 보지 않는다.
    if _SCHEME.match(target) or target.startswith("//"):
        return None
    # 3. '#' 앞(경로)과 뒤(앵커)를 먼저 나눈 뒤 각각 퍼센트 해독한다. 해독한 뒤에 나누면 파일 이름에 든 %23('#')이
    #    앵커 구분으로 잘못 읽힌다.
    raw_path, _, raw_anchor = target.partition("#")
    path_part = unquote(raw_path)
    anchor = unquote(raw_anchor)
    # 역슬래시를 퍼센트 인코딩해 적은 경로(편집기가 자동으로 바꾸는 경우가 있다)도 해독하면 같은 꼴이다.
    if "\\" in path_part:
        return _BACKSLASH_PROBLEM
    if path_part == "":
        # '#제목'만 있거나 '#' 하나뿐인 링크: 같은 문서. 앵커가 비면 확인할 것이 없다.
        if anchor == "" or anchor in _slugs_of(md, cache):
            return None
        return "이 문서에 그 제목 앵커가 없다"
    if path_part.startswith("/"):
        return "슬래시로 시작하는 경로는 쓰지 않는다(문서가 있는 폴더 기준 상대 경로로 쓴다)"
    # 문서가 있는 폴더 기준으로 푼다. normpath는 글자만으로 '..'를 접으므로 바로 앞 폴더가 심볼릭 링크인 경우는 따지지 않는다.
    resolved = Path(os.path.normpath(md.parent / path_part))
    if resolved != repo and repo not in resolved.parents:
        return "저장소 밖을 가리킨다"
    try:
        if not resolved.exists():
            return "대상이 없다"
        if anchor == "":
            return None
        # 4. 앵커: 줄 앵커이거나 .md 문서의 제목이어야 한다.
        line_anchor = _LINE_ANCHOR.fullmatch(anchor)
        if line_anchor is not None:
            return _line_anchor_problem(resolved, anchor, line_anchor)
        if not (resolved.is_file() and resolved.suffix.lower() == ".md"):
            return "제목 앵커는 .md 문서에만 붙일 수 있다(다른 파일에는 줄 앵커만 쓴다)"
        if anchor in _slugs_of(resolved, cache):
            return None
        return "그 문서에 그 제목 앵커가 없다"
    except (OSError, ValueError) as error:
        # 대상을 열 수 없는 경우(접근 권한, 입출력 오류, 운영체제가 받지 못하는 경로 등). 검사가 죽지 않게 이유로 알린다.
        # 파이썬 3.11(Windows)에서 확인: 널 문자나 쓸 수 없는 글자가 든 경로는 exists가 예외 대신 False를 돌려줘 위의 "대상이 없다"로 나간다.
        return f"대상을 확인할 수 없다: {type(error).__name__}"


def _inside(root: Path, path: Path) -> bool:
    """path가 root 자신이거나 그 아래인지(둘 다 resolve한 경로)."""
    return path == root or root in path.parents


def _scan_file(repo: Path, md: Path) -> tuple[int, list[str]]:
    """문서 하나를 검사한다. (찾은 링크 수, 문제 줄 목록)을 돌려준다.

    md는 repo 안의 파일이어야 한다(아니면 ValueError). 문제 줄은 `<파일>:<줄>: <대상>: <이유>`이고 파일은 repo
    기준 슬래시 경로다. 링크 하나당 문제는 하나만 낸다.
    """
    repo = repo.resolve()
    md = md.resolve()
    shown = md.relative_to(repo).as_posix()
    text = _read_text(md)
    cache = {md: heading_slugs(text)}
    links = iter_links(text)
    problems = []
    for line, target in links:
        reason = _judge(repo, md, target, cache)
        if reason is not None:
            problems.append(f"{shown}:{line}: {target}: {reason}")
    return len(links), problems


def check_file(repo: Path, md: Path) -> list[str]:
    """repo 안의 마크다운 문서 md의 끊긴 링크를 `<파일>:<줄>: <대상>: <이유>` 줄로 돌려준다. 없으면 빈 목록.

    repo와 md는 서로 같은 기준(둘 다 절대 경로이거나 현재 폴더 기준 상대 경로)으로 준다. md가 repo 밖이면
    ValueError다. 파일을 읽지 못하면 OSError가 그대로 나간다(main이 종료 코드 2로 바꾼다).
    """
    return _scan_file(repo, md)[1]


def _build_parser() -> argparse.ArgumentParser:
    """명령줄 인자 해석기. 도움말은 한국어다."""
    parser = argparse.ArgumentParser(
        prog="check_links.py",
        add_help=False,  # 기본 -h 설명이 영어라서 아래에서 한국어 설명으로 직접 더한다
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "루트 문서의 상대 링크가 끊기지 않았는지 본다.\n"
            "\n"
            "인라인 링크·그림·참조 정의의 대상 파일이나 폴더, '#제목' 앵커, 줄 앵커(L<줄> 또는 L<시작>-L<끝>)가\n"
            "있는지 확인한다. 저장소 밖을 가리키는 링크와 Windows 꼴 경로(역슬래시, 드라이브 글자, file: 주소)는\n"
            "대상이 있어도 문제로 알린다. 바깥 주소(https 등)와 코드 안의 글은 보지 않는다.\n"
            "\n"
            "이 도구는 읽기만 한다. 문서를 고치지 않는다."
        ),
        epilog=(
            "종료 코드: 0 = 모두 통과, 1 = 끊긴 링크가 있음(한 줄씩 출력), 2 = 검사를 시작할 수 없음(준 파일이\n"
            "없거나 저장소 밖에 있음, 저장소 폴더가 아님, 기본 문서가 하나도 없음). 출력의 끝 줄은\n"
            "'링크 N개, 끊김 M개'이며, 통과 여부는 끝 줄 글자가 아니라 종료 코드로 판정한다.\n"
            "끊긴 링크 한 줄의 꼴: <파일>:<줄>: <대상>: <이유>\n"
            "\n"
            "예: uv run --no-project tools/check_links.py\n"
            "    uv run --no-project tools/check_links.py --repo <저장소> <문서>.md"
        ),
    )
    parser.add_argument("-h", "--help", action="help", help="이 도움말을 보여 주고 끝낸다")
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        metavar="<저장소>",
        help="링크가 저장소 안을 가리키는지 판단하는 기준이 되는 저장소 뿌리 (기본값: 이 파일에서 두 단계 위 폴더)",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        metavar="<파일>",
        help=(
            "검사할 마크다운 문서 (기본값: README.md, docs/*.md 이름순, e2e/README.md 가운데 있는 것). "
            "현재 폴더 기준 경로이고 절대 경로도 된다. 저장소 안의 파일이어야 한다."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """문서의 링크를 검사하고 문제를 출력한다. 종료 코드는 0(통과), 1(끊긴 링크), 2(검사를 시작할 수 없음)."""
    _use_utf8_output()
    args = _build_parser().parse_args(argv)
    repo = args.repo if args.repo is not None else DEFAULT_REPO
    if not repo.is_dir():
        print(f"저장소 폴더가 아니다: {repo}", file=sys.stderr)
        return 2
    if args.files:
        files = list(args.files)
        for path in files:
            if not path.is_file():
                print(f"검사할 파일이 없다: {path}", file=sys.stderr)
                return 2
            if not _inside(repo.resolve(), path.resolve()):
                print(f"저장소 밖의 파일은 검사하지 않는다: {path}", file=sys.stderr)
                return 2
    else:
        files = default_files(repo)
        if not files:
            print(f"검사할 문서가 없다(README.md, docs/*.md, e2e/README.md 모두 없음): {repo}", file=sys.stderr)
            return 2
    total = 0
    problems: list[str] = []
    for path in files:
        try:
            count, found = _scan_file(repo, path)
        except OSError as error:
            print(f"파일을 읽을 수 없다: {path}: {type(error).__name__}: {error}", file=sys.stderr)
            return 2
        total += count
        problems += found
    for problem in problems:
        print(problem)
    print(f"링크 {total}개, 끊김 {len(problems)}개")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
