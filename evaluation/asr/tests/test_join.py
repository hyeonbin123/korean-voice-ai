"""짝짓기 검증(join.verify)의 시험.

verify는 서로 다른 구성 요소가 저장한 기록이 정말 같은 발화를 가리키는지 여덟 가지로 확인하고, 어긋난 점마다
한 줄을 돌려준다(통과하면 빈 목록). 이 파일은 합성 고정물로 이를 시험한다.

  - 맞는 고정물은 빈 목록이다. stt-scratch 파일의 줄 차례를 바꿔도 가설이 제 행에 붙는다(id로 읽는다).
  - 여덟 검사에 어긋남을 하나씩 넣으면 그 점을 말하는 줄이 하나 나온다.
  - 2·3·4번 검사는 같은 가설 리포트에도 열네 묶음과 같은 범위로 걸려서, 그 리포트의 이름이 든 줄이 나온다.
  - 깨진 행 번호 집합은 뒤 검사를 막고, 줄의 차례는 늘 같다.

작은 고정물은 발화 네 개다: 행 1과 2는 같은 문장을 두 번 녹음한 것(같은 길이)이고, 행 3은 stt-scratch의
정답이 공통 정답과 다른 알려진 차이 행이다. 한글 전용 표시는 행 0~2 가운데 두 곳에 있다. verify의 키워드
인자를 이 크기에 맞춰 넘긴다(명령줄은 언제나 기본값인 실제 크기를 쓴다).
"""

from dataclasses import replace

import pytest

from asr_compare import join, sources
from asr_compare.sources import System, Utterance

SMALL_BUILD = {"utterances": 4, "hangul_only": 2, "differences": (3,)}
FULL_BUILD = {"utterances": 382, "hangul_only": 257, "differences": (23, 57)}
SMALL_VERIFY = {"utterances": 4, "hangul_only": 2, "known_reference_differences": (3,)}
COMMON = "whisper-large-v3-turbo"
TWIN_NAMES = [
    "turbo-n-d1a",
    "qwen3-asr-1.7b-fixed",
    "qwen3-asr-1.7b-qn-fixed",
    "qwen3-asr-1.7b-qn-s050-fixed",
]


@pytest.fixture
def loaded(build_repository):
    """작은 합성 저장소를 읽은 결과."""
    return sources.load_repository(build_repository("small", **SMALL_BUILD).root)


def get(loaded, key: str) -> System:
    """키로 묶음 하나(같은 가설 리포트 포함)를 찾는다."""
    return next(s for s in [*loaded.systems, *loaded.twins.values()] if s.key == key)


def edit(base: System, row: int, **changes) -> System:
    """묶음의 한 행에서 발화 필드를 바꾼 복사본."""
    utterances = tuple(replace(u, **changes) if u.row == row else u for u in base.utterances)
    return replace(base, utterances=utterances)


def systems_with(loaded, new: System) -> list[System]:
    """읽은 묶음 목록에서 같은 키의 묶음을 new로 바꾼 목록."""
    return [new if s.key == new.key else s for s in loaded.systems]


def with_twin(loaded, new: System) -> dict[str, System]:
    """읽은 형제 리포트 사전에서 같은 이름의 리포트를 new로 바꾼 사전(사전 안의 차례는 그대로다)."""
    return {**loaded.twins, new.key: new}


def with_sentence(base: System, row: int, sentence: str) -> System:
    """한 행의 문장 번호를 바꾸고 id 글도 같이 바꾼다.

    그 문장의 첫 녹음인 행에만 쓴다. 이렇게 하면 4번 검사에는 걸리지 않고 2번 검사에만 걸린다(id 글을 두고
    문장 번호만 바꾸면 두 검사가 한꺼번에 걸린다).
    """
    ids = tuple(
        sentence if u.row == row else identifier
        for u, identifier in zip(base.utterances, base.ids, strict=True)
    )
    return replace(edit(base, row, sentence=sentence), ids=ids)


def hand_made(sentences, ids, key=COMMON):
    """공통 정답 묶음 하나뿐인, 손으로 만든 whisper-ko-ft 꼴 묶음."""
    utterances = tuple(Utterance(row, str(s), 5.0, "가", "가") for row, s in enumerate(sentences))
    return System(key, "whisper-ko-ft", "demo", (), utterances, ids=tuple(ids))


