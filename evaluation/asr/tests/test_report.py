"""채점 결과 만들기(report)의 시험.

두 부분이다.

  - `build`: 묶음 둘·발화 넷의 작은 고정물을 손으로 계산한 값과 견준다. 구간은 같은 다시 뽑기 번호로 따로 다시
    계산해서 견주고, 발화를 튜플의 위치가 아니라 행 번호로 찾는지, 빠진 행을 조용히 넘어가지 않는지 본다.
  - 글 만들기(`render_json`, `render_markdown`): 채점하지 않고 손으로 쓴 결과 사전으로 글의 꼴을 시험한다.
    같은 결과에서 언제나 같은 글이 나오는지, 반올림과 부호, Markdown 표의 모양을 글자 그대로 고정한다.

손으로 계산한 고정물(정규화한 정답 글자 수는 행마다 4)
    공통 정답 묶음의 편집 수는 행 0부터 3까지 0, 1, 0, 1이고 합 2, 다른 묶음은 1, 0, 2, 1이고 합 4다. 그래서
    전체 글자 오류율은 2/16 = 0.125와 4/16 = 0.25, 차이는 -0.125다. 앞이 적은 발화는 행 0과 2, 많은 발화는
    행 1, 같은 발화는 행 3이다. 한글 전용은 행 0과 2이고, 거기서는 편집 수가 0, 0 대 1, 2라서 0.0 대 0.375,
    차이는 -0.375이며 앞이 적은 발화 둘이다.

정답 글자 수가 행마다 다른 고정물(`UNEVEN_*`, 다섯 행)
    위 고정물은 글자 수가 모든 행에서 같아서, 구간의 분모(다시 뽑기마다 뽑힌 발화의 글자 수 합)를 고정하지
    못한다. 이 고정물의 정규화한 정답 글자 수는 6, 2, 7, 3, 8(합 26)이다. 공통 정답 묶음의 편집 수는 0, 1, 2,
    0, 2(합 5), 다른 묶음은 1, 0, 2, 1, 4(합 8)다. 한글 전용은 행 0, 2, 3(글자 수 6, 7, 3으로 합 16, 편집 수
    0, 2, 0 대 1, 2, 1)이고 행 1과 4에는 라틴 문자나 숫자가 있다. 앞이 적은 발화는 행 0, 3, 4, 많은 발화는
    행 1, 같은 발화는 행 2이고, 한글 전용에서는 적은 발화가 행 0과 3, 같은 발화가 행 2다.
"""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from asr_compare import join, report, score
from asr_compare.sources import System, Utterance

COMMON = join.COMMON_REFERENCE
OTHER = "voice-turbo"
PAIRS = (("both", COMMON, OTHER),)
INPUTS = (("a/first.json", "0" * 64), ("b/second.jsonl", "f" * 64))
MINUS = "\N{MINUS SIGN}"

REFERENCES = ["가나다라", "마바 사아", "차카타파", "ab, cd"]
COMMON_HYPOTHESES = ["가나다라", "마바사", "차카타파", "abxd"]
OTHER_HYPOTHESES = ["가나 다", "마바사아", "차카", "abyd"]
HANGUL = (True, False, True, False)


def system(key: str, component: str, references, hypotheses) -> System:
    utterances = tuple(
        Utterance(row, str(row), 5.0, reference, hypothesis)
        for row, (reference, hypothesis) in enumerate(zip(references, hypotheses, strict=True))
    )
    return System(key, component, f"{key}.json", (), utterances)


def common_system() -> System:
    return system(COMMON, "whisper-ko-ft", REFERENCES, COMMON_HYPOTHESES)


def other_system(references=None) -> System:
    # 이 묶음의 정답은 일부러 엉뚱한 글이다. 채점은 공통 정답 묶음의 정답으로만 하므로 결과에 영향이 없어야
    # 한다.
    return system(OTHER, "voice-translator", references or ["엉뚱한 정답"] * 4, OTHER_HYPOTHESES)


def build_small(systems=None, hangul=HANGUL, **options) -> dict:
    systems = [common_system(), other_system()] if systems is None else systems
    return report.build(systems, hangul, INPUTS, pairs=options.pop("pairs", PAIRS), **options)


# ---------------------------------------------------------------------------------------------
# build: 손으로 계산한 값
# ---------------------------------------------------------------------------------------------


