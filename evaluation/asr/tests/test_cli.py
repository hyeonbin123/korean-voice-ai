"""명령줄(cli)의 시험: 종료 코드, 출력, 결과 파일, 줄바꿈과 글자 코드.

명령줄은 언제나 실제 크기의 기본값(382발화, 한글 전용 257, 알려진 정답 차이 행 23·57)으로 검증하므로, 이
파일의 시험은 실제 크기의 합성 저장소(`conftest.py`의 `full_repository`)를 쓴다. 그 폴더는 시험 묶음
전체에서 한 번만 만들고, 고치는 시험은 복사해서 고친다. 점수를 매기는 `run`도 한 번만 돌려(`full_results`)
여러 시험이 그 결과를 나눠 쓴다. 그 합성 저장소는 재료의 sha256을 적은 고정 목록(`inputs.sha256`)도 자기
재료로 만들어 두므로, `run`과 `verify`가 끝까지 돈다. 재료를 일부러 바꾸는 시험은 목록을 그대로 두어 `run`과
`verify`가 멈추는 것을 보거나, 목록을 다시 만들어(`repin`) 그 뒤의 검증을 본다.

실제 저장소로는 시험하지 않는다.
"""

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from asr_compare import cli, recorded, sources

JSON_NAME = "fleurs-ko-test.json"
MARKDOWN_NAME = "fleurs-ko-test.md"
FINAL_LINE = "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 0개"


@pytest.fixture(autouse=True)
def recorded_values_of_the_synthetic_repository(monkeypatch, full_repository):
    """구현의 기록값 사전을 합성 저장소의 값으로 바꿔 끼운다.

    명령줄에는 기록값을 바꾸는 옵션이 없다(실제 저장소의 값은 코드에 고정돼 있다). 합성 저장소로 도는 이
    파일의 시험은 그 사전을 이 저장소의 값으로 바꿔서 같은 검사를 돌린다.
    """
    monkeypatch.setattr(recorded, "EXPECTED", full_repository.expected_values())


def reproduction_lines(synthetic) -> list[str]:
    """합성 저장소에서 `check`가 찍어야 하는 재현 줄 열네 개(묶음 차례는 고정 목록의 차례)."""
    lines = []
    for key, scopes in synthetic.recorded_values().items():
        edits, length = scopes["all"]
        line = f"{key}: 기록 {edits}/{length} = 다시 센 {edits}/{length}"
        if "hangul_only" in scopes:
            edits, length = scopes["hangul_only"]
            line += f", 한글 전용 기록 {edits}/{length} = 다시 센 {edits}/{length}"
        lines.append(line)
    return lines


def invoke(capsys, *argv: str):
    """main을 부르고 (종료 코드, 표준 출력, 표준 오류)를 돌려준다."""
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def snapshot(root: Path) -> dict[str, bytes]:
    """폴더 안 모든 파일의 (상대 경로 -> 바이트)."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def results_folder(repository: Path) -> Path:
    return repository / "evaluation" / "asr" / "results"


def put_results(repository: Path, source: Path, *, crlf: bool = False) -> Path:
    """source의 결과 파일 둘을 저장소의 결과 폴더로 복사한다(crlf이면 줄 끝을 CRLF로 바꿔 둔다)."""
    folder = results_folder(repository)
    folder.mkdir(parents=True, exist_ok=True)
    for name in (JSON_NAME, MARKDOWN_NAME):
        data = (source / name).read_bytes()
        (folder / name).write_bytes(data.replace(b"\n", b"\r\n") if crlf else data)
    return folder


PINNED_NAME = "evaluation/asr/inputs.sha256"
SUMMARY_OF_ONE_CHANGED_INPUT = "재료 1개가 고정 목록(evaluation/asr/inputs.sha256)과 다르다"


def pinned_path(repository: Path) -> Path:
    return repository / PINNED_NAME


def digest_of(path: Path) -> str:
    """파일의 sha256. 줄 끝의 CRLF는 LF로 바꾼 바이트에서 센다(구현의 `digest`와 따로 적은 같은 정의다)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def repin(repository: Path) -> None:
    """고정 목록을 지금 재료의 sha256으로 다시 쓴다(재료를 일부러 바꾼 시험이 목록 대조는 통과하게 한다)."""
    path = pinned_path(repository)
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.split("  ", 1)[1]
        lines.append(f"{digest_of(repository / name)}  {name}")
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8", newline="\n")


def change_one_character(path: Path) -> None:
    """리포트의 `model` 값 글자 하나를 바꾼다. 읽는 값은 그대로이고 파일의 sha256만 달라진다."""
    text = path.read_text(encoding="utf-8")
    assert '"model": "synthetic"' in text
    changed = text.replace('"model": "synthetic"', '"model": "synthetid"', 1)
    path.write_text(changed, encoding="utf-8", newline="\n")


@pytest.fixture(scope="session")
def full_results(full_repository, tmp_path_factory):
    """실제 크기의 합성 저장소에 `run`을 한 번 돌린 결과: (결과 폴더, 표준 출력).

    시험 묶음 전체에서 한 번만 돌린다.
    """
    out = tmp_path_factory.mktemp("results") / "out"
    captured = io.StringIO()
    # 함수 범위의 monkeypatch는 세션 fixture에서 쓸 수 없으므로 여기서 따로 끼워 넣고 되돌린다.
    with pytest.MonkeyPatch.context() as patch, contextlib.redirect_stdout(captured):
        patch.setattr(recorded, "EXPECTED", full_repository.expected_values())
        code = cli.main(["run", "--repo", str(full_repository.root), "--out", str(out)])
    assert code == 0, captured.getvalue()
    return out, captured.getvalue()


# ---------------------------------------------------------------------------------------------
# 도움말과 쓰임
# ---------------------------------------------------------------------------------------------

HELP_PHRASES = {
    (): "종료 코드",
    ("check",): "아무것도 쓰지 않습니다",
    ("run",): "--out",
    ("verify",): "다시 만든",
}


@pytest.mark.parametrize("command", list(HELP_PHRASES), ids=["main", "check", "run", "verify"])
def test_help_exits_zero_and_is_written_in_korean(capsys, command):
    code, out, err = invoke(capsys, *command, "--help")
    assert (code, err) == (0, "")
    assert "asr-compare" in out
    # argparse는 도움말을 터미널 폭에 맞춰 줄바꿈하므로, 공백을 하나로 모은 글에서 구절을 찾는다.
    assert HELP_PHRASES[command] in " ".join(out.split())


