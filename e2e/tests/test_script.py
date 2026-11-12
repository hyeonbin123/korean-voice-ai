"""통화 대본(call-e2e-script/1) 읽기와 검사 시험.

저장소에 들어 있는 실제 대본(calls/shop-cancel.json)이 읽히는지, 서비스 한도를 넘거나 모양이 틀린 대본이
모두 ScriptError로 거절되는지, 한도의 경계값(40개·1,000자·32자·40자)이 한 글자 차이로 갈리지 않고 포함되는지를
고정한다. 거절 시험은 오류 글에 틀린 항목의 이름이 들어 있는지도 본다: 엉뚱한 이유로 거절돼도 통과하는 시험을
막으려는 것이다.
"""

import hashlib
import json
from pathlib import Path

import pytest

from call_e2e.script import CallScript, ScriptError, load_script, script_sha256

E2E_DIR = Path(__file__).resolve().parents[1]
SHOP_CANCEL = E2E_DIR / "calls" / "shop-cancel.json"


def valid_script() -> dict:
    """모든 검사를 통과하는 대본 사전. 시험마다 새로 만들어 한 시험의 수정이 다른 시험에 번지지 않게 한다."""
    return {
        "format": "call-e2e-script/1",
        "call_id": "shop-cancel",
        "title": "주문 하나를 취소하는 통화",
        "domain": "shop",
        "customer_turns": ["안녕하세요, 주문을 취소하려고요.", "O-90005 주문 취소해 주세요."],
        "expect": {
            "tool_calls": [["find_customer", True], ["cancel_order", True]],
            "session_status": "open",
            "summary_model": "offline:canned",
        },
    }


def write_script(tmp_path: Path, data: object) -> Path:
    """대본 사전을 UTF-8(BOM 없음)·LF JSON 파일로 쓰고 경로를 돌려준다."""
    path = tmp_path / "script.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8", newline="\n")
    return path


def test_shop_cancel_script_loads():
    script = load_script(SHOP_CANCEL)
    assert isinstance(script, CallScript)
    assert script.call_id == "shop-cancel"
    assert script.title == "주문 하나를 취소하는 통화"
    assert script.domain == "shop"
    assert script.customer_turns == (
        "안녕하세요, 주문을 취소하려고요.",
        "정예준이고 010-0000-9005입니다.",
        "O-90005 주문 취소해 주세요.",
    )
    assert script.expect_tool_calls == (("find_customer", True), ("cancel_order", True))
    assert script.expect_session_status == "open"
    assert script.expect_summary_model == "offline:canned"


def test_loaded_script_is_immutable():
    script = load_script(SHOP_CANCEL)
    with pytest.raises(AttributeError):
        script.domain = "telecom"  # type: ignore[misc]