def test_build_counts_edits_and_lengths_by_hand():
    result = build_small()
    assert list(result) == ["format", "set", "utterances", "hangul_only", "inputs", "systems", "pairs"]
    assert result["format"] == "asr-compare/1"
    assert result["set"] == "fleurs-ko-test"
    assert result["utterances"] == 4
    assert result["hangul_only"] == 2
    assert result["inputs"] == [
        {"path": "a/first.json", "sha256": "0" * 64},
        {"path": "b/second.jsonl", "sha256": "f" * 64},
    ]
    common, other = result["systems"]
    assert list(common) == ["key", "component", "path", "also", "all", "hangul_only"]
    assert (common["key"], common["component"], common["path"], common["also"]) == (
        COMMON,
        "whisper-ko-ft",
        f"{COMMON}.json",
        [],
    )
    assert list(common["all"]) == ["edits", "length", "cer", "interval"]
    assert (common["all"]["edits"], common["all"]["length"], common["all"]["cer"]) == (2, 16, 0.125)
    assert (other["all"]["edits"], other["all"]["length"], other["all"]["cer"]) == (4, 16, 0.25)
    assert (
        common["hangul_only"]["edits"],
        common["hangul_only"]["length"],
        common["hangul_only"]["cer"],
    ) == (
        0,
        8,
        0.0,
    )
    assert (other["hangul_only"]["edits"], other["hangul_only"]["length"], other["hangul_only"]["cer"]) == (
        3,
        8,
        0.375,
    )


def test_the_sibling_report_names_of_a_system_are_carried_into_its_entry():
    # 같은 가설이라고 적힌 형제 리포트의 이름은 적힌 차례 그대로 `also`에 실린다(없으면 빈 목록).
    tagged = replace(other_system(), also=("twin-b", "twin-a"))
    result = build_small([common_system(), tagged])
    assert [entry["also"] for entry in result["systems"]] == [[], ["twin-b", "twin-a"]]


def test_build_compares_the_pair_by_hand():
    result = build_small()
    assert len(result["pairs"]) == 1
    pair = result["pairs"][0]
    assert list(pair) == ["id", "minuend", "subtrahend", "all", "hangul_only"]
    assert (pair["id"], pair["minuend"], pair["subtrahend"]) == ("both", COMMON, OTHER)
    assert list(pair["all"]) == ["difference", "interval", "fewer_edits", "more_edits", "same"]
    # 앞 − 뒤: 공통 정답 묶음이 다른 묶음보다 적게 틀렸으므로 차이는 음수다.
    assert pair["all"]["difference"] == -0.125
    assert (pair["all"]["fewer_edits"], pair["all"]["more_edits"], pair["all"]["same"]) == (2, 1, 1)
    assert pair["hangul_only"]["difference"] == -0.375
    assert (pair["hangul_only"]["fewer_edits"], pair["hangul_only"]["more_edits"]) == (2, 0)
    assert pair["hangul_only"]["same"] == 0


def test_the_difference_is_the_difference_of_the_two_ratios():
    result = build_small()
    common, other = result["systems"]
    pair = result["pairs"][0]
    for scope in ("all", "hangul_only"):
        assert pair[scope]["difference"] == common[scope]["cer"] - other[scope]["cer"]
        counts = (pair[scope]["fewer_edits"], pair[scope]["more_edits"], pair[scope]["same"])
        assert sum(counts) == (4 if scope == "all" else 2)


def test_every_system_is_scored_against_the_common_reference():
    # 다른 묶음이 자기 정답을 어떻게 적어 놓았든 결과는 같다(자기 정답으로 세는 것은 이 도구의 일이 아니다).
    assert build_small() == build_small([common_system(), other_system(REFERENCES)])


def test_hypotheses_are_normalised_before_counting():
    # 다른 묶음의 첫 가설 "가나 다"는 공백이 있지만 정규화하면 "가나다"라서 편집은 하나(마지막 글자 삭제)다.
    other = build_small()["systems"][1]
    assert other["all"]["edits"] == 4


# ---------------------------------------------------------------------------------------------
# build: 구간은 같은 다시 뽑기 번호에서 나온다
# ---------------------------------------------------------------------------------------------


def resampled_ratios(edits, lengths, indices):
    return [sum(edits[i] for i in resample) / sum(lengths[i] for i in resample) for resample in indices]