def check_alone(system: System) -> list[str]:
    count = len(system.utterances)
    return join.verify(
        [system], (False,) * count, {}, utterances=count, hangul_only=0, known_reference_differences=()
    )


def check(loaded, *, systems=None, hangul=None, twins=None, **options) -> list[str]:
    """작은 고정물에 맞춘 인자로 verify를 부른다. 바꿀 것만 넘긴다."""
    return join.verify(
        list(loaded.systems) if systems is None else systems,
        loaded.hangul if hangul is None else hangul,
        loaded.twins if twins is None else twins,
        **{**SMALL_VERIFY, **options},
    )


def one_line(problems: list[str], *words: str) -> str:
    """어긋남이 정확히 한 줄이고, 그 줄에 words가 모두 들어 있음을 확인하고 그 줄을 돌려준다."""
    assert len(problems) == 1, problems
    for word in words:
        assert word in problems[0], (word, problems[0])
    return problems[0]


# ---------------------------------------------------------------------------------------------
# 맞는 고정물
# ---------------------------------------------------------------------------------------------


def test_consistent_fixture_has_no_problems(loaded):
    assert check(loaded) == []


def test_the_default_constants_describe_the_full_size_comparison(build_repository):
    # 명령줄은 기본값만 쓴다. 기본값이 실제 크기다(382발화, 한글 전용 257, 알려진 차이 둘).
    assert join.UTTERANCES == 382
    assert join.HANGUL_ONLY == 257
    assert join.KNOWN_REFERENCE_DIFFERENCES == (23, 57)
    full = sources.load_repository(build_repository("full", **FULL_BUILD).root)
    assert join.verify(list(full.systems), full.hangul, full.twins) == []


@pytest.mark.parametrize("order", ["id", "row", "reversed"])
def test_join_uses_the_row_number_not_file_order(build_repository, order):
    # 행 1과 2는 같은 문장·같은 길이의 두 녹음이라 문장 번호와 길이로는 구별되지 않는다. stt-scratch 파일의
    # 줄 차례를 어떻게 바꿔도 가설은 제 행에 붙어야 하고, 검증도 통과해야 한다(줄 차례로 짝지으면 두 가설이
    # 뒤바뀐다).
    synthetic = build_repository(stt_order=order, **SMALL_BUILD)
    loaded = sources.load_repository(synthetic.root)
    assert check(loaded) == []
    for key in ("stt-scratch-full", "stt-scratch-streaming"):
        stt = get(loaded, key)
        first, second = stt.utterances[1], stt.utterances[2]
        assert (first.sentence, round(first.seconds, 2)) == (second.sentence, round(second.seconds, 2))
        _, stored_hypotheses = synthetic.stored_texts(key)
        assert [u.hypothesis for u in stt.utterances] == list(stored_hypotheses)
        assert first.hypothesis != second.hypothesis


def test_twins_argument_is_required(loaded):
    # 같은 가설 리포트를 견주는 검사가 인자를 빼먹어서 조용히 꺼지는 길이 없어야 한다.
    with pytest.raises(TypeError):
        join.verify(list(loaded.systems), loaded.hangul)


# ---------------------------------------------------------------------------------------------
# 1: 발화 수와 행 번호
# ---------------------------------------------------------------------------------------------


def test_wrong_utterance_count_is_reported(loaded):
    voice = get(loaded, "voice-turbo")
    short = replace(voice, utterances=voice.utterances[:-1], ids=voice.ids[:-1])
    one_line(check(loaded, systems=systems_with(loaded, short)), "voice-turbo", "발화", "행 3")


def test_an_extra_utterance_is_reported(loaded):
    voice = get(loaded, "voice-turbo")
    extra = replace(
        voice, utterances=(*voice.utterances, Utterance(4, "999", 5.0, "가", "가")), ids=(*voice.ids, "999")
    )
    one_line(check(loaded, systems=systems_with(loaded, extra)), "voice-turbo", "발화", "행 4")


def test_a_duplicated_row_number_is_reported(loaded):
    # 발화 수는 맞지만 행 번호 1이 두 번 나오고 2가 빠졌다.
    base = get(loaded, "small-a")
    broken = replace(base, utterances=tuple(replace(u, row=1) if u.row == 2 else u for u in base.utterances))
    one_line(check(loaded, systems=systems_with(loaded, broken)), "small-a", "행 1", "행 2")


