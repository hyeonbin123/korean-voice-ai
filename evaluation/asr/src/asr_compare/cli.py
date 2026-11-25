"""같은 발화 인식 비교의 명령줄: `asr-compare check | run | verify`.

세 명령이 하는 일
    check   저장소의 재료 열아홉 개를 읽고 짝짓기 검증 여덟 가지(`join.verify`)를 돌린다. 검증이 통과하면
            이어서 구성 요소가 이미 기록한 값을 저장된 가설에서 다시 세어(`recorded`) 묶음마다 한 줄씩
            찍는다. 어긋남 줄을 모두 찍고 끝 줄에 `묶음 N개, 발화 N개(한글 전용 N개), 어긋남 M개`를 쓴다.
            M은 검증의 어긋남 줄 수와 재현이 다른 묶음 수의 합이다. 아무것도 쓰지 않는다. 묶음을 서로 견주는
            값은 만들지 않는다.
    run     check와 같은 관문(검증과 기록값 재현)이 통과하면 채점해서 `--out` 폴더에 결과 파일 둘
            (`fleurs-ko-test.json`, `fleurs-ko-test.md`)을 쓴다. 관문에 걸리면 check와 같은 줄을 찍고 아무
            파일도 만들지 않는다.
    verify  같은 관문을 지난 뒤, 저장소의 `evaluation/asr/results/` 아래 결과 파일 둘이 지금 재료에서 다시
            만든 글과 글자까지 같은지 견준다. 관문에 걸리면 견주지 않는다. 결과 파일의 줄 끝이
            CRLF여도(줄바꿈 변환을 켠 채 받은 복제본) LF로 보고 견준다.

한 관문
    세 명령은 `_pass_gate` 하나를 지난다. 재현이 다른데 결과 파일을 쓰거나 견주는 길이 따로 생기지 않게
    하려는 것이다. 관문은 읽기, 짝짓기 검증, 그리고 검증이 통과했을 때만 기록값 재현을 한다(행을 믿을 수
    없으면 센 값도 믿을 수 없다). 찍는 것은 명령마다 다르다: check는 줄을 모두, run은 요약 한 줄(걸리면
    줄까지), verify는 걸릴 때만 찍는다.

종료 코드
    0 = 통과, 1 = 어긋남(검증에 걸렸거나 기록값이 재현되지 않았거나 결과 파일이 다시 만든 것과 다름), 2 =
    읽지 못함(재료·결과 파일이 없거나 형식이 틀림, 저장소 폴더가 아님, 결과를 쓰지 못함)이거나 잘못된 사용.
    읽기 오류(`SourceError`)와 위 경우만 잡고, 그 밖의 예외는 잡지 않는다: 버그는 흔적(추적 출력)과 함께
    실패해야 하고, 실패했는데 0으로 끝나는 길이 없어야 한다.

출력
    표준 출력·오류는 시작할 때 UTF-8과 LF 줄 끝으로 다시 연다(한국어 Windows의 파이썬은 파이프나 파일로 나가는
    출력을 cp949로 쓰고 줄 끝을 CRLF로 바꾼다). 어긋남 줄에는 상한이 없다: 모두 찍고, 끝 줄의 수와 찍힌 줄
    수가 같다.

저장소 뿌리(`--repo`)의 기본값은 이 파일에서 올라간 곳이다. 작업 폴더에 기대지 않는다(`--out`만 작업 폴더
기준 상대 경로를 받는다).
"""

import argparse
import itertools
import sys
from dataclasses import dataclass
from pathlib import Path

from . import join, recorded, report, sources

# 이 파일은 <저장소>/evaluation/asr/src/asr_compare/cli.py에 있다. parents[0] = asr_compare, [1] = src, [2]
# = asr, [3] = evaluation, [4] = 저장소 뿌리.
DEFAULT_REPO = Path(__file__).resolve().parents[4]

# 커밋된 결과 파일이 있는 폴더(저장소 뿌리 기준).
RESULTS_DIR = Path("evaluation") / "asr" / "results"