def test_intervals_come_from_the_shared_resamples():
    result = build_small()
    common_edits, other_edits, lengths = [0, 1, 0, 1], [1, 0, 2, 1], [4, 4, 4, 4]
    # 전체: 모든 묶음과 짝이 같은 다시 뽑기 번호(발화 4개 기준)를 쓴다.
    indices = score.resample_indices(4)
    common_ratios = resampled_ratios(common_edits, lengths, indices)
    other_ratios = resampled_ratios(other_edits, lengths, indices)
    # 한글 전용: 한글 전용 행(0, 2)을 행 번호 순으로 늘어놓은 목록의 위치를 뽑는다.
    hangul_indices = score.resample_indices(2)
    common_hangul = resampled_ratios([0, 0], [4, 4], hangul_indices)
    other_hangul = resampled_ratios([1, 2], [4, 4], hangul_indices)

    common, other = result["systems"]
    assert common["all"]["interval"] == list(score.interval(common_ratios))
    assert other["all"]["interval"] == list(score.interval(other_ratios))
    assert common["hangul_only"]["interval"] == list(score.interval(common_hangul))
    assert other["hangul_only"]["interval"] == list(score.interval(other_hangul))
    pair = result["pairs"][0]
    all_differences = [a - b for a, b in zip(common_ratios, other_ratios, strict=True)]
    hangul_differences = [a - b for a, b in zip(common_hangul, other_hangul, strict=True)]
    assert pair["all"]["interval"] == list(score.interval(all_differences))
    assert pair["hangul_only"]["interval"] == list(score.interval(hangul_differences))


def test_identical_systems_have_a_zero_difference_and_a_zero_width_interval():
    # 두 묶음이 같은 다시 뽑기 번호를 쓰면, 같은 가설을 가진 두 묶음의 차이는 뽑을 때마다 0이다. 묶음마다
    # 다른 번호를 쓰면 구간이 0 폭이 되지 않는다.
    twin = system(OTHER, "voice-translator", REFERENCES, COMMON_HYPOTHESES)
    pair = build_small([common_system(), twin])["pairs"][0]
    for scope, count in (("all", 4), ("hangul_only", 2)):
        assert pair[scope]["difference"] == 0.0
        assert pair[scope]["interval"] == [0.0, 0.0]
        assert (pair[scope]["fewer_edits"], pair[scope]["more_edits"], pair[scope]["same"]) == (0, 0, count)


def test_the_default_pairs_are_the_three_named_comparisons():
    assert report.PAIRS == (
        ("decoding-path", "whisper-large-v3-turbo", "voice-turbo"),
        ("vad", "voice-turbo", "voice-turbo-vad"),
        ("both", "whisper-large-v3-turbo", "voice-turbo-vad"),
    )


# ---------------------------------------------------------------------------------------------
# build: 정답 글자 수가 행마다 다르다
# ---------------------------------------------------------------------------------------------

# 위의 고정물은 정규화한 정답 글자 수가 모든 행에서 4라서, 다시 뽑기마다 '뽑힌 발화의 글자 수 합'으로 나누는
# 것과 '범위 전체의 글자 수 합'으로 나누는 것이 같은 값이다. 한글 전용 범위의 글자 수를 행 번호가 아니라
# 목록의 위치로 잡아도 같다. 실제 재료는 글자 수가 행마다 다르므로, 두 가지를 가르는 고정물을 따로 둔다.
UNEVEN_REFERENCES = ["가나다라마바", "Ab", "다라마바사아자", "차카타", "타파하 3 나다라마"]
UNEVEN_LENGTHS = [6, 2, 7, 3, 8]
UNEVEN_HANGUL = (True, False, True, True, False)
UNEVEN_HANGUL_ROWS = (0, 2, 3)
# 가설은 정답의 끝 글자를 지운 것이라, 지운 글자 수가 곧 편집 수다. 행 1은 "ab"에서 "b"를 지웠다.
UNEVEN_COMMON_HYPOTHESES = ["가나다라마바", "A", "다라마바사", "차카타", "타파하 3 나다"]
UNEVEN_COMMON_EDITS = [0, 1, 2, 0, 2]
UNEVEN_OTHER_HYPOTHESES = ["가나다라마", "ab", "다라마바사", "차카", "타파하 3"]
UNEVEN_OTHER_EDITS = [1, 0, 2, 1, 4]