def test_a_missing_subcommand_is_a_usage_error(capsys):
    code, out, err = invoke(capsys)
    assert (code, out) == (2, "")
    assert "usage" in err


def test_run_needs_the_output_folder(capsys, full_repository):
    code, out, err = invoke(capsys, "run", "--repo", str(full_repository.root))
    assert (code, out) == (2, "")
    assert "--out" in err


def test_the_default_repository_is_the_checkout_that_holds_the_package():
    # 기본 저장소 뿌리는 이 패키지 파일에서 올라간 곳이다(작업 폴더에 기대지 않는다).
    assert (cli.DEFAULT_REPO / "evaluation" / "asr" / "pyproject.toml").is_file()
    assert cli.DEFAULT_REPO == Path(cli.__file__).resolve().parents[4]


# ---------------------------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------------------------


def test_check_passes_on_consistent_inputs(capsys, full_repository):
    # 결합 검증이 통과하면 묶음마다 재현 줄 하나(고정 목록의 차례), 끝 줄에 요약이 온다.
    code, out, err = invoke(capsys, "check", "--repo", str(full_repository.root))
    assert (code, err) == (0, "")
    assert out == "\n".join([*reproduction_lines(full_repository), FINAL_LINE]) + "\n"


def test_check_reproduces_hangul_only_values_only_for_the_component_that_recorded_them(
    capsys, full_repository
):
    # voice-translator와 whisper-ko-ft는 한글 전용 값을 기록하지 않았다. 그 값은 세지도 찍지도 않는다.
    code, out, err = invoke(capsys, "check", "--repo", str(full_repository.root))
    assert (code, err) == (0, "")
    with_hangul_only = [line.split(":")[0] for line in out.splitlines() if "한글 전용 기록" in line]
    assert with_hangul_only == ["stt-scratch-full", "stt-scratch-streaming"]


def test_check_changes_nothing(capsys, full_repository, copy_repository):
    root = copy_repository(full_repository)
    before = snapshot(root)
    invoke(capsys, "check", "--repo", str(root))
    assert snapshot(root) == before


def break_sentences(root: Path, count: int) -> None:
    """voice-turbo 리포트의 앞 count개 발화의 문장 번호를 0으로 바꾼다.

    그러면 문장 번호 검사에 count줄이 걸린다.
    """
    path = root / sources.SYSTEMS[1].path
    document = json.loads(path.read_text(encoding="utf-8"))
    for item in document[0]["languages"]["ko"]["items"][:count]:
        item["id"] = 0
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def test_check_prints_every_mismatch_line_and_counts_them(capsys, full_repository, copy_repository):
    # 줄 수에 상한이 없다. 끝 줄의 어긋남 수와 그 앞에 찍힌 줄 수가 같다.
    root = copy_repository(full_repository)
    break_sentences(root, 60)
    code, out, err = invoke(capsys, "check", "--repo", str(root))
    lines = out.splitlines()
    assert (code, err) == (1, "")
    problems, last = lines[:-1], lines[-1]
    assert len(problems) == 60
    assert all(line.startswith("voice-turbo: 행 ") and "문장 번호" in line for line in problems)
    assert last == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 60개"


def rewrite_whisper_report(root: Path, name: str, change) -> str:
    """whisper-ko-ft 꼴 리포트 하나를 읽어 `change(문서)`로 고쳐 다시 쓴다. 뿌리 기준 경로를 돌려준다."""
    relative = f"whisper-ko-ft/reports/{name}/fleurs-ko-test.json"
    path = root / relative
    document = json.loads(path.read_text(encoding="utf-8"))
    change(document)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return relative


def test_check_reports_a_recorded_value_that_is_not_reproduced(capsys, full_repository, monkeypatch):
    # 기록값 하나를 틀리게 하면 그 묶음의 줄에 기록값과 다시 센 값이 함께 보이고, 어긋남 수에 한 개로
    # 들어간다.
    values = full_repository.expected_values()
    edits, length = values["voice-turbo"]["all"]
    values["voice-turbo"]["all"] = (edits + 1, length)
    monkeypatch.setattr(recorded, "EXPECTED", values)
    code, out, err = invoke(capsys, "check", "--repo", str(full_repository.root))
    assert (code, err) == (1, "")
    expected = reproduction_lines(full_repository)
    expected[1] = f"voice-turbo: 기록 {edits + 1}/{length} ≠ 다시 센 {edits}/{length}"
    assert out.splitlines() == [*expected, "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 1개"]


def test_check_holds_whisper_large_v3_turbo_to_the_recorded_sum_in_the_dictionary(
    capsys, full_repository, monkeypatch
):
    # 이 묶음은 리포트에 저장된 값과 사전의 기록값 둘이 있다. 줄에 보이는 기록값은 사전의 것이고, 사전의 값이
    # 틀리면(리포트의 저장된 값은 맞아도) 어긋남이다.
    values = full_repository.expected_values()
    edits, length = values["whisper-large-v3-turbo"]["all"]
    values["whisper-large-v3-turbo"]["all"] = (edits + 1, length)
    monkeypatch.setattr(recorded, "EXPECTED", values)
    code, out, err = invoke(capsys, "check", "--repo", str(full_repository.root))
    assert (code, err) == (1, "")
    expected = reproduction_lines(full_repository)
    expected[3] = f"whisper-large-v3-turbo: 기록 {edits + 1}/{length} ≠ 다시 센 {edits}/{length}"
    assert out.splitlines() == [*expected, "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 1개"]


def test_check_reports_a_hangul_only_record_that_is_not_reproduced(capsys, full_repository, monkeypatch):
    values = full_repository.expected_values()
    edits, length = values["stt-scratch-streaming"]["hangul_only"]
    values["stt-scratch-streaming"]["hangul_only"] = (edits, length + 1)
    monkeypatch.setattr(recorded, "EXPECTED", values)
    code, out, err = invoke(capsys, "check", "--repo", str(full_repository.root))
    assert (code, err) == (1, "")
    all_edits, all_length = values["stt-scratch-streaming"]["all"]
    line = out.splitlines()[13]
    assert line == (
        f"stt-scratch-streaming: 기록 {all_edits}/{all_length} = 다시 센 {all_edits}/{all_length}, "
        f"한글 전용 기록 {edits}/{length + 1} ≠ 다시 센 {edits}/{length}"
    )
    assert out.splitlines()[-1] == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 1개"


