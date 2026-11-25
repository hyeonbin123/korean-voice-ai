"""커밋한 결과 파일과, 그것을 옮겨 적은 문서의 시험.

저장소에 커밋된 결과 파일 둘(`evaluation/asr/results/fleurs-ko-test.json`, `fleurs-ko-test.md`)과 규칙
문서(`docs/asr-comparison.md`)의 결과 절을 실제 저장소에서 읽어 서로 견준다. 합성 고정물이 아니라 실제 파일을
읽고, 읽기만 하며 아무것도 쓰지 않는다. 하는 일은 셋이다.

  - 재계산: `asr-compare verify`가 통과한다. 커밋된 결과 파일 둘이 지금의 코드와 재료로 다시 만든 글과
    글자까지 같다. 결과 파일이 바뀌거나, 코드나 재료가 바뀌어 같은 결과가 나오지 않으면 이 시험이 알려 준다.
  - 기록값: 결과 JSON의 수가 구성 요소가 이미 적어 둔 값과 맞는다. voice-translator와 whisper-ko-ft 묶음은
    공통 정답이 그 묶음들의 정답과 정규화하면 같아서, 공통 정답으로 다시 센 전체 범위의 편집 수와 정답 글자
    수가 기록값 그대로여야 한다. stt-scratch 묶음은 정답이 두 행에서 다르므로(악센트가 붙은 글자) 전체
    범위가 아니라 한글 전용 범위가 기록값과 같다. 열네 묶음의 정답 글자 수는 범위마다 서로 같다(모두 공통
    정답으로 세었다).
  - 문서: 규칙 문서의 결과 절에 옮겨 적은 표가 결과 Markdown의 표와 글자까지 같다.

수치를 이 파일에 새로 적지 않는다. 기대값은 이미 있는 기록(`recorded.EXPECTED`와 whisper-ko-ft 리포트에 저장된
발화별 값), 결과 파일, 문서에서 읽은 것이고, 이 시험은 그것들이 서로 맞는지만 본다.

결과 파일이나 문서가 없거나 읽을 수 없으면 건너뛰지 않고 실패한다. 결과가 사라졌는데 시험이 초록이면 안 된다.
"""

import json
from pathlib import Path

import pytest

from asr_compare import cli, recorded, sources

# 이 파일은 <저장소>/evaluation/asr/tests/ 아래에 있다. parents[0] = tests, [1] = asr, [2] = evaluation,
# [3] = 저장소 뿌리.
REPOSITORY = Path(__file__).resolve().parents[3]

# 커밋한 결과 파일과 문서의 자리. 구현의 상수를 가져다 쓰지 않고 따로 적는다(구현의 상수가 틀려도 시험이 같이
# 틀리지 않게 한다).
RESULTS = REPOSITORY / "evaluation" / "asr" / "results"
RESULT_JSON = RESULTS / "fleurs-ko-test.json"
RESULT_MARKDOWN = RESULTS / "fleurs-ko-test.md"
DOCUMENT = REPOSITORY / "docs" / "asr-comparison.md"

# 문서에서 결과를 옮겨 적은 절의 제목은 이 글로 시작한다.
RESULT_SECTION = "## 결과 ("
# 결과 Markdown의 표는 셋이다: 전체 범위, 한글 전용 범위, 짝 비교.
TABLE_COUNT = 3

# 묶음 키 -> 그 묶음을 낸 구성 요소(구현의 고정 목록에서 읽는다).
COMPONENT = {spec.key: spec.component for spec in sources.SYSTEMS}


def read_text(path: Path) -> str:
    """UTF-8 글 파일을 읽어 줄 끝의 CRLF를 LF로 접어 돌려준다.

    줄바꿈 변환을 켠 채 받은 복제본에서는 같은 파일이 CRLF로 들어오므로, 읽는 쪽에서 접는다. 파일이 없거나
    읽을 수 없으면 건너뛰지 않고 실패한다.
    """
    name = path.relative_to(REPOSITORY).as_posix()
    try:
        return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        pytest.fail(f"{name}: 읽지 못했다({type(error).__name__})", pytrace=False)


