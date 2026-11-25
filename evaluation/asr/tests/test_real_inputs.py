"""저장소가 커밋해 둔 실제 재료로 하는 시험: 결합 검증과, 구성 요소가 이미 기록한 값의 재현.

이 파일만 합성 고정물이 아니라 저장소의 리포트 파일(구성 요소 폴더 아래의 추적 파일)을 읽는다. 읽기만 하고
아무것도 쓰지 않는다. 하는 일은 둘이다.

  - 결합 검증: 열네 묶음이 발화 단위로 일대일로 짝지어지는지(`join.verify`가 빈 목록을 돌려준다).
  - 기록값 재현: 각 구성 요소가 이미 적어 둔 값(그 구성 요소의 자기 정답으로 센 편집 수의 합과 정답 글자 수의
    합, whisper-ko-ft는 리포트에 저장된 발화별 값과 `summary.error_rate`)을 저장된 가설에서 다시 세어 얻는지.

새 수치를 내지 않는다. 묶음을 서로 견주는 값(공통 정답으로 다시 센 값, 구간, 묶음 사이의 차이)과, 구성 요소가
기록하지 않은 범위(voice-translator와 whisper-ko-ft의 한글 전용)는 세지 않고 실패 메시지에도 싣지 않는다.

재료 파일이 없거나 읽을 수 없으면 건너뛰지 않고 실패한다. 재료가 사라졌는데 시험이 초록이면 안 된다.
"""

from pathlib import Path

import pytest

from asr_compare import cli, join, recorded, score, sources

# 이 파일은 <저장소>/evaluation/asr/tests/ 아래에 있다. parents[0] = tests, [1] = asr, [2] = evaluation,
# [3] = 저장소 뿌리.
REPOSITORY = Path(__file__).resolve().parents[3]

FINAL_LINE = "묶음 14개, 발화 382개(한글 전용 257개), 어긋남 0개"

# whisper-ko-ft 리포트가 `summary.error_rate`로 이미 적어 둔 값(열 묶음). 기록한 수치는 고치지 않는 것이
# 저장소의 규칙이므로, 리포트가 바뀌면 이 시험이 알려 준다.
RECORDED_RATES = {
    "whisper-small": 0.07624,
    "whisper-large-v3-turbo": 0.05209,
    "small-a": 0.11584,
    "turbo-l2": 0.0694,
    "turbo-t": 0.0685,
    "turbo-n": 0.05549,
    "turbo-n2": 0.05724,
    "qwen3-asr-1.7b": 0.04468,
    "qwen3-asr-1.7b-qn": 0.05679,
    "qwen3-asr-1.7b-qn-s050": 0.04774,
}


@pytest.fixture(scope="module")
def loaded() -> sources.Loaded:
    """실제 저장소의 재료 열아홉 개를 읽은 것. 읽지 못하면 건너뛰지 않고 실패한다."""
    try:
        return sources.load_repository(REPOSITORY)
    except sources.SourceError as error:
        pytest.fail(f"실제 재료를 읽지 못했다: {error}", pytrace=False)


def test_real_inputs_join_one_to_one(loaded):
    assert len(loaded.systems) == 14
    assert len(loaded.twins) == 4
    assert len(loaded.inputs) == 19
    problems = join.verify(list(loaded.systems), loaded.hangul, loaded.twins)
    assert problems == [], "\n".join(problems)


def test_the_recorded_values_name_only_what_the_components_recorded():
    # 구성 요소가 기록하지 않은 범위를 사전에 두지 않는다: 한글 전용은 stt-scratch 묶음뿐이다.
    assert {key: set(scopes) for key, scopes in recorded.EXPECTED.items()} == {
        "voice-turbo-vad": {"all"},
        "voice-turbo": {"all"},
        "whisper-large-v3-turbo": {"all"},
        "stt-scratch-full": {"all", "hangul_only"},
        "stt-scratch-streaming": {"all", "hangul_only"},
    }
    assert set(recorded.EXPECTED) <= {spec.key for spec in sources.SYSTEMS}


def test_recorded_values_are_reproduced(loaded):
    by_key = {system.key: system for system in loaded.systems}

    # 사전에 적은 값: 그 구성 요소의 자기 정답으로 다시 센 합과 글자 그대로 같다.
    for key, scopes in recorded.EXPECTED.items():
        system = by_key[key]
        for scope, expected in scopes.items():
            flags = loaded.hangul if scope == "hangul_only" else None
            recounted = score.totals(
                (utterance.reference, utterance.hypothesis)
                for utterance in system.utterances
                if flags is None or flags[utterance.row]
            )
            assert recounted == expected, f"{key} {scope}: 기록 {expected}, 다시 센 {recounted}"

    # whisper-ko-ft 열 묶음: 발화마다 다시 센 값이 리포트에 저장된 값과 같고, 합의 비율이
    # summary.error_rate와 같다.
    assert set(loaded.stored) == set(RECORDED_RATES)
    for key, rate in RECORDED_RATES.items():
        stored = loaded.stored[key]
        counted = [score.counts(u.reference, u.hypothesis) for u in by_key[key].utterances]
        different = [
            row for row, (pair, saved) in enumerate(zip(counted, stored.counts, strict=True)) if pair != saved
        ]
        assert different == [], f"{key}: 발화별 기록과 다른 행 {different[:5]}"
        edits = sum(pair[0] for pair in counted)
        length = sum(pair[1] for pair in counted)
        assert stored.error_rate == rate, f"{key}: 리포트에 적힌 오류율 {stored.error_rate}, 기대 {rate}"
        assert round(edits / length, 5) == rate, (
            f"{key}: 기록 오류율 {rate}, 다시 센 {round(edits / length, 5)}"
        )


def test_check_command_passes_on_the_repository(capsys):
    code = cli.main(["check", "--repo", str(REPOSITORY)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.splitlines()[-1] == FINAL_LINE
