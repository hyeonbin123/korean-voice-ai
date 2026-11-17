"""scripts/asr_condition.py 테스트: verbalizer v2 규칙과 캐시 계획. 여기서는 음성 모델을 올리지 않는다.

이 스크립트는 옆 프로젝트(support-agent)의 음성 환경에서 돌지만, 글 규칙과 계획 부분은 이 프로젝트
환경에서도 import할 수 있어야 한다(import할 때 numpy, scipy, support_agent를 쓰지 않는다).
"""

# [테스트 묶음] 음성 조건 데이터를 만드는 scripts/asr_condition.py를 음성 모델 없이 검증한다. (1) 합성에 넘길
# 글을 만드는 규칙(verbalizer v1/v2), (2) 캐시를 보고 새로 합성할 발화를 세는 계획(plan, --dry-run), (3) 음성
# 환경이 캐시와 다르면 전체 재합성을 거절하는 보호, (4) 음성 조건 v3의 1패스(소리 남기기)와 2패스(남긴 소리를
# 다른 인식기로 다시 듣기).
# [왜 중요한가] v1 조건은 운송장번호를 기수와 범위 "에서"로 읽게 한 측정 인공물이 있었다(docs/experiments.md
# "음성 조건 v2"). v2가 운송장번호만 숫자 하나씩 읽고 나머지 발화는 v1과 글자까지 같아야 바뀐 발화만 다시
# 합성하고 v1 결과와 비교할 수 있다. 합성·인식은 GPU 몇 시간짜리라, 다시 돌리기 전에 무엇을 할지 정확히 세는
# 것이 중요하다.

import functools
import importlib.util
import json
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

# 스크립트는 support-agent의 음성 환경에서 도는 독립 파일이라 패키지로 import하지 않고 경로로 읽는다(_load).
# SUPPORT_AGENT는 옆 support-agent 폴더 위치다. 그 폴더가 있고 git이 고정 커밋을 풀 수 있으면 고정한 verbalize
# 사본이 그 커밋의 원본과 바이트까지 같은지 확인한다(아니면 건너뜀. GitHub CI의 얕은 체크아웃에는 그 커밋이
# 없다). CACHE는 기록된 음성 캐시(outputs/는 커밋하지 않으므로 이 PC에만 있다)로, 있으면 고정한 읽기가 기록된
# 발화와 글자까지 같은지 확인한다.
ROOT = Path(__file__).resolve().parents[1]
SUPPORT_AGENT = ROOT.parent / "support-agent"
CACHE = ROOT / "outputs" / "asr" / "cache.jsonl"
# 4단계 인공물이 드러나는 쓴 글과, 고정한 verbalize(support-agent a5717ce)가 v1·v2로 읽는 글. v1 기대값은
# docs/experiments.md "음성 조건 v2"에 적힌 4단계 읽기("육천이백구십일 칠천팔백칠십칠에서 오천백육십팔 로")다.
TRACKING_TEXT = "운송장 번호 6291-7877-5168로 조회"
TRACKING_V1 = "운송장 번호 육천이백구십일 칠천팔백칠십칠에서 오천백육십팔 로 조회"
TRACKING_V2 = "운송장 번호 육이구일, 칠팔칠칠, 오일육팔 로 조회"


# 파일 경로로 모듈을 불러오는 도우미. 스크립트를 불러오는 순간 numpy·scipy·support_agent를 import하면 이
# 환경에서 실패하므로, 불러오기 자체가 그런 의존성 없이 되는지도 함께 확인된다(모듈 docstring).
def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


asr = _load("asr_condition", ROOT / "scripts" / "asr_condition.py")


# 실제 verbalize 대신 공백만 정리하는 가짜. 그래서 아래 기대값은 이 스크립트가 더하는 규칙(운송장번호 읽기)만
# 보여 준다.
def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# v2는 운송장번호(4-4-4자리)를 숫자 하나씩 한글 이름으로, 묶음 사이에 쉼표를 두고 읽는다. 0은 "공"으로
# 읽고(전화번호를 읽는 verbalize와 같은 방식), 전각 숫자도 NFKC로 바꿔 같은 규칙을 적용한다.
@pytest.mark.parametrize(
    "text,spoken",
    [
        ("운송장 번호 6291-7877-5168로 조회할게요", "운송장 번호 육이구일, 칠팔칠칠, 오일육팔 로 조회할게요"),
        ("1000-0203-0040입니다.", "일공공공, 공이공삼, 공공사공 입니다."),
        ("운송장 6291-7877-5168", "운송장 육이구일, 칠팔칠칠, 오일육팔"),
        ("６２９１-７８７７-５１６８요", "육이구일, 칠팔칠칠, 오일육팔 요"),  # 전각 숫자(NFKC)
    ],
)
def test_v2_reads_tracking_numbers_digit_by_digit(text, spoken):
    assert asr.spoken_form(text, squash, "v2") == spoken


# 운송장번호 꼴이 아닌 것은 v2도 손대지 않고 verbalize에 맡겨 v1과 글자까지 같아야 한다: 진짜 범위(3-5일,
# 2~3일), 전화번호, 묶음이 둘·넷인 숫자, 첫 묶음이 다섯 자리인 숫자, 주문·접수번호, 주소 번지. 이 조건이
# 지켜져야 v2에서 다시 합성할 발화가 운송장번호 발화로만 한정된다(규칙: 조건 v2는 이것만 바꾼다).
@pytest.mark.parametrize(
    "text",
    [
        "환불은 3-5일 이내에 됩니다",  # 진짜 범위는 verbalizer가 읽는 그대로 둔다
        "보통 2~3일 걸립니다",
        "010-1234-5678로 연락 주세요",  # 전화번호는 verbalizer가 맡는다
        "1234-5678로",  # 묶음 둘
        "1234-5678-9012-3456요",  # 묶음 넷: 운송장번호 꼴이 아니라 그대로 둔다
        "12345-6789-0123요",
        "주문번호 D3928174, 접수번호 R123456",
        "서울 강남구 역삼동 761-4 입니다",
    ],
)
def test_v2_leaves_everything_else_to_the_verbalizer(text):
    assert asr.spoken_form(text, squash, "v2") == asr.spoken_form(text, squash, "v1") == squash(text)


