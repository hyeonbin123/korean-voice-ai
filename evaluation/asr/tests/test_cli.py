"""명령줄(cli)의 시험: 종료 코드, 출력, 결과 파일, 줄바꿈과 글자 코드.

명령줄은 언제나 실제 크기의 기본값(382발화, 한글 전용 257, 알려진 정답 차이 행 23·57)으로 검증하므로, 이
파일의 시험은 실제 크기의 합성 저장소(`conftest.py`의 `full_repository`)를 쓴다. 그 폴더는 시험 묶음
전체에서 한 번만 만들고, 고치는 시험은 복사해서 고친다. 점수를 매기는 `run`도 한 번만 돌려(`full_results`)
여러 시험이 그 결과를 나눠 쓴다.

실제 저장소로는 시험하지 않는다.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from asr_compare import cli, sources

JSON_NAME = "fleurs-ko-test.json"
MARKDOWN_NAME = "fleurs-ko-test.md"
FINAL_LINE = "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 0개"


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


@pytest.fixture(scope="session")
def full_results(full_repository, tmp_path_factory):
    """실제 크기의 합성 저장소에 `run`을 한 번 돌린 결과: (결과 폴더, 표준 출력).

    시험 묶음 전체에서 한 번만 돌린다.
    """
    out = tmp_path_factory.mktemp("results") / "out"
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
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
    code, out, err = invoke(capsys, "check", "--repo", str(full_repository.root))
    assert (code, out, err) == (0, FINAL_LINE + "\n", "")


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
# run
# ---------------------------------------------------------------------------------------------


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
    out_dir = tmp_path / "must-not-exist"
    code, out, err = invoke(capsys, "run", "--repo", str(root), "--out", str(out_dir))
    assert (code, err) == (1, "")
    assert out.splitlines()[-1] == "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 3개"
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
    assert "같다" in out


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


def test_verify_notices_when_a_material_file_changed_after_the_results_were_made(
    capsys, full_repository, full_results, copy_repository
):
    # 재료의 sha256이 결과 파일에 들어 있어서, 짝짓기 검증을 통과하는 작은 변경(읽지 않는 키)도 결과가
    # 낡았다고 알린다.
    out_dir, _ = full_results
    root = copy_repository(full_repository)
    put_results(root, out_dir)
    path = root / sources.SYSTEMS[1].path
    document = json.loads(path.read_text(encoding="utf-8"))
    document[0]["variant"] = "changed after the results were made"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
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


def test_output_is_utf8_when_piped(full_repository, tmp_path):
    base = [sys.executable, "-m", "asr_compare.cli"]
    checked = subprocess.run(
        [*base, "check", "--repo", str(full_repository.root)],
        capture_output=True,
        env=child_environment(),
        cwd=tmp_path,
        check=False,
    )
    assert checked.returncode == 0
    assert checked.stdout.decode("utf-8") == FINAL_LINE + "\n"
    helped = subprocess.run(
        [*base, "--help"], capture_output=True, env=child_environment(), cwd=tmp_path, check=False
    )
    assert helped.returncode == 0
    assert "종료 코드" in helped.stdout.decode("utf-8")


def test_output_has_no_carriage_returns_even_where_the_platform_would_add_them(full_repository, tmp_path):
    # 윈도우의 파이썬은 줄 끝을 CRLF로 바꿔 쓴다. 출력을 파일로 받아 쓰는 다음 일(재료 목록 만들기)이 CR
    # 없는 글을 받도록, 표준 출력도 LF로 쓴다. 표준 오류도 같다.
    base = [sys.executable, "-m", "asr_compare.cli"]
    ok = subprocess.run(
        [*base, "check", "--repo", str(full_repository.root)],
        capture_output=True,
        env=child_environment(),
        cwd=tmp_path,
        check=False,
    )
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
