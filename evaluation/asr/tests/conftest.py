"""합성 고정물 도우미: 실제 저장소와 같은 꼴의 폴더를 pytest 임시 폴더 아래에 만든다.

왜 합성인가
    이 도구가 읽는 실제 재료(구성 요소가 커밋해 둔 리포트 파일)로는 시험하지 않는다. 시험의 기대값을 실제
    파일에서 뽑으면 시험이 도구와 같은 실수를 되풀이할 수 있고, 새 수치를 만들지 않는다는 이 도구의 약속도
    시험에서부터 흔들린다. 그래서 시험은 지어낸 짧은 글로 실제와 같은 꼴의 재료 파일 열아홉 개를 만들어
    쓴다. 글은 random.Random에 고정 시드를 주어 만들므로 시험은 언제나 같은 결과를 낸다.

실제와 같은 꼴이란
    - voice-translator(파일 2개): 최상위가 길이 1인 리스트이고, 정답·가설은 공백과 문장부호를 뺀 정규화된
      글이다.
    - whisper-ko-ft(파일 14개): 발화의 id는 문장 번호이고 같은 문장의 둘째 녹음부터 `<번호>#<n>`이다. 글은
      원문이다. 같은 가설을 가진 형제 리포트(`turbo-n-d1a` 등) 네 개가 이 14개에 들어 있다. 발화마다 `edits`와
      `length`, 파일 앞쪽 `summary`에 `error_rate`를 적고, 값은 그 파일의 글에서 이 파일의 따로 짠 계산으로 센
      것이다(구현의 채점을 쓰지 않는다).
    - stt-scratch(파일 3개): 발화의 id는 `fleurs/test/<문장>/<행>`이고, 파일 안 차례는 행 번호 순이 아니라
      id 글자의 사전순이다. 가설 파일 둘은 CRLF 줄 끝으로 저장돼 있다. 정답은 한글·라틴 문자·숫자·공백만
      남기는 학습용 정규화를 거쳐 있어서, 악센트가 붙은 글자(ó)가 든 정답은 공통 정답과 달라진다.

고정물의 모양(시험이 기대는 성질)
    - 같은 문장을 두 번 녹음한 행이 있다(행 번호가 4로 나눠 2 남는 행이 바로 앞 행과 같은 문장, 같은
      길이다). 같은 문장·같은 길이라서 문장 번호나 길이로는 두 행을 구별할 수 없고, 행 번호로만 구별된다.
    - 모든 행의 가설은 행 번호를 꼬리표로 달아 서로 다른 글이다. 그래서 가설이 엉뚱한 행에 붙으면 글이
      달라진다.
    - 음성 길이는 구성 요소마다 소수 넷째 자리 이하에서만 조금씩 다르게 적혀 있다(소수 둘째 자리로
      반올림하면 같다).
    - 알려진 정답 차이 행에는 악센트가 붙은 낱말이 있고 한글 전용이 아니다. 그런 행은 같은 문장을 다시
      녹음한 행과 겹치지 않는다.

이 파일의 구성
    write_repository(...)가 폴더를 만들고, build_repository 도우미(fixture)가 그 함수를 임시 폴더에 묶어
    시험에 넘긴다. 구현의 sources.SYSTEMS를 가져다 쓰지 않고 파일 목록을 아래에 따로 적는다: 목록이나 경로가
    어긋나면 이 도우미가 만든 폴더를 구현이 읽지 못해 시험이 실패한다(시험과 구현이 같은 실수를 함께 하지
    않게 한다).
"""

import hashlib
import json
import random
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------------------------
# 파일 목록(구현과 따로 적는다)
# ---------------------------------------------------------------------------------------------

VOICE_FILES = {
    "voice-turbo-vad": "voice-translator/backend/eval/reports/stt_t14_test_20260913_055810.json",
    "voice-turbo": "voice-translator/backend/eval/reports/stt_t2_test_20260912_224129_rescored.json",
}
WHISPER_REPORTS = (
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
)
# 같은 가설을 가진 형제 리포트 이름 -> 그 가설을 가진 묶음의 키
TWIN_OF = {
    "turbo-n-d1a": "turbo-n",
    "qwen3-asr-1.7b-fixed": "qwen3-asr-1.7b",
    "qwen3-asr-1.7b-qn-fixed": "qwen3-asr-1.7b-qn",
    "qwen3-asr-1.7b-qn-s050-fixed": "qwen3-asr-1.7b-qn-s050",
}
STT_MANIFEST = "stt-scratch/manifests/test_fleurs.jsonl"
# 재료의 sha256을 적어 두는 파일(저장소 뿌리 기준). 구현의 이름을 가져다 쓰지 않고 따로 적는다.
PINNED_INPUTS = "evaluation/asr/inputs.sha256"
STT_FILES = {
    "stt-scratch-full": "stt-scratch/reports/final/test_fleurs-full.hyps.jsonl",
    "stt-scratch-streaming": "stt-scratch/reports/final/test_fleurs-streaming.hyps.jsonl",
}

