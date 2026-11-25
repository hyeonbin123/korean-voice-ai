"""읽기 계층(sources)의 시험.

세 구성 요소의 리포트 꼴(voice-translator, whisper-ko-ft, stt-scratch)을 손으로 쓴 작은 예(3발화)로 만들어
바이트로 주고, 발화가 기대대로 나오는지 본다. 이어서 이 읽기가 지켜야 할 약속을 시험한다: 행 번호는 파일 안
차례가 아니라 각 꼴이 정한 자리에서 읽고, 줄바꿈 방식이 달라도 같은 결과를 내고, 읽지 못하는 입력은 모두
SourceError 하나로 알린다. 저장소 단위(load_repository)는 합성 고정물 폴더로 시험한다(실제 리포트 파일은
열지 않는다).
"""

import hashlib
import json
import sys

import pytest

from asr_compare import sources
from asr_compare.sources import SourceError, System, Utterance

VOICE_PATH = "voice-translator/backend/eval/reports/demo.json"
WHISPER_PATH = "whisper-ko-ft/reports/demo/fleurs-ko-test.json"
STT_PATH = "stt-scratch/reports/final/demo.hyps.jsonl"

SYSTEM_KEYS = [
    "voice-turbo-vad",
    "voice-turbo",
    "whisper-small",
    "whisper-large-v3-turbo",
    "small-a",
    "turbo-l2",
    "turbo-t",
    "turbo-n",
    "turbo-n2",
    "qwen3-asr-1.7b",
    "qwen3-asr-1.7b-qn",
    "qwen3-asr-1.7b-qn-s050",
    "stt-scratch-full",
    "stt-scratch-streaming",
]
TWIN_NAMES = [
    "turbo-n-d1a",
    "qwen3-asr-1.7b-fixed",
    "qwen3-asr-1.7b-qn-fixed",
    "qwen3-asr-1.7b-qn-s050-fixed",
]
FULL_SIZE = {"utterances": 382, "hangul_only": 257, "differences": (23, 57)}

# changed()에 값 대신 주면 그 키를 뺀다.
MISSING = object()


@pytest.fixture(autouse=True)
def default_int_digit_limit():
    """정수 변환의 자릿수 한도를 파이썬 기본값(4300)으로 고정하고, 시험이 끝나면 원래대로 돌린다.

    '아주 긴 수' 사례는 이 한도를 넘는 5,000자리 수로 JSON 값을 읽을 수 없는 경우를 만든다. 환경 설정으로
    한도를 풀어 둔 곳에서도 같은 결과가 나오게 한다.
    """
    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(4300)
    yield
    sys.set_int_max_str_digits(previous)


# ---------------------------------------------------------------------------------------------
# 손으로 쓴 작은 예(3발화)
# ---------------------------------------------------------------------------------------------


def dump(value) -> bytes:
    """JSON 문서 하나를 UTF-8 바이트(LF 줄 끝)로 만든다."""
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def dump_lines(rows) -> bytes:
    """사전 목록을 한 줄에 하나씩 적은 JSONL 바이트(LF 줄 끝)로 만든다."""
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")


def changed(base: dict, **changes) -> dict:
    """base의 복사본에서 키를 바꾼다. 값으로 MISSING을 주면 그 키를 뺀다."""
    result = dict(base)
    for key, value in changes.items():
        if value is MISSING:
            del result[key]
        else:
            result[key] = value
    return result


def voice_items():
    return [
        {
            "id": 1883,
            "audio_s": 5.2,
            "elapsed_s": 0.1,
            "error": 0.0,
            "reference": "가나다",
            "hypothesis": "가나다",
        },
        {
            "id": 1929,
            "audio_s": 7.4,
            "elapsed_s": 0.2,
            "error": 0.0,
            "reference": "라마바",
            "hypothesis": "라마",
        },
        {
            "id": 1701,
            "audio_s": 6.1,
            "elapsed_s": 0.3,
            "error": 0.0,
            "reference": "사아자",
            "hypothesis": "사아자차",
        },
    ]


def voice_document(items=None):
    """voice-translator 꼴: 최상위가 길이 1인 리스트이고, 한국어(ko) 말고 영어(en)도 들어 있다."""
    items = voice_items() if items is None else items
    english = {"items": [{"id": 1, "audio_s": 1.0, "reference": "x", "hypothesis": "y"}]}
    return [{"model": "demo", "languages": {"ko": {"metric": "cer", "items": items}, "en": english}}]


def whisper_rows():
    return [
        {
            "id": "7",
            "speaker": "a",
            "seconds": 5.2,
            "reference": "가 나, 다.",
            "hypothesis": "가 나 다",
            "edits": 0,
        },
        {"id": "9", "speaker": "b", "seconds": 7.4, "reference": "라마바", "hypothesis": "라마", "edits": 1},
        {
            "id": "7#2",
            "speaker": "c",
            "seconds": 6.1,
            "reference": "가 나, 다.",
            "hypothesis": "사아자차",
            "edits": 2,
        },
    ]