def test_check_reports_a_stored_utterance_count_that_is_not_reproduced(
    capsys, full_repository, copy_repository
):
    # whisper-ko-ft 꼴 파일에 저장된 발화별 edits 하나가 다시 센 값과 다르다.
    root = copy_repository(full_repository)

    def raise_one(document):
        document["utterances"][5]["edits"] += 1

    rewrite_whisper_report(root, "whisper-small", raise_one)
    code, out, err = invoke(capsys, "check", "--repo", str(root))
    assert (code, err) == (1, "")
    edits, length = full_repository.recorded_values()["whisper-small"]["all"]
    lines = out.splitlines()
    head = f"whisper-small: 기록 {edits + 1}/{length} ≠ 다시 센 {edits}/{length}"
    assert lines[2] == f"{head}, 발화별 기록과 다른 행 1개(행 5)"
    assert [line for line in lines if "≠" in line] == [lines[2]]
    assert lines[-1] == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 1개"


def test_check_reports_stored_counts_that_cancel_out_in_the_sum(capsys, full_repository, copy_repository):
    # 발화별 값 둘이 서로 상쇄돼 합은 같아도 발화별 기록이 다르면 어긋남이다.
    root = copy_repository(full_repository)
    lowered = []

    def move_one_edit(document):
        rows = document["utterances"]
        other = next(row for row in range(4, len(rows)) if rows[row]["edits"] > 0)
        rows[3]["edits"] += 1
        rows[other]["edits"] -= 1
        lowered.append(other)

    rewrite_whisper_report(root, "turbo-t", move_one_edit)
    code, out, err = invoke(capsys, "check", "--repo", str(root))
    assert (code, err) == (1, "")
    edits, length = full_repository.recorded_values()["turbo-t"]["all"]
    head = f"turbo-t: 기록 {edits}/{length} = 다시 센 {edits}/{length}"
    assert f"{head}, 발화별 기록과 다른 행 2개(행 3, {lowered[0]})" in out.splitlines()
    assert out.splitlines()[-1] == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 1개"


def test_check_lists_only_the_first_rows_when_many_stored_counts_differ(
    capsys, full_repository, copy_repository
):
    root = copy_repository(full_repository)

    def raise_seven(document):
        for row in range(7):
            document["utterances"][row]["edits"] += 1

    rewrite_whisper_report(root, "turbo-l2", raise_seven)
    code, out, err = invoke(capsys, "check", "--repo", str(root))
    assert (code, err) == (1, "")
    (line,) = [line for line in out.splitlines() if line.startswith("turbo-l2: ")]
    assert line.endswith(", 발화별 기록과 다른 행 7개(행 0, 1, 2, 3, 4 외 2개)")
    assert out.splitlines()[-1] == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 1개"


def test_check_reports_a_recorded_error_rate_that_is_not_reproduced(capsys, full_repository, copy_repository):
    root = copy_repository(full_repository)

    def other_rate(document):
        document["summary"]["error_rate"] = 0.5

    rewrite_whisper_report(root, "small-a", other_rate)
    code, out, err = invoke(capsys, "check", "--repo", str(root))
    assert (code, err) == (1, "")
    edits, length = full_repository.recorded_values()["small-a"]["all"]
    head = f"small-a: 기록 {edits}/{length} = 다시 센 {edits}/{length}"
    assert f"{head}, 기록 오류율 0.5 ≠ 다시 센 {round(edits / length, 5)}" in out.splitlines()
    assert out.splitlines()[-1] == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 1개"


def test_check_counts_every_system_that_is_not_reproduced(
    capsys, full_repository, copy_repository, monkeypatch
):
    # 어긋남 수 = 재현이 다른 묶음의 수. 한 묶음에서 어긋나는 곳이 여럿이어도 그 묶음은 한 개다.
    root = copy_repository(full_repository)

    def raise_two(document):
        document["utterances"][0]["edits"] += 1
        document["utterances"][1]["edits"] += 1
        document["summary"]["error_rate"] = 0.5

    rewrite_whisper_report(root, "turbo-l2", raise_two)
    values = full_repository.expected_values()
    edits, length = values["voice-turbo-vad"]["all"]
    values["voice-turbo-vad"]["all"] = (edits, length + 1)
    monkeypatch.setattr(recorded, "EXPECTED", values)
    code, out, err = invoke(capsys, "check", "--repo", str(root))
    assert (code, err) == (1, "")
    lines = out.splitlines()
    assert [line.split(":")[0] for line in lines if "≠" in line] == ["voice-turbo-vad", "turbo-l2"]
    assert lines[-1] == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 2개"


def test_check_reports_a_missing_stored_count_as_unreadable(capsys, full_repository, copy_repository):
    root = copy_repository(full_repository)
    relative = rewrite_whisper_report(
        root, "small-a", lambda document: document["utterances"][2].pop("edits")
    )
    code, out, err = invoke(capsys, "check", "--repo", str(root))
    assert (code, out) == (2, "")
    assert err.splitlines() == [f"{relative}: utterances[2]: 'edits' 키가 없다"]


def test_check_reports_a_stored_count_of_the_wrong_type_as_unreadable(
    capsys, full_repository, copy_repository
):
    root = copy_repository(full_repository)

    def make_text(document):
        document["utterances"][4]["length"] = "46"

    relative = rewrite_whisper_report(root, "turbo-n", make_text)
    code, out, err = invoke(capsys, "check", "--repo", str(root))
    assert (code, out) == (2, "")
    assert err.splitlines() == [f"{relative}: utterances[4].length: 정수가 아니다(str)"]


def test_check_reports_a_missing_recorded_error_rate_as_unreadable(capsys, full_repository, copy_repository):
    root = copy_repository(full_repository)
    relative = rewrite_whisper_report(
        root, "turbo-n2", lambda document: document["summary"].pop("error_rate")
    )
    code, out, err = invoke(capsys, "check", "--repo", str(root))
    assert (code, out) == (2, "")
    assert err.splitlines() == [f"{relative}: summary: 'error_rate' 키가 없다"]


def test_check_reports_a_missing_file_as_unreadable(capsys, full_repository, copy_repository):
    root = copy_repository(full_repository)
    missing = sources.SYSTEMS[2].path
    (root / missing).unlink()
    code, out, err = invoke(capsys, "check", "--repo", str(root))
    assert (code, out) == (2, "")
    assert err.splitlines() == [f"{missing}: 파일이 없다"]