# v1은 verbalize를 그대로 부른 결과이고, 모르는 verbalizer 이름은 조용히 넘기지 않고 ValueError로 거절한다.
def test_v1_is_the_verbalizer_alone():
    assert asr.spoken_form("6291-7877-5168로", lambda s: f"<{s}>", "v1") == "<6291-7877-5168로>"
    with pytest.raises(ValueError):
        asr.spoken_form("x", squash, "v3")


# --- 고정한 verbalize: v1은 4단계 때의 support-agent 읽기다 ----------------------------------------------
# support-agent는 2026-10-13(877b691)에 운송장번호 읽기를 고쳤다. 스크립트가 그 저장소의 현재 verbalize를
# 부르면 v1이 몰래 v2와 같은 읽기가 되고, v2 키가 캐시에 있어 실행도 멈추지 않는다. 그래서 v1·v2는 4단계 때의
# 파일을 옮긴 사본(scripts/verbalize_a5717ce.py)만 쓴다. 아래 테스트는 이 고정이 CI에서도(support-agent 없이)
# 확인되게 한다.


# 사본의 본문(머리 주석을 뺀 부분)이 support-agent 커밋 a5717ce의 verbalize.py와 같은 git blob인지 확인한다.
# Windows 체크아웃(core.autocrlf)으로 줄바꿈이 CRLF가 되어도 같은 blob으로 계산돼야 한다.
def test_the_pinned_copy_is_the_support_agent_file_at_the_pinned_commit():
    raw = asr.PINNED_VERBALIZE.read_bytes()
    assert asr.git_blob_id(asr.pinned_body(raw)) == asr.PINNED_BLOB
    assert asr.git_blob_id(asr.pinned_body(raw.replace(b"\n", b"\r\n"))) == asr.PINNED_BLOB
    assert asr.pinned_body(raw).startswith(b'"""')  # 원본 첫 줄(모듈 docstring)부터가 본문


# 고정한 verbalize로 v1이 4단계의 인공물(기수와 범위 "에서")을 글자까지 재현하고, v2는 그 v1에서 운송장번호만
# 숫자 하나씩 읽는지 본다. v2의 쉼표 꼴은 verbalize가 전화번호를 읽는 꼴과 같고, 운송장번호가 없는 발화는 v2도
# v1과 글자까지 같다.
def test_v1_is_the_stage4_reading_and_v2_differs_only_in_tracking_numbers():
    verbalize = asr.load_verbalize()
    assert asr.spoken_form(TRACKING_TEXT, verbalize, "v1") == TRACKING_V1
    assert asr.spoken_form(TRACKING_TEXT, verbalize, "v2") == TRACKING_V2
    assert verbalize("010-1234-5678로") == "공일공, 일이삼사, 오육칠팔 로"  # 같은 쉼표 꼴
    for same in ("환불은 3-5일 이내", "2~3일 내로", "주문번호 D3928174요", "38,900원입니다"):
        assert asr.spoken_form(same, verbalize, "v2") == asr.spoken_form(same, verbalize, "v1")


# 실제 실행은 PYTHONPATH에 support-agent/src가 있어 support_agent.voice.verbalize를 import할 수 있다. 그
# 모듈이 다른(고친) 읽기를 하더라도 load_verbalize는 고정 사본을 써야 한다. 여기서는 가짜 모듈을
# sys.modules에 넣어 그 상황을 만든다.
def test_load_verbalize_ignores_the_sibling_verbalizer(monkeypatch):
    fake = types.ModuleType("support_agent.voice.verbalize")
    fake.verbalize = lambda text: "현재 support-agent의 읽기"
    for name in ("support_agent", "support_agent.voice"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "support_agent.voice.verbalize", fake)
    assert asr.load_verbalize()(TRACKING_TEXT) == TRACKING_V1


# 사본의 머리 주석은 바꿔도 되지만, 본문이 한 글자라도 바뀌면 load_verbalize가 멈춘다(SystemExit). v1의 뜻이
# 몰래 바뀌는 것을 막는다.
def test_an_edited_copy_is_refused(tmp_path, monkeypatch):
    raw = asr.PINNED_VERBALIZE.read_bytes()
    copy = tmp_path / "verbalize_a5717ce.py"
    monkeypatch.setattr(asr, "PINNED_VERBALIZE", copy)
    copy.write_bytes(b"# another header note\n" + raw)
    assert asr.load_verbalize()(TRACKING_TEXT) == TRACKING_V1
    copy.write_bytes(raw.replace("에서".encode(), "부터".encode()))
    with pytest.raises(SystemExit, match="a5717ce"):
        asr.load_verbalize()


# 옆 support-agent 폴더가 있고 git이 고정 커밋 a5717ce를 풀 수 있으면, 사본 본문이 그 커밋의
# src/support_agent/voice/verbalize.py와 바이트까지 같은지 git으로 직접 확인한다(출처 확인). 단독 저장소였을
# 때는 옆 폴더의 .git을 조건으로 봤지만, 모노레포에서는 support-agent가 .git 없는 하위 폴더이고 그 이력이 같은
# 저장소에 있어 폴더가 있는지만 본다(git -C로 그 폴더에서 부르면 git이 위로 올라가 같은 저장소를 찾는다).
# <커밋>:<경로>의 경로는 그 커밋 트리의 맨 위 기준이라 support-agent/ 접두 없이 그대로 맞는다. 폴더가 없으면
# 건너뛰고, 폴더가 있어도 git이 그 커밋을 풀지 못하면(GitHub CI의 얕은 체크아웃에는 그 커밋이 없다) 본문에서
# 건너뛴다.
@pytest.mark.skipif(not SUPPORT_AGENT.is_dir(), reason="support-agent is not checked out here")
def test_the_pinned_copy_matches_the_support_agent_history():
    spec = f"{asr.PINNED_COMMIT}:{asr.PINNED_SOURCE}"
    shown = subprocess.run(["git", "-C", str(SUPPORT_AGENT), "cat-file", "blob", spec], capture_output=True)
    if shown.returncode != 0:
        pytest.skip(f"{spec} is not in the local support-agent history")
    assert shown.stdout == asr.pinned_body(asr.PINNED_VERBALIZE.read_bytes())