def whisper_document(rows=None):
    """whisper-ko-ft 꼴: 요약(summary)과 발화 목록(utterances)."""
    return {"summary": {"model": "demo"}, "utterances": whisper_rows() if rows is None else rows}


def stt_manifest_rows():
    return [
        {"id": "fleurs/test/7/0", "corpus": "fleurs", "duration_s": 5.2, "hangul_only": True},
        {"id": "fleurs/test/7/1", "corpus": "fleurs", "duration_s": 5.2, "hangul_only": False},
        {"id": "fleurs/test/9/2", "corpus": "fleurs", "duration_s": 6.1, "hangul_only": True},
    ]


def stt_hyp_rows():
    return [
        {"id": "fleurs/test/7/0", "ref": "가 나 다", "hyp": "가 나 다"},
        {"id": "fleurs/test/7/1", "ref": "가 나 다", "hyp": "가 나다라"},
        {"id": "fleurs/test/9/2", "ref": "라마바", "hyp": "라마"},
    ]


# ---------------------------------------------------------------------------------------------
# 한 꼴씩 읽기
# ---------------------------------------------------------------------------------------------


def test_load_voice_reads_the_position_as_the_row_number():
    # 영어(en) 항목과 읽지 않는 키(elapsed_s, error)가 함께 있어도 한국어 발화만 읽는다.
    system = sources.load_voice(dump(voice_document()), "voice-turbo", VOICE_PATH)
    assert system == System(
        key="voice-turbo",
        component="voice-translator",
        path=VOICE_PATH,
        also=(),
        utterances=(
            Utterance(0, "1883", 5.2, "가나다", "가나다"),
            Utterance(1, "1929", 7.4, "라마바", "라마"),
            Utterance(2, "1701", 6.1, "사아자", "사아자차"),
        ),
        ids=("1883", "1929", "1701"),
    )


def test_load_whisper_reads_the_row_and_sentence_and_keeps_the_id_text():
    system = sources.load_whisper(dump(whisper_document()), "turbo-n", WHISPER_PATH)
    assert system.key == "turbo-n"
    assert system.component == "whisper-ko-ft"
    assert system.path == WHISPER_PATH
    assert system.also == ()
    # 문장 번호는 id에서 `#` 앞이고, 같은 문장의 둘째 녹음(7#2)도 문장 7이다.
    assert [(u.row, u.sentence) for u in system.utterances] == [(0, "7"), (1, "9"), (2, "7")]
    # `#` 뒤의 수는 문장 번호에서 버리지만 id 글은 그대로 남겨 둔다(짝짓기 검증이 쓴다).
    assert system.ids == ("7", "9", "7#2")
    # 글은 정규화하지 않은 원문 그대로다.
    assert system.utterances[0] == Utterance(0, "7", 5.2, "가 나, 다.", "가 나 다")


def test_load_stt_reads_the_row_and_sentence_from_the_id():
    manifest = dump_lines(stt_manifest_rows())
    system, hangul = sources.load_stt(manifest, dump_lines(stt_hyp_rows()), "stt-scratch-full", STT_PATH)
    assert system.component == "stt-scratch"
    assert system.utterances == (
        Utterance(0, "7", 5.2, "가 나 다", "가 나 다"),
        Utterance(1, "7", 5.2, "가 나 다", "가 나다라"),
        Utterance(2, "9", 6.1, "라마바", "라마"),
    )
    assert system.ids == ("fleurs/test/7/0", "fleurs/test/7/1", "fleurs/test/9/2")
    assert hangul == (True, False, True)


def test_stt_rows_come_from_the_id_not_the_file_order():
    # stt-scratch의 파일은 행 번호 순이 아니라 id 글자의 사전순으로 저장돼 있다. 여기서는 `7/2`가 `7/0`보다
    # 앞에 온다. 행 번호는 줄의 위치가 아니라 id의 마지막 수이므로 2와 0으로 읽어야 하고, 가설은 제 행에
    # 붙어야 한다.
    manifest_rows = [
        {"id": "fleurs/test/7/2", "duration_s": 5.2, "hangul_only": False},
        {"id": "fleurs/test/7/0", "duration_s": 5.2, "hangul_only": True},
        {"id": "fleurs/test/8/1", "duration_s": 6.1, "hangul_only": True},
    ]
    hyp_rows = [
        {"id": "fleurs/test/7/2", "ref": "정답", "hyp": "둘째 녹음의 가설"},
        {"id": "fleurs/test/7/0", "ref": "정답", "hyp": "첫째 녹음의 가설"},
        {"id": "fleurs/test/8/1", "ref": "다른 정답", "hyp": "다른 가설"},
    ]
    system, hangul = sources.load_stt(dump_lines(manifest_rows), dump_lines(hyp_rows), "stt", STT_PATH)
    assert [u.row for u in system.utterances] == [0, 1, 2]
    assert [u.hypothesis for u in system.utterances] == ["첫째 녹음의 가설", "다른 가설", "둘째 녹음의 가설"]
    assert system.ids == ("fleurs/test/7/0", "fleurs/test/8/1", "fleurs/test/7/2")
    # 한글 전용 표시도 파일 차례가 아니라 행 번호 순이다.
    assert hangul == (True, True, False)