def test_check_reports_a_broken_json_file_as_unreadable(capsys, full_repository, copy_repository):
    root = copy_repository(full_repository)
    broken = sources.SYSTEMS[0].path
    (root / broken).write_bytes(b"[{")
    code, out, err = invoke(capsys, "check", "--repo", str(root))
    assert (code, out) == (2, "")
    assert len(err.splitlines()) == 1
    assert err.startswith(f"{broken}: JSON 문법 오류")


def test_check_reports_a_missing_repository_folder(capsys, tmp_path):
    code, out, err = invoke(capsys, "check", "--repo", str(tmp_path / "nowhere"))
    assert (code, out) == (2, "")
    assert "저장소 폴더" in err


# ---------------------------------------------------------------------------------------------
# 기록값 재현(recorded): 손으로 만든 작은 묶음으로
# ---------------------------------------------------------------------------------------------


def tiny_loaded(rows, *, hangul=None, stored=None) -> sources.Loaded:
    """묶음 하나(키 solo)만 가진 읽은 재료. rows는 (정답, 가설) 쌍의 목록이다."""
    utterances = tuple(
        sources.Utterance(row, str(row), 1.0, reference, hypothesis)
        for row, (reference, hypothesis) in enumerate(rows)
    )
    system = sources.System("solo", "stt-scratch", "solo.jsonl", (), utterances)
    flags = tuple(hangul) if hangul is not None else (False,) * len(utterances)
    return sources.Loaded((system,), {}, flags, (), stored or {})


def test_the_hangul_only_sum_is_counted_over_the_rows_the_manifest_marks(monkeypatch):
    rows = [("가나다", "가나다"), ("라마바", "라마"), ("사아자", "사아차")]
    loaded = tiny_loaded(rows, hangul=(True, False, True))
    monkeypatch.setattr(recorded, "EXPECTED", {"solo": {"all": (2, 9), "hangul_only": (1, 6)}})
    (result,) = recorded.reproduce(loaded)
    assert result.matches
    assert result.line == "solo: 기록 2/9 = 다시 센 2/9, 한글 전용 기록 1/6 = 다시 센 1/6"


def test_a_reference_that_normalises_to_nothing_is_reported_not_raised(monkeypatch):
    # 글자 오류율의 분모가 0이 되는 행이 있으면 다시 셀 수 없다. 죽지 않고 그 묶음의 줄로 알린다.
    loaded = tiny_loaded([("가나다", "가나다"), ("...", "가"), ("?!", "나")])
    monkeypatch.setattr(recorded, "EXPECTED", {"solo": {"all": (0, 3)}})
    (result,) = recorded.reproduce(loaded)
    assert not result.matches
    assert result.line == "solo: 정규화한 정답이 빈 글인 행이 있어 다시 셀 수 없다(행 1, 2)"


def test_a_recorded_name_that_no_system_has_is_a_program_error(monkeypatch):
    # 기록값 사전의 이름이 틀리면 조용히 건너뛰지 않는다(사람의 입력이 아니라 프로그램의 잘못이다).
    loaded = tiny_loaded([("가나다", "가나다")])
    monkeypatch.setattr(recorded, "EXPECTED", {"solo": {"all": (0, 3)}, "nobody": {"all": (0, 1)}})
    with pytest.raises(ValueError, match="nobody"):
        recorded.reproduce(loaded)


def test_an_unknown_scope_in_the_recorded_values_is_a_program_error(monkeypatch):
    loaded = tiny_loaded([("가나다", "가나다")])
    monkeypatch.setattr(recorded, "EXPECTED", {"solo": {"all": (0, 3), "hangul": (0, 3)}})
    with pytest.raises(ValueError, match="hangul"):
        recorded.reproduce(loaded)


def test_a_system_with_nothing_recorded_to_reproduce_is_a_program_error(monkeypatch):
    loaded = tiny_loaded([("가나다", "가나다")])
    monkeypatch.setattr(recorded, "EXPECTED", {})
    with pytest.raises(ValueError, match="solo"):
        recorded.reproduce(loaded)


# ---------------------------------------------------------------------------------------------
# check --print-inputs와 재료 고정 목록(inputs.sha256)
# ---------------------------------------------------------------------------------------------


def test_check_help_names_the_print_inputs_option(capsys):
    code, out, err = invoke(capsys, "check", "--help")
    assert (code, err) == (0, "")
    assert "--print-inputs" in out


def test_print_inputs_prints_one_line_per_material_in_path_order(capsys, full_repository):
    code, out, err = invoke(capsys, "check", "--print-inputs", "--repo", str(full_repository.root))
    assert (code, err) == (0, "")
    assert out == "".join(line + "\n" for line in full_repository.pinned_lines())
    paths = [line.split("  ", 1)[1] for line in out.splitlines()]
    assert len(paths) == 19 and paths == sorted(paths)
    assert all(len(line.split("  ", 1)[0]) == 64 for line in out.splitlines())


def test_print_inputs_gives_the_same_values_whatever_the_checkout_line_endings(
    capsys, full_repository, full_repository_crlf
):
    # 줄 끝의 CR을 뗀 바이트로 세므로, 줄바꿈 변환을 켠 채 받은 복제본에서도 같은 목록이 나온다.
    lf = invoke(capsys, "check", "--print-inputs", "--repo", str(full_repository.root))
    crlf = invoke(capsys, "check", "--print-inputs", "--repo", str(full_repository_crlf.root))
    assert lf[0] == 0
    assert lf == crlf


def test_print_inputs_does_not_verify_or_reproduce(capsys, full_repository, copy_repository):
    # 짝짓기 검증에 걸릴 재료도 목록에는 그대로 오른다. 검증 줄, 재현 줄, 요약 줄은 찍지 않는다.
    root = copy_repository(full_repository)
    break_sentences(root, 5)
    code, out, err = invoke(capsys, "check", "--print-inputs", "--repo", str(root))
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert len(lines) == 19
    changed = sources.SYSTEMS[1].path
    assert [line for line in lines if line not in full_repository.pinned_lines()] == [
        f"{digest_of(root / changed)}  {changed}"
    ]


def test_print_inputs_reports_a_missing_material_as_unreadable(capsys, full_repository, copy_repository):
    root = copy_repository(full_repository)
    missing = sources.SYSTEMS[2].path
    (root / missing).unlink()
    code, out, err = invoke(capsys, "check", "--print-inputs", "--repo", str(root))
    assert (code, out) == (2, "")
    assert err.splitlines() == [f"{missing}: 파일이 없다"]