def build_uneven() -> dict:
    systems = [
        system(COMMON, "whisper-ko-ft", UNEVEN_REFERENCES, UNEVEN_COMMON_HYPOTHESES),
        system(OTHER, "voice-translator", UNEVEN_REFERENCES, UNEVEN_OTHER_HYPOTHESES),
    ]
    return build_small(systems, hangul=UNEVEN_HANGUL)


def test_build_counts_by_hand_when_the_reference_lengths_differ():
    result = build_uneven()
    common, other = result["systems"]
    assert (common["all"]["edits"], common["all"]["length"], common["all"]["cer"]) == (5, 26, 5 / 26)
    assert (other["all"]["edits"], other["all"]["length"], other["all"]["cer"]) == (8, 26, 8 / 26)
    keys = ("edits", "length", "cer")
    assert tuple(common["hangul_only"][key] for key in keys) == (2, 16, 2 / 16)
    assert tuple(other["hangul_only"][key] for key in keys) == (4, 16, 4 / 16)
    pair = result["pairs"][0]
    assert pair["all"]["difference"] == 5 / 26 - 8 / 26
    assert (pair["all"]["fewer_edits"], pair["all"]["more_edits"], pair["all"]["same"]) == (3, 1, 1)
    assert pair["hangul_only"]["difference"] == 2 / 16 - 4 / 16
    hangul_pair = pair["hangul_only"]
    assert (hangul_pair["fewer_edits"], hangul_pair["more_edits"], hangul_pair["same"]) == (2, 0, 1)


def test_intervals_divide_by_the_lengths_of_the_drawn_utterances():
    # 구간의 값 하나는 (뽑힌 발화의 편집 수 합) ÷ (뽑힌 발화의 정답 글자 수 합)이다. 글자 수가 행마다 다르면
    # 나누는 수가 다시 뽑기마다 달라진다. 같은 다시 뽑기 번호로 따로 계산해 견준다.
    result = build_uneven()
    common, other = result["systems"]
    pair = result["pairs"][0]
    scopes = {
        "all": (score.resample_indices(5), UNEVEN_LENGTHS, UNEVEN_COMMON_EDITS, UNEVEN_OTHER_EDITS),
        # 한글 전용: 행 0, 2, 3을 행 번호 순으로 늘어놓은 목록의 위치를 뽑는다.
        # 글자 수는 그 행의 것이다(6, 7, 3).
        "hangul_only": (
            score.resample_indices(3),
            [UNEVEN_LENGTHS[row] for row in UNEVEN_HANGUL_ROWS],
            [UNEVEN_COMMON_EDITS[row] for row in UNEVEN_HANGUL_ROWS],
            [UNEVEN_OTHER_EDITS[row] for row in UNEVEN_HANGUL_ROWS],
        ),
    }
    for scope, (indices, lengths, common_edits, other_edits) in scopes.items():
        common_ratios = resampled_ratios(common_edits, lengths, indices)
        other_ratios = resampled_ratios(other_edits, lengths, indices)
        assert common[scope]["interval"] == list(score.interval(common_ratios)), scope
        assert other[scope]["interval"] == list(score.interval(other_ratios)), scope
        differences = [a - b for a, b in zip(common_ratios, other_ratios, strict=True)]
        assert pair[scope]["interval"] == list(score.interval(differences)), scope


def test_the_uneven_fixture_tells_the_wrong_denominators_apart():
    # 위 시험이 아무것도 고정하지 못하는 일이 없게, 이 고정물에서 틀린 분모가 다른 구간을 낸다는 것을
    # 확인한다. 틀린 식은 둘이다: 뽑힌 발화가 아니라 범위 전체의 글자 수 합으로 나눈다, 한글 전용의 글자 수를
    # 행 번호가 아니라 목록의 위치(행 0, 1, 2의 것)로 잡는다.
    hangul_lengths = [UNEVEN_LENGTHS[row] for row in UNEVEN_HANGUL_ROWS]
    assert sum(UNEVEN_LENGTHS[: len(hangul_lengths)]) != sum(hangul_lengths)
    all_indices = score.resample_indices(5)
    right = resampled_ratios(UNEVEN_COMMON_EDITS, UNEVEN_LENGTHS, all_indices)
    by_total = [
        sum(UNEVEN_COMMON_EDITS[i] for i in resample) / sum(UNEVEN_LENGTHS) for resample in all_indices
    ]
    assert score.interval(by_total) != score.interval(right)
    hangul_edits = [UNEVEN_COMMON_EDITS[row] for row in UNEVEN_HANGUL_ROWS]
    hangul_indices = score.resample_indices(3)
    right = resampled_ratios(hangul_edits, hangul_lengths, hangul_indices)
    by_total = [sum(hangul_edits[i] for i in resample) / sum(hangul_lengths) for resample in hangul_indices]
    by_position = resampled_ratios(hangul_edits, UNEVEN_LENGTHS[: len(hangul_lengths)], hangul_indices)
    assert score.interval(by_total) != score.interval(right)
    assert score.interval(by_position) != score.interval(right)