def shape_inputs(shape: str):
    """꼴마다 (LF 바이트, CRLF 바이트, 그 바이트를 읽는 함수)를 돌려준다.

    stt는 매니페스트를 고정해 두고 가설 파일만 바꿔서 읽는다.
    """
    if shape == "voice":
        lf = dump(voice_document())
        return lf, lf.replace(b"\n", b"\r\n"), lambda data: sources.load_voice(data, "k", VOICE_PATH)
    if shape == "whisper":
        lf = dump(whisper_document())
        return lf, lf.replace(b"\n", b"\r\n"), lambda data: sources.load_whisper(data, "k", WHISPER_PATH)
    lf = dump_lines(stt_hyp_rows())
    manifest = dump_lines(stt_manifest_rows())
    return lf, lf.replace(b"\n", b"\r\n"), lambda data: sources.load_stt(manifest, data, "k", STT_PATH)


@pytest.mark.parametrize("shape", ["voice", "whisper", "stt"])
def test_crlf_and_lf_inputs_give_the_same_rows(shape):
    # 줄바꿈 변환을 켠 채 받은 복제본에서는 같은 파일이 CRLF로 들어온다. 결과는 같아야 한다.
    lf, crlf, read = shape_inputs(shape)
    assert crlf != lf
    assert read(crlf) == read(lf)


def test_the_stt_manifest_is_read_with_crlf_too():
    manifest = dump_lines(stt_manifest_rows())
    hyps = dump_lines(stt_hyp_rows())
    crlf = manifest.replace(b"\n", b"\r\n")
    assert sources.load_stt(crlf, hyps, "k", STT_PATH) == sources.load_stt(manifest, hyps, "k", STT_PATH)


def test_a_line_separator_character_inside_a_json_string_does_not_split_the_line():
    # JSON은 문자열 안에 U+2028(줄 구분자)을 그대로 적는 것을 허용한다. 줄을 줄바꿈 문자로만 나눠야 이런 줄이
    # 깨지지 않는다(그 글자에서도 줄을 나누는 방식으로 읽으면 멀쩡한 파일을 JSON 문법 오류로 오해한다).
    separator = "\N{LINE SEPARATOR}"
    hyp_rows = stt_hyp_rows()
    hyp_rows[1] = {**hyp_rows[1], "hyp": f"앞{separator}뒤"}
    manifest = dump_lines(stt_manifest_rows())
    system, _ = sources.load_stt(manifest, dump_lines(hyp_rows), "k", STT_PATH)
    assert system.utterances[1].hypothesis == f"앞{separator}뒤"


@pytest.mark.parametrize("shape", ["voice", "whisper", "stt"])
def test_a_byte_order_mark_is_ignored(shape):
    lf, _, read = shape_inputs(shape)
    assert read(b"\xef\xbb\xbf" + lf) == read(lf)


# ---------------------------------------------------------------------------------------------
# digest
# ---------------------------------------------------------------------------------------------


def test_digest_is_the_sha256_of_the_bytes():
    # 알려진 값: `abc` 한 줄(LF)의 sha256. LF로 저장된 파일은 sha256sum 같은 도구의 값과 같다는 뜻이다.
    assert sources.digest(b"abc\n") == "edeaaff3f1774ad2888673770c6d64097e391bc362d7d6fb34982ddf0efd18cb"


def test_digest_ignores_line_ending_conversion():
    # 같은 내용을 LF와 CRLF로 주면 같은 값이다. CRLF로 커밋된 파일은 줄 끝의 CR을 뗀 내용의 값이 된다.
    assert sources.digest(b"a\nb\n") == sources.digest(b"a\r\nb\r\n")
    assert sources.digest(b"a\nb\n") != sources.digest(b"a\nb")


def test_digest_keeps_a_byte_order_mark_as_content():
    # BOM을 떼는 것은 읽을 때만이다. 값은 줄 끝만 맞춘 바이트에서 그대로 낸다.
    data = b"\xef\xbb\xbfabc\n"
    assert sources.digest(data) == hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------------------------
