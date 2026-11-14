"""저장소에 넣어 둔 예시 리포트(examples/shop-cancel/)와 이 폴더의 README를 확인한다.

예시 리포트는 두 오프라인 앱을 실제로 띄우고 calls/shop-cancel.json을 돌려 나온
call-report.json·call-report.md를 그대로 복사한 것이다. CI는 같은 일을 다시 해서 새로 나온 리포트가
이 예시와 바이트까지 같은지 `diff`로 본다. 이 파일의 시험은 앱 없이 돌며, 예시가 대본이나 렌더링 코드와
어긋난 것을 CI의 실제 실행보다 먼저 잡는다: 대본을 고치고 예시를 다시 만들지 않았거나,
render_markdown을 고치고 예시 Markdown을 다시 만들지 않은 경우다.

파일은 read_text가 아니라 바이트로 읽는다. read_text는 CRLF를 LF로 바꿔 읽어서, Windows에서 줄바꿈을
바꿔 받은 복제본(git의 core.autocrlf=true)에서도 통과해 버린다. CI가 견주는 것은 바이트이므로 시험도
바이트를 본다.

README 시험은 로컬 실행 명령이 서비스의 기본 포트(support-agent 8062, call-summary 8072)를 쓰지 않는지
본다. 그 PC에 두 서비스가 Docker Compose로 떠 있으면, 기본 포트로 돌린 시연은 오프라인 앱이 아니라 진짜
서비스와 이야기한다. support-agent의 `/healthz`가 돌려주는 `model`은 설정값이라 응답만 보고는 오프라인
앱인지 알 수 없다.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

from call_e2e.report import render_markdown

# 이 파일은 <e2e>/tests/test_examples.py에 있다. parents[0] = tests, parents[1] = e2e 폴더.
E2E_DIR = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = E2E_DIR / "examples" / "shop-cancel"
EXAMPLE_JSON = EXAMPLE_DIR / "call-report.json"
EXAMPLE_MD = EXAMPLE_DIR / "call-report.md"
SHOP_CANCEL = E2E_DIR / "calls" / "shop-cancel.json"
README = E2E_DIR / "README.md"

# 코드 울타리를 여는 줄: 앞 공백 0~3칸 뒤 백틱이나 물결표 세 개 이상(CommonMark의 울타리 규칙).
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# 절을 끝내는 제목 줄: 울타리 밖의 `# `·`## ` 제목. `### `처럼 더 깊은 제목은 그 절 안의 소제목이다.
_TOP_HEADING = re.compile(r"^#{1,2}\s")


def section_code_blocks(markdown: str, heading: str) -> list[str] | None:
    """`heading` 줄(예: `## 로컬에서 돌리기`)로 시작하는 절 안의 코드 울타리 내용을 차례대로 돌려준다.

    입력: Markdown 글 전체와 찾을 제목 줄(앞뒤 공백 없이 글자 그대로).
    출력: 울타리마다 여는 줄과 닫는 줄을 뺀 안쪽 줄들을 줄바꿈으로 이은 글의 목록. 그 제목이 없으면
    None이다(울타리가 하나도 없는 절은 빈 목록).

    절은 제목 다음 줄부터, 울타리 밖에서 처음 나오는 `# `·`## ` 제목 앞까지다. 울타리 안의 줄은 제목으로
    보지 않는다: PowerShell과 bash의 주석도 `#`로 시작해서, 그렇게 보면 절이 울타리 한가운데서 끝난다.
    울타리는 여는 줄과 같은 글자(백틱 또는 물결표)를 그보다 적지 않게 쓴 줄로 닫힌다. 닫히지 않은
    울타리는 글 끝까지다. 저장소 루트의 도구에도 비슷한 울타리 해석이 있지만, e2e는 루트 도구와 환경이
    따로라 가져다 쓰지 않고 이 시험에 필요한 만큼만 여기에 둔다.
    """
    blocks: list[str] = []
    found = in_section = False
    fence = ""  # 지금 열린 울타리의 표시(예: "```"). 울타리 밖이면 빈 글
    inside: list[str] = []
    for line in markdown.split("\n"):
        if fence:
            stripped = line.strip()
            closes = stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence)
            if closes and len(line) - len(line.lstrip(" ")) <= 3:
                if in_section:
                    blocks.append("\n".join(inside))
                fence = ""
            elif in_section:
                inside.append(line)
            continue
        opened = _FENCE_OPEN.match(line)
        if opened:
            fence, inside = opened.group(1), []
        elif _TOP_HEADING.match(line):
            if in_section:
                break
            if line.strip() == heading:
                found = in_section = True
    else:
        # 글 끝까지 닫히지 않은 울타리도 그 절의 코드로 본다(CommonMark도 글 끝까지를 울타리로 본다).
        if fence and in_section:
            blocks.append("\n".join(inside))
    return blocks if found else None


def test_example_markdown_is_the_rendering_of_the_example_json():
    # 예시 Markdown은 예시 JSON을 지금의 render_markdown으로 그린 것과 바이트까지 같아야 한다(UTF-8, LF).
    report = json.loads(EXAMPLE_JSON.read_bytes().decode("utf-8"))
    assert render_markdown(report).encode("utf-8") == EXAMPLE_MD.read_bytes()


def test_example_matches_the_call_script():
    # 예시에 적힌 대본 해시는 지금 저장소에 있는 대본 파일 바이트의 SHA-256이어야 한다. 대본을 고치고
    # 예시를 다시 만들지 않으면 여기서 실패한다(CI의 diff도 실패하지만, 그보다 먼저 앱 없이 알 수 있다).
    report = json.loads(EXAMPLE_JSON.read_bytes().decode("utf-8"))
    assert report["script"]["sha256"] == hashlib.sha256(SHOP_CANCEL.read_bytes()).hexdigest()


def test_readme_local_commands_avoid_service_ports():
    # `## 로컬에서 돌리기` 절의 코드 울타리 안 명령은 18062·18072만 쓰고 서비스 기본 포트를 쓰지 않는다.
    # ':18062'는 ':8062'를 품지 않으므로(콜론 바로 뒤가 1) 두 검사가 서로 섞이지 않는다.
    blocks = section_code_blocks(README.read_bytes().decode("utf-8"), "## 로컬에서 돌리기")
    assert blocks, "README에 '## 로컬에서 돌리기' 절이 없거나 그 절에 코드 울타리가 없다"
    code = "\n".join(blocks)
    assert "127.0.0.1:18062" in code
    assert "127.0.0.1:18072" in code
    assert ":8062" not in code
    assert ":8072" not in code
    # 포트를 실제로 잡는 것은 uvicorn에 주는 `--port` 값이다. 주소만 보면 그 값이 서비스 기본 포트로
    # 바뀌어도 모르고 지나가므로, 그 값이 18062·18072 차례인지 따로 본다.
    assert re.findall(r"'--port'\s*,\s*'(\d+)'", code) == ["18062", "18072"]


# 위 도우미가 절과 울타리를 바르게 가르는지 고정한다. 도우미가 울타리를 빠뜨리면 README 시험의
# '없음' 검사가 아무것도 보지 않고 통과할 수 있어서다.
_CASES = [
    # 절 안의 울타리 둘을 차례대로 읽고, 다음 `## ` 절의 울타리는 읽지 않는다.
    ("## 가\n```\none\n```\n글\n~~~ps\ntwo\n~~~\n## 나\n```\nthree\n```\n", ["one", "two"]),
    # 울타리 안의 `## ` 줄은 제목이 아니라 절이 끝나지 않고, `### ` 소제목도 절을 끝내지 않는다.
    (
        "## 가\n```\n## 주석\n```\n### 소제목\n```\nfour\n```\n# 다음\n```\nfive\n```\n",
        ["## 주석", "four"],
    ),
    # 다른 절의 울타리 안에 같은 제목 글이 있어도 그것은 제목이 아니다.
    ("## 나\n```\n## 가\n```\n## 가\n```\nsix\n```\n", ["six"]),
    # 백틱 넷으로 연 울타리는 백틱 셋으로 닫히지 않는다. 닫히지 않은 울타리는 글 끝까지다.
    ("## 가\n````\n```\nseven\n", ["```\nseven\n"]),
    # 제목은 있지만 울타리가 없으면 빈 목록, 제목이 없으면 None.
    ("## 가\n글만 있다\n", []),
    ("## 나\n```\neight\n```\n", None),
]


@pytest.mark.parametrize(("markdown", "expected"), _CASES)
def test_section_code_blocks_reads_only_the_fences_of_that_section(markdown, expected):
    assert section_code_blocks(markdown, "## 가") == expected