def test_a_row_number_outside_the_range_is_reported(loaded):
    base = get(loaded, "small-a")
    broken = replace(base, utterances=tuple(replace(u, row=7) if u.row == 3 else u for u in base.utterances))
    one_line(check(loaded, systems=systems_with(loaded, broken)), "small-a", "행 3", "행 7")


def test_a_wrong_row_set_in_a_twin_report_is_reported(loaded):
    base = get(loaded, "turbo-n-d1a")
    short = replace(base, utterances=base.utterances[:-1], ids=base.ids[:-1])
    one_line(check(loaded, twins={**loaded.twins, "turbo-n-d1a": short}), "turbo-n-d1a", "행 3")


def missing_rows_line(present: int, expected: int) -> str:
    """행 번호 0 ~ present-1만 가진 묶음 하나를 expected개 발화 기준으로 검증했을 때의 ① 줄 하나."""
    system = hand_made(list(range(1, present + 1)), [str(n) for n in range(1, present + 1)])
    problems = join.verify(
        [system], (False,) * expected, {}, utterances=expected, hangul_only=0, known_reference_differences=()
    )
    return one_line(problems, COMMON)


def test_a_long_list_of_rows_is_cut_after_ten_and_the_rest_is_counted():
    # 빠진 행이 스물다섯 개이면 앞 열 개(5~14)만 보이고 나머지는 개수로 적는다(외 15개).
    line = missing_rows_line(present=5, expected=30)
    assert line.endswith("빠진 행 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 외 15개")


def test_ten_rows_are_all_shown_and_one_more_is_counted():
    # 경계: 열 개는 모두 보이고(외 ~개가 붙지 않는다), 열한 개이면 열 개 뒤에 외 1개가 붙는다.
    assert missing_rows_line(present=5, expected=15).endswith("빠진 행 5, 6, 7, 8, 9, 10, 11, 12, 13, 14")
    assert missing_rows_line(present=5, expected=16).endswith(
        "빠진 행 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 외 1개"
    )


def test_a_broken_row_set_stops_the_other_checks(loaded):
    # 행 번호 집합이 깨진 묶음은 행으로 짝지을 수 없다. 이때는 그 줄만 돌려주고, 뒤 검사를 반쯤 돌려 엉뚱한
    # 줄을 쏟지 않는다. 같은 고정물에 문장 번호 어긋남도 넣어 두었지만 그 줄은 나오지 않는다.
    voice = get(loaded, "voice-turbo")
    short = replace(voice, utterances=voice.utterances[:-1], ids=voice.ids[:-1])
    other = edit(get(loaded, "whisper-small"), 0, sentence="999")
    systems = systems_with(loaded, other)
    systems = [short if s.key == "voice-turbo" else s for s in systems]
    one_line(check(loaded, systems=systems), "voice-turbo")


def test_the_utterance_count_to_expect_is_a_parameter(loaded):
    # 기본값(382)으로 작은 고정물을 검증하면 모든 묶음의 발화 수가 틀렸다고 나온다(기대 발화 수가 쓰인다).
    problems = join.verify(list(loaded.systems), loaded.hangul, loaded.twins)
    assert len(problems) == len(loaded.systems) + len(loaded.twins)
    assert all("382" in line for line in problems)


def test_no_systems_is_reported(loaded):
    # 견줄 묶음이 하나도 없으면 아무것도 확인하지 못한 채 통과하는 일이 없도록 어긋남으로 알린다.
    one_line(check(loaded, systems=[]), "묶음")


# ---------------------------------------------------------------------------------------------
# 2·3: 문장 번호와 음성 길이
# ---------------------------------------------------------------------------------------------


def test_a_sentence_number_mismatch_is_reported(loaded):
    broken = edit(get(loaded, "voice-turbo"), 2, sentence="999")
    one_line(check(loaded, systems=systems_with(loaded, broken)), "voice-turbo", "행 2", "문장 번호", "999")


def test_a_duration_mismatch_is_reported(loaded):
    base = get(loaded, "whisper-small")
    broken = edit(base, 1, seconds=base.utterances[1].seconds + 0.5)
    one_line(check(loaded, systems=systems_with(loaded, broken)), "whisper-small", "행 1", "음성 길이")


