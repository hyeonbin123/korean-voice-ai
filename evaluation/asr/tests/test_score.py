"""채점 규칙 가운데 정규화(score.PATTERN, score.normalize)의 시험.

정규화는 세 구성 요소(whisper-ko-ft, stt-scratch, voice-translator)가 각자 쓰는 한국어 정규화와 글자까지
같아야 한다. 그래서 기대값은 구성 요소의 동작을 글로 옮긴 것이다. 소문자로 바꾸고, 글자·숫자·공백·작은따옴표가
아닌 것과 밑줄을 공백으로 바꾸고, 작은따옴표도 공백으로 바꾼 뒤, 공백을 모두 지운다.

눈에 보이지 않거나 모양이 비슷한 글자(줄 바꿈 없는 공백, 전각 공백, 풀어 쓴 한글 자모)는 소스에 그 글자를
그대로 적지 않고 이름 이스케이프로 적는다(편집기가 조용히 바꾸지 못하게 하려는 것이다).
"""

import unicodedata

import pytest

from asr_compare import score


def test_the_pattern_is_the_shared_scoring_rule():
    # 세 구성 요소의 정규식과 글자 그대로 같은 글이다.
    assert score.PATTERN == r"[^\w\s']|_"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 영어 축약형의 작은따옴표, 숫자와 단위, 쉼표·느낌표가 모두 사라지고 소문자가 된다.
        ("It's 15m, OK!", "its15mok"),
        # 한국어에서 작은따옴표는 인용 부호라 공백이 되고, 공백은 모두 지운다.
        ("다리 밑 '수직' 간격", "다리밑수직간격"),
        ("ABC가", "abc가"),
        ("15,000원", "15000원"),
        # 밑줄은 \w에 들지만 따로 공백으로 바꾼다.
        ("a_b", "ab"),
        # 줄바꿈·탭·줄 끝의 공백·유니코드 공백(줄 바꿈 없는 공백, 전각 공백)도 모두 지운다.
        ("가\N{NO-BREAK SPACE}나\N{IDEOGRAPHIC SPACE}다\t라\n마 ", "가나다라마"),
        ("...,,!?", ""),
        ("", ""),
        # 악센트가 붙은 글자는 글자로 남는다(소문자만 된다).
        ("Córdoba", "córdoba"),
    ],
)
def test_normalize(text, expected):
    assert score.normalize(text) == expected


def test_normalize_does_not_compose_hangul():
    # 세 구성 요소 모두 유니코드 정규화(NFC)를 하지 않는다. 풀어 쓴 자모는 풀어 쓴 채로 남는다.
    decomposed = "\N{HANGUL CHOSEONG KIYEOK}\N{HANGUL JUNGSEONG A}"
    composed = "\N{HANGUL SYLLABLE GA}"
    # 이 시험의 전제: 두 글은 NFC로는 같은 글이지만 글자열로는 다르다.
    assert unicodedata.normalize("NFC", decomposed) == composed
    assert decomposed != composed
    assert score.normalize(decomposed) == decomposed
    assert score.normalize(composed) == composed


@pytest.mark.parametrize("text", ["It's 15m, OK!", "다리 밑 '수직' 간격", "a_b  c'd", "Córdoba."])
def test_normalize_is_idempotent(text):
    once = score.normalize(text)
    assert score.normalize(once) == once
