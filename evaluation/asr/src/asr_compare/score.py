"""채점 규칙: 정규화, 글자 단위 편집 거리와 합산, 다시 뽑기 번호와 95% 구간.

정규화(`PATTERN`, `normalize`)
    채점 전에 정답과 가설 양쪽에 똑같이 거는 정규화다.

    왜 구성 요소의 규칙을 그대로 옮겼나
        whisper-ko-ft(`whisper-ko-ft/src/whisper_ko_ft/text_norm.py`),
        stt-scratch(`stt-scratch/src/stt_scratch/text.py`),
        voice-translator(`voice-translator/backend/eval/text_norm.py`)의 한국어 채점 정규화는 같은 정규식과
        같은 순서를 쓴다. 이 도구가 그 규칙과 한 글자라도 다르면, 구성 요소가 기록한 값을 이 도구로 다시
        만들 수 없고 이 도구가 내는 비교표도 구성 요소의 표와 같은 자로 잰 것이 아니게 된다. 그래서 새
        규칙을 만들지 않고 같은 규칙을 한 곳(여기)에만 둔다.

    왜 공백까지 모두 지우나
        한국어 글자 오류율은 공백을 뺀 글자로 잰다(띄어쓰기 차이는 인식 오류가 아니라 표기 차이다). 또
        voice-translator의 리포트는 정답과 가설을 이미 정규화한 글(공백이 없다)로만 저장해서, 공백을 남기는
        채점으로는 세 구성 요소를 같은 자로 견줄 수 없다. 공백을 뺀 글자 오류율만 모두에게 성립한다.

글자 오류율(`edit_count`, `counts`, `totals`)
    정답과 가설을 `normalize`로 맞춘 뒤 글자 단위 편집 거리(치환·삭제·삽입의 비용이 모두 1)를 센다. 묶음의
    글자 오류율은 발화마다 센 편집 수의 합을 정규화한 정답 글자 수의 합으로 나눈 것이다. 발화별 비율의
    평균이 아니라서 긴 발화가 글자 수만큼 더 반영된다. 편집 거리의 정의는 하나뿐이라 표준 라이브러리로 직접
    짠다(이 도구의 환경에 채점 패키지를 들이지 않으려는 것이다).

95% 구간(`resample_indices`, `interval`)
    발화를 다시 뽑는 부트스트랩이다. 발화 n개에서 n개를 되돌려 뽑는 일을 1,000번 하고, 뽑을 때마다 글자
    오류율(짝이면 두 묶음의 글자 오류율의 차이)을 낸 뒤, 정렬한 값의 아래에서 25번째와 975번째를 구간으로
    쓴다. 뽑는 번호는 모든 묶음과 모든 짝이 같은 것을 쓴다(`report`가 한 번 만들어 나눠 쓴다). 그래서 짝의
    차이 구간은 같은 발화 표본에서 낸 두 글자 오류율의 차이의 분포가 된다.

    난수는 `random.Random(SEED)`의 `random()`만 쓴다. 같은 시드에서 같은 수열을 낸다고 파이썬 문서가
    보장하는 것은 이것뿐이고, `randrange`·`shuffle`·`sample` 같은 것은 파이썬 판에 따라 수열이 달라질 수
    있다. 구성 요소가 기록한 구간은 난수 생성기가 달라서 이 구간과 자릿수까지 같지는 않다.
"""

import random
import re
from collections.abc import Iterable

# 공백으로 바꿀 글자: 글자·숫자·공백·작은따옴표가 아닌 모든 것(`[^\w\s']`), 그리고 밑줄(`|_`). `\w`는 한글도
# 포함해서 한글은 지워지지 않는다. 밑줄은 `\w`에 들지만 문장부호로 다루려고 따로 넣었다. 작은따옴표는 이
# 식에서 제외돼 남지만, 한국어에서는 인용 부호이므로 normalize가 곧바로 공백으로 바꾼다.
PATTERN = r"[^\w\s']|_"

# 모듈을 불러올 때 한 번만 컴파일한다.
_PUNCTUATION = re.compile(PATTERN)

# 다시 뽑기의 횟수와 시드. 95% 구간은 이 횟수로 뽑은 값의 정렬한 25번째와 975번째라서, 횟수를 바꾸면
# `interval`도 함께 바뀌어야 한다.
RESAMPLES = 1000
SEED = 0


def normalize(text: str) -> str:
    """정답이나 가설 한 줄을 채점용 글자열로 바꾼다. 같은 함수를 정답과 가설 양쪽에 써야 표기 차이가 상쇄된다.

    순서는 세 구성 요소의 코드와 같다: 소문자로 바꾸고 → `PATTERN`에 맞는 글자를 공백으로 바꾸고 →
    작은따옴표도 공백으로 바꾼 뒤 → 모든 공백(유니코드 공백 포함)을 지운다. 그래서 "It's 15m, OK!"는
    "its15mok"가 되고, "책상 위 '빨간' 연필"은 "책상위빨간연필"이 된다.

    입력: 원문 한 줄. 출력: 공백이 없는 글자열(빈 글이면 빈 글자열).
    주의: 유니코드 정규화(NFC 등)는 하지 않는다. 세 구성 요소도 하지 않으므로, 풀어 쓴 한글 자모는 풀어 쓴
    채 남는다. 숫자 표기 ("이백만"과 "2,000,000")도 바꾸지 않는다.
    """
    text = _PUNCTUATION.sub(" ", text.lower())
    return "".join(text.replace("'", " ").split())