# 기록된 음성 캐시(키 → 읽은 글, 들린 글)를 한 번만 읽는다.
@functools.cache
def _recorded_cache() -> dict[str, dict]:
    rows = (json.loads(line) for line in CACHE.read_text(encoding="utf-8").splitlines() if line)
    return {row["key"]: row for row in rows}


# 기록된 v1(4단계)·v2 데이터의 모든 발화에서, 각 건의 meta.asr에 남은 음성 환경과 쓴 글(written)로 고정한
# 읽기의 캐시 키를 다시 만들면 캐시에 있고, 캐시의 읽은 글이 글자까지 같고, 캐시의 들린 글이 데이터의 전사와
# 같아야 한다. 즉 지금 스크립트로 다시 돌려도 캐시만으로 기록된 데이터가 그대로 나온다. 캐시가 없으면(CI)
# 건너뛴다.
@pytest.mark.skipif(not CACHE.exists(), reason="no local speech cache (outputs/ is not committed)")
@pytest.mark.parametrize(
    "verbalizer,names",
    [
        ("v1", ["dev-asr", "test-d", "train-half-asr"]),
        ("v2", ["dev-asr-v2", "test-d-v2", "train-half-asr-v2"]),
    ],
)
def test_the_pinned_readings_are_the_recorded_ones(verbalizer, names):
    cache, verbalize = _recorded_cache(), asr.load_verbalize()
    for name in names:
        for line in (ROOT / "datasets" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            meta = dict(item["meta"]["asr"])
            written = meta.pop("written")
            assert meta.pop("verbalizer", "v1") == verbalizer  # 4단계 파일에는 이 필드가 없다
            identity = asr.identity_key(meta)
            for i, (turn, text) in enumerate(zip(item["turns"], written, strict=True)):
                where = (name, item["item_id"], i)
                spoken = asr.spoken_form(text, verbalize, verbalizer)
                if not asr.has_hangul(spoken):
                    assert turn["text"] == "", where  # 소리 없는 발화
                    continue
                key = asr.cache_key(identity, turn["speaker"], asr.seed_of(item["item_id"], i), spoken)
                entry = cache.get(key)
                assert entry is not None, where
                assert entry["spoken"] == spoken and entry["heard"] == turn["text"], where


# 택배 건 하나: 운송장번호가 없는 발화, 있는 발화, "..."(한글이 없어 합성하지 않는 발화).
def _items():
    return [
        {
            "item_id": "dev-parcel-00001",
            "turns": [
                {"speaker": "상담원", "text": "새싹택배입니다."},
                {"speaker": "고객", "text": "운송장 6291-7877-5168로 조회해 주세요."},
                {"speaker": "고객", "text": "..."},  # 읽을 글이 없어 합성하지 않는다
            ],
        }
    ]


# 주어진 음성 환경·verbalizer로 이미 합성했다고 치는 캐시 키 집합을 만든다. 키는 (음성 환경, 화자, 발화 seed,
# 읽는 글)의 해시라, 읽는 글이 같으면 v1과 v2가 같은 키를 쓴다.
def _cache_for(items, identity_key, verbalizer):
    keys = set()
    for item_id, i, speaker, text in asr.utterances(items):
        spoken = asr.spoken_form(text, squash, verbalizer)
        if asr.has_hangul(spoken):
            keys.add(asr.cache_key(identity_key, speaker, asr.seed_of(item_id, i), spoken))
    return keys


# v1 캐시가 있을 때 v2 계획은 읽는 글이 바뀐 운송장번호 발화 하나만 새로 합성하고, 그대로인 발화는 캐시에서
# 가져오며, 소리 없는 발화는 따로 센다. v1로 다시 계획하면 합성할 것이 없다(--dry-run이 보여 주는 수).
def test_plan_after_v1_synthesises_only_the_changed_utterances():
    ident = asr.identity_key({"tts": "melotts/KR", "versions": {"torch": "2.11.0"}})
    v1_cache = _cache_for(_items(), ident, "v1")
    p = asr.plan(_items(), squash, ident, v1_cache, "v2")
    assert p == {
        "utterances": 3,
        "silent": 1,
        "changed": 1,
        "cached": 1,
        "to_synthesise": 1,
        "unchanged_not_cached": 0,
    }
    assert asr.plan(_items(), squash, ident, v1_cache, "v1")["to_synthesise"] == 0


# 음성 환경(여기서는 torch 버전)이 캐시와 다르면 v1과 같게 읽는 발화도 캐시에 없으므로 unchanged_not_cached가
# 0보다 커진다. 이 수가 "환경이 바뀌었다"는 신호다.
def test_plan_flags_a_changed_speech_environment():
    old = asr.identity_key({"tts": "melotts/KR", "versions": {"torch": "2.11.0"}})
    new = asr.identity_key({"tts": "melotts/KR", "versions": {"torch": "2.12.0"}})
    p = asr.plan(_items(), squash, new, _cache_for(_items(), old, "v1"), "v2")
    assert p["unchanged_not_cached"] == 1 and p["to_synthesise"] == 2


# 캐시 키에 verbalizer 이름을 넣지 않는다(키는 음성 환경 + 화자 + seed + 읽는 글, 커밋 82638b5). 그래야 v1과
# 같게 읽는 발화를 v2에서 다시 합성하지 않는다. verbalizer는 각 건의 meta에 남는다.
def test_the_cache_key_does_not_carry_the_verbalizer(tmp_path):
    ident = {"tts": "melotts/KR", "versions": {"torch": "2.11.0"}}
    ch1 = asr.Channel(tmp_path / "c.jsonl", verbalizer="v1", verbalize=squash, identity=ident)
    ch2 = asr.Channel(tmp_path / "c.jsonl", verbalizer="v2", verbalize=squash, identity=ident)
    assert ch1._id == ch2._id == asr.identity_key(ident)
    assert ch2.meta(["원문"]) == {**ident, "verbalizer": "v2", "written": ["원문"]}


# 캐시와 다른 음성 환경으로 실제 실행을 하면 v1과 같게 읽는 발화까지 모두 다시 합성하게 되므로, 스크립트는
# 모델을 올리기 전에 거절하고 종료 코드 2를 돌려야 한다(--allow-full-run 없이는). --dry-run은 계획만 보여 주고
# 0을 돌린다.
# monkeypatch로 음성 환경 정보와 verbalize를 가짜로 바꾸고, 모델 적재 함수가 불리면 실패하게 해 "모델을 올리지
# 않았음"까지 확인한다. 출력 파일도 생기지 않아야 한다.
def test_a_run_refuses_to_resynthesise_unchanged_utterances(tmp_path, monkeypatch, capsys):
    data = tmp_path / "datasets"
    data.mkdir()
    (data / "dev.jsonl").write_text(
        "".join(json.dumps(it, ensure_ascii=False) + "\n" for it in _items()), encoding="utf-8"
    )
    ident = {"tts": "melotts/KR", "versions": {"torch": "2.12.0"}}  # (빈) 캐시를 만든 음성 환경과 다르다
    monkeypatch.setattr(asr, "speech_identity", lambda whisper_model: ident)
    monkeypatch.setattr(asr, "load_verbalize", lambda: squash)

    def no_models(self):
        raise AssertionError("models loaded")

    monkeypatch.setattr(asr.Channel, "_load_models", no_models)
    out, cache = str(tmp_path / "out"), str(tmp_path / "c")
    args = ["--split", "dev", "--data", str(data), "--out", out, "--cache", cache]
    assert asr.main(args + ["--dry-run"]) == 0
    assert asr.main(args) == 2
    assert "unchanged" in capsys.readouterr().err
    assert not (tmp_path / "out" / "dev.jsonl").exists()


# --- 음성 조건 v3: 1패스는 소리를 남기고, 2패스는 남긴 소리를 다시 인식한다 ---------------------------


# v3 싼 관문이 고르는 "번호 발화": 쓴 글에 주문번호(D+7자리)·접수번호(R+6자리)·운송장번호(4-4-4) 꼴이 있는
# 발화만이다(전각 숫자 포함). 전화번호와 날짜는 넣지 않는다(docs/experiments.md 음성 조건 v3 "싼 첫 관문").
def test_identifier_turns_are_the_written_order_receipt_and_tracking_numbers():
    assert asr.says_identifier("주문번호는 D4477838입니다.")
    assert asr.says_identifier("접수번호 R123456요")
    assert asr.says_identifier("운송장 5891-6890-2287의 위치")
    assert asr.says_identifier("６２９１-７８７７-５１６８요")  # 전각 숫자(NFKC)
    assert not asr.says_identifier("010-1234-5678로 연락 주세요")
    assert not asr.says_identifier("11월 29일에 도착합니다")


# 가짜 합성 결과: 읽는 글을 그대로 담은 목록. 아래 가짜 wav_bytes가 이것을 바이트로 바꾸므로 "인식기가 받은
# 바이트"를 글로 확인할 수 있다.
class _FakeAudio(list):
    pass


# 가짜 인식기: 받은 바이트를 기록하고 "들림:<글>"을 돌려준다.
class _FakeListener:
    def __init__(self):
        self.heard: list[bytes] = []

    def transcribe(self, wav: bytes) -> str:
        self.heard.append(wav)
        return "들림:" + wav.decode()


# 모델 없이 도는 Channel을 만든다. _load_models와 _speak를 monkeypatch로 가짜로 바꿔 MeloTTS·faster-whisper를
# 올리지 않는다. cache_rows로 글 캐시(v2 캐시)를 미리 채울 수 있다.
def _fake_channel(tmp_path, monkeypatch, cache_rows=()):
    cache = tmp_path / "c.jsonl"
    cache.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in cache_rows), encoding="utf-8")
    ident = {"tts": "melotts/KR", "versions": {"torch": "2.11.0"}}
    ch = asr.Channel(cache, verbalizer="v2", verbalize=squash, identity=ident)

    def load(self):
        self.speaker, self.listener = object(), _FakeListener()
        self.wav_bytes = lambda audio, rate: type("A", (), {"wav": "".join(audio).encode()})()

    monkeypatch.setattr(asr.Channel, "_load_models", load)
    monkeypatch.setattr(asr.Channel, "_speak", lambda self, spoken, speaker, seed: _FakeAudio(spoken))
    return ch