def test_check_does_not_need_the_pinned_list(capsys, full_repository, copy_repository):
    # 고정 목록은 `check --print-inputs`가 만드는 것이다. 목록이 없거나 재료와 달라도 check는 돈다.
    root = copy_repository(full_repository)
    pinned_path(root).unlink()
    assert invoke(capsys, "check", "--repo", str(root))[0] == 0
    assert invoke(capsys, "check", "--print-inputs", "--repo", str(root))[0] == 0
    pinned_path(root).write_text("not a list\n", encoding="utf-8", newline="\n")
    assert invoke(capsys, "check", "--repo", str(root))[0] == 0


# ---------------------------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------------------------


def test_run_refuses_inputs_that_changed_after_the_rules(capsys, full_repository, copy_repository, tmp_path):
    # 재료 파일의 글자 하나만 달라도 run은 1로 멈추고 결과 파일을 하나도 만들지 않는다.
    root = copy_repository(full_repository)
    material = sources.SYSTEMS[1].path
    change_one_character(root / material)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    code, out, err = invoke(capsys, "run", "--repo", str(root), "--out", str(out_dir))
    assert (code, err) == (1, "")
    pinned = dict(full_repository.pinned_entries)[material]
    assert out.splitlines() == [
        f"{material}: 값이 다르다(고정 {pinned}, 지금 {digest_of(root / material)})",
        SUMMARY_OF_ONE_CHANGED_INPUT,
    ]
    assert list(out_dir.iterdir()) == []


def test_run_without_the_pinned_list_is_an_error(capsys, full_repository, copy_repository, tmp_path):
    root = copy_repository(full_repository)
    pinned_path(root).unlink()
    out_dir = tmp_path / "out"
    code, out, err = invoke(capsys, "run", "--repo", str(root), "--out", str(out_dir))
    assert (code, out) == (2, "")
    assert err.splitlines() == [f"{PINNED_NAME}: 파일이 없다"]
    assert not out_dir.exists()


def test_run_names_every_input_that_differs_from_the_pinned_list(
    capsys, full_repository, copy_repository, tmp_path
):
    # 다른 곳이 세 가지다: 값이 다름, 목록에 없음, 재료에 없음. 경로 순으로 한 줄씩 찍고 끝 줄에 개수를
    # 적는다.
    root = copy_repository(full_repository)
    entries = dict(full_repository.pinned_entries)
    changed, dropped = sources.SYSTEMS[1].path, sources.SYSTEMS[5].path
    stale = "whisper-ko-ft/reports/gone/fleurs-ko-test.json"
    change_one_character(root / changed)
    lines = [line for line in full_repository.pinned_lines() if not line.endswith("  " + dropped)]
    lines.append("a" * 64 + "  " + stale)
    pinned_path(root).write_text("".join(line + "\n" for line in lines), encoding="utf-8", newline="\n")
    out_dir = tmp_path / "out"
    code, out, err = invoke(capsys, "run", "--repo", str(root), "--out", str(out_dir))
    assert (code, err) == (1, "")
    expected = sorted(
        [
            (changed, f"{changed}: 값이 다르다(고정 {entries[changed]}, 지금 {digest_of(root / changed)})"),
            (dropped, f"{dropped}: 고정 목록에 없다(지금 {entries[dropped]})"),
            (stale, f"{stale}: 지금 재료에 없다(고정 {'a' * 64})"),
        ]
    )
    assert out.splitlines() == [
        *(line for _, line in expected),
        "재료 3개가 고정 목록(evaluation/asr/inputs.sha256)과 다르다",
    ]
    assert not out_dir.exists()


def test_run_compares_with_the_pinned_list_before_the_verification(
    capsys, full_repository, copy_repository, tmp_path
):
    # 재료가 고정 목록과 다르면 짝짓기 검증보다 먼저 멈춘다: 검증 줄도 검증의 요약 줄도 나오지 않는다.
    root = copy_repository(full_repository)
    break_sentences(root, 3)
    code, out, err = invoke(capsys, "run", "--repo", str(root), "--out", str(tmp_path / "out"))
    assert (code, err) == (1, "")
    assert "문장 번호" not in out and "어긋남 3개" not in out
    assert out.splitlines()[-1] == SUMMARY_OF_ONE_CHANGED_INPUT


def test_run_accepts_a_list_made_by_print_inputs(capsys, full_repository, copy_repository, tmp_path):
    # 재료를 바꾸면 run이 멈추고, `check --print-inputs`의 출력을 목록으로 삼으면 그 재료로 돈다.
    root = copy_repository(full_repository)
    change_one_character(root / sources.SYSTEMS[1].path)
    assert invoke(capsys, "run", "--repo", str(root), "--out", str(tmp_path / "refused"))[0] == 1
    code, out, err = invoke(capsys, "check", "--print-inputs", "--repo", str(root))
    assert (code, err) == (0, "")
    pinned_path(root).write_bytes(out.encode("utf-8"))
    code, _, err = invoke(capsys, "run", "--repo", str(root), "--out", str(tmp_path / "out"))
    assert (code, err) == (0, "")
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [JSON_NAME, MARKDOWN_NAME]


def test_a_pinned_list_with_crlf_line_endings_is_accepted(capsys, full_repository, copy_repository, tmp_path):
    # 줄바꿈 변환을 켠 채 받은 복제본에서는 목록의 줄 끝도 CRLF로 들어온다.
    root = copy_repository(full_repository)
    path = pinned_path(root)
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    code, _, err = invoke(capsys, "run", "--repo", str(root), "--out", str(tmp_path / "out"))
    assert (code, err) == (0, "")


MALFORMED_LISTS = (
    "empty-file",
    "one-space-between-the-fields",
    "digest-too-short",
    "digest-in-capitals",
    "blank-line-between-entries",
    "byte-order-mark",
    "same-path-twice",
)