def test_durations_are_compared_after_rounding_to_two_decimals(loaded):
    base = get(loaded, "whisper-small")
    seconds = base.utterances[1].seconds
    # 소수 셋째 자리 이하의 차이는 구성 요소마다 길이를 적는 자릿수가 달라서 생기는 것이라 어긋남이 아니다.
    assert check(loaded, systems=systems_with(loaded, edit(base, 1, seconds=seconds + 0.003))) == []
    # 소수 둘째 자리가 달라지면 어긋남이다.
    one_line(check(loaded, systems=systems_with(loaded, edit(base, 1, seconds=seconds + 0.01))), "음성 길이")


@pytest.mark.parametrize("name", TWIN_NAMES)
def test_a_sentence_number_mismatch_in_a_twin_report_is_reported(loaded, name):
    # 같은 가설 리포트도 행 번호로 가설을 견주는 대상이라, 문장 번호가 어긋나면 열네 묶음과 똑같이 알린다.
    broken = with_sentence(get(loaded, name), 3, "999")
    line = one_line(check(loaded, twins=with_twin(loaded, broken)), name, "행 3", "문장 번호", "999")
    assert line.startswith(f"{name}: ")


@pytest.mark.parametrize("name", TWIN_NAMES)
def test_a_duration_mismatch_in_a_twin_report_is_reported(loaded, name):
    base = get(loaded, name)
    broken = edit(base, 1, seconds=base.utterances[1].seconds + 0.5)
    line = one_line(check(loaded, twins=with_twin(loaded, broken)), name, "행 1", "음성 길이")
    assert line.startswith(f"{name}: ")


# ---------------------------------------------------------------------------------------------
# 4: whisper-ko-ft의 id
# ---------------------------------------------------------------------------------------------


def test_a_wrong_duplicate_suffix_in_a_whisper_id_is_reported(loaded):
    base = get(loaded, "turbo-n")
    assert base.ids[2].endswith("#2")
    wrong = base.ids[2].replace("#2", "#3")
    broken = replace(base, ids=(*base.ids[:2], wrong, *base.ids[3:]))
    one_line(check(loaded, systems=systems_with(loaded, broken)), "turbo-n", "행 2", "id", wrong, base.ids[2])


def test_a_missing_duplicate_suffix_is_reported(loaded):
    base = get(loaded, "turbo-n")
    broken = replace(base, ids=(*base.ids[:2], base.ids[1], *base.ids[3:]))
    one_line(check(loaded, systems=systems_with(loaded, broken)), "turbo-n", "행 2", "id")


def test_the_suffix_counts_every_earlier_recording_of_the_sentence():
    # 같은 문장의 녹음이 떨어져 있어도 n번째 등장이 맞아야 한다: 5, 6, 5#2, 7, 5#3.
    sentences = [5, 6, 5, 7, 5]
    assert check_alone(hand_made(sentences, ["5", "6", "5#2", "7", "5#3"])) == []
    one_line(check_alone(hand_made(sentences, ["5", "6", "5#2", "7", "5#2"])), "행 4", "5#3")


def test_the_ids_are_checked_in_row_order_not_tuple_order():
    # 발화 목록의 차례가 행 번호 순이 아니어도 n번째 등장은 행 번호 순으로 센다.
    base = hand_made([5, 6, 5], ["5", "6", "5#2"])
    reordered = replace(base, utterances=base.utterances[::-1], ids=base.ids[::-1])
    assert check_alone(reordered) == []


def test_missing_ids_cannot_switch_the_suffix_check_off(loaded):
    # id 목록이 비었거나 발화 수와 다르면 검사를 건너뛰지 않고 어긋남으로 알린다.
    base = get(loaded, "turbo-n")
    one_line(check(loaded, systems=systems_with(loaded, replace(base, ids=()))), "turbo-n", "id")


@pytest.mark.parametrize("name", TWIN_NAMES)
def test_a_wrong_duplicate_suffix_in_a_twin_report_id_is_reported(loaded, name):
    base = get(loaded, name)
    assert base.ids[2].endswith("#2")
    wrong = base.ids[2].replace("#2", "#3")
    broken = replace(base, ids=(*base.ids[:2], wrong, *base.ids[3:]))
    line = one_line(check(loaded, twins=with_twin(loaded, broken)), name, "행 2", "id", wrong, base.ids[2])
    assert line.startswith(f"{name}: ")


def test_missing_ids_in_a_twin_report_cannot_switch_the_suffix_check_off(loaded):
    base = get(loaded, "turbo-n-d1a")
    line = one_line(check(loaded, twins=with_twin(loaded, replace(base, ids=()))), "turbo-n-d1a", "id")
    assert line.startswith("turbo-n-d1a: ")