def _use_utf8_output() -> None:
    """표준 출력·오류를 UTF-8과 LF 줄 끝으로 다시 연다. 인코딩할 수 없는 글자는 \\uXXXX로 바꿔 죽지 않게 한다.

    한국어 Windows(코드 페이지 949)의 파이썬은 출력이 파이프나 파일이면 cp949로 쓰고 줄 끝을 CRLF로 바꿔서,
    한글이 깨지고 출력을 파일로 받아 쓰는 일(재료 목록 만들기 등)에 CR이 섞인다. Linux는 이미 UTF-8과 LF라
    바뀌는 것이 없다.

    모듈을 가져올 때가 아니라 main이 시작할 때 한다: 시험이 출력을 가로채는 중에 import만으로 표준 출력을
    바꾸지 않으려는 것이다. reconfigure가 없는 스트림(가로채기용 객체)이거나 이미 닫혔으면 건너뛴다. 출력
    모양은 보조 수단이라 실패해도 검사 자체를 막지 않는다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace", newline="\n")
        except (ValueError, OSError):
            continue


def build_parser() -> argparse.ArgumentParser:
    """세 하위 명령(check, run, verify)을 가진 한국어 도움말의 인자 해석기를 만든다."""
    parser = argparse.ArgumentParser(
        prog="asr-compare",
        description=(
            "세 구성 요소(whisper-ko-ft, stt-scratch, voice-translator)가 이미 저장해 둔 "
            "FLEURS 한국어 test의 발화별 가설을 같은 발화끼리 짝지어 같은 규칙으로 다시 채점해 견줍니다. "
            "새 디코딩은 하지 않고 저장소의 리포트 파일을 읽기만 합니다."
        ),
        epilog=(
            "종료 코드: 0 = 통과, "
            "1 = 어긋남(짝짓기 검증에 걸렸거나 기록값이 재현되지 않았거나 결과 파일이 다시 만든 것과 다름), "
            "2 = 읽지 못함(재료나 결과 파일이 없거나 형식이 틀림, 저장소 폴더가 아님, "
            "결과를 쓰지 못함)이거나 잘못된 사용."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="{check,run,verify}")

    repo_help = "저장소 뿌리(기본: 이 도구가 든 저장소)"
    check = commands.add_parser(
        "check",
        help="재료를 읽고 짝짓기 검증과 기록값 재현을 돌립니다",
        description=(
            "저장소의 재료 열아홉 개를 읽고 짝짓기 검증 여덟 가지를 돌립니다. "
            "검증이 통과하면 구성 요소가 이미 기록한 값을 저장된 가설에서 다시 세어 "
            "묶음마다 한 줄씩 찍습니다. "
            "어긋남 줄을 모두 찍고 끝 줄에 묶음·발화 수와 어긋남 수를 적습니다. 아무것도 쓰지 않습니다."
        ),
    )
    check.add_argument("--repo", type=Path, default=DEFAULT_REPO, help=repo_help)
    check.set_defaults(handler=_check)

    run = commands.add_parser(
        "run",
        help="검증과 기록값 재현이 통과하면 채점해서 결과 파일 둘을 씁니다",
        description=(
            "check와 같은 관문(짝짓기 검증과 기록값 재현)이 통과하면 채점해서 --out 폴더에 "
            "fleurs-ko-test.json과 fleurs-ko-test.md를 씁니다. "
            "관문에 걸리면 어긋남 줄을 찍고 아무 파일도 만들지 않습니다."
        ),
    )
    run.add_argument("--repo", type=Path, default=DEFAULT_REPO, help=repo_help)
    run.add_argument(
        "--out",
        required=True,
        type=Path,
        help="결과 파일을 쓸 폴더(작업 폴더 기준 상대 경로 가능; 없으면 부모까지 만듦)",
    )
    run.set_defaults(handler=_run)

    verify = commands.add_parser(
        "verify",
        help="커밋된 결과 파일이 다시 만든 것과 같은지 견줍니다",
        description=(
            "check와 같은 관문(짝짓기 검증과 기록값 재현)을 지난 뒤, "
            "저장소의 evaluation/asr/results/ 아래 결과 파일 둘을 "
            "지금 재료에서 다시 만든 글과 글자까지 견줍니다. "
            "관문에 걸리면 견주지 않고 그 줄을 찍습니다. "
            "결과 파일의 줄 끝이 CRLF여도 LF로 보고 견줍니다. "
            "다르면 파일 이름과 처음 다른 줄 번호를 찍습니다."
        ),
    )
    verify.add_argument("--repo", type=Path, default=DEFAULT_REPO, help=repo_help)
    verify.set_defaults(handler=_verify)
    return parser


@dataclass(frozen=True)
class _Gate:
    """읽기, 짝짓기 검증, 기록값 재현을 지난 결과. `check`·`run`·`verify`가 같은 관문의 결과를 쓴다.

    loaded      읽은 재료.
    lines       찍을 줄. 짝짓기 검증이 어긋났으면 그 어긋남 줄들(상한이 없다), 통과했으면 묶음마다 재현 줄
                하나다.
    mismatches  요약 줄의 어긋남 수: 검증의 어긋남 줄 수와 재현이 다른 묶음 수의 합이다. 검증이 어긋나면
                재현은 돌리지 않으므로 둘 가운데 하나만 0이 아니다. 0이면 관문을 통과한 것이다.
    """

    loaded: sources.Loaded
    lines: list[str]
    mismatches: int

    @property
    def summary(self) -> str:
        loaded = self.loaded
        hangul_only = sum(1 for flag in loaded.hangul if flag)
        return (
            f"묶음 {len(loaded.systems)}개, 발화 {len(loaded.hangul)}개(한글 전용 {hangul_only}개), "
            f"어긋남 {self.mismatches}개"
        )

    def show(self, *, lines: bool, summary: bool) -> None:
        """줄과 요약 줄을 고른 대로 찍는다. 줄은 요약 앞에 온다."""
        if lines:
            for line in self.lines:
                print(line)
        if summary:
            print(self.summary)


def _pass_gate(repo: Path) -> _Gate:
    """재료를 읽고(읽지 못하면 SourceError) 검증을 돌리고, 통과하면 기록값을 다시 센다. 아무것도 찍지 않는다.

    세 명령이 모두 이 함수를 지난다. 재현이 다른데 결과 파일을 쓰거나 견주는 길을 따로 만들지 않으려는 것이다.
    """
    loaded = sources.load_repository(repo)
    problems = join.verify(list(loaded.systems), loaded.hangul, loaded.twins)
    if problems:
        return _Gate(loaded, problems, len(problems))
    reproductions = recorded.reproduce(loaded)
    return _Gate(
        loaded,
        [item.line for item in reproductions],
        sum(1 for item in reproductions if not item.matches),
    )


def _check(args: argparse.Namespace) -> int:
    gate = _pass_gate(args.repo)
    gate.show(lines=True, summary=True)
    return 1 if gate.mismatches else 0


def _run(args: argparse.Namespace) -> int:
    gate = _pass_gate(args.repo)
    # 통과하면 요약 한 줄만 찍고 넘어가고, 걸리면 어느 묶음이 왜 걸렸는지 줄까지 찍는다.
    gate.show(lines=bool(gate.mismatches), summary=True)
    if gate.mismatches:
        return 1
    loaded = gate.loaded
    # 글 둘을 모두 만든 뒤에 쓴다: 채점이나 글 만들기가 실패해도 반쯤 쓴 결과 폴더가 남지 않는다.
    result = report.build(loaded.systems, loaded.hangul, loaded.inputs)
    texts = {
        report.RESULT_JSON: report.render_json(result),
        report.RESULT_MARKDOWN: report.render_markdown(result),
    }
    try:
        args.out.mkdir(parents=True, exist_ok=True)
        paths = []
        for name, text in texts.items():
            path = args.out / name
            path.write_text(text, encoding="utf-8", newline="\n")
            paths.append(path)
    except OSError as error:
        print(
            f"결과 파일을 쓰지 못했다({error.strerror or type(error).__name__}): {args.out.as_posix()}",
            file=sys.stderr,
        )
        return 2
    for path in paths:
        print(f"쓴 파일: {path.as_posix()}")
    return 0


def _first_different_line(expected: str, actual: str) -> int:
    """두 글이 처음 달라지는 줄 번호(1부터)를 돌려준다. 한쪽이 먼저 끝나면 그 다음 줄 번호다."""
    lines = itertools.zip_longest(expected.split("\n"), actual.split("\n"))
    for number, (left, right) in enumerate(lines, start=1):
        if left != right:
            return number
    raise ValueError("두 글이 같다")


def _verify(args: argparse.Namespace) -> int:
    folder = args.repo / RESULTS_DIR
    names = (report.RESULT_JSON, report.RESULT_MARKDOWN)
    missing = [name for name in names if not (folder / name).is_file()]
    if missing:
        # 견줄 것이 없는데 통과로 끝나면 안 된다.
        print(f"결과 파일이 없다: {', '.join(missing)} ({folder.as_posix()})", file=sys.stderr)
        return 2
    gate = _pass_gate(args.repo)
    if gate.mismatches:
        gate.show(lines=True, summary=True)
        return 1
    loaded = gate.loaded
    result = report.build(loaded.systems, loaded.hangul, loaded.inputs)
    expected = {
        report.RESULT_JSON: report.render_json(result),
        report.RESULT_MARKDOWN: report.render_markdown(result),
    }
    different = []
    for name in names:
        try:
            # 줄바꿈 변환을 켠 채 받은 복제본의 CRLF는 LF로 보고 견준다. BOM은 떼지 않는다(있으면 다른
            # 것이다).
            actual = (folder / name).read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            print(f"결과 파일을 읽지 못했다: {name} ({type(error).__name__})", file=sys.stderr)
            return 2
        if actual != expected[name]:
            different.append(f"{name}: {_first_different_line(expected[name], actual)}번째 줄부터 다르다")
    for line in different:
        print(line)
    if different:
        return 1
    print(f"결과 파일 둘이 다시 만든 것과 같다: {folder.as_posix()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """명령을 해석해 실행하고 종료 코드(0, 1, 2)를 돌려준다. `--help`는 0, 잘못된 사용은 2다."""
    _use_utf8_output()
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exit_request:
        # argparse는 --help에 0, 잘못된 인자에 2를 준다.
        return exit_request.code if isinstance(exit_request.code, int) else 2
    if not args.repo.is_dir():
        print(f"저장소 폴더가 아니다: {args.repo}", file=sys.stderr)
        return 2
    try:
        return args.handler(args)
    except sources.SourceError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