# ---------------------------------------------------------------------------------------------
# build: 행 번호로 찾고, 빠진 것은 조용히 넘기지 않는다
# ---------------------------------------------------------------------------------------------


def test_build_does_not_depend_on_the_tuple_order():
    # 발화를 튜플의 위치가 아니라 행 번호로 찾는다. 한 묶음의 발화 차례를 뒤집거나 돌려도 결과와 글이 같다.
    expected = build_small()
    other = other_system()
    common = common_system()
    for reordered in (
        replace(other, utterances=other.utterances[::-1]),
        replace(other, utterances=other.utterances[2:] + other.utterances[:2]),
    ):
        result = build_small([common, reordered])
        assert result == expected
        assert report.render_json(result) == report.render_json(expected)
    reversed_common = replace(common, utterances=common.utterances[::-1])
    assert build_small([reversed_common, other]) == expected


def test_build_stops_when_a_row_is_missing():
    other = other_system()
    broken = replace(other, utterances=tuple(u for u in other.utterances if u.row != 2))
    with pytest.raises(ValueError, match=r"voice-turbo.*빠진 행.*2"):
        build_small([common_system(), broken])


def test_build_stops_when_a_row_appears_twice():
    other = other_system()
    broken = replace(other, utterances=(*other.utterances, other.utterances[0]))
    with pytest.raises(ValueError, match="voice-turbo.*두 번"):
        build_small([common_system(), broken])


def test_build_stops_when_a_row_is_outside_the_range():
    other = other_system()
    moved = tuple(replace(u, row=7) if u.row == 3 else u for u in other.utterances)
    with pytest.raises(ValueError, match=r"voice-turbo.*빠진 행.*3.*범위 밖 행.*7"):
        build_small([common_system(), replace(other, utterances=moved)])


@pytest.mark.parametrize("reference", ["", "  ", "...", "'!?"])
def test_build_stops_when_the_common_reference_is_empty(reference):
    # 정규화한 정답이 빈 글인 행은 글자 오류율의 분모를 0으로 만든다. 빈 값이나 0으로 메우지 않고 멈춘다.
    references = [*REFERENCES[:1], reference, *REFERENCES[2:]]
    common = system(COMMON, "whisper-ko-ft", references, COMMON_HYPOTHESES)
    with pytest.raises(ValueError, match="행 1.*빈 글"):
        build_small([common, other_system()])


def test_build_needs_the_common_reference_system():
    with pytest.raises(ValueError, match="공통 정답"):
        build_small([other_system()], pairs=())


def test_build_needs_both_systems_of_every_pair():
    with pytest.raises(ValueError, match="no-such-system"):
        build_small(pairs=(("broken", COMMON, "no-such-system"),))


def test_build_needs_at_least_one_hangul_only_utterance():
    with pytest.raises(ValueError, match="한글 전용"):
        build_small(hangul=(False, False, False, False))


def test_build_rejects_two_systems_with_the_same_key():
    with pytest.raises(ValueError, match="두 번"):
        build_small([common_system(), common_system(), other_system()])


# ---------------------------------------------------------------------------------------------
# 글 만들기: 손으로 쓴 결과로 글의 꼴을 고정한다
# ---------------------------------------------------------------------------------------------