# ---------------------------------------------------------------------------------------------
# 5: 정규화한 정답
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key", ["voice-turbo-vad", "voice-turbo", "whisper-small", "turbo-n", "qwen3-asr-1.7b-qn-s050"]
)
def test_a_reference_mismatch_is_reported(loaded, key):
    base = get(loaded, key)
    broken = edit(base, 0, reference=base.utterances[0].reference + "추가")
    one_line(check(loaded, systems=systems_with(loaded, broken)), key, "행 0", "정답", COMMON)


def test_a_reference_mismatch_in_a_twin_report_is_reported(loaded):
    base = get(loaded, "turbo-n-d1a")
    broken = edit(base, 0, reference=base.utterances[0].reference + "추가")
    one_line(check(loaded, twins={**loaded.twins, "turbo-n-d1a": broken}), "turbo-n-d1a", "행 0", "정답")


def test_references_are_compared_after_normalising(loaded):
    # 띄어쓰기·문장부호·대소문자만 다른 정답은 어긋남이 아니다(채점이 정규화하므로 같은 정답이다).
    base = get(loaded, "whisper-small")
    reference = base.utterances[0].reference
    noisy = " " + reference.replace(" ", "  ").upper() + " ... "
    assert check(loaded, systems=systems_with(loaded, edit(base, 0, reference=noisy))) == []


def test_a_missing_common_reference_system_is_reported(loaded):
    # 기준이 되는 공통 정답 묶음이 목록에 없으면 정답을 견줄 수 없다. 조용히 건너뛰지 않고 한 줄로 알린다.
    systems = [s for s in loaded.systems if s.key != COMMON]
    one_line(check(loaded, systems=systems), COMMON, "공통 정답")


# ---------------------------------------------------------------------------------------------
# 6: stt-scratch의 알려진 정답 차이
# ---------------------------------------------------------------------------------------------


def test_an_unknown_stt_reference_difference_is_reported(loaded):
    base = get(loaded, "stt-scratch-full")
    broken = edit(base, 0, reference=base.utterances[0].reference + "추가")
    one_line(check(loaded, systems=systems_with(loaded, broken)), "stt-scratch-full", "행 0", "알려진")


def test_known_difference_rows_must_still_differ(loaded):
    # 알려진 차이 행(3)의 정답이 더는 다르지 않아도 어긋남이다. 알려진 목록이 낡았다는 뜻이다.
    base = get(loaded, "stt-scratch-full")
    common = get(loaded, COMMON)
    broken = edit(base, 3, reference=common.utterances[3].reference)
    one_line(check(loaded, systems=systems_with(loaded, broken)), "stt-scratch-full", "행 3", "알려진")


def test_the_known_differences_are_a_parameter(loaded):
    # 알려진 차이 행의 목록을 비우면 행 3의 차이는 알려지지 않은 차이가 된다(두 stt-scratch 묶음 모두에서).
    problems = check(loaded, known_reference_differences=())
    assert len(problems) == 2
    assert all("행 3" in line and "알려진" in line for line in problems)


def test_a_known_difference_row_must_not_be_hangul_only(loaded):
    # 한글 전용 수는 그대로 두고(한 곳을 켜고 한 곳을 끈다) 알려진 차이 행만 한글 전용으로 표시한다.
    flags = list(loaded.hangul)
    flags[flags.index(True)] = False
    flags[3] = True
    one_line(check(loaded, hangul=tuple(flags)), "행 3", "한글 전용")


# ---------------------------------------------------------------------------------------------
# 7: 같은 가설을 가진 리포트
# ---------------------------------------------------------------------------------------------


def test_a_twin_hypothesis_mismatch_is_reported(loaded):
    base = get(loaded, "qwen3-asr-1.7b-qn-fixed")
    broken = edit(base, 2, hypothesis=base.utterances[2].hypothesis + "가")
    one_line(
        check(loaded, twins={**loaded.twins, "qwen3-asr-1.7b-qn-fixed": broken}),
        "qwen3-asr-1.7b-qn",
        "qwen3-asr-1.7b-qn-fixed",
        "행 2",
        "가설",
    )


