"""채점 규칙이 세 구성 요소의 것과 같다는 것을 글자로 묶는 시험.

이 도구의 정규화(`score.normalize`)는 whisper-ko-ft, stt-scratch, voice-translator가 각자 쓰는 한국어
정규화와 같은 규칙이어야 한다. 그래야 이 도구가 구성 요소의 기록을 다시 만들 수 있고, 비교표가 구성 요소의
표와 같은 자로 잰 것이 된다. 이 시험은 세 구성 요소의 정규식이 `score.PATTERN`과 글자 그대로 같은지 소스에서
확인한다. 구성 요소 한 곳이 이 정규식을 바꾸면 이 시험이 실패해서, 비교표를 다시 보게 만든다.

읽는 것은 세 구성 요소의 소스 글뿐이다(코드를 불러오지 않고, 어떤 파일도 고치지 않는다).
"""

from pathlib import Path

from asr_compare import score

# 이 파일은 <저장소>/evaluation/asr/tests/ 아래에 있다. parents[0] = tests, [1] = asr, [2] = evaluation,
# [3] = 저장소 뿌리.
REPOSITORY = Path(__file__).resolve().parents[3]

COMPONENT_FILES = (
    "whisper-ko-ft/src/whisper_ko_ft/text_norm.py",
    "stt-scratch/src/stt_scratch/text.py",
    "voice-translator/backend/eval/text_norm.py",
)


def test_the_three_components_normalise_the_same_way():
    literal = f're.compile(r"{score.PATTERN}")'
    for relative in COMPONENT_FILES:
        text = (REPOSITORY / relative).read_text(encoding="utf-8")
        assert literal in text, (
            f"{relative}에 {literal}가 없다. 구성 요소의 채점 정규화가 바뀌었다면 "
            "이 도구의 규칙과 비교표를 다시 보아야 한다."
        )