# 1패스(--keep-audio): 발화마다 다시 합성해 인식기가 받은 WAV 바이트를 그대로 저장하고, index에 키·T의 글·같은
# 키의 글 캐시 값·업종을 한 줄씩 적는지 확인한다. 다른 팔이 모두 이 같은 바이트를 들어야 비교가 공정하다(문서
# "소리" 절).
# 소리 없는 발화도 행을 남기고(wav None), 두 번째 실행은 아무것도 다시 합성하지 않으며(이어 하기), 다시 읽은
# 저장소의 행이 같은지도 본다.
def test_pass_one_keeps_the_heard_audio_and_indexes_every_turn(tmp_path, monkeypatch):
    items = [{**it, "domain": "parcel"} for it in _items()]
    first = asr.spoken_form(items[0]["turns"][0]["text"], squash, "v2")
    key0 = asr.cache_key(
        asr.identity_key({"tts": "melotts/KR", "versions": {"torch": "2.11.0"}}),
        "상담원",
        asr.seed_of("dev-parcel-00001", 0),
        first,
    )
    ch = _fake_channel(tmp_path, monkeypatch, [{"key": key0, "spoken": first, "heard": "예전에 들림"}])
    store = asr.WavStore(tmp_path / "wav")
    n = asr.save_wavs(ch, items, store, "dev")
    assert n == {"synthesised": 2, "silent": 1}
    rows = store.split_rows("dev")
    assert [(r["item_id"], r["turn"]) for r in rows] == [("dev-parcel-00001", i) for i in range(3)]
    assert rows[0]["key"] == key0 and rows[0]["cached_heard"] == "예전에 들림"
    assert rows[0]["heard"] == "들림:" + first and rows[0]["domain"] == "parcel"
    assert (store.root / rows[0]["wav"]).read_bytes() == first.encode()  # 인식기가 받은 바이트
    assert rows[1]["spoken"] == "운송장 육이구일, 칠팔칠칠, 오일육팔 로 조회해 주세요."
    assert rows[2]["wav"] is None and rows[2]["heard"] == "" and rows[2]["audio_seconds"] == 0.0
    # 이어 하기: 두 번째 실행은 아무것도 합성하지 않고, 다시 읽은 저장소의 행도 같다
    assert asr.save_wavs(ch, items, store, "dev") == {"done": 3}
    assert asr.WavStore(tmp_path / "wav").split_rows("dev") == rows