def test_twin_hypotheses_are_compared_letter_for_letter(loaded):
    # 정규화하기 전의 저장된 글로 견준다: 문장부호 하나나 띄어쓰기 하나 다른 것도 어긋남이다.
    base = get(loaded, "turbo-n-d1a")
    broken = edit(base, 0, hypothesis=base.utterances[0].hypothesis + " ")
    one_line(check(loaded, twins={**loaded.twins, "turbo-n-d1a": broken}), "turbo-n-d1a", "행 0", "가설")


def test_missing_twin_is_reported(loaded):
    # 묶음이 같은 가설이라고 적은 리포트를 읽은 목록(twins)에서 찾을 수 없으면 조용히 건너뛰지 않는다.
    twins = {name: twin for name, twin in loaded.twins.items() if name != "qwen3-asr-1.7b-fixed"}
    one_line(check(loaded, twins=twins), "qwen3-asr-1.7b", "qwen3-asr-1.7b-fixed")


def test_twins_nobody_refers_to_are_still_checked_for_their_rows(loaded):
    # 어느 묶음도 가리키지 않는 형제 리포트가 twins에 있어도 행 번호 집합은 확인한다.
    base = get(loaded, "turbo-n-d1a")
    stray = replace(base, key="stray", utterances=base.utterances[:-1], ids=base.ids[:-1])
    one_line(check(loaded, twins={**loaded.twins, "stray": stray}), "stray", "행 3")


# ---------------------------------------------------------------------------------------------
# 8: 한글 전용 표시
# ---------------------------------------------------------------------------------------------


def test_the_hangul_only_count_is_checked(loaded):
    flags = list(loaded.hangul)
    flags[flags.index(False)] = True
    one_line(check(loaded, hangul=tuple(flags)), "한글 전용", "3", "2")


def test_the_hangul_only_length_is_checked(loaded):
    # 표시의 길이가 발화 수와 다르면 그 한 줄로 알린다. 행 번호로 표시를 찾는 다른 검사(6번)가 범위를 넘어
    # 읽지 않는지도 함께 본다(알려진 차이 행 3은 길이 3인 표시의 밖이다).
    one_line(check(loaded, hangul=loaded.hangul[:3]), "한글 전용", "3", "4")


# ---------------------------------------------------------------------------------------------
# 줄의 차례
# ---------------------------------------------------------------------------------------------


def test_lines_come_in_the_order_of_the_checks_and_do_not_change(loaded):
    # 문장 번호(2)·음성 길이(3)·한글 전용 수(8)가 한꺼번에 어긋난 고정물: 줄은 검사 번호 순으로 나온다.
    voice = edit(get(loaded, "voice-turbo"), 1, sentence="999")
    small_a = edit(get(loaded, "small-a"), 2, seconds=50.0)
    systems = [
        small_a if s.key == "small-a" else voice if s.key == "voice-turbo" else s for s in loaded.systems
    ]
    flags = list(loaded.hangul)
    flags[flags.index(False)] = True
    problems = check(loaded, systems=systems, hangul=tuple(flags))
    assert len(problems) == 3
    assert "voice-turbo" in problems[0] and "문장 번호" in problems[0]
    assert "small-a" in problems[1] and "음성 길이" in problems[1]
    assert "한글 전용" in problems[2]
    assert check(loaded, systems=systems, hangul=tuple(flags)) == problems


def test_lines_of_twin_reports_follow_the_systems_in_name_order(loaded):
    # 같은 검사 안에서 줄의 차례는 읽은 열네 묶음 다음에 형제 리포트를 이름 순으로 늘어놓은 것이다.
    # 사전에 넣은 차례가 아니다: loaded.twins에서 turbo-n-d1a는 qwen3-asr-1.7b-fixed보다 앞이지만
    # 이름 순으로는 뒤다.
    names = list(loaded.twins)
    assert names.index("turbo-n-d1a") < names.index("qwen3-asr-1.7b-fixed")
    voice = edit(get(loaded, "voice-turbo"), 3, sentence="999")
    twins = with_twin(loaded, with_sentence(get(loaded, "turbo-n-d1a"), 3, "999"))
    twins = {**twins, "qwen3-asr-1.7b-fixed": with_sentence(get(loaded, "qwen3-asr-1.7b-fixed"), 3, "999")}
    problems = check(loaded, systems=systems_with(loaded, voice), twins=twins)
    assert [line.split(":")[0] for line in problems] == ["voice-turbo", "qwen3-asr-1.7b-fixed", "turbo-n-d1a"]