# ---------------------------------------------------------------------------------------------
# 지어낸 글
# ---------------------------------------------------------------------------------------------

# 낱말은 흔한 한국어 낱말을 아무렇게나 이어 붙인 것이다. 어느 코퍼스의 문장도 옮겨 적지 않았다.
WORDS = (
    "아침", "시장", "바다", "기차", "도서관", "다리", "골목", "정원", "자전거", "소식",
    "편지", "계절", "노래", "구름", "창문", "약속", "여행", "지도", "손님", "가방",
    "언덕", "마을", "공원", "여름", "겨울", "이야기", "친구", "하늘", "나무", "강",
)  # fmt: skip
# 숫자·라틴 문자·따옴표·문장부호가 든 낱말: 정규화가 실제로 할 일을 하게 한다.
DECORATED_WORDS = ("15분", "'수직'", "OK", "3.5미터", "Wi-Fi")
# 정규화 뒤에도 남는 비한글 글자(ó)가 든 낱말: 알려진 정답 차이 행에만 넣는다.
ACCENTED_WORD = "Córdoba"
# 가설을 일부러 틀리게 만들 때 끼워 넣거나 바꿔 넣는 글자
SYLLABLES = "가나다라마바사아자차카타파하"

# stt-scratch의 정답 정규화: 한글 음절·라틴 문자·숫자·공백이 아닌 글자는 공백으로 바꾸고 공백을 하나로 모은다.
_STT_NON_TEXT = re.compile(r"[^가-힣A-Za-z0-9\s]")


def sentence_text(sentence: int, accented: bool) -> str:
    """문장 번호에서 원문 정답을 만든다.

    같은 문장 번호는 언제나 같은 글이다(같은 문장을 두 번 녹음한 행은 정답이 같다).
    """
    rng = random.Random(f"text:{sentence}")
    words = [rng.choice(WORDS) for _ in range(rng.randint(3, 6))]
    if rng.random() < 0.4:
        words.insert(rng.randrange(len(words) + 1), rng.choice(DECORATED_WORDS))
    if accented:
        words.insert(rng.randrange(len(words) + 1), ACCENTED_WORD)
    return " ".join(words) + rng.choice((".", "?", ","))


def mutate(rng: random.Random, text: str, rate: float) -> str:
    """글자마다 rate 안팎의 확률로 지우거나 바꾸거나 끼워 넣어 틀린 가설을 만든다."""
    out = []
    for char in text:
        roll = rng.random()
        if roll < rate / 3:
            continue
        out.append(rng.choice(SYLLABLES) if roll < 2 * rate / 3 else char)
        if rng.random() < rate / 6:
            out.append(rng.choice(SYLLABLES))
    return "".join(out)


def plain(text: str) -> str:
    """voice-translator가 저장하는 꼴: 소문자로 바꾸고 글자·숫자만 남긴다.

    구현의 정규화를 쓰지 않고 따로 짠 것이다(시험이 구현과 같은 실수를 하지 않게 한다).
    """
    return "".join(char for char in text.lower() if char.isalnum())


def stt_style(text: str) -> str:
    """stt-scratch가 정답으로 저장하는 꼴(구현의 정규화를 쓰지 않는 따로 짠 것)."""
    return " ".join(_STT_NON_TEXT.sub(" ", text).split())


def edit_distance(first: str, second: str) -> int:
    """글자 단위 편집 거리(치환·삭제·삽입 비용 1). 표를 처음부터 끝까지 채우는 가장 단순한 꼴이다.

    구현의 편집 거리(앞뒤 같은 글자를 먼저 걷어 낸다)와 일부러 다르게 짠 것이다. 시험이 기대값을 구현과 같은
    실수로 만들지 않게 한다.
    """
    previous = list(range(len(second) + 1))
    for row, char in enumerate(first, start=1):
        current = [row]
        for column, other in enumerate(second, start=1):
            current.append(
                min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + (char != other))
            )
        previous = current
    return previous[-1]