# --only-ids는 번호 발화만 합성해 남기고(싼 관문용), 나중에 전체를 돌리면 이미 남긴 발화는 건너뛰고 나머지만
# 더한다.
def test_pass_one_can_keep_only_identifier_turns(tmp_path, monkeypatch):
    ch = _fake_channel(tmp_path, monkeypatch)
    store = asr.WavStore(tmp_path / "wav")
    items = [{**it, "domain": "parcel"} for it in _items()]
    assert asr.save_wavs(ch, items, store, "dev", only_ids=True) == {"synthesised": 1}
    assert [r["turn"] for r in store.split_rows("dev")] == [1]
    # 나중에 전체를 돌리면 나머지 발화를 더하고 처음 남긴 발화는 그대로 둔다
    assert asr.save_wavs(ch, items, store, "dev") == {"done": 1, "synthesised": 1, "silent": 1}


# 2패스(--recognise): 남긴 WAV마다 한 번씩 인식하고 팔 이름과 함께 가설 파일에 적는다. 맥락을 주면(Th 팔) 그
# 건 업종의 맥락 글이 hotwords로 넘어가고, 맥락이 없는 팔(L)은 None이다. 다시 돌리면 이미 적은 발화는
# 건너뛴다(이어 하기). 소리 없는 발화는 인식하지 않는다.
def test_pass_two_recognises_each_kept_wav_once_with_the_domain_context(tmp_path, monkeypatch):
    ch = _fake_channel(tmp_path, monkeypatch)
    store = asr.WavStore(tmp_path / "wav")
    asr.save_wavs(ch, [{**it, "domain": "parcel"} for it in _items()], store, "dev")
    calls = []

    def transcribe(wav: bytes, hotwords: str | None) -> str:
        calls.append(hotwords)
        return f"{wav.decode()}|{hotwords}"

    hyp = tmp_path / "hyp" / "Th.jsonl"
    context = {"parcel": "새싹택배, 전자레인지"}
    assert asr.recognise(store, "dev", "Th", hyp, transcribe, context) == {"recognised": 2}
    assert calls == ["새싹택배, 전자레인지"] * 2
    rows = [json.loads(line) for line in hyp.read_text(encoding="utf-8").splitlines()]
    assert [(r["item_id"], r["turn"], r["arm"]) for r in rows] == [
        ("dev-parcel-00001", 0, "Th"),
        ("dev-parcel-00001", 1, "Th"),
    ]
    assert rows[0]["heard"].endswith("|새싹택배, 전자레인지")
    assert asr.recognise(store, "dev", "Th", hyp, transcribe, context) == {"done": 2}
    assert asr.recognise(store, "dev", "L", tmp_path / "L.jsonl", transcribe, None) == {"recognised": 2}
    assert calls[-1] is None  # 맥락을 싣는 팔은 Th와 Qc뿐이다


# faster-whisper 팔의 모델과 hotwords 여부가 규칙 표(T: turbo, Th: turbo + 맥락, L: large-v3, N: whisper-ko-ft
# turbo-n 변환본)와 같은지 확인한다.
def test_the_recogniser_arms_and_their_decoding():
    assert set(asr.RECOGNISERS) == {"T", "Th", "L", "N"}
    assert asr.RECOGNISERS["T"] == ("large-v3-turbo", False)
    assert asr.RECOGNISERS["Th"] == ("large-v3-turbo", True)
    assert asr.RECOGNISERS["L"] == ("large-v3", False)
    assert asr.RECOGNISERS["N"][0].replace("\\", "/").endswith("whisper-ko-ft/outputs/turbo-n/ct2")


# 1패스 계획(keep_plan)이 발화 수, 이미 한 것, 소리 없음, 합성할 것, 글 캐시에 키가 있는 것을 세는지 본다.
# 저장소의 음성 환경 기록(identity.json)은 write=False면 쓰지 않고, 다른 환경으로 같은 저장소에 더하려 하면
# SystemExit로 거절한다(서로 다른 음성 환경의 소리를 섞지 않게).
def test_the_pass_one_plan_counts_what_it_would_synthesise(tmp_path, monkeypatch):
    ch = _fake_channel(tmp_path, monkeypatch)
    store = asr.WavStore(tmp_path / "wav")
    items = [{**it, "domain": "parcel"} for it in _items()]
    plan = asr.keep_plan(ch, items, store, only_ids=False)
    assert plan == {"turns": 3, "done": 0, "silent": 1, "to_synthesise": 2, "in_text_cache": 0}
    store.check_identity({"a": 1}, write=False)
    assert not (store.root / "identity.json").exists()
    store.check_identity({"a": 1})
    with pytest.raises(SystemExit):
        store.check_identity({"a": 2}, write=False)
    asr.save_wavs(ch, items, store, "dev", only_ids=True)
    assert asr.keep_plan(ch, items, store, only_ids=True)["done"] == 1