def handmade_result() -> dict:
    """채점하지 않고 손으로 쓴 결과 사전(꼴은 build가 돌려주는 것과 같다)."""
    return {
        "format": "asr-compare/1",
        "set": "fleurs-ko-test",
        "utterances": 4,
        "hangul_only": 2,
        "inputs": [{"path": "a/first.json", "sha256": "0" * 64}],
        "systems": [
            {
                "key": "voice-turbo",
                "component": "voice-translator",
                "path": "a/first.json",
                "also": [],
                "all": {"edits": 2, "length": 16, "cer": 0.125, "interval": [0.0625, 0.1875]},
                "hangul_only": {"edits": 0, "length": 8, "cer": 0.0, "interval": [0.0, 0.0625]},
            },
            {
                "key": "turbo-n",
                "component": "whisper-ko-ft",
                "path": "b/second.json",
                "also": ["turbo-n-d1a"],
                "all": {"edits": 4, "length": 16, "cer": 0.25, "interval": [0.125, 0.375]},
                "hangul_only": {"edits": 3, "length": 8, "cer": 0.375, "interval": [0.125, 0.5]},
            },
        ],
        "pairs": [
            {
                "id": "both",
                "minuend": "voice-turbo",
                "subtrahend": "turbo-n",
                "all": {
                    "difference": -0.125,
                    "interval": [-0.25, 0.0],
                    "fewer_edits": 2,
                    "more_edits": 1,
                    "same": 1,
                },
                "hangul_only": {
                    "difference": -0.375,
                    "interval": [-0.5, -0.25],
                    "fewer_edits": 2,
                    "more_edits": 0,
                    "same": 0,
                },
            }
        ],
    }


GOLDEN = "\n".join(
    [
        "# 같은 발화 인식 비교 (fleurs-ko-test)",
        "",
        "> 구성 요소가 이미 커밋한 발화별 가설을 같은 규칙으로 다시 채점한 결과다(새 디코딩 없음). "
        "읽은 재료와 sha256은 같은 이름의 JSON 파일의 `inputs`에 있고, 규칙은 저장소의 "
        "`docs/asr-comparison.md`에 있다. 95% 구간은 발화를 다시 뽑는 부트스트랩이다(1000번, 시드 0).",
        "",
        "## 전체 4발화",
        "",
        "| 묶음 | 구성 요소 | 편집 수 | 정답 글자 수 | 글자 오류율(%) | 95% 구간(%) |",
        "|---|---|---:|---:|---:|---|",
        "| voice-turbo | voice-translator | 2 | 16 | 12.50 | [6.25, 18.75] |",
        "| turbo-n | whisper-ko-ft | 4 | 16 | 25.00 | [12.50, 37.50] |",
        "",
        "## 한글 전용 2발화",
        "",
        "| 묶음 | 구성 요소 | 편집 수 | 정답 글자 수 | 글자 오류율(%) | 95% 구간(%) |",
        "|---|---|---:|---:|---:|---|",
        "| voice-turbo | voice-translator | 0 | 8 | 0.00 | [0.00, 6.25] |",
        "| turbo-n | whisper-ko-ft | 3 | 8 | 37.50 | [12.50, 50.00] |",
        "",
        "## 짝 비교",
        "",
        "| 짝 | 앞 "
        + MINUS
        + " 뒤 | 범위 | 차이(%p) | 95% 구간(%p) | 앞이 적은 발화 | 앞이 많은 발화 | 같은 발화 |",
        "|---|---|---|---:|---|---:|---:|---:|",
        f"| both | voice-turbo {MINUS} turbo-n | 전체 | -12.50 | [-25.00, +0.00] | 2 | 1 | 1 |",
        f"| both | voice-turbo {MINUS} turbo-n | 한글 전용 | -37.50 | [-50.00, -25.00] | 2 | 0 | 0 |",
    ]
)
GOLDEN += "\n"


def test_render_markdown_has_exactly_the_agreed_shape():
    assert report.render_markdown(handmade_result()) == GOLDEN


def test_render_markdown_keeps_the_order_of_the_systems():
    # 줄 차례는 읽은 묶음의 차례 그대로다(오류율이나 이름으로 정렬하지 않는다).
    result = handmade_result()
    result["systems"].reverse()
    lines = report.render_markdown(result).splitlines()
    rows = [line for line in lines if line.startswith(("| turbo-n |", "| voice-turbo |"))]
    # 전체 표와 한글 전용 표 모두 turbo-n이 먼저다(이름이나 오류율로 다시 정렬하지 않았다).
    assert [row.split(" |")[0] for row in rows] == [
        "| turbo-n",
        "| voice-turbo",
        "| turbo-n",
        "| voice-turbo",
    ]


def test_render_markdown_has_no_plain_lines_that_would_merge():
    # Markdown은 빈 줄 없이 이어진 보통 줄을 한 문단으로 붙여 보여 준다. 모든 줄이 제목·인용·표 가운데
    # 하나여야 한다.
    text = report.render_markdown(handmade_result())
    starts = ("# ", "## ", "> ", "|")  # 표의 구분선(|---|)은 `| `가 아니라 `|`로 시작한다
    assert [line for line in text.splitlines() if line and not line.startswith(starts)] == []