# 읽지 못하는 입력은 SourceError 하나로 알린다
# ---------------------------------------------------------------------------------------------


def voice_call(data: bytes):
    return lambda: sources.load_voice(data, "voice-turbo", VOICE_PATH)


def whisper_call(data: bytes):
    return lambda: sources.load_whisper(data, "turbo-n", WHISPER_PATH)


def stt_call(manifest_rows=None, hyp_rows=None, *, manifest=None, hyps=None):
    """stt를 읽는 호출. 줄 목록을 바꿔 주거나, 바이트를 통째로 주어 읽는 쪽 오류를 만든다."""
    if manifest is None:
        manifest = dump_lines(stt_manifest_rows() if manifest_rows is None else manifest_rows)
    if hyps is None:
        hyps = dump_lines(stt_hyp_rows() if hyp_rows is None else hyp_rows)
    return lambda: sources.load_stt(manifest, hyps, "stt-scratch-full", STT_PATH)


def voice_with(**changes):
    return voice_call(dump(voice_document([changed(voice_items()[0], **changes)])))


def whisper_with(**changes):
    return whisper_call(dump(whisper_document([changed(whisper_rows()[0], **changes)])))


def manifest_with(**changes):
    """세 줄 매니페스트에서 첫 줄의 값만 바꾼 줄 목록.

    가설 파일은 세 줄 그대로다. 매니페스트를 한 줄로 줄이면, 지켜야 할 검사가 꺼졌을 때 '가설 파일의 id가
    매니페스트에 없다'는 다른 까닭의 오류가 대신 나와 시험이 거짓으로 통과한다. 세 줄을 유지하면 그 검사를 끈
    구현은 오류 없이 읽고 이 사례를 통과하지 못한다.
    """
    return [changed(stt_manifest_rows()[0], **changes), *stt_manifest_rows()[1:]]


def hyps_with(**changes):
    """세 줄 가설 파일에서 첫 줄의 값만 바꾼 줄 목록(위와 같은 까닭이다)."""
    return [changed(stt_hyp_rows()[0], **changes), *stt_hyp_rows()[1:]]


def unreadable(case_id: str, call, path: str, reason: str):
    """읽지 못하는 입력 사례 하나: 호출, 메시지가 시작해야 할 파일 경로, 메시지에 든 까닭의 한 토막."""
    return pytest.param(call, path, reason, id=case_id)


MANIFEST = sources.STT_MANIFEST
# 문법은 맞지만 값을 읽을 수 없는 입력: 정수 자릿수 한도(4300자리)를 넘는 수, 파서가 못 읽게 깊게 겹친 괄호.
HUGE_NUMBER = b"9" * 5000
DEEP_NESTING = b"[" * 100_000 + b"]" * 100_000
VALID_HYP_LINE = b'{"id": "fleurs/test/7/0", "ref": "a", "hyp": "b"}\n'