# --- hyp 메타의 출처 기록(_git_commit, _code_trees) --------------------------------------------------------
# 이 스크립트는 support-agent의 음성 환경과 소스(PYTHONPATH=../support-agent/src)로 돌므로, 결과에 영향을 주는
# 코드는 이 구성 요소 폴더와 그 형제 폴더의 코드 경로(src, pyproject.toml, uv.lock)다. hyp 메타의 commit은
# 그 경로들에서 추적 파일이 바뀌었는지만 보고(저장소 전체를 보지 않는다), trees는 두 폴더의 커밋된 내용의 트리
# 해시다(docs/experiments.md "측정 출처를 이 폴더 기준으로"). 아래 시험은 임시 git 저장소에 폴더 둘을 만들어
# scope로 주고 확인한다. 음성 모델, GPU, 네트워크는 쓰지 않는다.

# 임시 저장소의 git 명령마다 주는 설정: 시험용 사용자(커밋에 필요), 줄바꿈 변환 끔(Windows에서 바이트가 바뀌지
# 않게), 서명 끔(서명을 켜 둔 PC에서 시험 커밋이 입력을 기다리며 멈추지 않게). 이 PC나 CI의 전역 설정에 기대지
# 않는다.
_REPO_GIT_CONFIG = ("user.name=t", "user.email=t@t", "core.autocrlf=false", "commit.gpgsign=false")


# 임시 저장소 root에서 git을 실행하고 출력(앞뒤 공백을 뗀 글)을 돌려준다. 실패하면 예외가 나 시험이 멈춘다.
def _repo_git(root: Path, *args: str) -> str:
    options = [part for setting in _REPO_GIT_CONFIG for part in ("-c", setting)]
    done = subprocess.run(["git", *options, *args], cwd=root, check=True, capture_output=True, text=True)
    return done.stdout.strip()


# 파일 하나를 UTF-8·LF로 쓴다(없는 폴더는 만든다. Windows에서 줄바꿈이 바뀌어 시험이 PC마다 달라지지 않게).
def _write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


# 임시 git 저장소 하나에 폴더 둘을 첫 커밋으로 넣고 (저장소 뿌리, scope)를 돌려준다. a/는 이 스크립트가 있는
# 구성 요소 폴더(전체가 코드 경로 ".")를, b/는 형제 폴더를 흉내 낸다. b/의 코드 경로는 src, pyproject.toml,
# uv.lock뿐이고 reports/는 코드 경로가 아니다. scope는 CODE_SCOPE와 같은 꼴이다.
# 주의: pytest의 tmp_path는 이 구성 요소의 .pytest-tmp 아래(진짜 저장소 안의, 추적하지 않는 폴더)다. 그 안에서
# git init한 폴더는 자기 .git이 먼저 잡히므로 진짜 저장소와 섞이지 않는다.
@pytest.fixture
def code_repo(tmp_path):
    repo = tmp_path / "repo"
    files = ("a/x.py", "b/src/y.py", "b/pyproject.toml", "b/uv.lock", "b/reports/r.json")
    for rel in files:
        _write_lf(repo / rel, f"{rel}\n")
    _repo_git(repo, "init", "--quiet")
    _repo_git(repo, "add", *files)
    _repo_git(repo, "commit", "--quiet", "-m", "first")
    scope = ((repo / "a", (".",)), (repo / "b", ("src", "pyproject.toml", "uv.lock")))
    return repo, scope


# 코드 경로 밖의 파일(b/reports/)만 바뀌었거나 추적하지 않는 새 파일만 생겼으면 +dirty가 붙지 않고 커밋 해시
# 그대로다(40자). 전제로, 경로를 한정하지 않고 저장소 전체로 보면 그 변경이 센다는 것을 먼저 확인한다:
# 그렇지 않으면 이 시험은 범위를 좁히지 않아도 통과한다. 추적하지 않는 파일은 코드 경로 안이어도 세지
# 않는다(예전과 같다, --untracked-files=no). 전제를 만드는 status는 추적하지 않는 파일을 세는
# 옵션(--untracked-files=normal)을 명시해, 사용자의 전역 설정(status.showUntrackedFiles)에 기대지 않는다.
def test_commit_is_clean_when_only_unlisted_paths_change(code_repo):
    repo, scope = code_repo
    head = _repo_git(repo, "rev-parse", "HEAD")
    assert len(head) == 40 and asr._git_commit(scope) == head  # 처음에는 깨끗하다
    _write_lf(repo / "b" / "reports" / "r.json", "changed\n")
    assert _repo_git(repo, "status", "--porcelain", "--untracked-files=no") != ""  # 전제: 전체로 보면 센다
    assert asr._git_commit(scope) == head
    _write_lf(repo / "b" / "src" / "new.py", "untracked\n")
    counted = _repo_git(repo, "status", "--porcelain", "--untracked-files=normal", "--", "b/src")
    assert counted != ""  # 전제: 추적하지 않는 파일까지 세면 센다
    assert asr._git_commit(scope) == head