# (이름, 대본을 망가뜨리는 함수, 오류 글에 들어 있어야 하는 항목 이름). 앞의 여덟은 서비스 쪽 한도와 대본
# 형식이 정한 거절 사유이고, 나머지는 빠진 키·잘못된 자료형·경계 밖 값이다.
BAD_SCRIPTS = [
    ("unknown_key", lambda d: d.update(extra=1), "extra"),
    ("wrong_format", lambda d: d.update(format="call-e2e-script/2"), "format"),
    ("no_customer_turns", lambda d: d.update(customer_turns=[]), "customer_turns"),
    ("41_customer_turns", lambda d: d.update(customer_turns=["안녕하세요"] * 41), "customer_turns"),
    ("1001_char_turn", lambda d: d.update(customer_turns=["가" * 1001]), "customer_turns"),
    ("blank_turn", lambda d: d.update(customer_turns=["안녕하세요", "   "]), "customer_turns"),
    ("unpaired_tool_expectation", lambda d: d["expect"].update(tool_calls=[["find_customer"]]), "tool_calls"),
    ("session_status_done", lambda d: d["expect"].update(session_status="done"), "session_status"),
    ("unknown_expect_key", lambda d: d["expect"].update(extra=1), "extra"),
    ("missing_call_id", lambda d: d.pop("call_id"), "call_id"),
    ("missing_title", lambda d: d.pop("title"), "title"),
    ("missing_domain", lambda d: d.pop("domain"), "domain"),
    ("missing_customer_turns", lambda d: d.pop("customer_turns"), "customer_turns"),
    ("missing_expect", lambda d: d.pop("expect"), "expect"),
    ("missing_expect_tool_calls", lambda d: d["expect"].pop("tool_calls"), "tool_calls"),
    ("missing_expect_session_status", lambda d: d["expect"].pop("session_status"), "session_status"),
    ("expect_not_an_object", lambda d: d.update(expect=["open"]), "expect"),
    ("call_id_with_capital", lambda d: d.update(call_id="Shop-cancel"), "call_id"),
    ("call_id_with_underscore", lambda d: d.update(call_id="shop_cancel"), "call_id"),
    ("call_id_empty", lambda d: d.update(call_id=""), "call_id"),
    ("call_id_41_chars", lambda d: d.update(call_id="a" * 41), "call_id"),
    ("call_id_with_trailing_newline", lambda d: d.update(call_id="shop-cancel\n"), "call_id"),
    ("call_id_not_text", lambda d: d.update(call_id=7), "call_id"),
    ("blank_title", lambda d: d.update(title="  "), "title"),
    ("title_not_text", lambda d: d.update(title=3), "title"),
    ("empty_domain", lambda d: d.update(domain=""), "domain"),
    ("33_char_domain", lambda d: d.update(domain="d" * 33), "domain"),
    ("domain_not_text", lambda d: d.update(domain=1), "domain"),
    ("customer_turns_is_a_string", lambda d: d.update(customer_turns="안녕하세요"), "customer_turns"),
    ("customer_turn_not_text", lambda d: d.update(customer_turns=[1]), "customer_turns"),
    ("tool_calls_is_a_string", lambda d: d["expect"].update(tool_calls="find_customer"), "tool_calls"),
    ("tool_pair_too_long", lambda d: d["expect"].update(tool_calls=[["a", True, "x"]]), "tool_calls"),
    ("tool_pair_is_a_string", lambda d: d["expect"].update(tool_calls=["find_customer"]), "tool_calls"),
    ("tool_name_not_text", lambda d: d["expect"].update(tool_calls=[[1, True]]), "tool_calls"),
    ("tool_name_empty", lambda d: d["expect"].update(tool_calls=[["", True]]), "tool_calls"),
    ("tool_ok_is_text", lambda d: d["expect"].update(tool_calls=[["find_customer", "yes"]]), "tool_calls"),
    ("tool_ok_is_a_number", lambda d: d["expect"].update(tool_calls=[["find_customer", 1]]), "tool_calls"),
    ("session_status_not_text", lambda d: d["expect"].update(session_status=["open"]), "session_status"),
    ("empty_summary_model", lambda d: d["expect"].update(summary_model=""), "summary_model"),
    ("summary_model_not_text", lambda d: d["expect"].update(summary_model=5), "summary_model"),
]


@pytest.mark.parametrize(
    ("mutate", "field"), [(m, f) for _, m, f in BAD_SCRIPTS], ids=[n for n, _, _ in BAD_SCRIPTS]
)
def test_bad_scripts_are_rejected(tmp_path, mutate, field):
    data = valid_script()
    mutate(data)
    with pytest.raises(ScriptError) as info:
        load_script(write_script(tmp_path, data))
    assert field in str(info.value)