def edit_count(reference: str, hypothesis: str) -> int:
    """두 글자열의 글자 단위 편집 거리(치환·삭제·삽입의 비용이 모두 1)를 돌려준다.

    입력은 이미 정규화한 글자열이라고 본다(이 함수는 정규화하지 않는다. 정규화까지 하는 것은 `counts`다).
    이 함수는 두 글자열에 대해 대칭이다.

    구현: 앞과 뒤에서 같은 글자를 먼저 걷어 낸다. 걷어 내도 편집 거리는 달라지지 않고, 가설이 정답과 대체로
    비슷한 이 도구의 입력에서는 셀 칸이 크게 줄어든다. 남은 가운데는 두 줄짜리 표(앞 줄, 지금 줄)로 센다.
    """
    start = 0
    shortest = min(len(reference), len(hypothesis))
    while start < shortest and reference[start] == hypothesis[start]:
        start += 1
    reference_end, hypothesis_end = len(reference), len(hypothesis)
    while (
        reference_end > start
        and hypothesis_end > start
        and reference[reference_end - 1] == hypothesis[hypothesis_end - 1]
    ):
        reference_end -= 1
        hypothesis_end -= 1
    reference, hypothesis = reference[start:reference_end], hypothesis[start:hypothesis_end]
    if not reference:
        return len(hypothesis)
    if not hypothesis:
        return len(reference)

    previous = list(range(len(hypothesis) + 1))
    for row, reference_char in enumerate(reference, start=1):
        current = [row]
        for column, hypothesis_char in enumerate(hypothesis, start=1):
            # 칸 하나는 세 길 가운데 가장 싼 것이다: 정답의 글자를 지운다, 가설에 글자를 끼워
            # 넣는다, 글자 하나를 바꾼다(같은 글자면 비용 0).
            deleted = previous[column] + 1
            inserted = current[column - 1] + 1
            replaced = previous[column - 1] + (reference_char != hypothesis_char)
            current.append(min(deleted, inserted, replaced))
        previous = current
    return previous[-1]


def counts(reference: str, hypothesis: str) -> tuple[int, int]:
    """발화 하나의 (편집 수, 정규화한 정답 글자 수)를 돌려준다. 정답과 가설을 모두 `normalize`한 뒤 센다.

    정규화한 정답이 빈 글이면 ValueError다. 글자 오류율의 분모가 0이 되는 발화이고, 0이나 빈 값으로 메워
    조용히 넘어가면 합과 비율이 틀리기 때문이다.
    """
    normalized = normalize(reference)
    if not normalized:
        raise ValueError("정규화한 정답이 빈 글이다(글자 오류율의 분모가 0이 된다)")
    return edit_count(normalized, normalize(hypothesis)), len(normalized)


def totals(rows: Iterable[tuple[str, str]]) -> tuple[int, int]:
    """(정답, 가설) 쌍들의 편집 수 합과 정규화한 정답 글자 수 합을 돌려준다.

    합은 줄 차례대로 더한다(정수라서 차례와 상관없이 같다). 정답이 빈 행이 있으면 ValueError다(`counts`). 쌍이
    하나도 없으면 (0, 0)이다. 비율은 이 함수가 내지 않는다(분모가 0일 수 있어서 부르는 쪽이 정한다).
    """
    edits = 0
    length = 0
    for reference, hypothesis in rows:
        row_edits, row_length = counts(reference, hypothesis)
        edits += row_edits
        length += row_length
    return edits, length


def resample_indices(count: int) -> list[list[int]]:
    """부트스트랩의 다시 뽑기 번호를 만든다: 번호 count개를 되돌려 뽑는 일을 `RESAMPLES`번 한다.

    번호는 0부터 count-1까지다. `random.Random(SEED)`로 `int(rng.random() * count)`를 count개씩 차례로
    뽑는다. 호출할 때마다 같은 결과다(전역 난수 상태와 상관없다). 한 번 만들어 모든 묶음과 모든 짝이 같은
    번호를 쓰게 하는 것은 부르는 쪽(`report`)의 일이다.
    """
    rng = random.Random(SEED)
    return [[int(rng.random() * count) for _ in range(count)] for _ in range(RESAMPLES)]


def interval(values: list[float]) -> tuple[float, float]:
    """다시 뽑기마다 낸 값 `RESAMPLES`개의 95% 구간을 돌려준다.

    정렬한 값의 아래에서 25번째와 975번째(1부터 센다)다.

    값이 `RESAMPLES`개가 아니면 ValueError다. 25번째와 975번째가 95% 구간인 것은 1,000개일 때뿐이고, 다른
    개수를 조용히 받아 엉뚱한 구간을 내지 않으려는 것이다. 입력 목록은 고치지 않는다(정렬한 사본을 쓴다).
    """
    if len(values) != RESAMPLES:
        raise ValueError(f"다시 뽑기 값이 {RESAMPLES}개여야 한다(받은 것 {len(values)}개)")
    ordered = sorted(values)
    return ordered[24], ordered[974]
