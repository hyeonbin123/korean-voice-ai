"""같은 발화끼리 정말 짝지어졌는지 확인하는 짝짓기 검증.

왜 있나
    이 도구는 서로 다른 구성 요소가 저장한 가설을 행 번호로 짝지어 같은 발화끼리 견준다(`sources` 머리
    설명). 행 번호가 같은 발화를 가리킨다는 것은 전제이고, 전제가 틀린 채로 표를 만들면 표 전체가 조용히
    틀린다. 그래서 표를 만들기 전에 이 검증이 먼저 통과해야 한다. 이 모듈은 읽은 데이터만 보고(파일을 열지
    않는다) 어긋난 점마다 한 줄을 돌려준다. 빈 목록이 통과다.

검사 여덟 가지
    어긋난 점마다 한 줄이고, 줄에는 묶음 키와 행 번호가 들어간다. 줄의 차례는 아래 번호 순이고, 같은 검사
    안에서는 묶음 순(열네 묶음 다음에 같은 가설 리포트를 이름 순으로), 행 번호 순이다.

    1. 발화 수와 행 번호: 묶음마다(같은 가설 리포트 포함) 발화가 `utterances`개이고 행 번호 0 ~
       utterances-1이 정확히 한 번씩 나온다. 어긋난 묶음마다 한 줄이고, 이 검사에서 어긋남이 나오면 그
       줄들만 돌려주고 끝낸다: 행 번호가 깨진 묶음은 뒤 검사에서 행으로 짝지을 수 없어, 뒤 검사를 반쯤
       돌리면 엉뚱한 줄이 쏟아지기 때문이다.
    2. 문장 번호: 행마다 모든 묶음(같은 가설 리포트 포함)의 문장 번호가 같다(기준은 첫 묶음). 행 번호 전제가
       맞는지 보는 첫째 증거다. 같은 가설 리포트는 7번 검사가 행 번호로 가설을 견주는 대상이라, 2·3·4번도
       열네 묶음과 같은 범위로 건다.
    3. 음성 길이: 행마다 모든 묶음(같은 가설 리포트 포함)의 음성 길이가 같다. 소수 둘째 자리로 반올림해서
       견준다(구성 요소마다 적은 자릿수가 다르다). 같은 문장을 두 번 녹음한 행은 문장 번호가 같으므로 길이가
       둘째 증거다.
    4. whisper-ko-ft의 id: whisper-ko-ft 꼴의 묶음(같은 가설 리포트 포함)에서, 행 번호 순으로 그 문장의 첫
       녹음은 `<문장>`, n번째(n >= 2) 녹음은 `<문장>#<n>`이어야 한다. 리포트가 같은 문장의 녹음 순서를 행
       번호 순서와 다르게 적었다면 여기서 드러난다.
    5. 정규화한 정답: voice-translator와 whisper-ko-ft 묶음(같은 가설 리포트 포함)의 정규화한 정답이 모든
       행에서 공통 정답 (`whisper-large-v3-turbo` 묶음의 정답)과 같다. 통과하면 이 묶음들은 어느 쪽 정답으로
       세어도 같다.
    6. stt-scratch의 정답: stt-scratch 묶음의 정규화한 정답이 공통 정답과 다른 행의 집합이
       `known_reference_differences`와 정확히 같다(알려진 행이 더는 다르지 않아도 어긋남이다). 그 행들은
       한글 전용 표시가 없어야 한다. stt-scratch는 정답을 한글·영문자·숫자·공백만 남기는 학습용 정규화로
       저장해서, 악센트가 붙은 글자처럼 그 밖의 글자가 든 정답은 공통 정답과 달라진다. 그런 정답이 든 행이
       알려진 두 행이고, 두 행 모두 한글 전용이 아니다.
    7. 같은 가설 리포트: 묶음이 같은 가설이라고 적은 리포트(`System.also`)의 가설이 모든 행에서 묶음의
       가설과 글자까지 같다. 정규화하기 전의 저장된 글로 견준다. 적힌 리포트를 읽은 목록(`twins`)에서 찾지
       못하면 그것도 어긋남이다.
    8. 한글 전용 표시: 길이가 `utterances`이고 참인 것이 `hangul_only`개다.

이 검사들로도 잡지 못하는 것
    voice-translator와 whisper-ko-ft는 리포트 안의 위치를 행 번호로 받아들이는 전제 위에 있고(`sources` 머리
    설명), 2·3·4번 검사가 그 전제의 증거다. 같은 문장을 두 번 이상 녹음한 문장은 여럿이지만 대부분 음성
    길이가 달라서 3번 검사가 구별한다. 문장 번호와 음성 길이(소수 둘째 자리)가 모두 같은 쌍은 실제 재료에
    하나다(행 64와 187). whisper-ko-ft는 그 두 행도 `#n`이 순서를 말해 주어서, 항목을 통째로 맞바꾸면 4번
    검사가 잡는다. voice-translator의 그 두 행만 리포트가 원래 순서대로 저장됐다는 전제에 기댄다. 두 행은
    같은 문장이라 정답이 같으므로, 전제가 틀려도 묶음의 오류율(합)은 달라지지 않고 발화별로 짝짓는 값만 그
    두 행에서 달라질 수 있다. stt-scratch는 발화 id에 행 번호가 있어 이 틈이 없다.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .score import normalize
from .sources import STT, VOICE, WHISPER, System, Utterance

# 세 구성 요소가 쓰는 FLEURS 한국어 test의 발화 수, 그중 한글 전용(숫자·라틴 문자가 없는) 발화 수,
# stt-scratch의 정규화한 정답이 공통 정답과 달라지는 행(위 6번). 명령줄은 언제나 이 기본값으로 검증하고
# 바꾸는 옵션을 두지 않는다. 검증 함수의 키워드 인자는 시험이 작은 고정물로 같은 검사를 돌리게 하는 용도다.
UTTERANCES = 382
HANGUL_ONLY = 257
KNOWN_REFERENCE_DIFFERENCES = (23, 57)

# 공통 정답을 가진 묶음의 키. 다른 묶음의 정규화한 정답을 이것과 견준다.
COMMON_REFERENCE = "whisper-large-v3-turbo"


@dataclass(frozen=True)
class _Entry:
    """검사 하나가 보는 묶음: 줄에 쓸 이름, 묶음, 행 번호 -> 발화.

    행 번호가 정확히 한 번씩임을 확인한 뒤에만 만드므로(1번 검사) `rows`는 0 ~ utterances-1을 빠짐없이 가진다.
    """

    label: str
    system: System
    rows: dict[int, Utterance]


def _show(rows: list[int], limit: int = 10) -> str:
    """행 번호 목록을 줄에 쓸 글로 바꾼다. 길면 앞 limit개만 보이고 나머지는 개수로 적는다."""
    text = ", ".join(str(row) for row in rows[:limit])
    return text if len(rows) <= limit else f"{text} 외 {len(rows) - limit}개"


def _row_set_problem(label: str, system: System, utterances: int) -> str | None:
    """1번 검사: 묶음 하나의 행 번호가 0 ~ utterances-1을 한 번씩 담았는지. 어긋나면 그 한 줄을 돌려준다."""
    counts = Counter(utterance.row for utterance in system.utterances)
    missing = [row for row in range(utterances) if counts[row] == 0]
    repeated = [row for row in range(utterances) if counts[row] > 1]
    outside = sorted(row for row in counts if not 0 <= row < utterances)
    if not (missing or repeated or outside):
        return None
    details = []
    if missing:
        details.append(f"빠진 행 {_show(missing)}")
    if repeated:
        details.append(f"두 번 이상 나온 행 {_show(repeated)}")
    if outside:
        details.append(f"범위 밖 행 {_show(outside)}")
    return (
        f"{label}: 발화 {len(system.utterances)}개(기대 {utterances}개), "
        f"행 번호가 0~{utterances - 1}을 한 번씩 담고 있지 않다: {', '.join(details)}"
    )


def _check_sentences(entries: list[_Entry], utterances: int) -> list[str]:
    """2번 검사: 문장 번호가 첫 묶음과 같은지.

    entries는 열네 묶음 다음에 같은 가설 리포트를 이름 순으로 늘어놓은 목록이고, 첫 묶음이 기준이다.
    """
    base = entries[0]
    return [
        f"{entry.label}: 행 {row}: 문장 번호가 {entry.rows[row].sentence}인데 "
        f"{base.label}에서는 {base.rows[row].sentence}다"
        for entry in entries[1:]
        for row in range(utterances)
        if entry.rows[row].sentence != base.rows[row].sentence
    ]


def _check_seconds(entries: list[_Entry], utterances: int) -> list[str]:
    """3번 검사: 음성 길이를 소수 둘째 자리로 반올림한 값이 첫 묶음과 같은지.

    entries는 2번 검사와 같다(열네 묶음 다음에 같은 가설 리포트).
    """
    base = entries[0]
    lines = []
    for entry in entries[1:]:
        for row in range(utterances):
            seconds = round(entry.rows[row].seconds, 2)
            base_seconds = round(base.rows[row].seconds, 2)
            if seconds != base_seconds:
                lines.append(
                    f"{entry.label}: 행 {row}: 음성 길이가 {seconds:.2f}초인데 "
                    f"{base.label}에서는 {base_seconds:.2f}초다(소수 둘째 자리 기준)"
                )
    return lines


def _check_ids(entries: list[_Entry]) -> list[str]:
    """4번 검사: whisper-ko-ft 꼴 묶음(같은 가설 리포트 포함)의 id가 문장의 n번째 녹음 표시와 맞는지.

    n번째 등장은 행 번호 순으로 센다(떨어져 있는 녹음도 센다). id 목록이 비었거나 발화 수와 다르면 이 검사를
    건너뛰지 않고 그 사실을 어긋남으로 알린다.
    """
    lines = []
    for entry in entries:
        system = entry.system
        if system.component != WHISPER:
            continue
        if len(system.ids) != len(system.utterances):
            lines.append(
                f"{entry.label}: id 목록이 발화와 맞지 않는다"
                f"(id {len(system.ids)}개, 발화 {len(system.utterances)}개)"
            )
            continue
        stored = {u.row: identifier for u, identifier in zip(system.utterances, system.ids, strict=True)}
        seen: Counter[str] = Counter()
        for row in sorted(entry.rows):
            sentence = entry.rows[row].sentence
            seen[sentence] += 1
            expected = sentence if seen[sentence] == 1 else f"{sentence}#{seen[sentence]}"
            if stored[row] != expected:
                lines.append(
                    f"{entry.label}: 행 {row}: id가 {stored[row]}인데 문장 {sentence}의 "
                    f"{seen[sentence]}번째 녹음이므로 {expected}여야 한다"
                )
    return lines


def _check_references(everyone: list[_Entry], common: _Entry, utterances: int) -> list[str]:
    """5번 검사: 정규화한 정답이 공통 정답과 같은지.

    대상은 voice-translator와 whisper-ko-ft 묶음이다(같은 가설 리포트 포함).
    """
    expected = {row: normalize(common.rows[row].reference) for row in range(utterances)}
    return [
        f"{entry.label}: 행 {row}: 정규화한 정답이 {common.label}의 것과 다르다"
        for entry in everyone
        if entry is not common and entry.system.component in (VOICE, WHISPER)
        for row in range(utterances)
        if normalize(entry.rows[row].reference) != expected[row]
    ]


def _check_stt_references(
    main: list[_Entry], common: _Entry, hangul: tuple[bool, ...], utterances: int, known: tuple[int, ...]
) -> list[str]:
    """6번 검사: stt-scratch의 정답이 공통 정답과 다른 행이 알려진 행과 정확히 같은지.

    알려진 차이 행이 한글 전용으로 표시돼 있지 않은지도 함께 본다.
    """
    expected = {row: normalize(common.rows[row].reference) for row in range(utterances)}
    known_rows = set(known)
    lines = []
    for entry in main:
        if entry.system.component != STT:
            continue
        different = {
            row for row in range(utterances) if normalize(entry.rows[row].reference) != expected[row]
        }
        lines.extend(
            f"{entry.label}: 행 {row}: 정규화한 정답이 {common.label}의 것과 다른데 "
            "알려진 정답 차이 행이 아니다"
            for row in sorted(different - known_rows)
        )
        lines.extend(
            f"{entry.label}: 행 {row}: 알려진 정답 차이 행인데 정규화한 정답이 {common.label}의 것과 같다"
            for row in sorted(known_rows - different)
        )
    # 한글 전용 표시는 stt-scratch 매니페스트의 것이라 묶음이 아니라 행에 붙는다. 표시의 길이가 틀리면(8번
    # 검사가 알린다) 행으로 찾을 수 없으므로 범위를 넘어 읽지 않는다.
    lines.extend(
        f"행 {row}: 알려진 정답 차이 행이 한글 전용으로 표시돼 있다"
        for row in sorted(known_rows)
        if row < len(hangul) and hangul[row]
    )
    return lines


def _check_twins(main: list[_Entry], twins: dict[str, _Entry]) -> list[str]:
    """7번 검사: 같은 가설이라고 적은 리포트의 가설이 묶음의 가설과 글자까지 같은지."""
    lines = []
    for entry in main:
        for name in entry.system.also:
            twin = twins.get(name)
            if twin is None:
                lines.append(f"{entry.label}: 같은 가설이라고 적은 리포트 {name}이(가) 읽은 목록에 없다")
                continue
            lines.extend(
                f"{entry.label}: 행 {row}: 가설이 같은 가설이라고 적은 리포트 {name}의 것과 "
                "글자까지 같지 않다"
                for row in sorted(entry.rows)
                if entry.rows[row].hypothesis != twin.rows[row].hypothesis
            )
    return lines


def _check_hangul(hangul: tuple[bool, ...], utterances: int, hangul_only: int) -> list[str]:
    """8번 검사: 한글 전용 표시의 길이와 참의 개수."""
    lines = []
    if len(hangul) != utterances:
        lines.append(f"한글 전용 표시가 {len(hangul)}개다(발화 수 {utterances}개와 같아야 한다)")
    count = sum(1 for flag in hangul if flag)
    if count != hangul_only:
        lines.append(f"한글 전용 발화가 {count}개다(기대 {hangul_only}개)")
    return lines


def verify(
    systems: Sequence[System],
    hangul: tuple[bool, ...],
    twins: Mapping[str, System],
    *,
    utterances: int = UTTERANCES,
    hangul_only: int = HANGUL_ONLY,
    known_reference_differences: tuple[int, ...] = KNOWN_REFERENCE_DIFFERENCES,
) -> list[str]:
    """읽은 묶음들이 같은 발화끼리 짝지어졌는지 여덟 가지로 확인하고, 어긋난 점마다 한 줄을 돌려준다.

    빈 목록이 통과다.

    systems  견줄 묶음(차례 그대로. 2·3번 검사의 기준은 첫 묶음이다). 2·3·4번 검사는 `twins`의 형제 리포트에도
             같은 범위로 건다.
    hangul   한글 전용 표시(행 번호 순).
    twins    같은 가설이라고 적힌 형제 리포트(이름 -> 묶음). 기본값이 없는 필수 인자다: 빼먹어서 7번 검사가
             조용히 꺼지는 길을 만들지 않으려는 것이다.
    키워드 인자는 시험이 작은 고정물을 쓰게 하려는 것이고, 기본값은 실제 크기다(위 상수). 명령줄은 기본값만
    쓴다.

    묶음이 하나도 없거나 공통 정답 묶음(`COMMON_REFERENCE`)이 목록에 없으면, 아무것도 확인하지 못한 채
    통과하지 않도록 그 사실을 어긋남 한 줄로 알린다. 줄의 차례는 늘 같다: 검사 번호 순, 같은 검사 안에서는
    묶음 순(`systems`의 차례 다음에 형제 리포트를 이름 순으로), 행 번호 순.
    """
    if not systems:
        return ["견줄 묶음이 하나도 없다"]
    # 형제 리포트는 이름 순으로 늘어놓는다(사전의 삽입 순서에 줄의 차례가 기대지 않게 한다).
    named = [(system.key, system) for system in systems] + [(name, twins[name]) for name in sorted(twins)]

    # 1번 검사. 어긋나면 행으로 짝지을 수 없으므로 여기서 끝낸다.
    problems = [line for label, system in named if (line := _row_set_problem(label, system, utterances))]
    if problems:
        return problems

    everyone = [_Entry(label, system, {u.row: u for u in system.utterances}) for label, system in named]
    main = everyone[: len(systems)]
    twin_entries = {entry.label: entry for entry in everyone[len(systems) :]}

    problems += _check_sentences(everyone, utterances)
    problems += _check_seconds(everyone, utterances)
    problems += _check_ids(everyone)
    common = next((entry for entry in main if entry.system.key == COMMON_REFERENCE), None)
    if common is None:
        problems.append(
            f"공통 정답 묶음 {COMMON_REFERENCE}이(가) 목록에 없어 정답을 견줄 수 없다"
            "(5번과 6번 검사를 건너뛴다)"
        )
    else:
        problems += _check_references(everyone, common, utterances)
        problems += _check_stt_references(main, common, hangul, utterances, known_reference_differences)
    problems += _check_twins(main, twin_entries)
    problems += _check_hangul(hangul, utterances, hangul_only)
    return problems