# 코드 경로의 추적 파일이 바뀌면 +dirty로 끝난다. 형제 폴더의 코드 경로(src, pyproject.toml, uv.lock)와 이
# 구성 요소 폴더의 파일 모두 센다. 되돌리면 다시 깨끗하다(+dirty는 그때그때의 작업 트리 상태다).
def test_commit_is_dirty_when_sibling_code_changes(code_repo):
    repo, scope = code_repo
    head = _repo_git(repo, "rev-parse", "HEAD")
    for rel in ("b/src/y.py", "b/pyproject.toml", "b/uv.lock", "a/x.py"):
        original = (repo / rel).read_text(encoding="utf-8")
        _write_lf(repo / rel, original + "changed\n")
        assert asr._git_commit(scope) == head + "+dirty", rel
        _write_lf(repo / rel, original)
        assert asr._git_commit(scope) == head, rel


# trees는 폴더 이름을 키로, 그 폴더의 커밋된 내용의 트리 해시(git rev-parse HEAD:<폴더>)를 값으로 하고 scope의
# 순서를 지킨다. 다른 폴더만 고친 커밋으로는 이 폴더의 트리가 그대로이고, 커밋하지 않은 변경은 가리키지 않는다
# (그것은 +dirty가 본다).
def test_trees_name_each_folder(code_repo):
    repo, scope = code_repo
    trees = asr._code_trees(scope)
    assert trees == {"a": _repo_git(repo, "rev-parse", "HEAD:a"), "b": _repo_git(repo, "rev-parse", "HEAD:b")}
    assert list(trees) == ["a", "b"] and all(len(tree) == 40 for tree in trees.values())
    _write_lf(repo / "a" / "x.py", "changed but not committed\n")
    assert asr._code_trees(scope) == trees  # 커밋하지 않은 변경은 트리 해시에 나타나지 않는다
    _repo_git(repo, "add", "a/x.py")
    _repo_git(repo, "commit", "--quiet", "-m", "change a")
    after = asr._code_trees(scope)
    assert after["a"] == _repo_git(repo, "rev-parse", "HEAD:a") != trees["a"]
    assert after["b"] == trees["b"]  # a/만 고친 커밋이라 b/의 트리는 그대로다


# git이 읽지 못하면 지금까지의 표시가 그대로다: commit은 "?"이고 trees의 값은 모두 None이다(null로 기록된다).
# 저장소가 아닌 폴더 만들기: tmp_path는 이 구성 요소의 .pytest-tmp 아래라 진짜 저장소 안에 있다. 그래서 .git이
# 없는 보통 폴더라도 git이 위 폴더로 올라가며 바깥의 진짜 저장소를 찾아 성공해 버린다.
# GIT_CEILING_DIRECTORIES에 그 폴더의 부모를 주면 git이 그 폴더에서 위로 올라가지 않으므로, .git이 없는 이
# 폴더는 저장소가 아닌 것이 된다. 이 전제가 어긋나면(git이 위로 올라가면) 시험이 아무것도 확인하지 못한 채
# 통과하지 않도록 먼저 단언한다.
# 형제 폴더가 없을 때도 같다(이 스크립트는 그 폴더 없이는 돌지 못한다). 이때 이 구성 요소 폴더의 트리는
# 읽힌다.
def test_outside_a_repository_the_old_markers_stay(code_repo, tmp_path, monkeypatch):
    repo, _ = code_repo
    plain = {name: tmp_path / name for name in ("plain_a", "plain_b")}
    for folder in plain.values():
        folder.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    for folder in plain.values():
        found = subprocess.run(["git", "rev-parse", "HEAD"], cwd=folder, capture_output=True, text=True)
        assert found.returncode != 0, "premise failed: git found a repository above the plain folder"
    outside = tuple((folder, (".",)) for folder in plain.values())
    assert asr._git_commit(outside) == "?"
    assert asr._code_trees(outside) == {"plain_a": None, "plain_b": None}
    missing = ((repo / "a", (".",)), (repo / "no-such-folder", ("src",)))
    assert asr._git_commit(missing) == "?"
    assert asr._code_trees(missing) == {"a": _repo_git(repo, "rev-parse", "HEAD:a"), "no-such-folder": None}


# 폴더가 작업 트리에는 있는데 HEAD에는 없으면(저장소 안의 추적하지 않는 폴더: 형제 폴더를 따로 받아 둔
# 사본이나 가상환경 폴더를 가리킨 경우) 그 폴더로 한정한 status는 늘 빈 글이다. 그래서 status만 보면 읽지
# 못한 것이 깨끗한 것처럼 보여 맨 해시가 나온다. commit은 scope의 폴더마다 HEAD에 있는 폴더인지도 봐서 "?"를
# 낸다(패키지 쪽 공식 검사가 같은 까닭으로 같은 확인을 한다, docs/experiments.md "측정 출처를 이 폴더
# 기준으로"의 덧붙임). 그 폴더가 첫째여도 둘째여도 같다. trees는 그 폴더만 None이다. 전제로, 그 폴더로
# 한정한 status가 빈 글이고 HEAD:./가 풀리지 않는다는 것을 먼저 단언한다. 대조로, 같은 저장소의 커밋된
# 폴더만 주면 맨 해시가 나온다.
def test_a_folder_missing_from_head_gives_the_old_marker(code_repo):
    repo, scope = code_repo
    loose = repo / "loose"
    _write_lf(loose / "src" / "z.py", "not committed\n")
    assert _repo_git(loose, "status", "--porcelain", "--untracked-files=no", "--", "src") == ""  # 전제
    found = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD:./"], cwd=loose, capture_output=True, text=True
    )
    assert found.returncode != 0, "premise failed: HEAD:./ resolves in a folder that is not committed"
    assert asr._git_commit(scope) == _repo_git(repo, "rev-parse", "HEAD")  # 대조
    loose_second = ((repo / "a", (".",)), (loose, ("src",)))
    loose_first = ((loose, (".",)), (repo / "b", ("src", "pyproject.toml", "uv.lock")))
    assert asr._git_commit(loose_second) == "?"
    assert asr._git_commit(loose_first) == "?"
    assert asr._code_trees(loose_second) == {"a": _repo_git(repo, "rev-parse", "HEAD:a"), "loose": None}


