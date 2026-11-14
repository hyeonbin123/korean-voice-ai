"""`tools/check_links.py` 시험.

이 도구는 루트 문서(README.md, docs/*.md, e2e/README.md)의 상대 링크가 열리는지 본다. 시험은 다섯 가지를
고정한다.
    1. 제목 앵커 만들기(github_slug, heading_slugs): GitHub와 같은 slug, 같은 제목의 번호 붙이기, 제목으로 읽는 줄.
    2. 링크 찾기(iter_links): 인라인 링크·그림·참조 정의를 찾고, 코드 안의 글은 링크로 읽지 않는다.
    3. 판정(check_file): 대상 파일·폴더, 제목 앵커, 줄 앵커가 없으면 문제로 알리고 바깥 주소는 보지 않는다.
       저장소 밖을 가리키는 링크와 Windows 꼴 경로(역슬래시, 드라이브 글자, file: 주소)는 대상이 있어도 문제다.
    4. 검사할 문서 모음(default_files): 정해진 문서만 정해진 순서로. 파일 시스템이 돌려주는 순서에 기대지 않는다.
    5. 명령줄(main): 종료 코드 0(통과) / 1(끊긴 링크) / 2(검사를 시작할 수 없음)와 출력 꼴, 현재 폴더 기준
       상대 경로 인자, 읽기 실패.

시험용 저장소는 tmp_path 아래 `repo` 폴더에 글 몇 개로 만든다. 저장소 밖 파일이 필요한 시험은 그 부모 폴더
(tmp_path)를 쓴다. 실제 저장소 문서는 읽지 않는다.
"""

import codecs
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest
from check_links import check_file, default_files, github_slug, heading_slugs, iter_links, main

# 이 파일은 <저장소>/tools/tests/에 있다. parents[1] = tools. 도구를 스크립트로 직접 돌리는 시험이 쓴다.
TOOLS = Path(__file__).resolve().parents[1]

# 제목 "결과"의 앵커를 퍼센트 인코딩한 글(UTF-8 바이트를 %와 16진수 두 자리로 적은 꼴)과 소문자 16진수 판.
# 손으로 적지 않고 표준 라이브러리로 만든다: 인코딩 규칙을 시험이 따로 복제하지 않고 표준 구현에 맡기려는 것이다.
ENCODED_RESULT = quote("결과")
ENCODED_RESULT_LOWER = ENCODED_RESULT.lower()