def malformed_lists(good: list[str]) -> dict[str, tuple[bytes, str]]:
    """꼴이 깨진 고정 목록 몇 가지: 이름 -> (파일 내용, 오류 메시지가 `<경로>: `에 이어 가져야 하는 글)."""

    def joined(lines: list[str]) -> bytes:
        return "".join(line + "\n" for line in lines).encode("utf-8")

    def not_a_line(number: int) -> str:
        return f"{number}번째 줄이 '<sha256>  <경로>' 꼴이 아니다"

    first = good[0]
    return {
        "empty-file": (b"", "적힌 재료가 하나도 없다"),
        "one-space-between-the-fields": (
            joined([*good[:2], good[2].replace("  ", " ", 1), *good[3:]]),
            not_a_line(3),
        ),
        "digest-too-short": (joined([first[1:], *good[1:]]), not_a_line(1)),
        "digest-in-capitals": (joined([first[:64].upper() + first[64:], *good[1:]]), not_a_line(1)),
        "blank-line-between-entries": (joined([first, "", *good[1:]]), not_a_line(2)),
        "byte-order-mark": (b"\xef\xbb\xbf" + joined(good), not_a_line(1)),
        "same-path-twice": (
            joined([*good, first]),
            f"{len(good) + 1}번째 줄: 경로 '{first.split('  ', 1)[1]}'가 두 번 나온다",
        ),
    }


@pytest.mark.parametrize("name", MALFORMED_LISTS)
def test_run_rejects_a_malformed_pinned_list(capsys, full_repository, copy_repository, tmp_path, name):
    root = copy_repository(full_repository)
    content, reason = malformed_lists(full_repository.pinned_lines())[name]
    pinned_path(root).write_bytes(content)
    out_dir = tmp_path / "out"
    code, out, err = invoke(capsys, "run", "--repo", str(root), "--out", str(out_dir))
    assert (code, out) == (2, "")
    assert err.splitlines() == [f"{PINNED_NAME}: {reason}"]
    assert not out_dir.exists()


def test_run_rejects_a_pinned_list_that_is_not_utf8(capsys, full_repository, copy_repository, tmp_path):
    root = copy_repository(full_repository)
    pinned_path(root).write_bytes(b"\xff\xfe" + b"x" * 10)
    code, out, err = invoke(capsys, "run", "--repo", str(root), "--out", str(tmp_path / "out"))
    assert (code, out) == (2, "")
    assert len(err.splitlines()) == 1 and err.startswith(f"{PINNED_NAME}: UTF-8로 읽을 수 없다")


def test_run_reports_a_pinned_list_that_cannot_be_read(capsys, full_repository, copy_repository, tmp_path):
    # 목록 자리에 파일이 아닌 것(폴더)이 있다.
    root = copy_repository(full_repository)
    pinned_path(root).unlink()
    pinned_path(root).mkdir()
    code, out, err = invoke(capsys, "run", "--repo", str(root), "--out", str(tmp_path / "out"))
    assert (code, out) == (2, "")
    assert len(err.splitlines()) == 1 and err.startswith(f"{PINNED_NAME}: 파일을 읽지 못했다(")


def test_run_writes_both_result_files(full_results):
    out_dir, printed = full_results
    assert sorted(p.name for p in out_dir.iterdir()) == [JSON_NAME, MARKDOWN_NAME]
    for path in out_dir.iterdir():
        data = path.read_bytes()
        assert b"\r" not in data
        assert data.endswith(b"\n") and not data.endswith(b"\n\n")
        assert not data.startswith(b"\xef\xbb\xbf")
    document = json.loads((out_dir / JSON_NAME).read_text(encoding="utf-8"))
    assert (document["utterances"], document["hangul_only"]) == (382, 257)
    assert [system["key"] for system in document["systems"]] == [spec.key for spec in sources.SYSTEMS]
    # 같은 가설이라고 적힌 형제 리포트의 이름이 해당 묶음 항목에 실린다.
    assert {system["key"]: system["also"] for system in document["systems"]} == {
        spec.key: list(spec.also) for spec in sources.SYSTEMS
    }
    assert [pair["id"] for pair in document["pairs"]] == ["decoding-path", "vad", "both"]
    assert len(document["inputs"]) == 19
    lines = printed.splitlines()
    assert lines[0] == FINAL_LINE
    assert [Path(line.split(": ", 1)[1]).name for line in lines[1:]] == [JSON_NAME, MARKDOWN_NAME]


def test_run_writes_nothing_when_the_join_fails(capsys, full_repository, copy_repository, tmp_path):
    root = copy_repository(full_repository)
    break_sentences(root, 3)
    repin(root)  # 고정 목록 대조는 통과하고 짝짓기 검증에서 멈추게 한다
    out_dir = tmp_path / "must-not-exist"
    code, out, err = invoke(capsys, "run", "--repo", str(root), "--out", str(out_dir))
    assert (code, err) == (1, "")
    assert out.splitlines()[-1] == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 3개"
    assert not out_dir.exists()


def test_run_writes_nothing_when_a_recorded_value_is_not_reproduced(
    capsys, full_repository, tmp_path, monkeypatch
):
    # run도 check와 같은 관문을 지난다. 기록값이 재현되지 않으면 결과 파일을 쓰지 않고 그 줄들을 찍는다.
    values = full_repository.expected_values()
    edits, length = values["voice-turbo-vad"]["all"]
    values["voice-turbo-vad"]["all"] = (edits + 1, length)
    monkeypatch.setattr(recorded, "EXPECTED", values)
    out_dir = tmp_path / "must-not-exist"
    code, out, err = invoke(capsys, "run", "--repo", str(full_repository.root), "--out", str(out_dir))
    assert (code, err) == (1, "")
    lines = out.splitlines()
    assert len(lines) == 15
    assert lines[0] == f"voice-turbo-vad: 기록 {edits + 1}/{length} ≠ 다시 센 {edits}/{length}"
    assert lines[-1] == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 1개"
    assert not out_dir.exists()


