"""구성 요소가 이미 기록한 채점 값을, 저장된 가설에서 다시 세어 같은 값이 나오는지 본다.

왜 있나
    이 도구는 구성 요소 세 곳이 따로 저장한 가설을 한 규칙으로 다시 채점해 견준다. 그 표가 구성 요소의
    기록과 같은 자로 잰 것이라고 말하려면, 먼저 이 도구가 가설을 읽고 세는 방식이 구성 요소가 이미 적어 둔
    값을 그대로 다시 만든다는 것을 확인해 두어야 한다. 짝짓기 검증(`join.verify`)은 발화가 일대일로 맞는지를
    보고, 이 모듈은 세는 방식이 기록과 맞는지를 본다. `check`가 둘을 차례로 돌리고, `run`과 `verify`도 같은
    관문을 지난다.

무엇을 세나 (새 수치를 내지 않는다)
    각 구성 요소가 저장한 자기 정답으로 세어, 그 구성 요소가 이미 적어 둔 값과 견준다.
      - voice-translator 묶음 둘, whisper-large-v3-turbo, stt-scratch 묶음 둘: 아래 `EXPECTED`에 적은 편집
        수의 합과 정규화한 정답 글자 수의 합. stt-scratch는 한글 전용 발화만 센 합도 기록해 두었으므로
        그것도 센다.
      - whisper-ko-ft 열 묶음: 리포트에 발화마다 저장된 (edits, length)와 `summary.error_rate`. 사전에는
        적지 않고 리포트 파일에서 읽는다(`sources.Stored`).
    세지 않는 것: 공통 정답으로 다시 센 값, 95% 구간, 묶음 사이의 차이, 구성 요소가 기록하지 않은
    범위(voice-translator와 whisper-ko-ft의 한글 전용). 그런 값은 `run`만 낸다. 이 모듈이 돌려주는 줄에도
    나오지 않는다.

기록값 사전을 바꾸는 길은 없다
    `EXPECTED`는 코드에 적은 고정 값이다. 명령줄에는 이 값을 바꾸는 옵션이 없고, 시험만 합성 저장소의 값으로
    바꿔 끼운다(`recorded.EXPECTED`를 읽을 때마다 이 모듈의 이름으로 찾는다. 다른 곳에 복사해 두지 않는다).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from . import score
from .sources import Loaded, System

# 범위의 이름. 결과 파일의 범위 이름과 같다.
SCOPES = ("all", "hangul_only")

# 묶음의 키 -> 범위 -> (편집 수의 합, 정규화한 정답 글자 수의 합). 모두 그 구성 요소가 저장한 자기 정답으로
# 센 값이다. 구성 요소가 기록하지 않은 범위는 키를 두지 않는다. 출처는 파일을 열어 글자로 확인한 곳이다.
#
#   - stt-scratch 둘: stt-scratch/reports/final/test_fleurs-full.json과 test_fleurs-streaming.json의
#     all.cer_ns(edits, length)와 hangul_only.cer_ns(edits, length). 공백을 뺀 글자 오류율의 분자와 분모다.
#   - voice-translator 둘: voice-translator/backend/eval/reports/stt_t14_test_20260913_055810.json과
#     stt_t2_test_20260912_224129_rescored.json의 languages.ko.error가 각각 808 / 17680, 854 / 17680과
#     글자까지 같다(그 파일이 적은 비율이 이 두 합에서 나온다).
#   - whisper-large-v3-turbo: whisper-ko-ft/reports/whisper-large-v3-turbo/fleurs-ko-test.json에 발화마다
#     저장된 edits와 length의 합이다. 같은 파일의 summary.error_rate가 round(921 / 17680, 5)와 같다.
EXPECTED: dict[str, dict[str, tuple[int, int]]] = {
    "voice-turbo-vad": {"all": (808, 17680)},
    "voice-turbo": {"all": (854, 17680)},
    "whisper-large-v3-turbo": {"all": (921, 17680)},
    "stt-scratch-full": {"all": (3488, 17678), "hangul_only": (1659, 11346)},
    "stt-scratch-streaming": {"all": (4023, 17678), "hangul_only": (2013, 11346)},
}


@dataclass(frozen=True)
class Reproduction:
    """묶음 하나의 재현 결과.

    key      묶음의 키.
    line     `check`가 찍는 한 줄. 꼴은 `<키>: 기록 <편집>/<글자> = 다시 센 <편집>/<글자>`이고, 한글 전용
             기록이 있는 묶음은 `, 한글 전용 기록 … = 다시 센 …`이 이어진다. 다르면 `=` 대신 `≠`를 쓰고,
             합은 같아도 발화별 기록이나 오류율이 다르면 그 까닭이 뒤에 붙는다.
    matches  이 묶음의 기록값이 모두 재현됐는지.
    """

    key: str
    line: str
    matches: bool


def _sum(counts: Iterable[tuple[int, int]]) -> tuple[int, int]:
    """(편집 수, 글자 수) 쌍들의 합."""
    pairs = list(counts)
    return sum(edits for edits, _ in pairs), sum(length for _, length in pairs)


def _text(pair: tuple[int, int]) -> str:
    return f"{pair[0]}/{pair[1]}"


def _compare(recorded: tuple[int, int], recounted: tuple[int, int]) -> str:
    return f"기록 {_text(recorded)} {'=' if recorded == recounted else '≠'} 다시 센 {_text(recounted)}"


def _rows(rows: list[int], limit: int = 5) -> str:
    """줄에 쓸 행 번호 목록. 길면 앞 limit개만 보이고 나머지는 개수로 적는다."""
    text = ", ".join(str(row) for row in rows[:limit])
    return text if len(rows) <= limit else f"{text} 외 {len(rows) - limit}개"


def _check_names(loaded: Loaded) -> None:
    """기록값 사전의 키와 범위 이름이 읽은 묶음과 맞는지 본다. 틀리면 ValueError(프로그램의 잘못이다)."""
    known = {system.key for system in loaded.systems}
    for key, scopes in EXPECTED.items():
        if key not in known:
            raise ValueError(f"기록값 사전의 묶음 {key}이(가) 읽은 묶음에 없다")
        unknown = [scope for scope in scopes if scope not in SCOPES]
        if unknown:
            raise ValueError(f"기록값 사전의 {key}에 알 수 없는 범위가 있다: {', '.join(unknown)}")


def _reproduce(system: System, loaded: Loaded) -> Reproduction:
    wanted = EXPECTED.get(system.key, {})
    stored = loaded.stored.get(system.key)
    if "all" not in wanted and stored is None:
        raise ValueError(
            f"{system.key}: 다시 셀 기록값이 없다(기록값 사전에도, 리포트가 적어 둔 값에도 없다)"
        )

    counted: list[tuple[int, int]] = []
    empty: list[int] = []
    for utterance in system.utterances:
        try:
            counted.append(score.counts(utterance.reference, utterance.hypothesis))
        except ValueError:  # 정규화한 정답이 빈 글이라 글자 오류율의 분모가 0이 된다
            empty.append(utterance.row)
    if empty:
        line = f"{system.key}: 정규화한 정답이 빈 글인 행이 있어 다시 셀 수 없다(행 {_rows(empty)})"
        return Reproduction(system.key, line, False)

    recounted = _sum(counted)
    recorded_all = wanted["all"] if "all" in wanted else _sum(stored.counts)
    matches = recorded_all == recounted
    line = f"{system.key}: {_compare(recorded_all, recounted)}"

    if "hangul_only" in wanted:
        # 한글 전용은 구성 요소가 기록한 묶음(wanted에 적힌 것)에서만 센다. 표시는 행 번호 순이다.
        subset = _sum(
            pair
            for utterance, pair in zip(system.utterances, counted, strict=True)
            if loaded.hangul[utterance.row]
        )
        matches = matches and wanted["hangul_only"] == subset
        line += f", 한글 전용 {_compare(wanted['hangul_only'], subset)}"

    if stored is not None:
        different = [
            utterance.row
            for utterance, pair, saved in zip(system.utterances, counted, stored.counts, strict=True)
            if pair != saved
        ]
        if different:
            matches = False
            line += f", 발화별 기록과 다른 행 {len(different)}개(행 {_rows(different)})"
        rate = round(recounted[0] / recounted[1], 5)
        if rate != stored.error_rate:
            matches = False
            line += f", 기록 오류율 {stored.error_rate} ≠ 다시 센 {rate}"
    return Reproduction(system.key, line, matches)


def reproduce(loaded: Loaded) -> list[Reproduction]:
    """읽은 묶음 열네 개의 기록값을 모두 다시 세어, 묶음마다 하나씩 고정 목록의 차례로 돌려준다.

    `join.verify`가 통과한 뒤에만 부른다: 행 번호가 한 번씩 있다고 믿고 한글 전용 표시를 행 번호로 찾는다.
    기록값 사전의 이름이 틀리거나 어느 묶음에도 다시 셀 기록이 없으면 ValueError다. 사람의 입력이 아니라
    프로그램의 잘못이라서 조용히 넘기지 않는다.
    """
    _check_names(loaded)
    return [_reproduce(system, loaded) for system in loaded.systems]