def test_render_markdown_avoids_tilde_and_bold_markers():
    # 물결표 둘은 같은 문단에서 취소선이 되고, 굵게 표시 바로 뒤의 한글은 GitHub이 그리지 못한다.
    text = report.render_markdown(handmade_result())
    assert "~" not in text
    assert "**" not in text


def test_render_markdown_is_lf_and_ends_with_one_newline():
    text = report.render_markdown(handmade_result())
    assert "\r" not in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_render_markdown_percent_comes_from_the_unrounded_value():
    # 0.0001502를 소수 여섯째 자리로 먼저 반올림하면 0.00015이고, 그 100배(0.015)를 소수 둘째 자리로 쓰면
    # 0.01이 된다. 반올림하기 전의 값(0.01502)에서 만들면 0.02다. Markdown은 반올림하기 전의 값에서 만든다.
    result = handmade_result()
    result["systems"][0]["all"]["cer"] = 0.0001502
    text = report.render_markdown(result)
    assert "| 2 | 16 | 0.02 |" in text
    assert '"cer": 0.00015' in report.render_json(result)


def test_render_markdown_signs_differences_and_never_prints_a_negative_zero():
    result = handmade_result()
    pair = result["pairs"][0]
    pair["all"]["difference"] = 0.002
    pair["all"]["interval"] = [-0.000001, 0.0]
    pair["hangul_only"]["difference"] = -0.000001
    text = report.render_markdown(result)
    assert "| both | voice-turbo " + MINUS + " turbo-n | 전체 | +0.20 | [+0.00, +0.00] |" in text
    assert "| 한글 전용 | +0.00 | [-50.00, -25.00] |" in text
    assert "-0.00" not in text


# ---------------------------------------------------------------------------------------------
# 글 만들기: JSON
# ---------------------------------------------------------------------------------------------


def test_render_json_is_stable_and_plain():
    result = build_small()
    text = report.render_json(result)
    assert text == report.render_json(build_small())
    assert "\r" not in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert not text.startswith("\N{ZERO WIDTH NO-BREAK SPACE}")
    assert json.loads(text)["format"] == "asr-compare/1"


def test_render_json_keeps_the_order_the_code_built():
    # sort_keys에 기대지 않는다: 키 차례는 코드가 정한 차례(사전순이 아니다) 그대로다.
    document = json.loads(report.render_json(handmade_result()))
    assert list(document) == ["format", "set", "utterances", "hangul_only", "inputs", "systems", "pairs"]
    assert list(document["systems"][0]) == ["key", "component", "path", "also", "all", "hangul_only"]
    assert list(document["systems"][0]["all"]) == ["edits", "length", "cer", "interval"]
    assert list(document["pairs"][0]["all"]) == [
        "difference",
        "interval",
        "fewer_edits",
        "more_edits",
        "same",
    ]


def test_render_json_uses_one_space_indentation_and_keeps_text_unescaped():
    result = handmade_result()
    result["systems"][0]["component"] = "음성 번역"
    text = report.render_json(result)
    assert text.startswith('{\n "format": "asr-compare/1",\n')
    assert "음성 번역" in text


def test_render_json_rounds_ratios_to_six_decimals_and_leaves_counts_alone():
    result = handmade_result()
    result["systems"][0]["all"]["cer"] = 1 / 3
    result["systems"][0]["all"]["interval"] = [0.12345649, 2 / 3]
    document = json.loads(report.render_json(result))
    stored = document["systems"][0]["all"]
    assert stored["cer"] == 0.333333
    assert stored["interval"] == [0.123456, 0.666667]
    assert (stored["edits"], stored["length"]) == (2, 16)
    assert document["utterances"] == 4


def test_render_json_does_not_change_its_input():
    result = handmade_result()
    result["systems"][0]["all"]["cer"] = 1 / 3
    before = deepcopy(result)
    report.render_json(result)
    assert result == before


def test_render_json_never_writes_a_negative_zero():
    result = handmade_result()
    result["pairs"][0]["all"]["difference"] = -1e-9
    result["pairs"][0]["all"]["interval"] = [-1e-9, 0.0]
    text = report.render_json(result)
    assert "-0.0" not in text
    assert json.loads(text)["pairs"][0]["all"]["difference"] == 0.0