UNREADABLE = [
    # --- voice-translator ---
    unreadable("voice-not-utf8", voice_call(b"\xff\xfe\xfd"), VOICE_PATH, "UTF-8로 읽을 수 없다"),
    unreadable("voice-json-syntax", voice_call(b'[{"languages":'), VOICE_PATH, "JSON 문법 오류"),
    unreadable(
        "voice-number-too-long", voice_call(b"[" + HUGE_NUMBER + b"]"), VOICE_PATH, "JSON 값을 읽을 수 없다"
    ),
    unreadable(
        "voice-nested-too-deep",
        voice_call(DEEP_NESTING),
        VOICE_PATH,
        "JSON이 너무 깊게 겹쳐 있어 읽을 수 없다",
    ),
    unreadable(
        "voice-top-level-is-not-a-list", voice_call(dump({})), VOICE_PATH, "최상위가 길이 1인 목록이 아니다"
    ),
    unreadable(
        "voice-top-level-list-is-empty", voice_call(dump([])), VOICE_PATH, "최상위가 길이 1인 목록이 아니다"
    ),
    unreadable(
        "voice-top-level-list-has-two",
        voice_call(dump(voice_document() * 2)),
        VOICE_PATH,
        "최상위가 길이 1인 목록이 아니다",
    ),
    unreadable(
        "voice-no-languages", voice_call(dump([{"model": "demo"}])), VOICE_PATH, "'languages' 키가 없다"
    ),
    unreadable("voice-no-korean", voice_call(dump([{"languages": {}}])), VOICE_PATH, "'ko' 키가 없다"),
    unreadable(
        "voice-items-not-a-list",
        voice_call(dump([{"languages": {"ko": {"items": {}}}}])),
        VOICE_PATH,
        "languages.ko.items: 목록이 아니다",
    ),
    unreadable(
        "voice-item-not-an-object",
        voice_call(dump(voice_document(["x"]))),
        VOICE_PATH,
        "items[0]: JSON 객체가 아니다",
    ),
    unreadable(
        "voice-no-reference", voice_with(reference=MISSING), VOICE_PATH, "items[0]: 'reference' 키가 없다"
    ),
    unreadable(
        "voice-hypothesis-is-null",
        voice_with(hypothesis=None),
        VOICE_PATH,
        "items[0].hypothesis: 글이 아니다",
    ),
    unreadable("voice-id-is-a-string", voice_with(id="1883"), VOICE_PATH, "items[0].id: 정수가 아니다"),
    unreadable("voice-id-is-a-boolean", voice_with(id=True), VOICE_PATH, "items[0].id: 정수가 아니다"),
    unreadable(
        "voice-seconds-is-a-string",
        voice_with(audio_s="5.2"),
        VOICE_PATH,
        "items[0].audio_s: 수가 아니다",
    ),
    # true는 파이썬에서 정수 1이다. 수로 받으면 안 된다.
    unreadable(
        "voice-seconds-is-a-boolean",
        voice_with(audio_s=True),
        VOICE_PATH,
        "items[0].audio_s: 수가 아니다",
    ),
    unreadable(
        "voice-seconds-is-nan",
        voice_with(audio_s=float("nan")),
        VOICE_PATH,
        "items[0].audio_s: 유한한 수가 아니다",
    ),
    # 실수로 바꿀 수 없을 만큼 큰 정수: 파서는 읽지만 float()가 넘친다.
    unreadable(
        "voice-seconds-is-too-big-for-a-float",
        voice_with(audio_s=10**400),
        VOICE_PATH,
        "items[0].audio_s: 유한한 수가 아니다",
    ),
    # --- whisper-ko-ft ---
    unreadable("whisper-not-utf8", whisper_call(b"\xff\xfe\xfd"), WHISPER_PATH, "UTF-8로 읽을 수 없다"),
    unreadable("whisper-json-syntax", whisper_call(b'{"utterances": ['), WHISPER_PATH, "JSON 문법 오류"),
    unreadable(
        "whisper-top-level-is-not-an-object",
        whisper_call(dump([])),
        WHISPER_PATH,
        "최상위: JSON 객체가 아니다",
    ),
    unreadable(
        "whisper-no-utterances",
        whisper_call(dump({"summary": {}})),
        WHISPER_PATH,
        "최상위: 'utterances' 키가 없다",
    ),
    unreadable(
        "whisper-utterances-not-a-list",
        whisper_call(dump({"utterances": {}})),
        WHISPER_PATH,
        "utterances: 목록이 아니다",
    ),
    unreadable("whisper-id-is-a-number", whisper_with(id=7), WHISPER_PATH, "utterances[0].id: 글이 아니다"),
    unreadable(
        "whisper-no-seconds",
        whisper_with(seconds=MISSING),
        WHISPER_PATH,
        "utterances[0]: 'seconds' 키가 없다",
    ),
    unreadable(
        "whisper-reference-is-a-list",
        whisper_with(reference=["가"]),
        WHISPER_PATH,
        "utterances[0].reference: 글이 아니다",
    ),
    unreadable(
        "whisper-no-hypothesis",
        whisper_with(hypothesis=MISSING),
        WHISPER_PATH,
        "utterances[0]: 'hypothesis' 키가 없다",
    ),
    # --- stt-scratch: 매니페스트(세 줄에서 첫 줄만 바꾼다) ---
    unreadable("stt-manifest-not-utf8", stt_call(manifest=b"\xff\xfe\xfd"), MANIFEST, "UTF-8로 읽을 수 없다"),
    unreadable(
        "stt-manifest-json-syntax",
        stt_call(manifest=b'{"id": "fleurs/test/7/0"\n'),
        MANIFEST,
        "1번째 줄이 JSON이 아니다",
    ),
    unreadable(
        "stt-manifest-id-shape",
        stt_call(manifest_rows=manifest_with(id="fleurs/test/7")),
        MANIFEST,
        "꼴이 아니다",
    ),
    # 행 번호는 아홉 자리까지다. 열 자리는 꼴이 아니고, 아주 긴 수도 정수 변환까지 가지 않고 같은 오류가 된다.
    unreadable(
        "stt-manifest-row-number-has-ten-digits",
        stt_call(manifest_rows=manifest_with(id="fleurs/test/7/1234567890")),
        MANIFEST,
        "꼴이 아니다",
    ),
    unreadable(
        "stt-manifest-row-number-is-huge",
        stt_call(manifest_rows=manifest_with(id="fleurs/test/7/" + "9" * 5000)),
        MANIFEST,
        "꼴이 아니다",
    ),
    unreadable(
        "stt-manifest-hangul-flag-is-not-a-boolean",
        stt_call(manifest_rows=manifest_with(hangul_only="yes")),
        MANIFEST,
        "1번째 줄.hangul_only: 참/거짓이 아니다",
    ),
    unreadable(
        "stt-manifest-no-duration",
        stt_call(manifest_rows=manifest_with(duration_s=MISSING)),
        MANIFEST,
        "1번째 줄: 'duration_s' 키가 없다",
    ),
    unreadable(
        "stt-manifest-duplicate-id",
        stt_call(manifest_rows=[*stt_manifest_rows(), stt_manifest_rows()[0]]),
        MANIFEST,
        "두 번 나온다",
    ),
    # --- stt-scratch: 가설 파일(세 줄에서 첫 줄만 바꾼다) ---
    unreadable("stt-hyps-not-utf8", stt_call(hyps=b"\xff\xfe\xfd"), STT_PATH, "UTF-8로 읽을 수 없다"),
    unreadable(
        "stt-hyps-json-syntax-on-line-two",
        stt_call(hyps=VALID_HYP_LINE + b'{"id": \n'),
        STT_PATH,
        "2번째 줄이 JSON이 아니다",
    ),
    unreadable(
        "stt-hyps-number-too-long-on-line-two",
        stt_call(
            hyps=VALID_HYP_LINE + b'{"id": "fleurs/test/7/1", "ref": "a", "hyp": ' + HUGE_NUMBER + b"}\n"
        ),
        STT_PATH,
        "2번째 줄의 JSON 값을 읽을 수 없다",
    ),
    unreadable(
        "stt-hyps-nested-too-deep-on-line-two",
        stt_call(hyps=VALID_HYP_LINE + DEEP_NESTING + b"\n"),
        STT_PATH,
        "2번째 줄의 JSON이 너무 깊게 겹쳐 있어 읽을 수 없다",
    ),
    unreadable("stt-hyps-id-shape", stt_call(hyp_rows=hyps_with(id="test/7/0")), STT_PATH, "꼴이 아니다"),
    unreadable(
        "stt-hyps-row-number-has-ten-digits",
        stt_call(hyp_rows=hyps_with(id="fleurs/test/7/1234567890")),
        STT_PATH,
        "꼴이 아니다",
    ),
    unreadable(
        "stt-hyps-id-not-in-the-manifest",
        stt_call(hyp_rows=[*stt_hyp_rows()[:2], changed(stt_hyp_rows()[2], id="fleurs/test/9/9")]),
        STT_PATH,
        f"3번째 줄: id 'fleurs/test/9/9'가 매니페스트({MANIFEST})에 없다",
    ),
    unreadable(
        "stt-manifest-id-not-in-the-hyps",
        stt_call(hyp_rows=stt_hyp_rows()[:2]),
        STT_PATH,
        "이 파일에 없다(처음 하나: 'fleurs/test/9/2')",
    ),
    unreadable(
        "stt-hyps-duplicate-id",
        stt_call(hyp_rows=[*stt_hyp_rows(), stt_hyp_rows()[0]]),
        STT_PATH,
        "4번째 줄: id 'fleurs/test/7/0'가 두 번 나온다",
    ),
    unreadable(
        "stt-hyps-no-hyp", stt_call(hyp_rows=hyps_with(hyp=MISSING)), STT_PATH, "1번째 줄: 'hyp' 키가 없다"
    ),
    unreadable(
        "stt-hyps-ref-is-a-number",
        stt_call(hyp_rows=hyps_with(ref=3)),
        STT_PATH,
        "1번째 줄.ref: 글이 아니다",
    ),
    unreadable(
        "stt-hyps-line-is-not-an-object",
        stt_call(hyp_rows=[[1, 2], *stt_hyp_rows()[1:]]),
        STT_PATH,
        "1번째 줄: JSON 객체가 아니다",
    ),
]