@pytest.mark.parametrize(
    "data",
    [
        {"format": "call-e2e-script/2", "scenario": "x", "turns": []},
        {"scenario": "x", "turns": []},
        {},
    ],
    ids=["other_version_with_other_keys", "no_format_with_other_keys", "empty_object"],
)
def test_the_format_is_checked_before_the_keys(tmp_path, data):
    """다른 판의 대본은 키 구성도 달라서, 키부터 검사하면 '모르는 키'라는 엉뚱한 이유로 거절된다.

    format 이름을 먼저 보므로 거절 사유가 format이어야 한다. 위 `BAD_SCRIPTS`의 틀린 format은 키가 모두
    맞는 대본이라, 이 검사 순서가 바뀌어도 통과하기 때문에 키 구성이 다른 대본으로 따로 본다.
    """
    with pytest.raises(ScriptError) as info:
        load_script(write_script(tmp_path, data))
    message = str(info.value)
    assert "format" in message
    assert "모르는 키" not in message
    assert "빠진 키" not in message


def test_limits_are_inclusive(tmp_path):
    """서비스가 받는 한도의 끝값(발화 40개, 발화 1,000자, 업종 32자, 통화 번호 40자)은 통과해야 한다."""
    data = valid_script()
    data["call_id"] = "a" * 40
    data["domain"] = "d" * 32
    data["customer_turns"] = ["가" * 1000] * 40
    script = load_script(write_script(tmp_path, data))
    assert len(script.customer_turns) == 40
    assert all(len(turn) == 1000 for turn in script.customer_turns)
    assert script.call_id == "a" * 40
    assert script.domain == "d" * 32


def test_turn_length_ignores_surrounding_whitespace_but_the_text_is_kept(tmp_path):
    """서버는 앞뒤 공백을 뺀 길이로 한도를 본다. 같은 기준으로 검사하되 글은 파일에 적힌 그대로 둔다."""
    data = valid_script()
    padded = "  " + "가" * 1000 + "\n"
    data["customer_turns"] = [padded]
    script = load_script(write_script(tmp_path, data))
    assert script.customer_turns == (padded,)


def test_summary_model_is_optional(tmp_path):
    data = valid_script()
    del data["expect"]["summary_model"]
    assert load_script(write_script(tmp_path, data)).expect_summary_model is None
    data["expect"]["summary_model"] = None
    assert load_script(write_script(tmp_path, data)).expect_summary_model is None


def test_an_empty_tool_expectation_means_no_tool_call_is_expected(tmp_path):
    data = valid_script()
    data["expect"]["tool_calls"] = []
    assert load_script(write_script(tmp_path, data)).expect_tool_calls == ()


@pytest.mark.parametrize("status", ["open", "handoff", "closed"])
def test_every_session_status_the_service_has_is_accepted(tmp_path, status):
    data = valid_script()
    data["expect"]["session_status"] = status
    assert load_script(write_script(tmp_path, data)).expect_session_status == status


def test_unreadable_files_raise_script_error(tmp_path):
    with pytest.raises(ScriptError):
        load_script(tmp_path / "missing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ScriptError):
        load_script(broken)
    not_utf8 = tmp_path / "not-utf8.json"
    not_utf8.write_bytes(b'{"format": "\xff"}')
    with pytest.raises(ScriptError):
        load_script(not_utf8)
    with pytest.raises(ScriptError):
        load_script(write_script(tmp_path, ["not", "an", "object"]))


def test_a_file_that_starts_with_a_byte_order_mark_is_rejected(tmp_path):
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(valid_script(), ensure_ascii=False).encode("utf-8"))
    with pytest.raises(ScriptError):
        load_script(path)


def test_script_sha256_hashes_the_file_bytes(tmp_path):
    expected = hashlib.sha256(SHOP_CANCEL.read_bytes()).hexdigest()
    assert script_sha256(SHOP_CANCEL) == expected
    assert len(expected) == 64

    original = write_script(tmp_path, valid_script())
    changed = tmp_path / "changed.json"
    changed.write_bytes(original.read_bytes() + b"\n")
    assert script_sha256(original) != script_sha256(changed)