def write(root: Path, rel: str, text: str) -> Path:
    """root 아래 rel 경로에 text를 UTF-8(BOM 없음), 줄바꿈 LF로 쓴다. 폴더가 없으면 만든다."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """tmp_path 아래의 빈 `repo` 폴더. 저장소 밖 파일은 부모(tmp_path)에 만든다."""
    root = tmp_path / "repo"
    root.mkdir()
    return root


def problems_of(repo: Path, rel: str = "README.md") -> list[str]:
    """repo 안의 문서 하나(기본값 README.md)를 검사한 문제 줄들."""
    return check_file(repo, repo / rel)


def target_of(problem: str) -> str:
    """문제 줄 `<파일>:<줄>: <대상>: <이유>`에서 대상만 꺼낸다(대상에 ': '이 든 시험은 없다)."""
    return problem.split(": ")[1]


def where_of(problem: str) -> str:
    """문제 줄 `<파일>:<줄>: <대상>: <이유>`에서 `<파일>:<줄>`만 꺼낸다."""
    return problem.split(": ")[0]


def reason_of(problem: str) -> str:
    """문제 줄 `<파일>:<줄>: <대상>: <이유>`에서 이유만 꺼낸다.

    이유에도 ': '이 들 수 있어('file: 주소는 …') 앞의 두 칸에서만 자른다.
    """
    return problem.split(": ", 2)[2]


# ---------------------------------------------------------------------------------------------
# 1. 제목 앵커 만들기
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "slug"),
    [
        # 괄호·쌍점은 사라지고, 공백은 하이픈이 되고, 한글·숫자·하이픈은 남는다.
        ("결과 요약 (2026-10 측정: 서빙)", "결과-요약-2026-10-측정-서빙"),
        # 영문 대문자는 소문자가 된다.
        ("측정 결과 (음성 Whisper)", "측정-결과-음성-whisper"),
        ("귀속 (2026-10-24 확인)", "귀속-2026-10-24-확인"),
        # 인라인 코드의 백틱은 떼고 글은 남긴다.
        ("Run `uv sync` now", "run-uv-sync-now"),
        ("데이터와 모델", "데이터와-모델"),
    ],
)
def test_github_slug_examples(heading, slug):
    assert github_slug(heading) == slug


def test_github_slug_drops_link_and_bold_markup():
    # [글](주소)는 글만 남고(주소 글자는 slug에 들어가지 않는다), **는 기호만 사라진다.
    assert github_slug("[참조 문서](docs/a.md)와 **굵은** 글") == "참조-문서와-굵은-글"


def test_duplicate_headings_get_numbered_slugs():
    assert heading_slugs("## 결과\n\n## 결과\n") == {"결과", "결과-1"}
    assert heading_slugs("## 결과\n## 결과\n## 결과\n") == {"결과", "결과-1", "결과-2"}
    # 이미 '결과-1'이라는 제목이 있으면 번호 붙인 slug가 겹치지 않게 한 번 더 번호를 붙인다(github-slugger와 같다).
    assert heading_slugs("## 결과\n## 결과\n## 결과-1\n") == {"결과", "결과-1", "결과-1-1"}


def test_heading_syntax_follows_commonmark():
    text = "\n".join(
        [
            "# 첫째 #",  # 뒤의 닫는 '#'은 제목 글이 아니다
            "   ## 둘째",  # 앞 공백은 세 칸까지 제목이다
            "    ### 셋째",  # 네 칸이면 들여쓴 코드라 제목이 아니다
            "#해시태그",  # '#' 뒤에 공백이 없으면 제목이 아니다
            "####### 일곱",  # '#'은 여섯 개까지다
            "## C#",  # 공백 없이 붙은 '#'은 제목 글이다(slug에서는 기호라 사라진다)
            "#",  # 글이 없는 제목은 앵커를 만들지 않는다
        ]
    )
    assert heading_slugs(text) == {"첫째", "둘째", "c"}


def test_headings_inside_code_fences_make_no_anchor():
    text = "# 제목\n\n```bash\n# 주석일 뿐\n```\n\n~~~\n## 물결 울타리\n~~~\n"
    assert heading_slugs(text) == {"제목"}


# ---------------------------------------------------------------------------------------------
# 2. 링크 찾기
# ---------------------------------------------------------------------------------------------


def test_iter_links_gives_line_numbers_and_targets_as_written():
    text = (
        "[a](x.md)\n"
        "\n"
        "```\n"
        "[b](y.md)\n"
        "```\n"
        '글 [c](z.md#앵커 "제목") `[d](w.md)` ![e](v.png)\n'
        "[참조]: u.md\n"
    )
    assert iter_links(text) == [(1, "x.md"), (6, "z.md#앵커"), (6, "v.png"), (7, "u.md")]


def test_link_title_angle_brackets_and_escaped_brackets():
    # 제목("…" 또는 '…')과 <…>는 대상이 아니다. 역슬래시로 이스케이프한 닫는 대괄호는 링크를 닫지 못한다.
    text = "[a](x.md 't') [b](<y.md>) [c](z.md \"t\") \\[d\\](w.md)\n"
    assert iter_links(text) == [(1, "x.md"), (1, "y.md"), (1, "z.md")]


# ---------------------------------------------------------------------------------------------
# 3. 판정
# ---------------------------------------------------------------------------------------------


def test_missing_relative_target_is_reported(repo):
    write(repo, "README.md", "처음 줄\n[문서](docs/없음.md)\n")
    problems = problems_of(repo)
    assert len(problems) == 1
    assert problems[0].startswith("README.md:2: docs/없음.md: ")


def test_existing_file_and_directory_pass(repo):
    write(repo, "docs/a.md", "# 문서\n\n[처음](../README.md) [공백](my%20file.md) [저장소](..) [이 폴더](./)\n")
    write(repo, "docs/my file.md", "# 공백이 든 이름\n")
    write(repo, "tools/x.py", "pass\n")
    write(repo, "README.md", "[문서](docs/a.md) [폴더](tools/) [폴더](tools) [점으로 시작](./docs/a.md)\n")
    assert problems_of(repo) == []
    assert problems_of(repo, "docs/a.md") == []


def test_heading_anchor_must_exist_and_may_be_percent_encoded(repo):
    write(repo, "docs/a.md", "# 문서\n\n## 결과\n")
    links = [
        "[없음](docs/a.md#없는-제목)",
        f"[인코딩](docs/a.md#{ENCODED_RESULT})",
        f"[소문자 16진수](docs/a.md#{ENCODED_RESULT_LOWER})",
        "[그대로](docs/a.md#결과)",
    ]
    write(repo, "README.md", "\n".join(links) + "\n")
    problems = problems_of(repo)
    assert len(problems) == 1
    assert problems[0].startswith("README.md:1: docs/a.md#없는-제목: ")


def test_same_file_anchor_checks_the_headings_of_the_same_file(repo):
    write(repo, "README.md", f"# 처음\n\n## 결과\n\n[여기](#결과) [인코딩](#{ENCODED_RESULT}) [없음](#없는-제목)\n")
    problems = problems_of(repo)
    assert len(problems) == 1
    assert problems[0].startswith("README.md:5: #없는-제목: ")


def test_line_anchor_needs_enough_lines(repo):
    write(repo, "src/two.py", "a = 1\nb = 2\n")
    write(repo, "src/no_newline.txt", "a\nb")  # 끝 줄바꿈이 없어도 두 줄이다
    write(repo, "docs/a.md", "# 문서\n")
    links = [
        "[1](src/two.py#L3)",  # 셋째 줄은 없다
        "[2](src/two.py#L1-L2)",  # 범위 전체가 있다
        "[3](src/two.py#L2)",
        "[4](src/two.py#L1-L3)",  # 끝 줄이 없다
        "[5](src/two.py#L0)",  # 줄은 1부터다
        "[6](src/no_newline.txt#L2)",
        "[7](src/no_newline.txt#L3)",
        "[8](docs#L1)",  # 폴더에는 줄 앵커를 붙일 수 없다
    ]
    write(repo, "README.md", "\n".join(links) + "\n")
    assert [where_of(p) for p in problems_of(repo)] == [
        "README.md:1",
        "README.md:4",
        "README.md:5",
        "README.md:7",
        "README.md:8",
    ]


def test_title_anchor_needs_a_markdown_target(repo):
    write(repo, "docs/a.md", "# 문서\n")
    # 파이썬 주석 '# 문서'는 마크다운으로 읽으면 제목 꼴이다. 그래도 .md가 아닌 파일에는 제목 앵커를 붙일 수 없다.
    write(repo, "src/x.py", "# 문서\n")
    write(repo, "README.md", "[1](src/x.py#문서)\n[2](docs#문서)\n[3](docs/a.md#문서)\n")
    assert [where_of(p) for p in problems_of(repo)] == ["README.md:1", "README.md:2"]


def test_absolute_urls_and_code_are_ignored(repo):
    lines = [
        "[웹](https://example.com/없는/페이지)",
        "[메일](mailto:someone@example.com)",
        "[스킴 생략](//example.com/x)",
        "`[인라인 코드](docs/없음.md)`",
        "``백틱 ` 하나가 든 [코드](docs/없음.md)``",
        "",
        "```markdown",
        "[울타리](docs/없음.md)",
        "[울타리 참조]: docs/없음.md",
        "```",
        "",
        "~~~",
        "[물결 울타리](docs/없음.md)",
        "~~~",
    ]
    write(repo, "README.md", "\n".join(lines) + "\n")
    assert problems_of(repo) == []


def test_a_lone_backtick_does_not_hide_the_links_that_follow(repo):
    # 짝 없는 백틱이 빈 줄 너머의 다음 백틱과 짝지어져 그 사이를 코드로 삼키면 끊긴 링크를 놓친다. 인라인 코드는 한 문단 안에서만 짝을 찾는다.
    write(repo, "README.md", "백틱 ` 하나\n\n[끊김](docs/없음.md)\n\n또 하나 `\n")
    assert [where_of(p) for p in problems_of(repo)] == ["README.md:3"]


def test_links_may_not_leave_the_repository(repo):
    write(repo.parent, "x.md", "# 저장소 밖\n")  # 밖에 파일이 실제로 있어도 문제다
    write(repo, "docs/a.md", "[1](../../x.md)\n[2](../..)\n[3](/docs/a.md)\n")
    problems = problems_of(repo, "docs/a.md")
    assert [target_of(p) for p in problems] == ["../../x.md", "../..", "/docs/a.md"]


def test_images_and_reference_definitions_are_checked(repo):
    write(repo, "README.md", "![그림](img/없음.png)\n\n[참조]: docs/없음.md\n")
    problems = problems_of(repo)
    assert [where_of(p) for p in problems] == ["README.md:1", "README.md:3"]
    assert [target_of(p) for p in problems] == ["img/없음.png", "docs/없음.md"]


def test_image_wrapped_in_a_link_checks_both_targets(repo):
    write(repo, "README.md", "[![구조도](img/없음.svg)](docs/없음.md)\n")
    assert [target_of(p) for p in problems_of(repo)] == ["img/없음.svg", "docs/없음.md"]
    write(repo, "img/있음.svg", "<svg/>\n")
    write(repo, "docs/있음.md", "# 문서\n")
    write(repo, "README.md", "[![구조도](img/있음.svg)](docs/있음.md)\n")
    assert problems_of(repo) == []


def test_reference_definition_forms(repo):
    write(repo, "docs/a.md", "# 문서\n")
    lines = [
        '[하나]: docs/a.md "제목"',  # 제목이 붙어도 대상은 docs/a.md
        "[둘]: <docs/a.md>",
        "[^1]: 각주",  # 한 낱말짜리 각주 정의도 링크 정의가 아니다
        "[참고]: 이 줄은 정의가 아니라 대상 뒤에 글이 이어지는 글이다",
    ]
    write(repo, "README.md", "\n".join(lines) + "\n")
    assert problems_of(repo) == []


def test_backslash_or_drive_path_link_is_reported(repo):
    # 드라이브 꼴은 실행 중에 조립한다: 이 파일의 글에 드라이브 경로 꼴이 남지 않게 하려는 것이다.
    drive = "Z" + ":"
    write(repo, "docs/a.md", "# 문서\n")  # 역슬래시를 슬래시로 읽으면 열리는 파일: 그래도 문제여야 한다
    write(repo, "x.md", "# 루트의 파일\n")
    links = [
        "[a](docs\\a.md)",
        f"[b]({drive}\\x.md)",
        "[c](file://" + "/" + drive + "/x.md)",
    ]
    write(repo, "README.md", "\n".join(links) + "\n")
    problems = problems_of(repo)
    assert [where_of(p) for p in problems] == ["README.md:1", "README.md:2", "README.md:3"]
    # 위치만 보면 안 된다: 역슬래시를 경로 구분자로 읽지 않는 Linux에서는 `docs\a.md`가 없는 파일이라, 이 꼴을 가려내는
    # 판정을 지워도 '대상이 없다'로 같은 줄에 걸려 통과한다. 이유 글까지 단언해야 어느 판정이 잡았는지 가려진다.
    assert "역슬래시" in reason_of(problems[0])
    assert "드라이브" in reason_of(problems[1])
    assert "file:" in reason_of(problems[2])


def test_drive_path_with_forward_slashes_is_not_taken_for_a_scheme(repo):
    # 드라이브 글자 한 자와 쌍점은 https: 같은 스킴처럼 생겼다. 바깥 주소로 오해해 건너뛰지 말고 문제로 알려야 한다.
    drive = "Z" + ":"
    write(repo, "README.md", f"[a]({drive}/x.md)\n[b](https://example.com/x.md)\n")
    problems = problems_of(repo)
    assert [where_of(p) for p in problems] == ["README.md:1"]
    assert "드라이브" in reason_of(problems[0])


def test_percent_encoded_backslash_is_reported_too(repo):
    # 역슬래시를 퍼센트 인코딩해 적은 경로는 해독하면 역슬래시 경로와 같다. 대상 파일이 있어도 문제여야 한다.
    write(repo, "docs/a.md", "# 문서\n")
    encoded = quote("docs\\a.md")  # 표준 라이브러리가 역슬래시를 인코딩한다(슬래시는 그대로 둔다)
    write(repo, "README.md", f"[a]({encoded})\n[b](docs/a.md)\n")
    problems = problems_of(repo)
    assert [where_of(p) for p in problems] == ["README.md:1"]
    assert target_of(problems[0]) == encoded
    assert "역슬래시" in reason_of(problems[0])  # Linux에서는 위치만으로는 '대상이 없다'와 구별되지 않는다


def test_empty_anchors_are_not_a_problem(repo):
    # 뒤에 아무 글도 없는 '#'은 확인할 앵커가 없다는 뜻이다. 제목이 하나도 없는 문서에서도, 파일 뒤에 붙어도 통과해야 한다.
    write(repo, "docs/a.md", "# 문서\n")
    write(repo, "src/x.py", "pass\n")
    write(repo, "README.md", "[1](#)\n[2](docs/a.md#)\n[3](src/x.py#)\n[4](docs/없음.md#)\n")
    problems = problems_of(repo)
    # 빈 앵커가 없는 파일을 가려 주지는 않는다.
    assert [where_of(p) for p in problems] == ["README.md:4"]
    assert reason_of(problems[0]) == "대상이 없다"


def test_percent_encoded_hash_belongs_to_the_file_name(repo):
    # %23은 파일 이름 속의 '#'이다. 앵커 구분은 문서에 적힌 그대로의 '#'이고, 퍼센트 해독은 나눈 뒤에 한다.
    write(repo, "docs/a#b.md", "# 제목\n")
    links = ["[1](docs/a%23b.md)", "[2](docs/a%23b.md#제목)", "[3](docs/a%23b.md#없는-제목)"]
    write(repo, "README.md", "\n".join(links) + "\n")
    problems = problems_of(repo)
    assert [where_of(p) for p in problems] == ["README.md:3"]
    assert "앵커" in reason_of(problems[0])


def test_line_anchor_counts_newline_bytes_only(repo):
    # 줄 수는 줄바꿈(\n) 바이트만 센다. str.splitlines()는 쪽 나눔(\x0c)과 유니코드 줄 구분자(U+2028)에서도 줄을 나눠 이
    # 파일을 5줄로 세지만, 줄바꿈으로는 3줄이다.
    (repo / "src").mkdir()
    (repo / "src" / "split.txt").write_bytes(b"a\x0cb\nc\n" + ("d" + chr(0x2028) + "e\n").encode("utf-8"))
    write(repo, "README.md", "[1](src/split.txt#L3)\n[2](src/split.txt#L4)\n[3](src/split.txt#L1-L5)\n")
    problems = problems_of(repo)
    assert [where_of(p) for p in problems] == ["README.md:2", "README.md:3"]
    assert "3줄뿐" in reason_of(problems[0])


def test_documented_limits_of_the_link_reader(repo):
    # 이 도구 머리말의 '보지 않는 것'이 적은 한계를 그대로 고정한다. 이 동작을 고치면 머리말도 함께 고친다.
    write(repo, "docs/b_(1).md", "# 문서\n")
    write(repo, "docs/my file.md", "# 문서\n")
    lines = [
        "[괄호](docs/b_(1).md)",  # 대상은 첫 ')'에서 끝난다: 파일 이름의 '(1'까지만 읽는다
        "[인코딩](docs/b_%281%29.md)",  # 괄호를 %28·%29로 적으면 파일이 열린다
        "[공백](<docs/my file.md>)",  # 공백이 든 <대상>은 링크로 읽지 않는다
        "[공백 없는 파일](<docs/없는 파일.md>)",  # 그래서 없는 파일이어도 조용히 지나간다
        '<a id="x"></a>',
        "[직접 쓴 앵커](#x)",  # 제목에서 만든 앵커만 안다
    ]
    write(repo, "README.md", "\n".join(lines) + "\n")
    problems = problems_of(repo)
    assert [(where_of(p), target_of(p)) for p in problems] == [
        ("README.md:1", "docs/b_(1"),
        ("README.md:6", "#x"),
    ]


def test_crlf_and_bom_documents_are_read_like_plain_ones(repo):
    (repo / "docs").mkdir()
    (repo / "docs" / "a.md").write_bytes("# 문서\r\n".encode("utf-8"))
    body = "# 제목\r\n\r\n[여기](#제목) [문서](docs/a.md) [없음](docs/없음.md)\r\n"
    (repo / "README.md").write_bytes(codecs.BOM_UTF8 + body.encode("utf-8"))
    problems = problems_of(repo)
    assert [target_of(p) for p in problems] == ["docs/없음.md"]
    assert problems[0].startswith("README.md:3: ")
    assert heading_slugs("# 제목\r\n\r\n## 결과\r\n") == {"제목", "결과"}


# ---------------------------------------------------------------------------------------------
# 4. 검사할 문서 모음
# ---------------------------------------------------------------------------------------------


def test_default_files_are_the_root_documents_in_a_fixed_order(repo):
    # 목록에 들면 안 되는 것(.md가 아닌 파일, docs의 하위 폴더, 다른 폴더의 README)을 섞어 만든다. 파일을 만드는 순서를
    # 섞어도 나열 순서는 바뀌지 않으므로, 정렬을 지켜 주는 시험은 바로 아래의 시험이 따로 맡는다.
    made = ["README.md", "docs/b.md", "docs/a.md", "docs/note.txt", "docs/sub/c.md", "e2e/README.md", "x/README.md"]
    for rel in made:
        write(repo, rel, "내용\n")
    names = [p.relative_to(repo).as_posix() for p in default_files(repo)]
    assert names == ["README.md", "docs/a.md", "docs/b.md", "e2e/README.md"]
    # 없는 문서는 건너뛴다.
    (repo / "README.md").unlink()
    (repo / "e2e" / "README.md").unlink()
    assert [p.relative_to(repo).as_posix() for p in default_files(repo)] == ["docs/a.md", "docs/b.md"]


def test_default_files_do_not_depend_on_the_order_the_file_system_lists(repo, monkeypatch):
    # 폴더를 나열하는 순서는 파일 시스템이 정하고 파이썬도 보장하지 않는다(NTFS에서는 이름순으로 나오지만 다른 파일
    # 시스템도 그렇다는 보장이 없다). 파일을 만드는 순서를 섞는 것으로는 이를 시험할 수 없으므로, 나열 결과를 이름의
    # 역순으로 돌려주도록 바꿔 둔다. 도구가 스스로 이름순으로 정렬하지 않으면 docs 문서가 c, b, a 순으로 나온다.
    for rel in ("README.md", "docs/a.md", "docs/b.md", "docs/c.md"):
        write(repo, rel, "내용\n")
    real_glob = Path.glob
    patterns: list[str] = []

    def reversed_glob(self, pattern):
        patterns.append(pattern)
        return iter(sorted(real_glob(self, pattern), key=lambda path: path.name, reverse=True))

    monkeypatch.setattr(Path, "glob", reversed_glob)
    names = [p.relative_to(repo).as_posix() for p in default_files(repo)]
    # 도구가 나열에 다른 방법을 쓰게 되면 위의 바꿔치기가 닿지 않아 이 시험이 아무것도 보지 못한다. 그때는 이 시험을 고친다.
    assert patterns == ["*.md"]
    assert names == ["README.md", "docs/a.md", "docs/b.md", "docs/c.md"]


# ---------------------------------------------------------------------------------------------
# 5. 명령줄
# ---------------------------------------------------------------------------------------------


def test_main_exit_codes(repo, capsys):
    write(repo, "docs/a.md", "# 문서\n")
    write(repo, "README.md", "[문서](docs/a.md)\n[웹](https://example.com)\n")
    assert main(["--repo", str(repo)]) == 0
    assert capsys.readouterr().out.splitlines() == ["링크 2개, 끊김 0개"]

    write(repo, "README.md", "[문서](docs/a.md)\n[없음](docs/없음.md)\n")
    assert main(["--repo", str(repo)]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("README.md:2: docs/없음.md: ")
    assert lines[1] == "링크 2개, 끊김 1개"

    assert main(["--repo", str(repo), str(repo / "없는파일.md")]) == 2
    captured = capsys.readouterr()
    assert "없는파일.md" in captured.err
    assert "끊김" not in captured.out


def test_main_checks_only_the_given_files(repo, capsys):
    write(repo, "README.md", "[없음](docs/없음.md)\n")
    write(repo, "docs/a.md", "[처음](../README.md)\n")
    assert main(["--repo", str(repo), str(repo / "docs" / "a.md")]) == 0
    assert capsys.readouterr().out.splitlines() == ["링크 1개, 끊김 0개"]


def test_main_resolves_relative_arguments_from_the_current_folder(repo, monkeypatch, capsys):
    # 파일 인자는 현재 폴더 기준이다(저장소 뿌리 기준이 아니다). 문제 줄에 보이는 경로는 어디서 돌려도 저장소 뿌리 기준이다.
    write(repo, "docs/a.md", "[없음](없는.md)\n")
    monkeypatch.chdir(repo)
    assert main(["--repo", str(repo), "docs/a.md"]) == 1
    assert capsys.readouterr().out.splitlines()[0].startswith("docs/a.md:1: 없는.md: ")
    monkeypatch.chdir(repo / "docs")
    assert main(["--repo", str(repo), "a.md"]) == 1
    assert capsys.readouterr().out.splitlines()[0].startswith("docs/a.md:1: 없는.md: ")
    # 저장소도 상대 경로로 줄 수 있다.
    monkeypatch.chdir(repo.parent)
    assert main(["--repo", "repo", "repo/docs/a.md"]) == 1
    assert capsys.readouterr().out.splitlines()[0].startswith("docs/a.md:1: 없는.md: ")


def test_main_exits_2_when_a_document_cannot_be_read(repo, monkeypatch, capsys):
    write(repo, "README.md", "[문서](docs/a.md)\n")
    unreadable = write(repo, "docs/a.md", "# 문서\n")
    real_read_bytes = Path.read_bytes

    def read_bytes(self):
        # 파일 권한은 운영체제마다 달라 시험에서 믿고 쓸 수 없으므로, 그 문서를 읽을 때만 읽기 실패를 일으킨다.
        if self.resolve() == unreadable.resolve():
            raise PermissionError(13, "권한이 없다", str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    # 문서를 읽지 못하면 검사를 끝낼 수 없다: 끊긴 링크가 없다는 뜻의 0도, 있다는 뜻의 1도 아니다.
    assert main(["--repo", str(repo)]) == 2
    captured = capsys.readouterr()
    assert "파일을 읽을 수 없다" in captured.err and "PermissionError" in captured.err
    assert "끊김" not in captured.out


def test_main_refuses_to_start_when_there_is_nothing_to_check(repo, tmp_path, capsys):
    # 검사할 문서가 하나도 없으면 통과가 아니라 시작할 수 없음이다(저장소 위치를 잘못 준 실수가 초록으로 보이지 않게).
    assert main(["--repo", str(repo)]) == 2
    assert capsys.readouterr().out == ""
    # 저장소 폴더가 아닌 경로.
    assert main(["--repo", str(repo / "없는폴더")]) == 2
    # 저장소 밖의 파일.
    outside = write(tmp_path, "x.md", "# 저장소 밖\n")
    assert main(["--repo", str(repo), str(outside)]) == 2
    assert "저장소 밖" in capsys.readouterr().err


def test_script_prints_utf8_even_when_output_is_piped(repo):
    # 한국어 Windows의 파이썬은 파이프로 나가는 출력을 cp949로 쓴다. 도구가 시작할 때 UTF-8로 다시 여는지 본다.
    # 같은 폴더의 check_root_numbers를 가져오는 것도 스크립트로 직접 돌릴 때만 드러나므로 함께 확인된다.
    write(repo, "README.md", "[없음](docs/없음.md)\n")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    done = subprocess.run(
        [sys.executable, str(TOOLS / "check_links.py"), "--repo", str(repo)],
        capture_output=True,
        env=env,
    )
    assert done.returncode == 1, done.stderr.decode("utf-8", errors="replace")
    lines = done.stdout.decode("utf-8").splitlines()
    assert lines[0].startswith("README.md:1: docs/없음.md: ")
    assert lines[-1] == "링크 1개, 끊김 1개"