def test_run_creates_missing_folders_relative_to_the_working_directory(
    capsys, full_repository, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    code, _, err = invoke(capsys, "run", "--repo", str(full_repository.root), "--out", "a/b/out")
    assert (code, err) == (0, "")
    assert sorted(p.name for p in (tmp_path / "a" / "b" / "out").iterdir()) == [JSON_NAME, MARKDOWN_NAME]


def test_run_reports_an_output_path_that_cannot_be_written(capsys, full_repository, tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    code, out, err = invoke(capsys, "run", "--repo", str(full_repository.root), "--out", str(blocker / "out"))
    assert code == 2
    assert len(err.splitlines()) == 1
    assert out.splitlines()[0] == FINAL_LINE


# ---------------------------------------------------------------------------------------------
# 처음부터 끝까지, verify
# ---------------------------------------------------------------------------------------------


def test_full_size_synthetic_inputs_run_end_to_end(capsys, full_repository, full_results, copy_repository):
    # check → run → (결과를 저장소의 결과 폴더에 두고) verify가 끝까지 돈다. 실제 재료로는 run을 돌려 볼 수
    # 없으므로 실제와 같은 꼴과 크기의 합성 재료로 이 흐름 전체를 시험한다.
    out_dir, _ = full_results
    assert invoke(capsys, "check", "--repo", str(full_repository.root))[0] == 0
    root = copy_repository(full_repository)
    put_results(root, out_dir)
    code, out, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, err) == (0, "")
    # 통과하면 이미 있던 대로 조용하다: 재현 줄이나 요약 줄을 찍지 않고 같다는 한 줄만 쓴다.
    assert len(out.splitlines()) == 1 and "같다" in out


def test_verify_without_result_files_is_an_error(capsys, full_repository, copy_repository):
    # 견줄 것이 없는데 통과하면 안 된다.
    root = copy_repository(full_repository)
    code, out, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, out) == (2, "")
    assert JSON_NAME in err and MARKDOWN_NAME in err


def test_verify_with_only_one_result_file_is_an_error(capsys, full_repository, full_results, copy_repository):
    out_dir, _ = full_results
    root = copy_repository(full_repository)
    folder = put_results(root, out_dir)
    (folder / MARKDOWN_NAME).unlink()
    code, out, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, out) == (2, "")
    assert MARKDOWN_NAME in err and JSON_NAME not in err


def test_verify_names_the_file_and_the_first_different_line(
    capsys, full_repository, full_results, copy_repository
):
    out_dir, _ = full_results
    root = copy_repository(full_repository)
    folder = put_results(root, out_dir)
    # JSON: 두 번째 줄의 글자 하나(결과의 형식 번호)를 바꾼다. Markdown: 끝에 줄 하나를 더한다.
    changed = (folder / JSON_NAME).read_text(encoding="utf-8").replace("asr-compare/1", "asr-compare/2", 1)
    (folder / JSON_NAME).write_text(changed, encoding="utf-8", newline="\n")
    markdown = (folder / MARKDOWN_NAME).read_text(encoding="utf-8")
    (folder / MARKDOWN_NAME).write_text(markdown + "덧붙인 줄\n", encoding="utf-8", newline="\n")
    code, out, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, err) == (1, "")
    expected_markdown_line = len(markdown.splitlines()) + 1
    assert out.splitlines() == [
        f"{JSON_NAME}: 2번째 줄부터 다르다",
        f"{MARKDOWN_NAME}: {expected_markdown_line}번째 줄부터 다르다",
    ]


def test_verify_does_not_ignore_a_byte_order_mark_in_a_result_file(
    capsys, full_repository, full_results, copy_repository
):
    # 재료는 앞의 BOM을 버리고 읽지만, 결과 파일은 바이트가 정확히 같아야 한다. 줄 끝만 LF로 맞추고 BOM은
    # 떼지 않으므로, BOM이 붙은 결과 파일은 다른 것으로 알린다(첫 줄부터 다르다).
    out_dir, _ = full_results
    root = copy_repository(full_repository)
    folder = put_results(root, out_dir)
    (folder / JSON_NAME).write_bytes(b"\xef\xbb\xbf" + (folder / JSON_NAME).read_bytes())
    code, out, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, err) == (1, "")
    assert out.splitlines() == [f"{JSON_NAME}: 1번째 줄부터 다르다"]


def test_verify_does_not_compare_when_a_recorded_value_is_not_reproduced(
    capsys, full_repository, full_results, copy_repository, monkeypatch
):
    # verify도 같은 관문을 지난다. 기록값이 재현되지 않으면 결과 파일을 견주지 않고 그 줄들을 찍는다.
    out_dir, _ = full_results
    root = copy_repository(full_repository)
    put_results(root, out_dir)
    values = full_repository.expected_values()
    edits, length = values["stt-scratch-full"]["all"]
    values["stt-scratch-full"]["all"] = (edits, length + 1)
    monkeypatch.setattr(recorded, "EXPECTED", values)
    code, out, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, err) == (1, "")
    lines = out.splitlines()
    assert len(lines) == 15
    assert [line.split(":")[0] for line in lines if "≠" in line] == ["stt-scratch-full"]
    assert lines[-1] == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 1개"
    assert "같다" not in out


def test_verify_refuses_inputs_that_changed_after_the_rules(
    capsys, full_repository, full_results, copy_repository
):
    # 재료가 고정 목록과 다르면 결과를 다시 만들어 견주기 전에 1로 멈춘다. 결과가 다른 까닭이 재료인지
    # 코드인지 출력에서 가를 수 있게 하려는 것이다(결과 파일 줄은 나오지 않는다).
    out_dir, _ = full_results
    root = copy_repository(full_repository)
    put_results(root, out_dir)
    material = sources.SYSTEMS[1].path
    change_one_character(root / material)
    code, out, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, err) == (1, "")
    pinned = dict(full_repository.pinned_entries)[material]
    assert out.splitlines() == [
        f"{material}: 값이 다르다(고정 {pinned}, 지금 {digest_of(root / material)})",
        SUMMARY_OF_ONE_CHANGED_INPUT,
    ]


def test_verify_compares_with_the_pinned_list_before_the_verification(
    capsys, full_repository, full_results, copy_repository
):
    # run과 같은 차례다. 재료가 고정 목록과 다르면 짝짓기 검증보다 먼저 멈춘다.
    out_dir, _ = full_results
    root = copy_repository(full_repository)
    put_results(root, out_dir)
    break_sentences(root, 3)
    code, out, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, err) == (1, "")
    assert "문장 번호" not in out and "어긋남 3개" not in out
    assert out.splitlines()[-1] == SUMMARY_OF_ONE_CHANGED_INPUT


def test_verify_without_the_pinned_list_is_an_error(capsys, full_repository, full_results, copy_repository):
    out_dir, _ = full_results
    root = copy_repository(full_repository)
    put_results(root, out_dir)
    pinned_path(root).unlink()
    code, out, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, out) == (2, "")
    assert err.splitlines() == [f"{PINNED_NAME}: 파일이 없다"]