@pytest.mark.parametrize(("call", "path", "reason"), UNREADABLE)
def test_unreadable_input_is_a_source_error(call, path, reason):
    # 읽는 쪽 오류는 모두 SourceError 하나다. 메시지는 어느 파일(저장소 뿌리 기준 경로)인지로 시작하고,
    # 사례마다 기대하는 까닭의 한 토막을 함께 단언한다. 그래야 방어 줄이 꺼진 구현에서 다른 까닭의
    # SourceError가 대신 나와 시험이 거짓으로 통과하는 일이 없다.
    with pytest.raises(SourceError) as info:
        call()
    message = str(info.value)
    assert message.startswith(f"{path}: "), message
    assert reason in message, message


def test_a_json_syntax_error_names_the_line():
    call = stt_call(hyps=b'{"id": "fleurs/test/7/0", "ref": "a", "hyp": "b"}\n{"id": \n')
    with pytest.raises(SourceError, match="2번째 줄"):
        call()


def test_a_row_number_of_nine_digits_is_still_read():
    # 행 번호는 아홉 자리까지 받는다(열 자리부터는 위의 사례처럼 꼴이 아니라서 SourceError다).
    identifier = "fleurs/test/7/999999999"
    manifest = dump_lines([{"id": identifier, "duration_s": 5.2, "hangul_only": True}])
    hyps = dump_lines([{"id": identifier, "ref": "정답", "hyp": "가설"}])
    system, hangul = sources.load_stt(manifest, hyps, "k", STT_PATH)
    assert [u.row for u in system.utterances] == [999_999_999]
    assert hangul == (True,)


