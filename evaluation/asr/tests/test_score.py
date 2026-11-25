"""채점 규칙(score)의 시험: 정규화, 글자 단위 편집 거리, 합산, 다시 뽑기 번호, 95% 구간.

정규화는 세 구성 요소(whisper-ko-ft, stt-scratch, voice-translator)가 각자 쓰는 한국어 정규화와 글자까지
같아야 한다. 그래서 기대값은 구성 요소의 동작을 글로 옮긴 것이다. 소문자로 바꾸고, 글자·숫자·공백·작은따옴표가
아닌 것과 밑줄을 공백으로 바꾸고, 작은따옴표도 공백으로 바꾼 뒤, 공백을 모두 지운다.

눈에 보이지 않거나 모양이 비슷한 글자(줄 바꿈 없는 공백, 전각 공백, 풀어 쓴 한글 자모)는 소스에 그 글자를
그대로 적지 않고 이름 이스케이프로 적는다(편집기가 조용히 바꾸지 못하게 하려는 것이다).
"""

import random
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


# ---------------------------------------------------------------------------------------------
# 글자 단위 편집 거리
# ---------------------------------------------------------------------------------------------


def matrix_distance(reference: str, hypothesis: str) -> int:
    """시험이 쓰는 기준 구현: 전체 행렬을 채우는 가장 단순한 편집 거리(치환·삭제·삽입 비용 1)."""
    rows, columns = len(reference) + 1, len(hypothesis) + 1
    table = [[0] * columns for _ in range(rows)]
    for i in range(rows):
        table[i][0] = i
    for j in range(columns):
        table[0][j] = j
    for i in range(1, rows):
        for j in range(1, columns):
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
            table[i][j] = min(table[i - 1][j] + 1, table[i][j - 1] + 1, table[i - 1][j - 1] + cost)
    return table[-1][-1]


@pytest.mark.parametrize(
    ("reference", "hypothesis", "expected"),
    [
        ("가나다", "가다", 1),  # 삭제 하나
        ("", "가", 1),  # 삽입 하나
        ("가", "", 1),
        ("", "", 0),
        ("가나다", "가나다", 0),
        ("가나다", "가라다", 1),  # 치환 하나
        ("가나다", "다나가", 2),  # 치환 둘
        ("kitten", "sitting", 3),  # 널리 알려진 예: 치환 둘과 삽입 하나
        ("flaw", "lawn", 2),
        ("abc", "xyz", 3),
        ("abcdef", "ghijkl", 6),
        ("가나다라마", "가나X라마", 1),  # 앞뒤가 같고 가운데만 다르다
        ("가나다라마", "마라다나가", 4),
    ],
)
def test_edit_count(reference, hypothesis, expected):
    assert score.edit_count(reference, hypothesis) == expected


def test_edit_count_matches_a_plain_matrix_on_random_strings():
    # 편집 거리의 정의(전체 행렬)와 같은 값을 내는지, 글자 몇 개짜리 무작위 짝 400개로 견준다. 어느 쪽을
    # 정답으로 보아도 같아야 하고(대칭), 길이 차보다 작을 수 없고 더 긴 쪽의 길이보다 클 수 없다.
    rng = random.Random(7)
    alphabet = "가나다라ab"
    for _ in range(400):
        reference = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))
        hypothesis = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))
        distance = score.edit_count(reference, hypothesis)
        assert distance == matrix_distance(reference, hypothesis), (reference, hypothesis)
        assert distance == score.edit_count(hypothesis, reference), (reference, hypothesis)
        assert abs(len(reference) - len(hypothesis)) <= distance <= max(len(reference), len(hypothesis))


def test_edit_count_handles_long_strings():
    reference = "가나다라마바사" * 40
    hypothesis = reference[:100] + "X" + reference[101:]
    assert score.edit_count(reference, hypothesis) == 1