def test_verify_notices_when_a_material_file_changed_after_the_results_were_made(
    capsys, full_repository, full_results, copy_repository
):
    # 고정 목록을 새 재료에 맞게 다시 만들었어도 결과 파일은 옛 재료로 만든 것이다. 재료의 sha256이 결과
    # 파일에 들어 있어서, 짝짓기 검증을 통과하는 작은 변경(읽지 않는 키)도 결과가 낡았다고 알린다.
    out_dir, _ = full_results
    root = copy_repository(full_repository)
    put_results(root, out_dir)
    path = root / sources.SYSTEMS[1].path
    document = json.loads(path.read_text(encoding="utf-8"))
    document[0]["variant"] = "changed after the results were made"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    code, printed, err = invoke(capsys, "check", "--print-inputs", "--repo", str(root))
    assert (code, err) == (0, "")
    pinned_path(root).write_bytes(printed.encode("utf-8"))
    code, out, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, err) == (1, "")
    assert [line.split(":")[0] for line in out.splitlines()] == [JSON_NAME]


def test_verify_reports_mismatches_of_the_materials_instead_of_comparing(
    capsys, full_repository, full_results, copy_repository
):
    out_dir, _ = full_results
    root = copy_repository(full_repository)
    put_results(root, out_dir)
    break_sentences(root, 2)
    repin(root)  # 고정 목록 대조는 통과하고 짝짓기 검증에서 멈추게 한다
    code, out, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, err) == (1, "")
    assert out.splitlines()[-1] == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 2개"


def test_results_do_not_depend_on_checkout_line_endings(
    capsys, full_results, full_repository_crlf, copy_repository, tmp_path
):
    # 모든 재료가 CRLF인 복제본에서 run을 돌려도 결과 파일의 바이트가 같고, 결과 파일도 CRLF로 받은 꼴이어도
    # verify가 통과한다.
    out_dir, _ = full_results
    crlf_out = tmp_path / "crlf-out"
    code, _, err = invoke(capsys, "run", "--repo", str(full_repository_crlf.root), "--out", str(crlf_out))
    assert (code, err) == (0, "")
    for name in (JSON_NAME, MARKDOWN_NAME):
        assert (crlf_out / name).read_bytes() == (out_dir / name).read_bytes()
    root = copy_repository(full_repository_crlf)
    put_results(root, out_dir, crlf=True)
    code, _, err = invoke(capsys, "verify", "--repo", str(root))
    assert (code, err) == (0, "")


# ---------------------------------------------------------------------------------------------
# 글자 코드와 줄바꿈(자식 프로세스로 파이프 출력을 본다)
# ---------------------------------------------------------------------------------------------


def child_environment() -> dict[str, str]:
    """표준 출력의 기본 인코딩이 cp949로 정해진 환경.

    환경 변수를 빼기만 하면 리눅스에서는 UTF-8이 기본이라 보호가 시험되지 않는다. 그래서 cp949를 일부러 준다.
    """
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "cp949"
    environment.pop("PYTHONUTF8", None)
    return environment


# 자식 프로세스에는 monkeypatch가 닿지 않는다. 합성 저장소의 기록값을 인자로 받아 사전에 끼워 넣은 뒤
# `cli.main`을 부르는 짧은 글을 `-c`로 준다(출력 설정은 `main`이 시작할 때 하므로 같은 길을 지난다).
CHILD_SCRIPT = (
    "import ast, sys\n"
    "from asr_compare import cli, recorded\n"
    "recorded.EXPECTED = ast.literal_eval(sys.argv[1])\n"
    "sys.exit(cli.main(sys.argv[2:]))\n"
)


def child_command(synthetic, *arguments: str) -> list[str]:
    return [sys.executable, "-c", CHILD_SCRIPT, repr(synthetic.expected_values()), *arguments]


def test_output_is_utf8_when_piped(full_repository, tmp_path):
    base = [sys.executable, "-m", "asr_compare.cli"]
    checked = subprocess.run(
        child_command(full_repository, "check", "--repo", str(full_repository.root)),
        capture_output=True,
        env=child_environment(),
        cwd=tmp_path,
        check=False,
    )
    assert checked.returncode == 0
    # 재현 줄에도 한글이 든다: cp949로 쓰였다면 UTF-8로 풀 수 없거나 글자가 다르다.
    assert checked.stdout.decode("utf-8").splitlines() == [*reproduction_lines(full_repository), FINAL_LINE]
    helped = subprocess.run(
        [*base, "--help"], capture_output=True, env=child_environment(), cwd=tmp_path, check=False
    )
    assert helped.returncode == 0
    assert "종료 코드" in helped.stdout.decode("utf-8")


def test_printed_inputs_have_lf_line_endings(full_repository, tmp_path):
    # 이 출력은 파일로 받아 고정 목록이 된다. 윈도우의 파이썬은 줄 끝을 CRLF로 바꿔 쓰므로, 표준 출력을 LF로
    # 다시 열지 않으면 목록의 줄 끝이 CRLF가 된다. 받은 바이트에 CR이 없고 줄마다 LF로 끝나야 한다.
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "asr_compare.cli",
            "check",
            "--print-inputs",
            "--repo",
            str(full_repository.root),
        ],
        capture_output=True,
        env=child_environment(),
        cwd=tmp_path,
        check=False,
    )
    assert done.returncode == 0
    assert done.stdout == "".join(line + "\n" for line in full_repository.pinned_lines()).encode("utf-8")
    assert b"\r" not in done.stdout
    assert done.stderr == b""


def test_output_has_no_carriage_returns_even_where_the_platform_would_add_them(full_repository, tmp_path):
    # 윈도우의 파이썬은 줄 끝을 CRLF로 바꿔 쓴다. 출력을 파일로 받아 쓰는 다음 일(재료 목록 만들기)이 CR
    # 없는 글을 받도록, 표준 출력도 LF로 쓴다. 표준 오류도 같다.
    base = [sys.executable, "-m", "asr_compare.cli"]
    ok = subprocess.run(
        child_command(full_repository, "check", "--repo", str(full_repository.root)),
        capture_output=True,
        env=child_environment(),
        cwd=tmp_path,
        check=False,
    )
    assert ok.returncode == 0
    assert b"\r" not in ok.stdout and b"\r" not in ok.stderr
    failed = subprocess.run(
        [*base, "check", "--repo", str(tmp_path / "nowhere")],
        capture_output=True,
        env=child_environment(),
        cwd=tmp_path,
        check=False,
    )
    assert failed.returncode == 2
    assert failed.stderr.decode("utf-8").startswith("저장소 폴더")
    assert b"\r" not in failed.stdout and b"\r" not in failed.stderr