# ---------------------------------------------------------------------------------------------
# 고정된 목록
# ---------------------------------------------------------------------------------------------


def test_the_fixed_system_list():
    assert [spec.key for spec in sources.SYSTEMS] == SYSTEM_KEYS
    components = [spec.component for spec in sources.SYSTEMS]
    assert components == ["voice-translator"] * 2 + ["whisper-ko-ft"] * 10 + ["stt-scratch"] * 2
    paths = {spec.key: spec.path for spec in sources.SYSTEMS}
    assert (
        paths["voice-turbo-vad"] == "voice-translator/backend/eval/reports/stt_t14_test_20260913_055810.json"
    )
    assert (
        paths["voice-turbo"]
        == "voice-translator/backend/eval/reports/stt_t2_test_20260912_224129_rescored.json"
    )
    assert (
        paths["qwen3-asr-1.7b-qn-s050"] == "whisper-ko-ft/reports/qwen3-asr-1.7b-qn-s050/fleurs-ko-test.json"
    )
    assert paths["stt-scratch-full"] == "stt-scratch/reports/final/test_fleurs-full.hyps.jsonl"
    assert paths["stt-scratch-streaming"] == "stt-scratch/reports/final/test_fleurs-streaming.hyps.jsonl"
    assert MANIFEST == "stt-scratch/manifests/test_fleurs.jsonl"
    # 같은 가설을 가진 다른 리포트: 이 넷뿐이다.
    also = {spec.key: spec.also for spec in sources.SYSTEMS if spec.also}
    assert also == {
        "turbo-n": ("turbo-n-d1a",),
        "qwen3-asr-1.7b": ("qwen3-asr-1.7b-fixed",),
        "qwen3-asr-1.7b-qn": ("qwen3-asr-1.7b-qn-fixed",),
        "qwen3-asr-1.7b-qn-s050": ("qwen3-asr-1.7b-qn-s050-fixed",),
    }
    assert list(sources.TWINS) == TWIN_NAMES


# ---------------------------------------------------------------------------------------------
# 저장소 단위 읽기(합성 고정물)
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("size", [{}, FULL_SIZE], ids=["small", "full-size"])
def test_the_fixture_repository_has_the_real_layout(build_repository, size):
    # 이 파일의 다른 시험들이 기대는 고정물의 성질: 파일 열아홉 개, stt-scratch 파일은 id 글자순(행 번호
    # 순이 아님), 가설 파일 둘만 CRLF. 고정물이 이 성질을 잃으면 행 번호 짝짓기 시험이 아무것도 시험하지
    # 못하게 된다.
    root = build_repository(**size).root
    assert len([p for p in root.rglob("*") if p.is_file()]) == 19
    for spec in sources.SYSTEMS[-2:]:
        data = (root / spec.path).read_bytes()
        assert b"\r\n" in data
        ids = [json.loads(line)["id"] for line in data.decode("utf-8").split("\r\n") if line]
        rows = [int(text.rsplit("/", 1)[1]) for text in ids]
        assert ids == sorted(ids), spec.key
        assert rows != sorted(rows), spec.key
    for path in (MANIFEST, sources.SYSTEMS[0].path, sources.SYSTEMS[2].path):
        assert b"\r\n" not in (root / path).read_bytes(), path


def test_load_repository_reads_the_fixed_systems_in_order(build_repository):
    loaded = sources.load_repository(build_repository().root)
    assert [system.key for system in loaded.systems] == SYSTEM_KEYS
    assert [system.component for system in loaded.systems] == [spec.component for spec in sources.SYSTEMS]
    assert [system.path for system in loaded.systems] == [spec.path for spec in sources.SYSTEMS]
    assert [system.also for system in loaded.systems] == [spec.also for spec in sources.SYSTEMS]
    assert list(loaded.twins) == TWIN_NAMES
    for name, twin in loaded.twins.items():
        assert twin.key == name
        assert twin.component == "whisper-ko-ft"
        assert twin.path == f"whisper-ko-ft/reports/{name}/fleurs-ko-test.json"
        assert twin.also == ()


