"""재료(구성 요소가 커밋해 둔 리포트 파일)를 읽어 발화 목록으로 바꾸는 읽기 계층.

이 모듈은 파일을 읽고 꼴을 확인해 `Utterance`(발화 하나)와 `System`(가설 묶음 하나)으로 바꿀 뿐, 두 묶음이
같은 발화를 가리키는지는 판단하지 않는다(그것은 `join.verify`가 한다). 재료 파일은 읽기만 한다.

읽는 세 꼴
    voice-translator   최상위가 길이 1인 목록이다. `[0]["languages"]["ko"]["items"]`의 항목이 `id`(정수 문장
                       번호), `audio_s`(음성 길이), `reference`, `hypothesis`를 가진다. 글은 이미
                       정규화한(공백이 없는) 글이다.
    whisper-ko-ft      `{"summary": ..., "utterances": [...]}`. 발화가 `id`(문장 번호. 같은 문장의 둘째
                       녹음부터 `<번호>#<n>`), `seconds`, `reference`, `hypothesis`(정규화 전 원문)를
                       가진다.
    stt-scratch        매니페스트(JSONL: `id`, `duration_s`, `hangul_only`)와 가설 파일(JSONL: `id`, `ref`,
                       `hyp`). `id`는 `fleurs/test/<문장 번호>/<행 번호>`이고, 파일 안 차례는 행 번호 순이
                       아니라 id 글자의 사전순이다.

행 번호로 짝짓는 까닭과 그 전제
    세 구성 요소는 같은 FLEURS 한국어 test(parquet)를 쓰고, 각 리포트의 발화는 그 parquet의 행과 하나씩
    대응한다. 이 도구는 그 행 번호로 같은 발화를 짝짓는다. 행 번호를 얻는 방법은 구성 요소마다 다르다.
      - stt-scratch는 발화 id의 마지막 수가 행 번호다. 파일 안 차례(id 글자의 사전순)에 기대지 않으므로 줄
        차례가 어떻게 바뀌어도 같은 결과가 나온다.
      - voice-translator와 whisper-ko-ft의 항목에는 행 번호가 없다. 이 도구는 리포트 안의 위치를 행 번호로
        받아들인다(전제). 이 전제의 증거는 `join.verify`의 문장 번호(2번)·음성 길이(3번) 검사와
        whisper-ko-ft의 `<번호>#<n>` 표시(4번) 검사다.
    파일 안 차례나 문장 번호, (문장 번호, 음성 길이)로 짝지으면 조용히 틀릴 수 있다. stt-scratch는 파일 안
    차례가 행 번호 순이 아니라서 어긋나고, 같은 문장을 두 번 녹음한 발화는 문장 번호가 같아 구별되지 않고,
    음성 길이까지 같은 쌍도 있어(실제 재료에 하나) 길이로도 구별되지 않는다. 그런 쌍이 전제에 남기는 틈은
    `join`의 머리 설명 '이 검사들로도 잡지 못하는 것'에 적었다.

리포트가 스스로 적어 둔 채점 값
    whisper-ko-ft의 리포트는 발화마다 `edits`와 `length`, 앞쪽 `summary`에 `error_rate`를 적어 둔다. 구성
    요소가 이미 기록한 값이라서 이 도구가 저장된 가설에서 다시 세어 같은 값이 나오는지 볼 수 있다(`recorded`
    모듈). `load_stored`가 그 값만 읽고(`Stored`), `load_repository`가 열 묶음 모두에 대해 같은 바이트에서
    함께 읽어 `Loaded.stored`에 싣는다. 파일을 다시 열지 않는다.

줄바꿈과 글자 코드에 흔들리지 않는 읽기
    줄바꿈 변환을 켠 채 받은 복제본에서는 같은 파일이 CRLF로 들어온다. 그래서 읽을 때는 언제나 바이트에서
    줄 끝의 CRLF를 LF로 바꾼 뒤 `utf-8-sig`(앞의 BOM은 버린다)로 푼다. 재료의 sha256(`digest`)도 같은 방식으로
    줄 끝을 맞춘 바이트에서 낸다. 그래서 LF로 커밋된 파일의 값은 `sha256sum`의 값과 같고, CRLF로 커밋된
    파일(stt-scratch의 가설 파일 둘)의 값은 줄 끝의 CR을 뗀 내용의 값이다. 어디서 받은 복제본이든 같은 값이
    나온다.

읽지 못함과 어긋남은 다르다
    파일이 없거나, UTF-8이 아니거나, JSON 문법이 틀렸거나(문법은 맞아도 파서가 읽지 못할 만큼 값이 크거나 깊게
    겹친 경우 포함), 기대한 키나 자료형이 아니면 `SourceError` 하나로 알린다(메시지에 저장소 뿌리 기준 경로와
    까닭이 들어 있다). 발화 수, 행 번호, 문장 번호처럼 내용이 서로 맞지 않는 것은 읽는 쪽의 오류가 아니라
    `join.verify`가 한 줄씩 알리는 어긋남이다. 이 모듈은 그런 내용을 고치거나 건너뛰지 않고 읽은 그대로
    돌려준다.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import NamedTuple

VOICE = "voice-translator"
WHISPER = "whisper-ko-ft"
STT = "stt-scratch"

# stt-scratch의 매니페스트: 두 stt-scratch 묶음이 같은 파일을 쓴다. 행 번호·문장 번호·음성 길이·한글 전용
# 표시는 가설 파일이 아니라 여기서 읽는다.
STT_MANIFEST = "stt-scratch/manifests/test_fleurs.jsonl"

# stt-scratch의 id: 문장 번호와 행 번호. 자릿수를 아홉 자리로 막아 터무니없이 긴 수가 정수 변환에서 예외로
# 번지지 않게 한다.
_STT_ID = re.compile(r"fleurs/test/([0-9]{1,9})/([0-9]{1,9})")


class SourceError(Exception):
    """재료를 읽지 못했다. 메시지는 `<저장소 뿌리 기준 경로>: <까닭>` 꼴이다.

    명령줄은 이 예외만 잡아 한 줄을 쓰고 종료 코드 2로 끝낸다. 다른 예외는 잡지 않는다: 버그는 흔적(추적
    출력)과 함께 실패해야 하고, 읽지 못했는데 통과로 끝나는 길이 없어야 하기 때문이다.
    """


@dataclass(frozen=True)
class Utterance:
    """발화 하나. 세 꼴 모두 이 다섯 값으로 바꿔 읽는다.

    row        FLEURS 한국어 test의 행 번호(0부터). 발화를 짝짓는 유일한 열쇠다.
    sentence   문장 번호(글). 같은 문장을 두 번 녹음한 발화는 문장 번호가 같다.
    seconds    음성 길이(초). 구성 요소마다 적은 자릿수가 달라서, 견줄 때는 소수 둘째 자리로 반올림한다.
    reference  리포트에 저장된 정답. 구성 요소마다 저장하는 꼴이 다르다(정규화 전 원문이거나 정규화한 글).
    hypothesis 리포트에 저장된 가설. 같은 방식으로 저장된 그대로다.
    """

    row: int
    sentence: str
    seconds: float
    reference: str
    hypothesis: str


@dataclass(frozen=True)
class System:
    """가설 묶음 하나: 한 리포트가 담은 발화 전체.

    key         묶음의 이름(`SYSTEMS`의 키. 같은 가설을 가진 형제 리포트는 그 리포트의 이름).
    component   읽은 구성 요소(voice-translator, whisper-ko-ft, stt-scratch).
    path        재료 파일의 저장소 뿌리 기준 경로(stt-scratch는 가설 파일).
    also        같은 가설이라고 적은 다른 리포트의 이름(`TWINS`). 이 모듈의 읽기 함수는 비워 두고
                `load_repository`가 채운다.
    utterances  발화. 읽기 함수가 만든 묶음은 행 번호 순이다(voice-translator와 whisper-ko-ft는 파일 안
                위치가 곧 행 번호이고, stt-scratch는 읽은 뒤 행 번호로 정렬했다). 손으로 만든 묶음은 그렇지
                않을 수 있고 `join.verify`는 행 번호의 집합만 본다. 그래서 발화를 찾는 코드는 튜플의 위치가
                아니라 `row`로 찾는다.
    ids         발화마다 리포트에 적힌 id 글(`utterances`와 같은 차례). whisper-ko-ft는 `#` 뒤의 수가
                여기에만 남아서, `join.verify`가 같은 문장의 n번째 녹음 표시가 맞는지 확인하는 데 쓴다.
    """

    key: str
    component: str
    path: str
    also: tuple[str, ...]
    utterances: tuple[Utterance, ...]
    ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Stored:
    """whisper-ko-ft 리포트가 스스로 적어 둔 채점 값. 이 도구가 다시 세어 볼 기록값이다.

    error_rate  `summary.error_rate`(글자 오류율. 소수 다섯째 자리까지 적힌다).
    counts      발화마다 (`edits`, `length`). 리포트의 `utterances` 안 차례이고 그 차례가 행 번호다.
    """

    error_rate: float
    counts: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Spec:
    """견줄 가설 묶음 하나가 어디에 있는지 적은 고정 목록의 항목. 파일을 읽기 전의 설명이다."""

    key: str
    component: str
    path: str
    also: tuple[str, ...] = ()


def _whisper_path(name: str) -> str:
    """whisper-ko-ft 리포트 폴더 이름에서 한국어 test 리포트 파일의 경로를 만든다."""
    return f"whisper-ko-ft/reports/{name}/fleurs-ko-test.json"


# 견줄 가설 묶음 열네 개(차례도 고정이다). 전화 채널로 잰 whisper-ko-ft 리포트는 조건이 달라 넣지 않았다.
#   - voice-translator의 `_rescored` 판은 정답을 다시 정규화해 저장한 파일이다. 원본에는 작은따옴표가 남은
#     정답이 있어서 다른 두 구성 요소와 같은 규칙으로 맞추려면 이 판을 읽는다.
#   - whisper-ko-ft의 키는 리포트 폴더 이름이다. 가설이 글자까지 같다고 적힌 형제 리포트(`also`)는 묶음으로
#     세지 않고, 읽은 뒤 `join.verify`가 정말 같은지 확인한다.
SYSTEMS: tuple[Spec, ...] = (
    Spec("voice-turbo-vad", VOICE, "voice-translator/backend/eval/reports/stt_t14_test_20260913_055810.json"),
    Spec(
        "voice-turbo",
        VOICE,
        "voice-translator/backend/eval/reports/stt_t2_test_20260912_224129_rescored.json",
    ),
    Spec("whisper-small", WHISPER, _whisper_path("whisper-small")),
    Spec("whisper-large-v3-turbo", WHISPER, _whisper_path("whisper-large-v3-turbo")),
    Spec("small-a", WHISPER, _whisper_path("small-a")),
    Spec("turbo-l2", WHISPER, _whisper_path("turbo-l2")),
    Spec("turbo-t", WHISPER, _whisper_path("turbo-t")),
    Spec("turbo-n", WHISPER, _whisper_path("turbo-n"), also=("turbo-n-d1a",)),
    Spec("turbo-n2", WHISPER, _whisper_path("turbo-n2")),
    Spec("qwen3-asr-1.7b", WHISPER, _whisper_path("qwen3-asr-1.7b"), also=("qwen3-asr-1.7b-fixed",)),
    Spec("qwen3-asr-1.7b-qn", WHISPER, _whisper_path("qwen3-asr-1.7b-qn"), also=("qwen3-asr-1.7b-qn-fixed",)),
    Spec(
        "qwen3-asr-1.7b-qn-s050",
        WHISPER,
        _whisper_path("qwen3-asr-1.7b-qn-s050"),
        also=("qwen3-asr-1.7b-qn-s050-fixed",),
    ),
    Spec("stt-scratch-full", STT, "stt-scratch/reports/final/test_fleurs-full.hyps.jsonl"),
    Spec("stt-scratch-streaming", STT, "stt-scratch/reports/final/test_fleurs-streaming.hyps.jsonl"),
)

# 같은 가설이라고 적힌 형제 리포트의 이름들(`SYSTEMS`의 `also`를 모은 것). 모두 whisper-ko-ft 리포트다.
TWINS: tuple[str, ...] = tuple(name for spec in SYSTEMS for name in spec.also)


def digest(data: bytes) -> str:
    """재료 파일의 sha256(16진수). 줄 끝 CRLF를 LF로 맞춘 바이트에서 낸다.

    그래서 줄바꿈 변환을 켠 채 받은 복제본에서도 같은 값이 나온다. LF로 저장된 파일은 `sha256sum`의 값과
    같고, CRLF로 저장된 파일은 줄 끝의 CR을 뗀 내용의 값이다. BOM은 떼지 않는다(떼는 것은 글로 풀 때뿐이다).
    """
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


# ---------------------------------------------------------------------------------------------
# 낮은 층: 글로 풀기, JSON 읽기, 값 꺼내기. 모든 실패는 SourceError(경로와 까닭)로 올린다.
# ---------------------------------------------------------------------------------------------


def _fail(path: str, reason: str) -> SourceError:
    return SourceError(f"{path}: {reason}")


def _decode(data: bytes, path: str) -> str:
    """바이트를 글로 푼다. 줄 끝을 LF로 맞춘 뒤 `utf-8-sig`로 풀어 앞의 BOM을 버린다."""
    try:
        return data.replace(b"\r\n", b"\n").decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise _fail(path, f"UTF-8로 읽을 수 없다({error.reason}, {error.start}번째 바이트 근처)") from error


def _parse_json(text: str, path: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise _fail(
            path, f"JSON 문법 오류({error.msg}, {error.lineno}번째 줄 {error.colno}번째 글자)"
        ) from error
    except RecursionError as error:
        # 문법은 맞지만 파이썬 파서가 읽을 수 없을 만큼 깊게 겹친 JSON(여는 괄호를 아주 많이 겹친 것).
        raise _fail(path, "JSON이 너무 깊게 겹쳐 있어 읽을 수 없다") from error
    except ValueError as error:
        # 문법은 맞지만 값을 바꾸지 못하는 경우(예: 정수 자릿수 한도를 넘는 아주 긴 수).
        raise _fail(path, f"JSON 값을 읽을 수 없다({error})") from error


def _parse_lines(data: bytes, path: str) -> list[tuple[int, object]]:
    """JSONL을 (줄 번호, 읽은 값) 목록으로 읽는다. 줄 번호는 1부터 세고, 빈 줄은 건너뛴다.

    줄은 `\\n`으로만 나눈다. `str.splitlines()`는 U+2028 같은 글자에서도 줄을 나누므로, 이스케이프하지 않고
    그 글자를 적은 JSON 문자열을 두 줄로 쪼개 멀쩡한 파일을 깨진 것으로 만들 수 있다.
    """
    rows: list[tuple[int, object]] = []
    for number, line in enumerate(_decode(data, path).split("\n"), start=1):
        if not line.strip():
            continue
        try:
            rows.append((number, json.loads(line)))
        except json.JSONDecodeError as error:
            raise _fail(path, f"{number}번째 줄이 JSON이 아니다({error.msg})") from error
        except RecursionError as error:
            raise _fail(path, f"{number}번째 줄의 JSON이 너무 깊게 겹쳐 있어 읽을 수 없다") from error
        except ValueError as error:
            raise _fail(path, f"{number}번째 줄의 JSON 값을 읽을 수 없다({error})") from error
    return rows


def _member(container: object, key: str, where: str, path: str) -> object:
    """JSON 객체에서 키의 값을 꺼낸다. 객체가 아니거나 키가 없으면 SourceError다."""
    if not isinstance(container, dict):
        raise _fail(path, f"{where}: JSON 객체가 아니다({type(container).__name__})")
    if key not in container:
        raise _fail(path, f"{where}: '{key}' 키가 없다")
    return container[key]


def _as_list(value: object, where: str, path: str) -> list:
    if not isinstance(value, list):
        raise _fail(path, f"{where}: 목록이 아니다({type(value).__name__})")
    return value


def _string(container: object, key: str, where: str, path: str) -> str:
    value = _member(container, key, where, path)
    if not isinstance(value, str):
        raise _fail(path, f"{where}.{key}: 글이 아니다({type(value).__name__})")
    return value


def _integer(container: object, key: str, where: str, path: str) -> int:
    value = _member(container, key, where, path)
    # bool은 int의 하위 형이라 따로 막는다(`true`를 문장 번호 1로 읽지 않는다).
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(path, f"{where}.{key}: 정수가 아니다({type(value).__name__})")
    return value


def _number(container: object, key: str, where: str, path: str) -> float:
    """유한한 수만 받는다. NaN과 무한대는 서로 같지 않거나 비교가 무의미해서 길이 검사를 엉뚱하게 만든다."""
    value = _member(container, key, where, path)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _fail(path, f"{where}.{key}: 수가 아니다({type(value).__name__})")
    try:
        number = float(value)
    except OverflowError:  # 실수로 바꿀 수 없을 만큼 큰 정수
        number = math.inf
    if not math.isfinite(number):
        raise _fail(path, f"{where}.{key}: 유한한 수가 아니다")
    return number


def _flag(container: object, key: str, where: str, path: str) -> bool:
    value = _member(container, key, where, path)
    if not isinstance(value, bool):
        raise _fail(path, f"{where}.{key}: 참/거짓이 아니다({type(value).__name__})")
    return value


# ---------------------------------------------------------------------------------------------
# 꼴마다 읽기
# ---------------------------------------------------------------------------------------------


def load_voice(data: bytes, key: str, path: str) -> System:
    """voice-translator 리포트를 읽는다. 행 번호는 `items` 안의 위치, 문장 번호는 `id`를 글로 바꾼 것이다.

    영어(`en`) 항목과 읽지 않는 키(`elapsed_s`, `error` 등)는 보지 않는다. 정답·가설은 저장된 글(이미
    정규화한 글) 그대로다. 위치를 행 번호로 받아들이는 것은 전제다(모듈 머리 설명).
    """
    document = _parse_json(_decode(data, path), path)
    if not isinstance(document, list) or len(document) != 1:
        raise _fail(path, "최상위가 길이 1인 목록이 아니다")
    languages = _member(document[0], "languages", "최상위 첫 항목", path)
    korean = _member(languages, "ko", "languages", path)
    items = _as_list(_member(korean, "items", "languages.ko", path), "languages.ko.items", path)
    utterances: list[Utterance] = []
    ids: list[str] = []
    for row, item in enumerate(items):
        where = f"items[{row}]"
        sentence = str(_integer(item, "id", where, path))
        utterances.append(
            Utterance(
                row=row,
                sentence=sentence,
                seconds=_number(item, "audio_s", where, path),
                reference=_string(item, "reference", where, path),
                hypothesis=_string(item, "hypothesis", where, path),
            )
        )
        ids.append(sentence)
    return System(key, VOICE, path, (), tuple(utterances), tuple(ids))


def load_whisper(data: bytes, key: str, path: str) -> System:
    """whisper-ko-ft 리포트를 읽는다. 행 번호는 `utterances` 안의 위치, 문장 번호는 `id`에서 `#` 앞이다.

    `#` 뒤의 수(같은 문장의 몇 번째 녹음인지)는 문장 번호에서는 버리지만, `id` 글 전체는 `System.ids`에
    그대로 남긴다. 정답·가설은 정규화하기 전의 원문 그대로다. 위치를 행 번호로 받아들이는 것은 전제다(모듈
    머리 설명).
    """
    document = _parse_json(_decode(data, path), path)
    items = _as_list(_member(document, "utterances", "최상위", path), "utterances", path)
    utterances: list[Utterance] = []
    ids: list[str] = []
    for row, item in enumerate(items):
        where = f"utterances[{row}]"
        identifier = _string(item, "id", where, path)
        utterances.append(
            Utterance(
                row=row,
                sentence=identifier.partition("#")[0],
                seconds=_number(item, "seconds", where, path),
                reference=_string(item, "reference", where, path),
                hypothesis=_string(item, "hypothesis", where, path),
            )
        )
        ids.append(identifier)
    return System(key, WHISPER, path, (), tuple(utterances), tuple(ids))


def load_stored(data: bytes, path: str) -> Stored:
    """whisper-ko-ft 리포트가 스스로 적어 둔 채점 값을 읽는다.

    읽는 것은 `summary.error_rate`와 발화마다의 `edits`, `length`다. `load_whisper`가 읽는 것과 같은 파일이고,
    그것이 읽지 않는 키만 읽는다. 값이 없거나 자료형이 틀리면 SourceError다. 값이 서로 맞는지(다시 센 값과
    같은지)는 여기서 보지 않는다. 그것은 `recorded`가 한다.
    """
    document = _parse_json(_decode(data, path), path)
    summary = _member(document, "summary", "최상위", path)
    error_rate = _number(summary, "error_rate", "summary", path)
    items = _as_list(_member(document, "utterances", "최상위", path), "utterances", path)
    counts = []
    for row, item in enumerate(items):
        where = f"utterances[{row}]"
        counts.append((_integer(item, "edits", where, path), _integer(item, "length", where, path)))
    return Stored(error_rate, tuple(counts))


class _Entry(NamedTuple):
    """stt-scratch 매니페스트 한 줄에서 읽은 값."""

    row: int
    sentence: str
    seconds: float
    hangul: bool


def _split_id(identifier: str, where: str, path: str) -> tuple[str, int]:
    """`fleurs/test/<문장 번호>/<행 번호>`를 (문장 번호, 행 번호)로 가른다. 이 꼴이 아니면 SourceError다."""
    match = _STT_ID.fullmatch(identifier)
    if match is None:
        raise _fail(path, f"{where}: id '{identifier}'가 fleurs/test/<문장 번호>/<행 번호> 꼴이 아니다")
    return match.group(1), int(match.group(2))


def _read_manifest(manifest: bytes) -> dict[str, _Entry]:
    """매니페스트를 id -> 값의 사전으로 읽는다.

    같은 id가 두 번 나오면 어느 쪽이 맞는지 알 수 없으므로 SourceError다.
    """
    entries: dict[str, _Entry] = {}
    for number, item in _parse_lines(manifest, STT_MANIFEST):
        where = f"{number}번째 줄"
        identifier = _string(item, "id", where, STT_MANIFEST)
        sentence, row = _split_id(identifier, where, STT_MANIFEST)
        if identifier in entries:
            raise _fail(STT_MANIFEST, f"{where}: id '{identifier}'가 두 번 나온다")
        entries[identifier] = _Entry(
            row=row,
            sentence=sentence,
            seconds=_number(item, "duration_s", where, STT_MANIFEST),
            hangul=_flag(item, "hangul_only", where, STT_MANIFEST),
        )
    return entries


def load_stt(manifest: bytes, hyps: bytes, key: str, path: str) -> tuple[System, tuple[bool, ...]]:
    """stt-scratch의 가설 파일 하나를 읽는다(매니페스트와 함께).

    행 번호는 `id`의 마지막 수, 문장 번호는 그 앞의 수이고, 음성 길이는 매니페스트의 `duration_s`, 정답은
    가설 파일의 `ref`, 가설은 `hyp`다. 파일 안 차례(id 글자 사전순)에 기대지 않으며, 읽은 뒤 발화를 행 번호
    순으로 정렬한다. 돌려주는 둘째 값은 매니페스트의 `hangul_only`를 행 번호 순으로 늘어놓은 것이다.

    가설 파일의 id가 매니페스트에 없거나 반대로 매니페스트의 id가 가설 파일에 없으면 SourceError다(두 파일이
    같은 발화를 말해야 하기 때문이다). 같은 행 번호가 두 번 나오는 것처럼 내용이 맞지 않는 점은 여기서
    판단하지 않고 `join.verify`가 알린다.
    """
    entries = _read_manifest(manifest)
    seen: set[str] = set()
    pairs: list[tuple[Utterance, str]] = []
    for number, item in _parse_lines(hyps, path):
        where = f"{number}번째 줄"
        identifier = _string(item, "id", where, path)
        _split_id(identifier, where, path)  # 꼴이 틀린 id는 '매니페스트에 없다'보다 먼저 꼴 오류로 알린다
        if identifier in seen:
            raise _fail(path, f"{where}: id '{identifier}'가 두 번 나온다")
        seen.add(identifier)
        entry = entries.get(identifier)
        if entry is None:
            raise _fail(path, f"{where}: id '{identifier}'가 매니페스트({STT_MANIFEST})에 없다")
        utterance = Utterance(
            row=entry.row,
            sentence=entry.sentence,
            seconds=entry.seconds,
            reference=_string(item, "ref", where, path),
            hypothesis=_string(item, "hyp", where, path),
        )
        pairs.append((utterance, identifier))
    absent = [identifier for identifier in entries if identifier not in seen]
    if absent:
        raise _fail(
            path,
            f"매니페스트({STT_MANIFEST})의 id {len(absent)}개가 이 파일에 없다(처음 하나: '{absent[0]}')",
        )
    pairs.sort(key=lambda pair: pair[0].row)
    hangul = tuple(entry.hangul for entry in sorted(entries.values(), key=lambda entry: entry.row))
    system = System(key, STT, path, (), tuple(u for u, _ in pairs), tuple(i for _, i in pairs))
    return system, hangul


# ---------------------------------------------------------------------------------------------
# 저장소 단위 읽기
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Loaded:
    """저장소 한 곳을 읽은 결과. 명령줄과 시험은 이 값으로만 실제 꼴의 폴더를 읽는다.

    systems   견줄 묶음 열네 개(`SYSTEMS`의 차례).
    twins     같은 가설이라고 적힌 형제 리포트 넷(키는 리포트 이름). 묶음으로 세지 않고, 가설이 같은지
              확인하는 데만 쓴다.
    hangul    한글 전용 표시(행 번호 순).
    inputs    읽은 재료 파일 열아홉 개의 (저장소 뿌리 기준 경로, sha256), 경로 순. sha256의 정의는
              `digest`에 있다.
    stored    whisper-ko-ft 묶음 열 개의 리포트가 스스로 적어 둔 값(키는 묶음의 키). 같은 바이트에서
              `systems`와 함께 읽는다. 형제 리포트는 읽지 않는다(가설이 같다는 것은 `join.verify`가 본다).
    """

    systems: tuple[System, ...]
    twins: dict[str, System]
    hangul: tuple[bool, ...]
    inputs: tuple[tuple[str, str], ...]
    stored: dict[str, Stored] = field(default_factory=dict)


def _read_file(root: Path, path: str) -> bytes:
    """저장소 뿌리 아래의 파일을 바이트로 읽는다. 읽지 못하면 SourceError(저장소 뿌리 기준 경로)다."""
    try:
        return root.joinpath(*path.split("/")).read_bytes()
    except FileNotFoundError as error:
        raise _fail(path, "파일이 없다") from error
    except OSError as error:
        raise _fail(path, f"파일을 읽지 못했다({error.strerror or type(error).__name__})") from error


def load_repository(root: Path) -> Loaded:
    """저장소 뿌리(`root`)에서 재료 파일 열아홉 개를 읽어 `Loaded`로 돌려준다.

    읽는 쪽 오류는 모두 SourceError다. whisper-ko-ft 열 묶음은 같은 바이트에서 리포트가 스스로 적어 둔 값
    (`Loaded.stored`)도 함께 읽는다. 두 stt-scratch 묶음이 같은 매니페스트에서 읽은 한글 전용 표시가 서로
    다르면(같은 파일에서 나왔으니 달라질 수 없다) 어느 한쪽을 고르지 않고 SourceError로 멈춘다. 이 함수는
    발화가 서로 맞는지(`join.verify`의 일)는 보지 않는다.
    """
    root = Path(root)
    digests: dict[str, str] = {}

    def read(path: str) -> bytes:
        data = _read_file(root, path)
        digests[path] = digest(data)
        return data

    systems: list[System] = []
    stored: dict[str, Stored] = {}
    manifest: bytes | None = None
    hangul: tuple[bool, ...] | None = None
    for spec in SYSTEMS:
        if spec.component == VOICE:
            system = load_voice(read(spec.path), spec.key, spec.path)
        elif spec.component == WHISPER:
            data = read(spec.path)
            system = load_whisper(data, spec.key, spec.path)
            stored[spec.key] = load_stored(data, spec.path)
        else:
            if manifest is None:
                manifest = read(STT_MANIFEST)
            system, flags = load_stt(manifest, read(spec.path), spec.key, spec.path)
            if hangul is not None and flags != hangul:
                raise _fail(STT_MANIFEST, f"{spec.key}: 앞서 읽은 stt-scratch 묶음과 한글 전용 표시가 다르다")
            hangul = flags
        systems.append(replace(system, also=spec.also))

    twins: dict[str, System] = {}
    for name in TWINS:
        path = _whisper_path(name)
        twins[name] = load_whisper(read(path), name, path)

    return Loaded(
        systems=tuple(systems),
        twins=twins,
        hangul=hangul if hangul is not None else (),
        inputs=tuple(sorted(digests.items())),
        stored=stored,
    )
