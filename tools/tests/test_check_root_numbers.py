"""`tools/check_root_numbers.py` 시험.

이 도구는 루트 문서에 옮겨 적은 수치가 구성 요소 기록 글자와 같은지 선언 파일(root-numbers.toml)로 대조한다.
시험은 세 가지를 고정한다.
    1. 규칙대로 쓴 선언은 통과한다.
    2. 규칙을 어길 때마다 문제로 알린다(조용히 건너뛰지 않는다). 문제는 한 번에 하나씩만 만들어, 어느 규칙이
       어떤 문제를 냈는지 시험이 정확히 가리킬 수 있게 한다.
    3. 파일을 읽고 출력하는 방법: 경로 꼴, BOM과 CRLF가 든 문서, 줄바꿈 없이 끝나는 문서, --repo를 주지 않았을
       때의 기본값, 선언 수 세기, 파이프로 나가는 출력의 인코딩, 수를 읽는 정규식의 막기 규칙.

시험용 저장소(`fake`)는 tmp_path 안에 글 두 개로 만든다: 첫 화면을 흉내 낸 루트 README.md, 수치의 출처를
흉내 낸 whisper-ko-ft/README.md. 실제 저장소 문서는 읽지 않는다.
"""

import codecs
import json
import os
import subprocess
import sys
from pathlib import Path

import check_root_numbers
import pytest
from check_root_numbers import (
    DeclarationError,
    Declarations,
    Problem,
    check,
    fence_mask,
    load_declarations,
    main,
    number_tokens,
    section_body,
)
from conftest import REPO

# 이 파일은 <저장소>/tools/tests/에 있다. parents[1] = tools. 도구를 스크립트로 직접 돌리는 시험이 쓴다.
TOOLS = Path(__file__).resolve().parents[1]

# 유니코드 빼기 기호(U+2212). 일반 하이픈과 구별되지 않는 글자라 소스에 직접 쓰지 않고 코드 번호로 만든다.
MINUS = chr(0x2212)

# 루트 README의 구성 요소 표 한 줄: 수치(1.96%)와 그 조건(학습에서 본 문장), 날짜 붙은 테스트 수(779)가 든다.
ROOT_LINE = "| whisper-ko-ft | Zeroth test CER 1.96% (학습에서 본 문장) | 779 (2026-11-20 CI) |"
# 구성 요소 README의 결과 표 한 줄: 같은 수치가 굵게 적혀 있다.
SOURCE_LINE = "| Zeroth test 457발화, CER | 4.48% [3.77, 5.32] | **1.96%** [1.36, 2.66] |"

ROOT_README = f"## 구성 요소\n{ROOT_LINE}\n\n## 다른 절\n1.96%\n"
SOURCE_README = f"## 지금까지의 결과\n{SOURCE_LINE}\n"

# 기본 [[number]] 선언. 시험마다 필요한 키만 바꿔 쓴다.
BASE = {
    "where": "README.md",
    "section": "구성 요소",
    "context": "Zeroth test CER 1.96",
    "condition": "학습에서 본 문장",
    "source": "whisper-ko-ft/README.md",
    "source_section": "지금까지의 결과",
    "source_context": "| Zeroth test 457발화, CER | 4.48% [3.77, 5.32] | **1.96",
    "value": "1.96",
}

# 기본 [[snapshot]] 선언: 구성 요소 기록 파일에 없는 수(CI에서 센 테스트 수)를 날짜와 근거와 함께 적는다.
SNAPSHOT = {
    "where": "README.md",
    "section": "구성 요소",
    "context": "학습에서 본 문장) | 779",
    "value": "779",
    "as_of": "2026-11-20",
    "evidence": "korean-voice-ai Actions run 1234567890 (whisper-ko-ft.yml, test)",
}


