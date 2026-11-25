"""채점 결과를 만들고(`build`) JSON과 Markdown 글로 쓴다(`render_json`, `render_markdown`).

`build`가 하는 일
    읽은 묶음들을 모두 같은 규칙으로 채점한다. 채점의 기준(정답)은 언제나 공통 정답, 곧
    `join.COMMON_REFERENCE` 묶음의 정답이다. 다른 묶음이 자기 정답을 어떻게 저장했든 그것으로는 세지
    않는다(다른 whisper-ko-ft 묶음과 voice-translator 묶음의 정규화한 정답이 공통 정답과 같다는 것은
    `join.verify`가 확인한다). 묶음마다 발화별 (편집 수, 정규화한 정답 글자 수)를 한 번만 세어 두고, 합과
    부트스트랩은 그 표에서 낸다. 편집 거리를 다시 뽑기마다 다시 세지 않는다.

    범위는 둘이다: 전체(`all`)와 한글 전용(`hangul_only`: 숫자·라틴 문자가 없는 발화). 한글 전용의 다시 뽑기
    번호는 '한글 전용 행을 행 번호 순으로 늘어놓은 목록'의 위치다. 다시 뽑기 번호는 범위마다 한 번만 만들어
    모든 묶음과 모든 짝이 같은 번호를 쓴다(`score` 머리 설명).

    짝 비교(`PAIRS`)는 모두 '앞 − 뒤'다. 차이 구간은 같은 다시 뽑기에서 낸 두 글자 오류율의 차이를 모아
    `score.interval`로 구한다. `fewer_edits`·`more_edits`·`same`은 발화마다 앞 묶음의 편집 수가 뒤 묶음보다
    적은·많은·같은 발화의 수다(셋의 합은 범위의 발화 수다).

`build`가 하지 않는 일
    짝짓기 검증(`join.verify`)을 대신하지 않는다. 그것이 통과한 입력인지는 부르는 쪽(명령줄의 `run`과
    `verify`)이 지킨다. 다만 `build` 자신도 받은 묶음에 행 번호가 빠졌거나 겹치거나 범위 밖이면 빈 값이나
    0으로 메우지 않고 ValueError로 멈춘다. 발화는 튜플의 위치가 아니라 `Utterance.row`로 찾는다(묶음마다 행
    번호 -> 발화의 사전을 만든다).

숫자를 어디서 반올림하나
    `build`가 돌려주는 사전의 비율(`cer`, `difference`, 구간의 두 끝)은 반올림하지 않은 값이다. 글로 쓸 때
    한 번씩만 반올림한다.
      - `render_json`: 비율을 `round(x, 6)`(소수 여섯째 자리)으로 저장한다. 편집 수·글자 수·발화 수는 정수
        그대로다.
      - `render_markdown`: 반올림하기 전의 값에 100을 곱해 소수 둘째 자리로 쓴다(차이는 부호를 붙인다).
    Markdown을 JSON에 저장된 값에서 만들면 반올림이 두 번(여섯째 자리, 둘째 자리) 겹쳐서, 같은 결과에서 나온
    두 글이 마지막 자리에서 어긋날 수 있다. 둘 다 같은 값에서 따로 한 번씩만 반올림한다. 반올림한 값이
    -0.0이 되면 0.0으로, 퍼센트 글이 -0.00이 되면 +0.00으로 쓴다.

글을 만드는 규칙
    `render_json`·`render_markdown`은 같은 결과에서 언제나 같은 글을 낸다. 사전의 키 차례는 `build`가 만든
    차례 그대로 쓰고(`sort_keys`에 기대지 않는다), 집합을 돌며 글을 만들지 않는다. 줄바꿈은 LF이고, 끝
    개행은 하나다. 파일로 쓰는 것은 부르는 쪽의 일이다(UTF-8, BOM 없음, LF로 쓴다).
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from . import join, score
from .sources import System, Utterance

FORMAT = "asr-compare/1"
SET = "fleurs-ko-test"
RESULT_JSON = f"{SET}.json"
RESULT_MARKDOWN = f"{SET}.md"

# 범위의 이름(결과 사전의 키이기도 하다)과 차례.
SCOPES = ("all", "hangul_only")

# 짝 비교: (이름, 앞 묶음의 키, 뒤 묶음의 키). 차이는 모두 '앞 − 뒤'다.
#   decoding-path  같은 이름의 모델(turbo)을 다른 도구로 디코딩한 두 실행의 차이다. 앞은 whisper-ko-ft의
#                  기준 실행(Transformers), 뒤는 voice-translator의 기본 실행(faster-whisper, 음성 구간
#                  검출 없음)이다.
#   vad            voice-translator의 faster-whisper 실행 둘의 차이다. 앞은 음성 구간 검출을 끈 기본
#                  실행, 뒤는 켠 실행(`vad_filter=True`)이다.
#   both           앞은 whisper-ko-ft의 기준 실행, 뒤는 음성 구간 검출을 켠 faster-whisper 실행이다(위
#                  둘이 모두 다르다).
PAIRS = (
    ("decoding-path", "whisper-large-v3-turbo", "voice-turbo"),
    ("vad", "voice-turbo", "voice-turbo-vad"),
    ("both", "whisper-large-v3-turbo", "voice-turbo-vad"),
)

MINUS = "\N{MINUS SIGN}"


@dataclass(frozen=True)
class _Scope:
    """한 묶음의 한 범위(전체 또는 한글 전용) 채점."""

    edits: list[int]  # 범위의 행 번호 순 발화별 편집 수
    total_edits: int
    total_length: int
    cer: float
    ratios: list[float]  # 다시 뽑기마다 낸 글자 오류율


def _numbers(rows: list[int], limit: int = 5) -> str:
    """오류 메시지에 쓸 행 번호 목록. 길면 앞 limit개만 보이고 나머지는 개수로 적는다."""
    if not rows:
        return "없음"
    text = ", ".join(str(row) for row in rows[:limit])
    return text if len(rows) <= limit else f"{text} 외 {len(rows) - limit}개"


def _by_row(system: System, count: int) -> dict[int, Utterance]:
    """묶음의 발화를 행 번호 -> 발화의 사전으로 만든다.

    행 번호가 정확히 0부터 count-1까지가 아니면(빠지거나 겹치거나 범위 밖이면) ValueError다.
    """
    table: dict[int, Utterance] = {}
    for utterance in system.utterances:
        if utterance.row in table:
            raise ValueError(f"{system.key}: 행 {utterance.row}이(가) 두 번 나온다")
        table[utterance.row] = utterance
    expected = set(range(count))
    if set(table) != expected:
        missing = sorted(expected - set(table))
        outside = sorted(set(table) - expected)
        raise ValueError(
            f"{system.key}: 행 번호가 0부터 {count - 1}까지와 다르다"
            f"(빠진 행 {_numbers(missing)}, 범위 밖 행 {_numbers(outside)})"
        )
    return table


def _score_scope(
    edits_by_row: list[int],
    rows: list[int],
    scope_lengths: list[int],
    length_sums: list[int],
    resamples: list[list[int]],
) -> _Scope:
    """묶음 하나의 한 범위를 채점한다.

    다시 뽑기마다 (뽑은 발화의 편집 수 합) ÷ (뽑은 발화의 글자 수 합)을 낸다.
    """
    edits = [edits_by_row[row] for row in rows]
    total_edits = sum(edits)
    total_length = sum(scope_lengths)
    ratios = [
        sum(map(edits.__getitem__, resample)) / length
        for resample, length in zip(resamples, length_sums, strict=True)
    ]
    return _Scope(edits, total_edits, total_length, total_edits / total_length, ratios)


def build(
    systems: Sequence[System],
    hangul: Sequence[bool],
    inputs: Sequence[tuple[str, str]],
    *,
    pairs: Sequence[tuple[str, str, str]] = PAIRS,
    common: str = join.COMMON_REFERENCE,
) -> dict:
    """읽은 묶음들을 채점해 결과 사전을 만든다(꼴은 모듈 머리 설명과 `render_json`의 출력이 보여 준다).

    systems  채점할 묶음(이 차례 그대로 결과의 `systems`가 된다).
    hangul   한글 전용 표시(행 번호 순). 길이가 발화 수다.
    inputs   읽은 재료의 (저장소 뿌리 기준 경로, sha256) 목록(`Loaded.inputs`). 결과의 `inputs`에 그대로
             적는다.
    pairs, common  시험이 작은 고정물을 쓰게 하는 키워드 인자다. 명령줄은 기본값(`PAIRS`, 공통 정답 묶음)만
                   쓴다.

    ValueError: 발화가 없거나, 한글 전용 발화가 없거나, 묶음의 키가 겹치거나 공통 정답 묶음·짝의 묶음이
    목록에 없거나, 묶음의 행 번호가 빠지거나 겹치거나 범위 밖이거나, 공통 정답이 정규화하면 빈 글인 행이
    있을 때.
    """
    count = len(hangul)
    if count == 0:
        raise ValueError("발화가 하나도 없다")
    tables: dict[str, dict[int, Utterance]] = {}
    for system in systems:
        if system.key in tables:
            raise ValueError(f"묶음 {system.key}이(가) 두 번 나온다")
        tables[system.key] = _by_row(system, count)
    if common not in tables:
        raise ValueError(f"공통 정답 묶음 {common}이(가) 목록에 없다")
    for pair_id, minuend, subtrahend in pairs:
        for key in (minuend, subtrahend):
            if key not in tables:
                raise ValueError(f"짝 {pair_id}: 묶음 {key}이(가) 목록에 없다")

    # 모든 묶음을 공통 정답으로 채점한다. 발화별 (편집 수, 정규화한 정답 글자 수)를 묶음마다 한 번만 센다.
    references = [tables[common][row].reference for row in range(count)]
    for row, text in enumerate(references):
        if not score.normalize(text):
            raise ValueError(f"{common}: 행 {row}의 정답을 정규화하면 빈 글이다")
    counted = {
        key: [score.counts(references[row], table[row].hypothesis) for row in range(count)]
        for key, table in tables.items()
    }
    lengths = [length for _, length in counted[common]]  # 정답이 같으므로 어느 묶음에서든 같다

    # 범위마다 다시 뽑기 번호를 한 번만 만든다. 글자 수의 합은 정답이 같아 묶음과 상관없으므로 한 번만 낸다.
    scope_rows = {"all": list(range(count)), "hangul_only": [row for row in range(count) if hangul[row]]}
    if not scope_rows["hangul_only"]:
        raise ValueError("한글 전용 발화가 하나도 없어 한글 전용 글자 오류율을 낼 수 없다")
    resamples = {name: score.resample_indices(len(rows)) for name, rows in scope_rows.items()}
    scope_lengths = {name: [lengths[row] for row in rows] for name, rows in scope_rows.items()}
    length_sums = {
        name: [sum(map(scope_lengths[name].__getitem__, resample)) for resample in resamples[name]]
        for name in SCOPES
    }

    scored: dict[str, dict[str, _Scope]] = {}
    system_entries = []
    for system in systems:
        edits_by_row = [edits for edits, _ in counted[system.key]]
        scored[system.key] = {
            name: _score_scope(
                edits_by_row, scope_rows[name], scope_lengths[name], length_sums[name], resamples[name]
            )
            for name in SCOPES
        }
        entry: dict = {
            "key": system.key,
            "component": system.component,
            "path": system.path,
            "also": list(system.also),
        }
        for name in SCOPES:
            result = scored[system.key][name]
            entry[name] = {
                "edits": result.total_edits,
                "length": result.total_length,
                "cer": result.cer,
                "interval": list(score.interval(result.ratios)),
            }
        system_entries.append(entry)

    pair_entries = []
    for pair_id, minuend, subtrahend in pairs:
        pair: dict = {"id": pair_id, "minuend": minuend, "subtrahend": subtrahend}
        for name in SCOPES:
            first, second = scored[minuend][name], scored[subtrahend][name]
            differences = [a - b for a, b in zip(first.ratios, second.ratios, strict=True)]
            pairs_of_edits = list(zip(first.edits, second.edits, strict=True))
            pair[name] = {
                "difference": first.cer - second.cer,
                "interval": list(score.interval(differences)),
                "fewer_edits": sum(1 for a, b in pairs_of_edits if a < b),
                "more_edits": sum(1 for a, b in pairs_of_edits if a > b),
                "same": sum(1 for a, b in pairs_of_edits if a == b),
            }
        pair_entries.append(pair)

    return {
        "format": FORMAT,
        "set": SET,
        "utterances": count,
        "hangul_only": len(scope_rows["hangul_only"]),
        "inputs": [{"path": path, "sha256": digest} for path, digest in inputs],
        "systems": system_entries,
        "pairs": pair_entries,
    }


# ---------------------------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------------------------


def _stored(value):
    """결과 사전을 JSON에 저장할 값으로 바꾼 사본.

    소수는 여섯째 자리로 반올림하고, 사전과 목록의 차례는 그대로 둔다. `round(x, 6) + 0.0`은 반올림한 값이
    -0.0이면 0.0으로 바꾼다(그 밖의 값은 그대로다).
    """
    if isinstance(value, float):
        return round(value, 6) + 0.0
    if isinstance(value, dict):
        return {key: _stored(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stored(item) for item in value]
    return value


def render_json(result: dict) -> str:
    """결과를 JSON 글로 쓴다. 입력은 고치지 않는다.

    한글은 이스케이프하지 않고, 들여쓰기는 한 칸이고, 끝 개행은 하나다.
    """
    return json.dumps(_stored(result), ensure_ascii=False, indent=1) + "\n"


# ---------------------------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------------------------

# 표의 열: (제목, 오른쪽 맞춤인지). 짝 표의 '앞 − 뒤'는 앞 묶음에서 뒤 묶음을 뺀 값이라는 뜻이다.
SYSTEM_COLUMNS = (
    ("묶음", False),
    ("구성 요소", False),
    ("편집 수", True),
    ("정답 글자 수", True),
    ("글자 오류율(%)", True),
    ("95% 구간(%)", False),
)
PAIR_COLUMNS = (
    ("짝", False),
    (f"앞 {MINUS} 뒤", False),
    ("범위", False),
    ("차이(%p)", True),
    ("95% 구간(%p)", False),
    ("앞이 적은 발화", True),
    ("앞이 많은 발화", True),
    ("같은 발화", True),
)
SCOPE_LABELS = {"all": "전체", "hangul_only": "한글 전용"}


def _percent(value: float) -> str:
    return f"{value * 100:.2f}"


def _signed_percent(value: float) -> str:
    text = f"{value * 100:+.2f}"
    return "+0.00" if text == "-0.00" else text


def _interval_text(interval: list[float], signed: bool) -> str:
    """구간을 `[아래, 위]` 꼴로 쓴다(물결표를 쓰지 않는다: 한 문단에 둘이 있으면 취소선이 된다)."""
    show = _signed_percent if signed else _percent
    return f"[{show(interval[0])}, {show(interval[1])}]"


def _table(columns: tuple[tuple[str, bool], ...], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(title for title, _ in columns) + " |"]
    lines.append("|" + "|".join("---:" if right else "---" for _, right in columns) + "|")
    lines.extend("| " + " | ".join(cells) + " |" for cells in rows)
    return lines


def _systems_table(result: dict, scope: str) -> list[str]:
    rows = []
    for system in result["systems"]:
        entry = system[scope]
        rows.append(
            [
                system["key"],
                system["component"],
                str(entry["edits"]),
                str(entry["length"]),
                _percent(entry["cer"]),
                _interval_text(entry["interval"], signed=False),
            ]
        )
    return _table(SYSTEM_COLUMNS, rows)


def _pairs_table(result: dict) -> list[str]:
    rows = []
    for pair in result["pairs"]:
        for scope in SCOPES:
            entry = pair[scope]
            rows.append(
                [
                    pair["id"],
                    f"{pair['minuend']} {MINUS} {pair['subtrahend']}",
                    SCOPE_LABELS[scope],
                    _signed_percent(entry["difference"]),
                    _interval_text(entry["interval"], signed=True),
                    str(entry["fewer_edits"]),
                    str(entry["more_edits"]),
                    str(entry["same"]),
                ]
            )
    return _table(PAIR_COLUMNS, rows)


def render_markdown(result: dict) -> str:
    """결과를 Markdown 글로 쓴다: 제목, 재료와 규칙이 어디 있는지 한 줄, 표 셋(전체, 한글 전용, 짝 비교).

    묶음의 줄 차례는 결과의 `systems` 차례 그대로다(오류율로 정렬하지 않는다). 판정 문구는 넣지 않는다. 모든
    줄이 제목·인용·표 가운데 하나라서 빈 줄 없이 이어진 보통 줄이 한 문단으로 붙는 일이 없다.
    """
    lines = [
        f"# 같은 발화 인식 비교 ({result['set']})",
        "",
        "> 구성 요소가 이미 커밋한 발화별 가설을 같은 규칙으로 다시 채점한 결과다(새 디코딩 없음). "
        "읽은 재료와 sha256은 같은 이름의 JSON 파일의 `inputs`에 있고, 규칙은 저장소의 "
        "`docs/asr-comparison.md`에 있다. 95% 구간은 발화를 다시 뽑는 부트스트랩이다"
        f"({score.RESAMPLES}번, 시드 {score.SEED}).",
        "",
        f"## 전체 {result['utterances']}발화",
        "",
        *_systems_table(result, "all"),
        "",
        f"## 한글 전용 {result['hangul_only']}발화",
        "",
        *_systems_table(result, "hangul_only"),
        "",
        "## 짝 비교",
        "",
        *_pairs_table(result),
    ]
    return "\n".join(lines) + "\n"