@pytest.mark.parametrize("size", [{}, FULL_SIZE], ids=["small", "full-size"])
def test_load_repository_reads_every_report_row_for_row(build_repository, size):
    synthetic = build_repository(**size)
    loaded = sources.load_repository(synthetic.root)
    count = len(synthetic.sentences)
    for system in [*loaded.systems, *loaded.twins.values()]:
        stored_references, stored_hypotheses = synthetic.stored_texts(system.key)
        assert [u.row for u in system.utterances] == list(range(count)), system.key
        for utterance in system.utterances:
            row = utterance.row
            assert utterance.sentence == synthetic.sentences[row], (system.key, row)
            # 구성 요소마다 길이를 조금씩 다르게 적었지만 소수 둘째 자리로 반올림하면 같다.
            assert round(utterance.seconds, 2) == synthetic.seconds[row], (system.key, row)
            assert utterance.reference == stored_references[row], (system.key, row)
            assert utterance.hypothesis == stored_hypotheses[row], (system.key, row)
    assert loaded.hangul == synthetic.hangul


def test_load_repository_lists_every_input_file_with_its_digest(build_repository):
    synthetic = build_repository(line_endings="real")
    loaded = sources.load_repository(synthetic.root)
    on_disk = sorted(
        p.relative_to(synthetic.root).as_posix() for p in synthetic.root.rglob("*") if p.is_file()
    )
    # 재료 파일 열아홉 개를 경로 순으로 한 번씩(매니페스트는 두 묶음이 쓰지만 한 번만 나온다).
    assert [path for path, _ in loaded.inputs] == on_disk
    assert len(loaded.inputs) == 19
    for path, digest in loaded.inputs:
        data = (synthetic.root / path).read_bytes()
        assert digest == hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest(), path


def test_load_repository_does_not_depend_on_line_endings(build_repository):
    # 같은 재료를 실제처럼(가설 파일만 CRLF), 모두 LF로, 모두 CRLF로 만든 세 벌은 읽은 결과도 재료의
    # sha256도 같다.
    real = sources.load_repository(build_repository("real", line_endings="real").root)
    lf = sources.load_repository(build_repository("lf", line_endings="lf").root)
    crlf = sources.load_repository(build_repository("crlf", line_endings="crlf").root)
    assert real == lf == crlf


def test_load_repository_names_the_missing_file(build_repository):
    synthetic = build_repository()
    missing = "whisper-ko-ft/reports/small-a/fleurs-ko-test.json"
    (synthetic.root / missing).unlink()
    with pytest.raises(SourceError) as info:
        sources.load_repository(synthetic.root)
    assert missing in str(info.value)


def test_load_repository_names_the_unreadable_file(build_repository):
    synthetic = build_repository()
    broken = "voice-translator/backend/eval/reports/stt_t14_test_20260913_055810.json"
    (synthetic.root / broken).write_bytes(b"[{")
    with pytest.raises(SourceError) as info:
        sources.load_repository(synthetic.root)
    assert broken in str(info.value)


def test_load_repository_names_a_directory_where_a_file_should_be(build_repository):
    synthetic = build_repository()
    path = synthetic.root / MANIFEST
    path.unlink()
    path.mkdir()
    with pytest.raises(SourceError) as info:
        sources.load_repository(synthetic.root)
    assert MANIFEST in str(info.value)


def test_error_messages_use_repository_relative_paths(build_repository):
    synthetic = build_repository()
    (synthetic.root / MANIFEST).write_bytes(b"\xff")
    with pytest.raises(SourceError) as info:
        sources.load_repository(synthetic.root)
    assert MANIFEST in str(info.value)
    assert str(synthetic.root) not in str(info.value)


def test_two_stt_systems_with_different_hangul_flags_are_an_error(build_repository, monkeypatch):
    # 두 stt-scratch 묶음은 같은 매니페스트를 쓰므로 한글 전용 표시가 같아야 한다. 코드가 바뀌어 달라지면
    # 어느 한쪽을 조용히 고르지 않고 멈춘다. 같은 매니페스트에서는 달라질 수 없으므로 둘째 호출의 결과를
    # 뒤집어 확인한다.
    synthetic = build_repository()
    real = sources.load_stt
    calls = []

    def flip_the_second(manifest, hyps, key, path):
        system, hangul = real(manifest, hyps, key, path)
        calls.append(key)
        return system, (tuple(not flag for flag in hangul) if len(calls) == 2 else hangul)

    monkeypatch.setattr(sources, "load_stt", flip_the_second)
    with pytest.raises(SourceError, match="한글 전용"):
        sources.load_repository(synthetic.root)