# git 실행 파일을 찾지 못해도(압축 파일로 받은 사본, git이 없는 컨테이너) 지금까지의 표시가 그대로다:
# commit은 "?"이고 trees의 값은 모두 None이다. PATH를 빈 폴더로 바꿔 git을 못 찾게 하고, 전제로 정말 못
# 찾는지 먼저 단언한다(git이 있는데 이 시험이 통과하는 일이 없게). shutil은 이 파일 위쪽 import 묶음에
# 없고, 그 묶음에 줄을 더하면 다른 문서가 줄 번호로 가리키는 33행이 밀리므로 함수 안에서 불러온다.
def test_without_git_the_old_markers_stay(code_repo, tmp_path, monkeypatch):
    import shutil

    _, scope = code_repo
    no_git = tmp_path / "bin-without-git"
    no_git.mkdir()
    monkeypatch.setenv("PATH", str(no_git))
    assert shutil.which("git") is None, "premise failed: git is still on PATH"
    assert asr._git_commit(scope) == "?"
    assert asr._code_trees(scope) == {"a": None, "b": None}


# 기본 scope(CODE_SCOPE)는 이 스크립트가 있는 구성 요소 폴더 전체와 형제 support-agent의 코드 경로다. 폴더는
# 프로세스의 작업 폴더가 아니라 스크립트 파일의 위치로 잡는다(scripts/에서 하나 위가 이 구성 요소 폴더, 둘
# 위가 저장소 뿌리). 기본값이 저장소 뿌리로 잘못 잡히면 +dirty가 다시 저장소 전체를 보게 된다. 인자 없이
# 부르는 기존 호출(run_pass_two가 하는 꼴)도 돈다: 이 PC의 실제 저장소 상태에 기대지 않고 결과의 꼴만 본다.
# 이 호출은 진짜 저장소의 git을 부르므로, 다른 git 명령과 색인 잠금을 다투지 않게 선택적 잠금을 끈다.
# 마지막에는 작업 폴더를 다른 곳으로 옮긴 뒤 스크립트를 새로 읽어도 기본 범위가 같은지 본다(pytest는 늘 이
# 구성 요소 폴더에서 돌아 작업 폴더가 ROOT와 같으므로, 이렇게 옮기지 않으면 범위를 작업 폴더로 잡는 실수가
# 시험에 드러나지 않는다).
def test_default_scope_is_this_folder_and_the_sibling_code(monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    script = (ROOT / "scripts" / "asr_condition.py").resolve()
    assert asr.CODE_SCOPE == (
        (script.parents[1], (".",)),
        (script.parents[2] / "support-agent", ("src", "pyproject.toml", "uv.lock")),
    )
    # 위 식과는 따로, 이 시험 파일의 위치에서 잡은 폴더와도 같다
    assert asr.CODE_SCOPE[0][0] == ROOT and asr.CODE_SCOPE[1][0] == SUPPORT_AGENT
    assert re.fullmatch(r"[0-9a-f]{40}(\+dirty)?|\?", asr._git_commit())
    trees = asr._code_trees()
    assert list(trees) == [folder.name for folder, _paths in asr.CODE_SCOPE]
    assert all(tree is None or re.fullmatch(r"[0-9a-f]{40}", tree) for tree in trees.values())
    monkeypatch.chdir(tmp_path)
    assert _load("asr_condition_elsewhere", script).CODE_SCOPE == asr.CODE_SCOPE


# 메타를 쓰는 두 호출 자리(asr_condition.py의 run_pass_two와 asr_qwen.py의 main)는 음성 모델과 GPU가 있어야
# 돌아서 이 환경에서는 실행하는 시험을 둘 수 없다. 그래서 소스를 ast로 읽어 write_hyp_meta에 넘기는 dict를
# 고정한다: commit 바로 다음 키가 trees이고, 두 값의 호출 꼴이 asr_condition은 기본 범위(두 폴더),
# asr_qwen은 이 폴더만(CODE_SCOPE[:1])이다. 위의 시험들은 두 함수와 기본 범위만 고정하고 이 연결은 보지
# 않으므로, trees 줄이 빠지거나 키 순서가 바뀌거나 asr_qwen이 형제 폴더까지 보게 되어도 다른 시험은 모두
# 통과한 채 기록되는 값만 달라진다. ast는 이 파일 위쪽 import 묶음에 없고, 그 묶음에 줄을 더하면 다른 문서가
# 줄 번호로 가리키는 33행이 밀리므로 함수 안에서 불러온다.
@pytest.mark.parametrize(
    "script,commit_call,trees_call",
    [
        ("asr_condition.py", "_git_commit()", "_code_trees()"),
        ("asr_qwen.py", "_git_commit(CODE_SCOPE[:1])", "_code_trees(CODE_SCOPE[:1])"),
    ],
    ids=["asr_condition", "asr_qwen"],
)
def test_hyp_meta_records_trees_right_after_commit(script, commit_call, trees_call):
    import ast

    tree = ast.parse((ROOT / "scripts" / script).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    writes = [call for call in calls if getattr(call.func, "id", None) == "write_hyp_meta"]
    assert len(writes) == 1  # 메타를 쓰는 자리는 하나다
    metas = [arg for arg in writes[0].args if isinstance(arg, ast.Dict)]
    assert len(metas) == 1  # 메타는 dict 리터럴로 넘긴다
    keys = [key.value for key in metas[0].keys]
    assert len(keys) == len(set(keys))  # 키가 겹치면 뒤의 값이 앞의 값을 덮는다
    at = keys.index("commit")
    assert keys[at + 1] == "trees"
    commit_value, trees_value = metas[0].values[at], metas[0].values[at + 1]
    assert (ast.unparse(commit_value), ast.unparse(trees_value)) == (commit_call, trees_call)