# ---------------------------------------------------------------------------------------------
# 합산
# ---------------------------------------------------------------------------------------------


def test_counts_gives_the_edits_and_the_normalised_reference_length():
    assert score.counts("가 나", "가나") == (0, 2)
    assert score.counts("It's OK!", "its ok") == (0, 5)
    assert score.counts("가나다라", "가") == (3, 4)
    assert score.counts("가나다", "") == (3, 3)


def test_totals_sums_edits_and_normalised_reference_lengths():
    assert score.totals([("가 나", "가나"), ("다라", "다")]) == (1, 4)


def test_totals_normalises_both_sides_before_counting():
    # 띄어쓰기·문장부호·대소문자와 작은따옴표 차이는 편집으로 세지 않는다.
    assert score.totals([("It's 15m, OK!", "ITS 15M ok")]) == (0, 8)


@pytest.mark.parametrize("reference", ["", "   ", "...", "'\"!?"])
def test_totals_rejects_an_empty_reference(reference):
    # 정규화한 정답이 빈 글이면 글자 오류율의 분모에 0이 들어간다. 조용히 건너뛰지 않고 멈춘다.
    with pytest.raises(ValueError, match="빈 글"):
        score.totals([("가", "가"), (reference, "가")])


def test_totals_accepts_any_iterable_and_nothing_at_all():
    assert score.totals(iter([("가나", "가")])) == (1, 2)
    assert score.totals([]) == (0, 0)


# ---------------------------------------------------------------------------------------------
# 다시 뽑기와 구간
# ---------------------------------------------------------------------------------------------


def test_the_resampling_constants():
    assert score.RESAMPLES == 1000
    assert score.SEED == 0


def test_resample_indices_have_the_requested_shape_and_range():
    indices = score.resample_indices(3)
    assert len(indices) == 1000
    assert all(len(resample) == 3 for resample in indices)
    assert all(0 <= index < 3 for resample in indices for index in resample)


def test_resample_indices_are_the_same_every_time():
    assert score.resample_indices(5) == score.resample_indices(5)


def test_resample_indices_come_from_random_of_the_seeded_generator():
    # random()은 같은 시드에서 같은 수열을 낸다고 파이썬 문서가 보장한다(randrange·shuffle 같은 것은 판마다
    # 달라질 수 있다). 처음 몇 개를 글자 그대로 고정해서, 뽑는 방식이 바뀌면 구간이 달라지기 전에 여기서
    # 걸리게 한다.
    assert score.resample_indices(3)[:4] == [[2, 2, 1], [0, 1, 1], [2, 0, 1], [1, 2, 1]]
    assert score.resample_indices(3)[-1] == [1, 0, 0]
    assert score.resample_indices(5)[:2] == [[4, 3, 2, 1, 2], [2, 3, 1, 2, 2]]


def test_resample_indices_do_not_use_the_global_random_state():
    state = random.getstate()
    try:
        random.seed(12345)
        first = score.resample_indices(4)
        random.seed(999)
        second = score.resample_indices(4)
    finally:
        random.setstate(state)
    assert first == second


def test_interval_is_the_25th_and_975th_of_a_thousand_sorted_values():
    # 정렬한 값의 아래에서 25번째와 975번째(1부터 센다). 0부터 999까지를 늘어놓으면 24와 974다.
    assert score.interval(list(range(1000))) == (24, 974)


def test_interval_sorts_a_copy_and_leaves_its_input_alone():
    values = [float(n) for n in reversed(range(1000))]
    original = list(values)
    assert score.interval(values) == (24.0, 974.0)
    assert values == original


@pytest.mark.parametrize("count", [0, 999, 1001])
def test_interval_needs_exactly_one_thousand_values(count):
    # 25번째와 975번째가 95% 구간인 것은 값이 1000개일 때뿐이다. 다른 개수를 조용히 받지 않는다.
    with pytest.raises(ValueError, match="1000"):
        score.interval([0.0] * count)