def table_blocks(text: str) -> list[list[str]]:
    """글에서 `|`로 시작하는 줄이 이어진 덩어리(Markdown 표)를 차례로 모은다. 덩어리 하나는 줄의 목록이다."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.startswith("|"):
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def result_section(document: str) -> str:
    """문서에서 `## 결과 (`로 시작하는 절의 글을 돌려준다: 그 제목 줄부터 다음 `## ` 제목 앞까지다.

    절이 여럿이면 첫 절이다. `### `로 시작하는 작은 제목은 절 안에 든다. 문서 앞쪽(규칙 절)의 표는 이 절
    밖이라 들어오지 않는다. 절이 없으면 건너뛰지 않고 실패한다.
    """
    lines = document.split("\n")
    starts = [number for number, line in enumerate(lines) if line.startswith(RESULT_SECTION)]
    if not starts:
        pytest.fail(f"{DOCUMENT.name}: '{RESULT_SECTION}'로 시작하는 절이 없다", pytrace=False)
    section: list[str] = []
    for line in lines[starts[0] :]:
        if section and line.startswith("## "):
            break
        section.append(line)
    return "\n".join(section)


def first_difference(left: list[str], right: list[str]) -> str:
    """두 줄 목록이 처음 달라지는 곳을 사람이 읽을 글로 돌려준다(한쪽이 먼저 끝나면 그 줄은 '(없음)')."""
    for number in range(max(len(left), len(right))):
        in_left = left[number] if number < len(left) else "(없음)"
        in_right = right[number] if number < len(right) else "(없음)"
        if in_left != in_right:
            return f"{number + 1}번째 줄: 문서 `{in_left}`, 결과 파일 `{in_right}`"
    return "같다"


@pytest.fixture(scope="module")
def loaded() -> sources.Loaded:
    """실제 저장소의 재료 열아홉 개를 읽은 것. 읽지 못하면 건너뛰지 않고 실패한다."""
    try:
        return sources.load_repository(REPOSITORY)
    except sources.SourceError as error:
        pytest.fail(f"실제 재료를 읽지 못했다: {error}", pytrace=False)


@pytest.fixture(scope="module")
def result() -> dict:
    """커밋한 결과 JSON을 읽은 것. 없거나 JSON이 아니면 건너뛰지 않고 실패한다."""
    try:
        return json.loads(read_text(RESULT_JSON))
    except json.JSONDecodeError as error:
        pytest.fail(f"{RESULT_JSON.name}: JSON 문법 오류({error})", pytrace=False)


# ---------------------------------------------------------------------------------------------
# 재계산
# ---------------------------------------------------------------------------------------------


def test_committed_results_are_reproduced(capsys):
    # `verify`는 재료가 고정 목록과 같은지, 짝짓기 검증과 기록값 재현이 통과하는지 본 뒤, 지금의 코드와
    # 재료로 결과 파일 둘을 다시 만들어 커밋된 파일과 글자까지 견준다. 0이면 모두 같다. 결과 파일이 없으면
    # 2라서 실패한다(건너뛰지 않는다).
    code = cli.main(["verify", "--repo", str(REPOSITORY)])
    captured = capsys.readouterr()
    assert code == 0, f"verify 종료 코드 {code}\n{captured.out}{captured.err}"


# ---------------------------------------------------------------------------------------------
# 기록값
# ---------------------------------------------------------------------------------------------


def totals(entry: dict, scope: str) -> tuple[int, int]:
    """결과 JSON의 묶음 하나에서 한 범위의 (편집 수, 정답 글자 수)를 꺼낸다."""
    return entry[scope]["edits"], entry[scope]["length"]


def test_results_keep_the_recorded_values(loaded, result):
    entries = {entry["key"]: entry for entry in result["systems"]}
    assert list(entries) == [spec.key for spec in sources.SYSTEMS]
    assert result["utterances"] == len(loaded.hangul)
    assert result["hangul_only"] == sum(loaded.hangul)

    # 전체 범위, voice-translator와 whisper-ko-ft: 공통 정답이 이 묶음들의 정답과 정규화하면 같으므로, 공통
    # 정답으로 센 값이 구성 요소가 자기 정답으로 센 기록값과 같다. 기록값은 voice-translator는 기록값 사전
    # (`recorded.EXPECTED`)의 것이고, whisper-ko-ft는 리포트에 저장된 발화별 값의 합이다.
    expected: dict[str, tuple[int, int]] = {
        key: scopes["all"] for key, scopes in recorded.EXPECTED.items() if COMPONENT[key] != "stt-scratch"
    }
    for key, stored in loaded.stored.items():
        summed = (sum(edits for edits, _ in stored.counts), sum(length for _, length in stored.counts))
        # 사전과 리포트 두 곳에 기록된 묶음은 두 기록이 서로 같아야 한다.
        assert expected.setdefault(key, summed) == summed, f"{key}: 사전의 기록과 리포트의 기록이 다르다"
    assert set(expected) == {key for key, component in COMPONENT.items() if component != "stt-scratch"}
    for key, recorded_value in expected.items():
        assert totals(entries[key], "all") == recorded_value, (
            f"{key}: 결과 {totals(entries[key], 'all')}, 기록 {recorded_value}"
        )

    # 한글 전용 범위, stt-scratch: 한글 전용 행에서는 그 구성 요소의 정답이 공통 정답과 같으므로 기록값과
    # 같다. 전체 범위는 정답이 두 행에서 달라 공통 정답으로 센 값이 기록보다 많아서 견주지 않는다.
    stt_keys = [key for key, component in COMPONENT.items() if component == "stt-scratch"]
    assert stt_keys
    for key in stt_keys:
        recorded_value = recorded.EXPECTED[key]["hangul_only"]
        assert totals(entries[key], "hangul_only") == recorded_value, (
            f"{key}: 결과 {totals(entries[key], 'hangul_only')}, 기록 {recorded_value}"
        )

    # 모든 묶음을 공통 정답으로 세므로 정답 글자 수는 범위마다 묶음 열네 개가 모두 같다.
    for scope in ("all", "hangul_only"):
        lengths = {entry[scope]["length"] for entry in entries.values()}
        assert len(lengths) == 1, f"{scope}: 정답 글자 수가 묶음마다 다르다 {sorted(lengths)}"


# ---------------------------------------------------------------------------------------------
# 문서
# ---------------------------------------------------------------------------------------------


def test_document_table_matches_the_result_file():
    # 문서의 결과 절에 있는 표를 차례로 찾아, 결과 Markdown의 표와 글자까지 견준다. 문서의 규칙 절에 있는
    # 표(재료 표 따위)는 결과 절 앞이라 대상이 아니다. 두 쪽 모두 표가 셋이어야 한다(하나를 빠뜨리거나 더해도
    # 걸린다).
    in_document = table_blocks(result_section(read_text(DOCUMENT)))
    in_result = table_blocks(read_text(RESULT_MARKDOWN))
    assert len(in_result) == TABLE_COUNT, f"{RESULT_MARKDOWN.name}의 표가 {len(in_result)}개다"
    assert len(in_document) == TABLE_COUNT, f"{DOCUMENT.name} 결과 절의 표가 {len(in_document)}개다"
    for number, (document_table, result_table) in enumerate(
        zip(in_document, in_result, strict=True), start=1
    ):
        assert document_table == result_table, (
            f"표 {number}번째가 다르다. {first_difference(document_table, result_table)}"
        )