def own_counts(reference: str, hypothesis: str) -> tuple[int, int]:
    """(편집 수, 정규화한 정답 글자 수): 정답과 가설을 `plain`으로 맞춘 글자열에서 센다."""
    normalized = plain(reference)
    return edit_distance(normalized, plain(hypothesis)), len(normalized)


def sum_counts(counts) -> tuple[int, int]:
    """(편집 수, 글자 수) 쌍들의 합."""
    pairs = list(counts)
    return sum(edits for edits, _ in pairs), sum(length for _, length in pairs)


def make_hypotheses(key: str, references: list[str], seed: int) -> tuple[str, ...]:
    """묶음 하나의 가설: 정답을 묶음마다 다른 정도로 틀리게 하고 행 번호 꼬리표를 붙인다."""
    rng = random.Random(f"hypothesis:{seed}:{key}")
    rate = 0.04 + (len(key) % 7) * 0.02
    return tuple(f"{mutate(rng, reference, rate)} {row}" for row, reference in enumerate(references))


# ---------------------------------------------------------------------------------------------
# 행의 배치
# ---------------------------------------------------------------------------------------------


def layout(count: int, differences: tuple[int, ...]) -> tuple[list[int], list[float]]:
    """행마다 (문장 번호, 음성 길이)를 정한다. 난수를 쓰지 않는 계산이라 크기가 달라도 같은 규칙이다.

    문장 번호 `7 + (행 * 37) % 1993`은 행이 1993보다 작으면 겹치지 않고 숫자 자릿수가 섞여 있어, id를 글자
    순으로 늘어놓으면 행 번호 순과 달라진다. 행 번호를 4로 나눠 2가 남는 행은 바로 앞 행의 문장과 길이를
    그대로 쓴다(같은 문장을 두 번 녹음한 행). 알려진 차이 행이거나 그 행을 베끼게 되는 행은 이 규칙에서
    빼서, 차이 행의 문장이 한 번만 나오게 한다.
    """
    sentences: list[int] = []
    seconds: list[float] = []
    for row in range(count):
        repeats = row >= 2 and row % 4 == 2 and row not in differences and (row - 1) not in differences
        if repeats:
            sentences.append(sentences[row - 1])
            seconds.append(seconds[row - 1])
        else:
            sentences.append(7 + (row * 37) % 1993)
            seconds.append(round(3 + ((row * 53) % 1700) / 100, 2))
    return sentences, seconds


def whisper_ids(sentences: list[int]) -> list[str]:
    """whisper-ko-ft의 id: 문장의 첫 녹음은 `<문장>`, n번째(n >= 2) 녹음은 `<문장>#<n>`."""
    seen: dict[int, int] = {}
    ids = []
    for sentence in sentences:
        seen[sentence] = seen.get(sentence, 0) + 1
        ids.append(str(sentence) if seen[sentence] == 1 else f"{sentence}#{seen[sentence]}")
    return ids