def put(path: Path, text: str) -> None:
    """UTF-8(BOM 없음), 줄바꿈 LF로 파일을 쓴다. 폴더가 없으면 만든다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def number(**changes) -> dict:
    """기본 [[number]] 선언의 복사본에 changes를 덮어쓴다(기본 선언 자체는 바뀌지 않는다)."""
    return {**BASE, **changes}


def toml_text(tables: dict[str, list[dict]]) -> str:
    """{표 이름: [선언, ...]}을 선언 파일 글로 바꾼다. 값은 JSON 문자열 규칙으로 감싼다(TOML 기본 문자열과
    호환되고, 한글은 그대로 쓴다)."""
    out = []
    for name, items in tables.items():
        for item in items:
            out.append(f"[[{name}]]")
            out += [f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in item.items()]
            out.append("")
    return "\n".join(out)


@pytest.fixture
def fake(tmp_path: Path) -> Path:
    """루트 README와 구성 요소 README를 갖춘 시험용 저장소 폴더."""
    put(tmp_path / "README.md", ROOT_README)
    put(tmp_path / "whisper-ko-ft" / "README.md", SOURCE_README)
    return tmp_path


def test_number_tokens_follow_the_call_summary_rule():
    # 출처(call-summary/src/call_summary/compare.py의 number_tokens)와 같은 예를 그대로 고정한다.
    assert number_tokens("| `qwen3.5:4b`, P1 | **55.6") == ["55.6"]
    assert number_tokens("\u22122.0%p") == ["-2.0"]
    assert number_tokens("(1,500건 학습)") == ["1500"]
    assert number_tokens("4B, 14B") == []
    # 출처 docstring이 말하는 나머지 규칙: 더하기 기호는 없애고, 0의 부호는 빼며, 소수 자리 수는 글 그대로다.
    assert number_tokens("+3") == ["3"]
    assert number_tokens("\u22120.0") == ["0.0"]
    assert number_tokens("0 0.0") == ["0", "0.0"]
    # 날짜의 하이픈은 부호가 아니다(앞 글자가 숫자라 부호로 읽지 않는다).
    assert number_tokens("2026-11-20") == ["2026", "11", "20"]


def test_declared_number_passes(fake):
    assert check(Declarations(numbers=[number()]), fake) == []
    # 선언 파일에서 읽어 와도 같은 선언이 같은 결과를 낸다.
    toml = fake / "root-numbers.toml"
    put(toml, toml_text({"number": [BASE], "snapshot": [SNAPSHOT]}))
    decls = load_declarations(toml)
    assert decls.numbers == [BASE] and decls.snapshots == [SNAPSHOT] and decls.coverage == []
    assert check(decls, fake) == []


def test_source_with_another_value_fails(fake):
    # (1) 기록 쪽 수와 선언의 source_context 끝을 함께 바꾼다: 한 번 나오지만 '마지막 수 != value'다.
    put(fake / "whisper-ko-ft" / "README.md", SOURCE_README.replace("**1.96%**", "**1.97%**"))
    changed = number(source_context=BASE["source_context"].removesuffix("1.96") + "1.97")
    problems = check(Declarations(numbers=[changed]), fake)
    assert len(problems) == 1
    assert "source" in problems[0].message and "1.97" in problems[0].message
    # (2) 기록 쪽만 바뀌면 선언한 source_context가 더는 나오지 않는다(0번).
    problems = check(Declarations(numbers=[number()]), fake)
    assert len(problems) == 1
    assert "source" in problems[0].message and "0 times" in problems[0].message


def test_context_must_occur_exactly_once_in_its_section(fake):
    decls = Declarations(numbers=[number()])
    # 같은 절 안에 두 번 나온다.
    put(fake / "README.md", ROOT_README.replace("\n\n## 다른 절", f"\n{ROOT_LINE}\n\n## 다른 절"))
    problems = check(decls, fake)
    assert len(problems) == 1 and "2 times" in problems[0].message
    # 다른 절에만 있다(선언한 절에는 없다).
    put(fake / "README.md", f"## 구성 요소\n내용 없음\n\n## 다른 절\n{ROOT_LINE}\n")
    problems = check(decls, fake)
    assert len(problems) == 1 and "0 times" in problems[0].message
    # 절 제목이 없으면 그 사실을 알린다(절 안에서 찾을 수 없으므로 조용히 통과하지 않는다).
    put(fake / "README.md", f"## 이름이 다른 절\n{ROOT_LINE}\n")
    problems = check(decls, fake)
    assert len(problems) == 1
    assert problems[0].message.startswith("section '구성 요소' found 0 times in README.md")
    # 겹쳐서 나오는 자리도 센다: "1.96 1.96"은 "1.96 1.96 1.96" 안에 겹쳐 두 번 있다.
    put(fake / "README.md", "## 구성 요소\n| 1.96 1.96 1.96 |\n")
    overlapping = number(context="1.96 1.96", condition="|")
    problems = check(Declarations(numbers=[overlapping]), fake)
    assert len(problems) == 1 and "2 times" in problems[0].message
    # context가 문서에 적힌 수의 중간에서 끝나면(문서는 1.96인데 context는 1.9까지) 한 번 나오고 마지막 수가
    # value와 같아도 문서가 말하는 수가 아니다. 루트 쪽과 기록 쪽 각각 문제가 하나씩이다.
    put(fake / "README.md", ROOT_README)
    cut = number(
        context="Zeroth test CER 1.9",
        source_context=BASE["source_context"].removesuffix("1.96") + "1.9",
        value="1.9",
    )
    problems = check(Declarations(numbers=[cut]), fake)
    assert len(problems) == 2
    assert all("whole number" in problem.message for problem in problems)
    # 부호를 뺀 채 시작해도 같다: 문서는 -2.0인데 context가 2.0부터 시작하면 문서가 말하는 수가 아니다.
    minus = chr(0x2212)
    put(fake / "README.md", f"## 구성 요소\n| 차이 | {minus}2.0%p | 2026-11-20 |\n")
    unsigned = {**SNAPSHOT, "context": "2.0%p", "value": "2.0"}
    problems = check(Declarations(snapshots=[unsigned]), fake)
    assert len(problems) == 1 and "whole number" in problems[0].message
    signed = {**SNAPSHOT, "context": f"{minus}2.0%p", "value": "-2.0"}
    assert check(Declarations(snapshots=[signed]), fake) == []


def test_code_fence_hash_lines_are_not_headings(fake):
    text = f"## 구성 요소\n```bash\n# 명세 만들기\n```\n{ROOT_LINE}\n\n## 다른 절\n1.96%\n"
    put(fake / "README.md", text)
    # 울타리 속 '# 명세 만들기'는 제목이 아니므로 그 줄 뒤의 context도 '구성 요소' 절에 있다.
    assert check(Declarations(numbers=[number()]), fake) == []
    body, hits = section_body(text, "구성 요소")
    assert hits == 1 and ROOT_LINE in body and "# 명세 만들기" in body
    assert section_body(text, "명세 만들기") == (None, 0)
    # section이 None이면 파일 전체다.
    whole, hits = section_body(text, None)
    assert hits == 1 and "## 다른 절" in whole

    # 대조군: 울타리를 걷어 내면 같은 줄이 제목이 되어 절이 거기서 끝나고 context는 사라진다.
    put(fake / "README.md", text.replace("```bash\n", "").replace("```\n", ""))
    problems = check(Declarations(numbers=[number()]), fake)
    assert len(problems) == 1 and "0 times" in problems[0].message

    # 울타리 해석 자체: 여는 줄·안쪽·닫는 줄이 모두 True다. 닫는 울타리는 같은 글자(` 또는 ~)를 열 때보다
    # 짧지 않게 써야 하므로, 4개짜리 울타리 속의 3개짜리 줄은 닫지 못한다.
    fenced = (
        "a\n```bash\n# c\n```\nb\n~~~\n# d\n~~~\n````\n```\n# e\n````\nf\n"
        "```inline``` 글\ng\n- 항목\n  ```bash\n  # h\n  ```\n"
    )
    assert fence_mask(fenced) == [
        False,
        True, True, True,  # 백틱 3개 울타리
        False,
        True, True, True,  # 물결표 울타리
        True, True, True, True,  # 백틱 4개 울타리 안의 3개짜리 줄은 닫지 못한다
        False,
        False,  # 같은 줄에 백틱이 또 있는 줄은 울타리가 아니라 인라인 코드다
        False,
        False,
        True, True, True,  # 목록 안에서 들여쓴 울타리
    ]  # fmt: skip
    # 닫히지 않은 울타리는 글 끝까지 이어진다. 줄 수는 splitlines()와 같다.
    assert fence_mask("x\n```\ny") == [False, True, True]
    assert len(fence_mask(fenced)) == len(fenced.splitlines())


def test_condition_must_be_on_the_context_line(fake):
    # 조건 글을 다음 줄로 옮긴다: 같은 줄에 없으므로 문제다.
    moved = ROOT_LINE.replace(" (학습에서 본 문장)", "")
    put(fake / "README.md", f"## 구성 요소\n{moved}\n(학습에서 본 문장)\n\n## 다른 절\n1.96%\n")
    problems = check(Declarations(numbers=[number()]), fake)
    assert len(problems) == 1 and "condition" in problems[0].message


def test_snapshot_needs_its_date_in_the_section(fake):
    stale = {**SNAPSHOT, "as_of": "2026-11-21"}
    problems = check(Declarations(snapshots=[stale]), fake)
    assert len(problems) == 1 and "2026-11-21" in problems[0].message
    assert check(Declarations(snapshots=[SNAPSHOT]), fake) == []
    # 날짜가 다른 절에만 있으면 그 절 본문에 없는 것이다.
    elsewhere = ROOT_README.replace(" (2026-11-20 CI)", "").replace("\n1.96%\n", "\n1.96% (2026-11-20)\n")
    put(fake / "README.md", elsewhere)
    problems = check(Declarations(snapshots=[SNAPSHOT]), fake)
    assert len(problems) == 1 and "2026-11-20" in problems[0].message


def test_coverage_flags_an_undeclared_percentage(fake):
    put(fake / "README.md", ROOT_README.replace("\n\n## 다른 절", "\n| 대조군 | 4.48% |\n\n## 다른 절"))
    decls = Declarations(numbers=[number()], coverage=[{"where": "README.md", "section": "구성 요소"}])
    problems = check(decls, fake)
    # 1.96%는 선언이 덮고, 선언 없이 끼어든 4.48%만 문제다. 퍼센트가 아닌 779·날짜는 보지 않는다.
    assert len(problems) == 1
    assert "4.48" in problems[0].message and "1.96" not in problems[0].message
    # snapshot 선언이 가리키는 자리도 덮개다: 4.48%를 snapshot으로 선언하면 문제가 사라진다.
    covering = {**SNAPSHOT, "context": "| 대조군 | 4.48", "value": "4.48"}
    covered = Declarations(numbers=[number()], snapshots=[covering], coverage=decls.coverage)
    assert check(covered, fake) == []
    # %p와 수 뒤에 공백 하나를 둔 꼴도 퍼센트로 본다.
    extra = "| 차이 | \u22122.0%p |\n| 비율 | 7.5 % |\n"
    put(fake / "README.md", ROOT_README.replace("\n\n## 다른 절", f"\n{extra}\n## 다른 절"))
    problems = check(decls, fake)
    assert len(problems) == 2
    assert "2.0" in problems[0].message and "7.5" in problems[1].message


def test_file_wide_coverage_accepts_declarations_with_a_section(fake):
    decls = Declarations(numbers=[number()], coverage=[{"where": "README.md"}])
    problems = check(decls, fake)
    # '구성 요소' 절의 1.96%는 그 절을 가리키는 선언이 덮고, 선언이 없는 '다른 절'(5번째 줄)의 1.96%만 남는다.
    assert len(problems) == 1
    assert "1.96" in problems[0].message and "line 5" in problems[0].message


def test_malformed_declarations_are_problems_not_skips(fake, tmp_path):
    def one_problem(decls: Declarations) -> str:
        problems = check(decls, fake)
        assert len(problems) == 1, problems
        return problems[0].message

    # 모르는 키
    message = one_problem(Declarations(numbers=[number(colour="x")]))
    assert "unknown key" in message and "colour" in message
    # 빠진 키
    missing = number()
    del missing["condition"]
    message = one_problem(Declarations(numbers=[missing]))
    assert "missing key" in message and "condition" in message
    # 빈 글
    assert "non-empty" in one_problem(Declarations(numbers=[number(context="")]))
    # value 꼴: 쉼표 없는 수를 글로 적어야 한다(1.9x, 숫자 그대로의 값, 쉼표 든 값은 모두 꼴 오류).
    for bad in ("1.9x", 1.96, "2,160"):
        assert "value must be" in one_problem(Declarations(numbers=[number(value=bad)]))
    # as_of 꼴: 달력에 있는 YYYY-MM-DD여야 한다.
    for bad in ("11/20", "2026-13-45"):
        assert "as_of must be" in one_problem(Declarations(snapshots=[{**SNAPSHOT, "as_of": bad}]))
    # 저장소 밖을 가리키는 경로
    message = one_problem(Declarations(numbers=[number(where="../README.md")]))
    assert "where must not contain '..'" in message
    # 여러 줄 context는 한 줄에서 찾을 수 없으므로 꼴 오류다.
    assert "context must be a single line" in one_problem(Declarations(numbers=[number(context="a\nb")]))
    # 읽을 수 없는 파일(없는 파일, UTF-8이 아닌 파일)도 건너뛰지 않고 문제로 알린다.
    message = one_problem(Declarations(numbers=[number(where="missing.md")]))
    assert "cannot read missing.md" in message and "FileNotFoundError" in message
    (fake / "latin.md").write_bytes(b"\xff\xfe\x00")
    message = one_problem(Declarations(numbers=[number(where="latin.md")]))
    assert "cannot read latin.md" in message and "UnicodeDecodeError" in message
    # 모르는 꼭대기 표는 읽는 단계에서 멈춘다(그 표의 선언이 조용히 빠지지 않게).
    toml = tmp_path / "typo.toml"
    put(toml, '[[nums]]\nwhere = "README.md"\n')
    with pytest.raises(DeclarationError):
        load_declarations(toml)


def test_main_exit_codes(fake, capsys):
    toml = fake / "root-numbers.toml"
    put(toml, toml_text({"number": [BASE]}))

    # 통과: 기본 --numbers는 <repo>/root-numbers.toml이다.
    assert main(["--repo", str(fake)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "선언 1개, 문제 0개"

    # 불일치: 기록 쪽 수가 바뀌었다. 문제 줄은 '<where>[<section>] <context 앞 40자>: <문제>' 꼴이다.
    put(fake / "whisper-ko-ft" / "README.md", SOURCE_README.replace("**1.96%**", "**1.97%**"))
    assert main(["--repo", str(fake), "--numbers", str(toml)]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("README.md[구성 요소] Zeroth test CER 1.96: ")
    assert lines[-1] == "선언 1개, 문제 1개"
    assert str(Problem("a.md", "절", "x" * 50, "m")) == "a.md[절] " + "x" * 40 + ": m"
    assert str(Problem("a.md", None, "ctx", "m")) == "a.md ctx: m"

    # 선언 파일을 못 읽거나(없음, TOML 문법 오류, 모르는 꼭대기 표) 해석할 수 없으면 2다.
    # 이유는 표준 오류에 나오고 표준 출력은 비어 있다.
    syntax = fake / "syntax.toml"
    put(syntax, "[[number]\n")
    typo = fake / "typo.toml"
    put(typo, "[[nums]]\n")
    for bad in (fake / "missing.toml", syntax, typo):
        assert main(["--repo", str(fake), "--numbers", str(bad)]) == 2
        captured = capsys.readouterr()
        assert captured.out == "" and captured.err != ""


# ---------------------------------------------------------------------------------------------
# 파일을 읽고 출력하는 방법, 수를 읽는 규칙
# ---------------------------------------------------------------------------------------------


def only_message(decls: Declarations, repo: Path) -> str:
    """선언들을 대조해 문제가 정확히 하나일 때 그 문제 글을 돌려준다(아니면 시험이 실패한다)."""
    problems = check(decls, repo)
    assert len(problems) == 1, problems
    return problems[0].message


def test_number_tokens_skip_names_and_read_signs_like_call_summary():
    # call-summary에서 같은 일을 하는 시험(tests/test_numbers.py의 test_number_tokens_read_signs_separators_and_skip_names)의
    # 예를 그대로 가져왔다: 부호, 천 단위 쉼표, 한글이 바로 붙은 수는 값으로 읽고 이름·판에 붙은 수는 읽지 않는다.
    assert number_tokens(f"{MINUS}1.7%p [{MINUS}5.8, +2.1]") == ["-1.7", "-5.8", "2.1"]
    assert number_tokens("+4.7%p [2.4, 7.2]") == ["4.7", "2.4", "7.2"]
    assert number_tokens("Qwen3-4B (1,500건 학습) 낮은 49.5이고 v2 q8_0") == ["1500", "49.5"]
    assert number_tokens("학습한 4B 0~1.5%, 14B 0~28%") == ["0", "1.5", "0", "28"]
    assert number_tokens(f"차이 {MINUS}0.0, -0.00") == ["0.0", "0.00"]
    assert number_tokens("**95.7** [93.3, 97.7]") == ["95.7", "93.3", "97.7"]
    # 빼기 부호는 유니코드 빼기 기호뿐 아니라 일반 하이픈으로 적어도 읽는다. 위의 '-0.00'은 0이라 부호가 빠지므로
    # 하이픈을 부호로 읽는지는 0이 아닌 수로 따로 본다.
    assert number_tokens("-1.7%p [-5.8, +2.1]") == ["-1.7", "-5.8", "2.1"]
    # 정규식의 막기 규칙을 하나씩 따로: 밑줄 바로 뒤의 수("q8_0"의 0)는 읽지 않고, 점과 숫자가 이어지다 영문자에 걸리는
    # 수("1.5b")는 되돌아가 앞의 "1"만 읽는 일 없이 통째로 읽지 않는다.
    assert number_tokens("q8_0") == []
    assert number_tokens("1.5b") == []
    assert number_tokens("qwen3.5:1.5b 2") == ["2"]


def test_plus_sign_is_optional_in_a_context_but_not_for_coverage(fake):
    # 더하기 부호는 정규화한 글자에서 빠지므로 context가 부호를 담든 말든 같은 수다. 그러나 coverage는 수 전체(부호 포함)가
    # context 자리 안에 들어야 덮인 것으로 보므로, 부호를 뺀 context는 문서의 '+3.0%p'를 덮지 못한다.
    put(fake / "README.md", "## 구성 요소\n| 차이 | +3.0%p | 2026-11-20 |\n")
    with_sign = {**SNAPSHOT, "context": "| 차이 | +3.0", "value": "3.0"}
    without_sign = {**SNAPSHOT, "context": "3.0%p", "value": "3.0"}
    coverage = [{"where": "README.md", "section": "구성 요소"}]
    assert check(Declarations(snapshots=[with_sign]), fake) == []
    assert check(Declarations(snapshots=[without_sign]), fake) == []
    assert check(Declarations(snapshots=[with_sign], coverage=coverage), fake) == []
    message = only_message(Declarations(snapshots=[without_sign], coverage=coverage), fake)
    assert "+3.0%p" in message


def test_context_must_hold_the_whole_number_with_its_thousands_separators(fake):
    # 천 단위 쉼표로 이어지는 수도 마찬가지다: 문서의 2,160을 앞이나 뒤에서 일부만 담은 context는 통과하지 못한다.
    put(fake / "README.md", "## 구성 요소\n| 학습 | 2,160건 | 2026-11-20 |\n")
    whole = {**SNAPSHOT, "context": "| 학습 | 2,160", "value": "2160"}
    assert check(Declarations(snapshots=[whole]), fake) == []
    for context, value in (("| 학습 | 2,16", "16"), ("160건", "160")):
        cut = {**SNAPSHOT, "context": context, "value": value}
        assert "whole number" in only_message(Declarations(snapshots=[cut]), fake), context


def test_snapshot_needs_evidence_and_a_section(fake):
    # snapshot은 구성 요소 기록에 짝이 없는 수라, 어느 절의 수인지(section)와 어디서 셌는지(evidence)가 선언에 남아야 한다.

    def without(key: str) -> dict:
        return {k: v for k, v in SNAPSHOT.items() if k != key}

    assert "missing key(s): evidence" in only_message(Declarations(snapshots=[without("evidence")]), fake)
    assert "evidence must be a non-empty string" in only_message(
        Declarations(snapshots=[{**SNAPSHOT, "evidence": " "}]), fake
    )
    assert "missing key(s): section" in only_message(Declarations(snapshots=[without("section")]), fake)


@pytest.mark.parametrize("key", ["where", "source"])
def test_declared_paths_must_be_relative_slash_paths(fake, key):
    # 루트 쪽(where)과 기록 쪽(source) 경로 모두 같다. 역슬래시는 Windows에서만 풀리고, 절대 경로·드라이브 꼴·'..'는 저장소 밖을
    # 읽게 된다. 드라이브 꼴은 실행 중에 조립한다: 이 파일의 글에 드라이브 경로 꼴이 남지 않게 하려는 것이다.
    drive = "Z" + ":"
    outside = "must be a path relative to the repository root"
    cases = {
        "docs\\a.md": "must use '/' separators, not backslashes",
        "/x.md": outside,
        f"{drive}/x.md": outside,
        f"{drive}x.md": outside,  # 드라이브 글자만 있고 슬래시가 없는 꼴
        "docs/../../x.md": "must not contain '..'",
    }
    for bad, reason in cases.items():
        message = only_message(Declarations(numbers=[number(**{key: bad})]), fake)
        assert f"{key} {reason}" in message, bad


def test_bom_and_crlf_documents_are_read_like_plain_ones(fake):
    # 윈도 편집기가 저장한 문서(맨 앞 BOM, CRLF 줄바꿈)도 같은 결과여야 한다. BOM이 남으면 첫 줄의 제목('## 구성 요소',
    # '## 지금까지의 결과')이 제목으로 읽히지 않아 절을 찾지 못한다.
    for rel, text in (("README.md", ROOT_README), ("whisper-ko-ft/README.md", SOURCE_README)):
        (fake / rel).write_bytes(codecs.BOM_UTF8 + text.replace("\n", "\r\n").encode("utf-8"))
    coverage = [{"where": "README.md", "section": "구성 요소"}]
    decls = Declarations(numbers=[number()], snapshots=[SNAPSHOT], coverage=coverage)
    assert check(decls, fake) == []


def test_last_line_without_a_newline_is_still_a_whole_line(fake):
    # 글이 줄바꿈 없이 끝나면 글 끝까지가 마지막 줄이다. 수 경계 검사, 조건 검사, coverage의 문제 줄이 모두 줄 끝을 찾는다.
    # (1) 글이 수로 끝난다: 줄 끝을 한 글자 일찍 자르면 문서의 수가 '1.96'이 아니라 '1.9'로 읽혀 경계 검사가 걸린다.
    put(fake / "README.md", "## 구성 요소\n| 구성 | 학습에서 본 문장 | CER 1.96")
    ends_with_number = number(context="CER 1.96", condition="학습에서 본 문장")
    assert check(Declarations(numbers=[ends_with_number]), fake) == []
    # (2) 글이 조건으로 끝난다: 한 글자 일찍 자르면 조건 글이 그 줄에 없는 것으로 읽힌다.
    put(fake / "README.md", "## 구성 요소\n| 구성 | CER 1.96% (학습에서 본 문장)")
    ends_with_condition = number(context="CER 1.96", condition="(학습에서 본 문장)")
    assert check(Declarations(numbers=[ends_with_condition]), fake) == []
    # (3) 글이 선언 없는 퍼센트 수로 끝난다: 문제에 그 줄 전체가 나온다. 줄바꿈이 있어도 앞뒤 공백만 뺀 줄 전체다.
    coverage = Declarations(coverage=[{"where": "README.md", "section": "구성 요소"}])
    put(fake / "README.md", "## 구성 요소\n| 대조군 | 4.48%")
    assert [p.context for p in check(coverage, fake)] == ["| 대조군 | 4.48%"]
    put(fake / "README.md", "## 구성 요소\n  | 대조군 | 4.48% |  \n\n끝\n")
    assert [p.context for p in check(coverage, fake)] == ["| 대조군 | 4.48% |"]
    # (4) 첫 줄이 곧 글 전체다: 앞에 줄바꿈이 없으면 줄은 글의 처음(0)에서 시작한다. 절을 주지 않은 선언으로 본다.
    put(fake / "README.md", "| 구성 | 학습에서 본 문장 | CER 1.96")
    one_line = {key: value for key, value in number().items() if key != "section"}
    one_line.update(context="CER 1.96", condition="학습에서 본 문장")
    assert check(Declarations(numbers=[one_line]), fake) == []
    # (5) 글의 첫 글자가 곧 수의 첫 글자다: 줄의 시작을 한 글자 늦게 잡으면 문서의 수가 '1.96'이 아니라 '.96'으로
    # 읽혀 경계 검사가 걸린다.
    put(fake / "README.md", "1.96% (학습에서 본 문장)")
    one_line.update(context="1.96", condition="학습에서 본 문장")
    assert check(Declarations(numbers=[one_line]), fake) == []


def test_coverage_reports_a_section_that_is_not_in_the_file(fake):
    message = only_message(Declarations(coverage=[{"where": "README.md", "section": "없는 절"}]), fake)
    assert message == "section '없는 절' found 0 times in README.md (must be exactly once)"


def test_coverage_does_not_borrow_declarations_of_another_file(fake):
    # 같은 글자 위치에 퍼센트 수가 있는 다른 문서를 만든다. README.md의 선언이 가리키는 자리는 그 문서의 수를 덮지 못한다.
    put(fake / "docs" / "other.md", ROOT_README)
    decls = Declarations(numbers=[number()], coverage=[{"where": "docs/other.md", "section": "구성 요소"}])
    problems = check(decls, fake)
    assert len(problems) == 1
    assert problems[0].where == "docs/other.md" and "1.96" in problems[0].message


def test_coverage_counts_percentages_inside_code_too(fake):
    # 코드 울타리와 인라인 코드 안의 수도 선언 없이 끼어든 수로 센다(예외를 두지 않는다). 그런 수도 선언이 덮어야 한다.
    put(fake / "README.md", "## 절\n\n```\n95% 완료\n```\n\n`7%`\n")
    problems = check(Declarations(coverage=[{"where": "README.md"}]), fake)
    assert len(problems) == 2
    assert "95%" in problems[0].message and "7%" in problems[1].message


def test_default_repo_is_the_checkout_that_holds_the_tool(fake, monkeypatch, capsys):
    # --repo를 주지 않으면 이 도구가 든 저장소(tools/의 부모)를 쓴다. 시험이 쓰는 저장소 뿌리(REPO)와 같은 곳이어야 한다.
    assert check_root_numbers.DEFAULT_REPO == REPO
    # 그 값은 도구 파일의 위치에서 나와야 하고 현재 폴더에서 나오면 안 된다. 시험은 보통 저장소 뿌리에서 돌아 두 값이
    # 같으므로, 현재 폴더를 다른 곳(시험용 폴더)으로 둔 새 프로세스에서 도구를 가져와 값을 찍어 본다.
    env = {**os.environ, "PYTHONPATH": str(TOOLS), "PYTHONUTF8": "1"}
    done = subprocess.run(
        [sys.executable, "-c", "import check_root_numbers; print(check_root_numbers.DEFAULT_REPO)"],
        capture_output=True,
        cwd=fake,
        env=env,
        check=True,
    )
    assert Path(done.stdout.decode("utf-8").strip()) == REPO
    # main이 그 값을 실제로 쓰는지는 기본값을 시험용 저장소로 바꿔 두고 --repo 없이 불러 본다.
    put(fake / "root-numbers.toml", toml_text({"number": [BASE]}))
    monkeypatch.setattr(check_root_numbers, "DEFAULT_REPO", fake)
    assert main([]) == 0
    assert capsys.readouterr().out.splitlines() == ["선언 1개, 문제 0개"]


def test_main_counts_every_kind_of_declaration(fake, capsys):
    # 끝 줄의 N은 [[number]], [[snapshot]], [[coverage]] 선언을 모두 더한 수다.
    coverage = {"where": "README.md", "section": "구성 요소"}
    put(
        fake / "root-numbers.toml",
        toml_text({"number": [BASE], "snapshot": [SNAPSHOT], "coverage": [coverage]}),
    )
    assert main(["--repo", str(fake)]) == 0
    assert capsys.readouterr().out.splitlines() == ["선언 3개, 문제 0개"]


def test_script_prints_utf8_even_when_output_is_piped(fake):
    # 한국어 Windows의 파이썬은 파이프로 나가는 출력을 cp949로 쓴다. 어느 PC에서나 같은 조건이 되도록 그 인코딩을 환경
    # 변수로 정해 두고, 도구가 시작할 때 UTF-8로 다시 여는지 본다. 문제 줄에 cp949로 쓸 수 없는 글자(빼기 기호)를 넣어,
    # 다시 열지 않으면 출력 도중에 죽는 것도 함께 잡는다.
    put(fake / "README.md", f"## 구성 요소\n| 차이 | {MINUS}2.0%p |\n")
    # 이 절에는 as_of 날짜가 없어 문제가 하나 난다.
    stale = {**SNAPSHOT, "context": f"{MINUS}2.0%p", "value": "-2.0"}
    put(fake / "root-numbers.toml", toml_text({"snapshot": [stale]}))
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUTF8"}
    env["PYTHONIOENCODING"] = "cp949"
    done = subprocess.run(
        [sys.executable, str(TOOLS / "check_root_numbers.py"), "--repo", str(fake)],
        capture_output=True,
        env=env,
        check=False,  # 종료 코드는 아래에서 직접 확인한다
    )
    assert done.returncode == 1, done.stderr.decode("utf-8", errors="replace")
    lines = done.stdout.decode("utf-8").splitlines()
    assert lines[0].startswith(f"README.md[구성 요소] {MINUS}2.0%p: as_of 2026-11-20 does not appear")
    assert lines[-1] == "선언 1개, 문제 1개"