# ---------------------------------------------------------------------------------------------
# 정답표와 폴더 만들기
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Synthetic:
    """합성 저장소 한 벌과, 그것을 만들 때 쓴 정답표(시험이 읽은 결과를 견주는 기준).

    sentences·seconds·references·stt_references·hangul은 행 번호 순이다. hypotheses는 묶음 키(같은 가설을 가진
    형제 리포트의 이름 포함) -> 행 번호 순의 원문 가설이다.
    """

    root: Path
    sentences: tuple[str, ...]
    seconds: tuple[float, ...]
    references: tuple[str, ...]
    stt_references: tuple[str, ...]
    hypotheses: dict[str, tuple[str, ...]]
    hangul: tuple[bool, ...]
    differences: tuple[int, ...]
    # 묶음 키 -> 발화별 (편집 수, 글자 수). 한 번 센 것을 되풀이해 세지 않으려는 저장 자리일 뿐이다(비교에
    # 쓰지 않는다).
    counts_cache: dict[str, list[tuple[int, int]]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    # 재료 열아홉 개의 (경로, sha256), 경로 순. `write_repository`가 채운다. 고정 목록 파일의 내용과 같다.
    pinned_entries: list[tuple[str, str]] = field(default_factory=list, init=False, repr=False, compare=False)

    def stored_texts(self, key: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """묶음의 리포트 파일에 저장된 (정답, 가설) 글. 구성 요소마다 저장하는 꼴이 다르다."""
        hypotheses = self.hypotheses[key]
        if key in VOICE_FILES:
            return tuple(plain(text) for text in self.references), tuple(plain(text) for text in hypotheses)
        if key in STT_FILES:
            return self.stt_references, hypotheses
        return self.references, hypotheses

    def pinned_lines(self) -> list[str]:
        """고정 목록(`inputs.sha256`)의 줄: `<sha256>  <뿌리 기준 경로>`, 경로 순. 줄 끝은 뺀 글이다."""
        return [f"{digest}  {path}" for path, digest in self.pinned_entries]

    def stored_counts(self, key: str) -> list[tuple[int, int]]:
        """묶음의 리포트에 저장된 글로 발화마다 센 (편집 수, 정규화한 정답 글자 수).

        그 구성 요소가 저장한 자기 정답으로 센다(공통 정답이 아니다). 행 번호 순이다. 같은 가설을 가진 형제
        리포트는 그 묶음과 같은 값이다. 한 번 센 값은 되풀이해 세지 않고 저장해 둔다.
        """
        main = TWIN_OF.get(key, key)
        if main not in self.counts_cache:
            references, hypotheses = self.stored_texts(main)
            self.counts_cache[main] = [
                own_counts(reference, hypothesis)
                for reference, hypothesis in zip(references, hypotheses, strict=True)
            ]
        return list(self.counts_cache[main])

    def recorded_values(self) -> dict[str, dict[str, tuple[int, int]]]:
        """묶음 열네 개의 기록값: 자기 정답으로 센 편집 수의 합과 정규화한 정답 글자 수의 합.

        키 차례는 구현의 고정 목록과 같다(voice-translator 둘, whisper-ko-ft 열, stt-scratch 둘). 한글 전용은
        stt-scratch 묶음에만 있다(다른 구성 요소는 기록하지 않는 범위다). 값은 이 파일의 따로 짠 계산으로 센
        것이다.
        """
        values: dict[str, dict[str, tuple[int, int]]] = {}
        for key in (*VOICE_FILES, *WHISPER_REPORTS, *STT_FILES):
            counts = self.stored_counts(key)
            entry = {"all": sum_counts(counts)}
            if key in STT_FILES:
                entry["hangul_only"] = sum_counts(
                    pair for pair, flag in zip(counts, self.hangul, strict=True) if flag
                )
            values[key] = entry
        return values

    def expected_values(self) -> dict[str, dict[str, tuple[int, int]]]:
        """구현의 기록값 사전(`recorded.EXPECTED`)과 같은 꼴의, 이 합성 저장소의 값.

        구현의 사전과 같은 묶음(voice-translator 둘, whisper-large-v3-turbo, stt-scratch 둘)만 담는다. 나머지
        whisper-ko-ft 묶음의 기록은 리포트 파일 안에 있다. 명령줄 시험이 구현의 실제 기록값 대신 끼워 넣는다.
        """
        values = self.recorded_values()
        return {key: values[key] for key in (*VOICE_FILES, "whisper-large-v3-turbo", *STT_FILES)}


def write_text(path: Path, text: str, *, crlf: bool) -> None:
    """글을 UTF-8(BOM 없음)로 쓴다. crlf이면 줄 끝을 CRLF로 바꿔 쓴다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\n", "\r\n") if crlf else text
    path.write_bytes(data.encode("utf-8"))


def jsonl(rows: list[dict]) -> str:
    """사전 목록을 한 줄에 하나씩 적은 JSONL 글로 바꾼다(끝 개행 하나)."""
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def write_repository(
    root: Path,
    *,
    utterances: int = 4,
    hangul_only: int = 2,
    differences: tuple[int, ...] = (3,),
    seed: int = 0,
    line_endings: str = "real",
    stt_order: str = "id",
    pinned: bool = False,
) -> Synthetic:
    """root 아래에 재료 파일 열아홉 개를 실제와 같은 폴더 구조·꼴로 만들고 정답표를 돌려준다.

    utterances            발화 수(행 번호 0 ~ utterances-1). 작게 쓰면 단위 시험용, 382면 실제 크기다.
    hangul_only           한글 전용으로 표시할 행의 수. 알려진 차이 행은 뽑지 않는다.
    differences           stt-scratch의 정답이 공통 정답과 달라지는 행 번호(알려진 정답 차이).
    seed                  가설과 한글 전용 행을 뽑는 시드.
    line_endings          "real"이면 실제처럼 stt-scratch 가설 파일 둘만 CRLF, "lf"면 모두 LF, "crlf"면 모두
                          CRLF.
    stt_order             stt-scratch 파일 안의 줄 차례: "id"(실제와 같은 id 글자 사전순), "row"(행 번호
                          순), "reversed"(id 글자 사전순의 거꾸로). 가설 파일에만 적용하고 매니페스트는
                          언제나 id 순이다.
    pinned                참이면 재료의 sha256을 적어 두는 파일(`evaluation/asr/inputs.sha256`)도 만든다. 그
                          파일은 재료가 아니라서, 재료 파일 열아홉 개만 있기를 기대하는 시험은
                          기본값(거짓)을 쓴다. 명령줄의 `run`·`verify`는 이 파일이 있어야 돌므로 그 시험의
                          고정물은 참으로 만든다.
    """
    if line_endings not in {"real", "lf", "crlf"}:
        raise ValueError(f"line_endings는 real·lf·crlf 가운데 하나여야 한다: {line_endings}")
    if stt_order not in {"id", "row", "reversed"}:
        raise ValueError(f"stt_order는 id·row·reversed 가운데 하나여야 한다: {stt_order}")
    eligible = [row for row in range(utterances) if row not in differences]
    if hangul_only > len(eligible):
        raise ValueError("한글 전용으로 뽑을 수 있는 행(알려진 차이 행 제외)보다 많이 요구했다")

    sentences, seconds = layout(utterances, differences)
    references = [sentence_text(sentences[row], accented=row in differences) for row in range(utterances)]
    stt_references = [stt_style(text) for text in references]
    flagged = set(random.Random(f"hangul:{seed}").sample(eligible, hangul_only))
    hangul = tuple(row in flagged for row in range(utterances))

    main_keys = [*VOICE_FILES, *WHISPER_REPORTS, *STT_FILES]
    hypotheses = {key: make_hypotheses(key, references, seed) for key in main_keys}
    for twin, main in TWIN_OF.items():
        hypotheses[twin] = hypotheses[main]

    all_crlf = line_endings == "crlf"
    hyps_crlf = line_endings in {"real", "crlf"}
    synthetic = Synthetic(
        root=root,
        sentences=tuple(str(sentence) for sentence in sentences),
        seconds=tuple(seconds),
        references=tuple(references),
        stt_references=tuple(stt_references),
        hypotheses=hypotheses,
        hangul=hangul,
        differences=differences,
    )

    # voice-translator: 최상위가 길이 1인 리스트. 읽지 않는 키(elapsed_s, error)의 값은 자리표시다.
    for key, path in VOICE_FILES.items():
        stored_references, stored_hypotheses = synthetic.stored_texts(key)
        items = [
            {
                "id": sentences[row],
                "audio_s": round(seconds[row] + 0.0004, 4),
                "elapsed_s": 0.0,
                "error": 0.0,
                "reference": stored_references[row],
                "hypothesis": stored_hypotheses[row],
            }
            for row in range(utterances)
        ]
        korean = {"metric": "cer", "count": utterances, "items": items}
        english = {"metric": "wer", "count": 0, "items": []}
        document = [{"model": "synthetic", "variant": key, "languages": {"ko": korean, "en": english}}]
        write_text(root / path, json.dumps(document, ensure_ascii=False, indent=2) + "\n", crlf=all_crlf)

    # whisper-ko-ft: 형제 리포트는 같은 가설을 가진 별도 파일이다. 발화마다 edits·length와 summary의
    # error_rate는 그 파일의 글에서 이 파일의 따로 짠 계산으로 센 값이다(실제 리포트가 스스로 적어 두는 값).
    ids = whisper_ids(sentences)
    for name in [*WHISPER_REPORTS, *TWIN_OF]:
        counts = synthetic.stored_counts(name)
        edits_sum, length_sum = sum_counts(counts)
        rows = [
            {
                "id": ids[row],
                "speaker": "synthetic",
                "seconds": seconds[row],
                "reference": references[row],
                "hypothesis": hypotheses[name][row],
                "edits": counts[row][0],
                "length": counts[row][1],
                "has_digit": any(char.isdigit() for char in references[row]),
            }
            for row in range(utterances)
        ]
        summary = {
            "model": "synthetic",
            "set": "fleurs-ko-test",
            "error_rate": round(edits_sum / length_sum, 5),
        }
        document = {"summary": summary, "utterances": rows}
        path = root / f"whisper-ko-ft/reports/{name}/fleurs-ko-test.json"
        write_text(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n", crlf=all_crlf)

    # stt-scratch: id는 문장과 행 번호를 담고, 파일 안 차례는 id 글자의 사전순이다.
    stt_ids = [f"fleurs/test/{sentences[row]}/{row}" for row in range(utterances)]
    by_id = sorted(range(utterances), key=lambda row: stt_ids[row])
    manifest_rows = [
        {
            "id": stt_ids[row],
            "corpus": "fleurs",
            "src_split": "test",
            "speaker": None,
            "duration_s": round(seconds[row] + 0.0002, 6),
            "text": stt_references[row],
            "text_raw": references[row],
            "hangul_only": hangul[row],
        }
        for row in by_id
    ]
    write_text(root / STT_MANIFEST, jsonl(manifest_rows), crlf=all_crlf)
    hyps_order = {"id": by_id, "row": list(range(utterances)), "reversed": by_id[::-1]}[stt_order]
    for key, path in STT_FILES.items():
        rows = [
            {"id": stt_ids[row], "ref": stt_references[row], "hyp": hypotheses[key][row]}
            for row in hyps_order
        ]
        write_text(root / path, jsonl(rows), crlf=hyps_crlf)

    # 재료 고정 목록: 위에서 쓴 재료 열아홉 개를 경로 순으로 적는다(한 줄에 sha256, 공백 둘, 경로). sha256은
    # 줄 끝의 CRLF를 LF로 바꾼 바이트에서 센다(구현의 `digest`를 쓰지 않고 정의를 따로 적는다). 파일은 다른
    # 재료 파일과 같은 줄 끝으로 쓴다.
    material_paths = [
        *VOICE_FILES.values(),
        *(f"whisper-ko-ft/reports/{name}/fleurs-ko-test.json" for name in [*WHISPER_REPORTS, *TWIN_OF]),
        STT_MANIFEST,
        *STT_FILES.values(),
    ]
    entries = sorted(
        (path, hashlib.sha256((root / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest())
        for path in material_paths
    )
    synthetic.pinned_entries.extend(entries)
    if pinned:
        text = "".join(line + "\n" for line in synthetic.pinned_lines())
        write_text(root / PINNED_INPUTS, text, crlf=all_crlf)
    return synthetic


@pytest.fixture
def build_repository(tmp_path):
    """합성 저장소를 만드는 함수를 돌려준다: build(이름, **write_repository의 인자) -> Synthetic.

    폴더는 이 시험의 pytest 임시 폴더 아래 `이름`으로 만들어지므로, 한 시험에서 이름을 달리해 여러 벌을 만들
    수 있다.
    """

    def build(name: str = "repo", **options) -> Synthetic:
        return write_repository(tmp_path / name, **options)

    return build


# 명령줄은 언제나 기본값(382발화, 한글 전용 257, 알려진 차이 행 23·57)으로 검증하므로, 명령줄 시험은 이
# 크기를 쓴다.
FULL_SIZE = {"utterances": 382, "hangul_only": 257, "differences": (23, 57)}


@pytest.fixture(scope="session")
def full_repository(tmp_path_factory) -> Synthetic:
    """실제 크기의 합성 저장소 한 벌. 시험 묶음 전체에서 한 번만 만든다.

    실제처럼 stt-scratch 가설 파일만 CRLF다.
    이 폴더는 고치지 않는다. 고치는 시험은 `copy_repository`로 복사해서 고친다.
    """
    return write_repository(tmp_path_factory.mktemp("full") / "repo", pinned=True, **FULL_SIZE)


@pytest.fixture(scope="session")
def full_repository_crlf(tmp_path_factory) -> Synthetic:
    """`full_repository`와 같은 내용을 모든 재료 파일이 CRLF인 꼴로 만든 것.

    줄바꿈 변환을 켠 채 받은 복제본을 흉내 낸다.
    """
    return write_repository(
        tmp_path_factory.mktemp("full-crlf") / "repo", line_endings="crlf", pinned=True, **FULL_SIZE
    )


@pytest.fixture
def copy_repository(tmp_path):
    """합성 저장소 폴더를 이 시험의 임시 폴더로 복사하는 함수를 돌려준다.

    copy(synthetic, 이름) -> 복사한 폴더.
    """

    def copy(source: Synthetic, name: str = "copy") -> Path:
        destination = tmp_path / name
        shutil.copytree(source.root, destination)
        return destination

    return copy
