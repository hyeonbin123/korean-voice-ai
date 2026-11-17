"""봉인 Zeroth 공식 test 사후 분석(scripts/sealed_breakdown.py) 테스트.

확인하는 성질:
(a) 합성 몇 발화로 whisper 앵커와의 짝 비교 경로(원래 id 순 정렬, 짝 차, 발화·화자 군집 구간, 부분집합)를
    계산하고, 숫자 발화 목록 안·밖 두 부분집합의 편집·글자 합이 전체와 같다.
(b) 결합이 일대일이 아니거나(중복·누락·남는 id) 짝의 정규화 정답이 다르거나(길이가 달라도, 길이는 같고 글자만
    달라도) 숫자 목록에 없는 id가 있으면 계산하지 않고 멈춘다(잘못 이은 짝으로 수치를 내지 않게).
(c) 인자 없는 기본 동작은 그대로다: 학습 문장 여부 분할이 커밋된 reports/final/zeroth_seen_unseen.json과 같고,
    앵커 인자는 둘을 함께 줘야 한다.
(d) 실데이터(data/raw의 Zeroth parquet와 형제 폴더의 whisper-ko-ft 체크아웃)가 있으면: 행 번호 결합이
    일대일(457발화), 두 부분집합 합 = 전체(707 / 19,288), 기대 재현값, 커밋된 결과 파일 재현. 없으면(CI)
    건너뛴다.
(e) 입력 파일 출처(file_provenance)를 임시 git 저장소로 확인한다: commit은 내용을 마지막으로 바꾼
    커밋(옮기기만 한 커밋은 건너뛰고 옮기면서 고친 커밋은 센다), blob은 HEAD의 git blob 해시, 얕은
    복제에서는 commit이 None, HEAD에 없는 파일(추적하지 않거나 무시된 파일, 지웠다 다시 만든 경로)은
    commit·blob이 None에 변경 있음, 파일 이름의 glob 글자는 글자 그대로, git이 안 되면 sha256만 값이 있다.
"""

# [왜 필요한가] 공개 문서가 whisper 제로샷 앵커(4.48 %)와 이 모델(3.67 %)을 나란히 놓는데, Zeroth 정답은
# 숫자를 한글로 풀어 쓰고 whisper는 아라비아 숫자를 내므로 그 표기 차이가 앵커 쪽 오류로 센다. 이 분석은
# 저장된 봉인 가설과 whisper-ko-ft의 발화별 보고서를 같은 발화로 짝지어 숫자 발화를 뺀 부분집합에서 다시
# 비교한다. 두 저장소의 발화 id가 달라(이 저장소는 parquet 행 번호) 결합을 잘못하면 그럴듯하지만 틀린 수치가
# 나오므로 결합 검사를 테스트로 고정한다.
# [방식] scripts/는 패키지가 아니라서 파일 경로로 모듈을 불러온다(tests/test_stage7_guards.py와 같은 방식).

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pytest

from stt_scratch.metrics import cluster_difference_interval, difference_interval, score_ns

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("sealed_breakdown", REPO / "scripts" / "sealed_breakdown.py")
sealed_breakdown = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sealed_breakdown)

# (d)에 쓰는 실데이터 위치: 0단계가 내려받은 Zeroth parquet와, 이 저장소 옆에 체크아웃한 whisper-ko-ft의
# 보고서.
PARQUET_DIR = REPO / "data" / "raw" / "zeroth_korean" / "data"
WHISPER_KO_FT = REPO.parent / "whisper-ko-ft"
ANCHOR = WHISPER_KO_FT / "reports" / "whisper-large-v3-turbo" / "zeroth-test.json"
DIGITS = WHISPER_KO_FT / "reports" / "digit_utterances" / "zeroth-test.json"
REAL = pytest.mark.skipif(
    not (sorted(PARQUET_DIR.glob("test-*.parquet")) and ANCHOR.exists() and DIGITS.exists()),
    reason="needs data/raw Zeroth parquet and a sibling whisper-ko-ft checkout",
)

# (a)·(b)의 합성 발화 6개. 이 저장소 id(행 번호)와 원래 id의 순서를 일부러 다르게 둬 정렬 기준을 시험한다.
# 화자는 3명. 원래 id "103_…"인 발화 둘은 앵커 가설에 아라비아 숫자가 들어 있다.
_ROWS = [
    ("zeroth/test/0", "105_001_0002", "105", "가나다라마", "가나다라마", "가나다라마", False),
    (
        "zeroth/test/1",
        "103_001_0001",
        "103",
        "이천 십 팔 년에 왔다",
        "이천 십 팔 년에 왔다",
        "2018년에 왔다",
        True,
    ),
    ("zeroth/test/2", "104_001_0005", "104", "마바사아", "마바사", "마바사아", False),
    ("zeroth/test/3", "105_001_0001", "105", "아자차카타", "아자차타타", "아자차카", False),
    ("zeroth/test/4", "103_001_0004", "103", "세 시 반", "세 시 반", "3시 반", True),
    ("zeroth/test/5", "104_001_0003", "104", "하나 둘 셋", "하나 둘", "하나 둘 셋", False),
]


# 합성 입력 묶음: 이 저장소 가설 행, 행 번호 → 원래 id, 행 번호 → 화자, 앵커 보고서의 발화 목록.
def _synthetic():
    rows = [{"id": r[0], "ref": r[3], "hyp": r[4]} for r in _ROWS]
    row_to_source = {r[0]: r[1] for r in _ROWS}
    speakers = {r[0]: r[2] for r in _ROWS}
    anchor = [
        {"id": r[1], "speaker": r[2], "reference": r[3], "hypothesis": r[5], "has_digit": r[6]} for r in _ROWS
    ]
    return rows, row_to_source, speakers, anchor


# (a) 짝 비교 경로: 원래 id 순으로 정렬되고, 비율·짝 차가 손으로 센 값과 같고, 구간이 같은 순서의 배열에 등록
# 함수(difference_interval)와 군집 함수(화자)를 쓴 값과 같다.
def test_paired_summary_on_synthetic_pairs():
    pairs = sealed_breakdown.pair_with_anchor(*_synthetic())
    assert [p.source_id for p in pairs] == sorted(r[1] for r in _ROWS)
    ours = np.array([score_ns(r[3], r[4]).edits for r in sorted(_ROWS, key=lambda r: r[1])], dtype=np.int64)
    anchor = np.array([score_ns(r[3], r[5]).edits for r in sorted(_ROWS, key=lambda r: r[1])], dtype=np.int64)
    lengths = np.array(
        [score_ns(r[3], r[3]).length for r in sorted(_ROWS, key=lambda r: r[1])], dtype=np.int64
    )
    speakers = [r[2] for r in sorted(_ROWS, key=lambda r: r[1])]

    s = sealed_breakdown.paired_summary(pairs)
    assert s["n"] == 6 and s["speakers"] == 3
    assert (s["edits_ours"], s["edits_anchor"], s["length"]) == (ours.sum(), anchor.sum(), lengths.sum())
    assert math.isclose(s["rate_ours"], ours.sum() / lengths.sum())
    assert math.isclose(s["rate_anchor"], anchor.sum() / lengths.sum())
    assert math.isclose(s["diff_ours_minus_anchor"], s["rate_ours"] - s["rate_anchor"])
    assert s["diff_ci95"]["utterance"] == list(difference_interval(ours, anchor, lengths))
    assert s["diff_ci95"]["speaker"] == list(cluster_difference_interval(ours, anchor, lengths, speakers))


# (a) 부분집합: 숫자 목록(원래 id 두 개) 밖·안, 앵커 가설에 숫자가 든 발화 제외. 목록 안·밖의 편집·글자 합은
# 전체와 같고, 학습 문장 분할은 목록 밖 발화만 나눈다.
def test_anchor_notation_subsets_add_up():
    pairs = sealed_breakdown.pair_with_anchor(*_synthetic())
    digit_ids = {"103_001_0001", "103_001_0004"}
    train = {"가나다라마", "마바사아"}
    out = sealed_breakdown.anchor_notation(pairs, digit_ids, train)
    whole, inside, outside = out["all"], out["digit_list"], out["excluding_digit_list"]
    assert (whole["n"], inside["n"], outside["n"]) == (6, 2, 4)
    for key in ("edits_ours", "edits_anchor", "length"):
        assert inside[key] + outside[key] == whole[key]
    assert out["excluding_anchor_digit_hypotheses"]["n"] == 4
    split = out["excluding_digit_list"]["split_by_train_sentence"]
    assert (split["sentence_in_train"]["n"], split["sentence_not_in_train"]["n"]) == (2, 2)


# (b) 결합 실패: 각 경우에 SystemExit로 멈춰야 한다.
def test_join_must_be_one_to_one_with_equal_references():
    rows, row_to_source, speakers, anchor = _synthetic()
    with pytest.raises(SystemExit):  # 앵커 보고서에 같은 id가 두 번
        sealed_breakdown.pair_with_anchor(rows, row_to_source, speakers, anchor + [dict(anchor[0])])
    with pytest.raises(SystemExit):  # 앵커 보고서에 한 발화가 없음
        sealed_breakdown.pair_with_anchor(rows, row_to_source, speakers, anchor[1:])
    with pytest.raises(SystemExit):  # 앵커 보고서에만 있는 발화
        extra = {**anchor[0], "id": "199_001_0001"}
        sealed_breakdown.pair_with_anchor(rows, row_to_source, speakers, anchor + [extra])
    with pytest.raises(SystemExit):  # 두 행 번호가 같은 원래 id로 이어짐
        sealed_breakdown.pair_with_anchor(
            rows, {**row_to_source, "zeroth/test/1": "105_001_0002"}, speakers, anchor
        )
    with pytest.raises(SystemExit):  # 정규화 정답의 길이가 다름
        changed = [dict(a) for a in anchor]
        changed[2]["reference"] = "마바사아자"
        sealed_breakdown.pair_with_anchor(rows, row_to_source, speakers, changed)
    with pytest.raises(SystemExit):  # 길이는 같고 글자가 다름(잘못 이은 짝)
        changed = [dict(a) for a in anchor]
        changed[2]["reference"] = "마바사자"
        sealed_breakdown.pair_with_anchor(rows, row_to_source, speakers, changed)
    with pytest.raises(SystemExit):  # has_digit 표시가 가설 내용과 다름
        changed = [dict(a) for a in anchor]
        changed[0]["has_digit"] = True
        sealed_breakdown.pair_with_anchor(rows, row_to_source, speakers, changed)
    pairs = sealed_breakdown.pair_with_anchor(rows, row_to_source, speakers, anchor)
    with pytest.raises(SystemExit):  # 숫자 목록에 짝에 없는 id가 있음
        sealed_breakdown.anchor_notation(pairs, {"103_001_0001", "999_999_9999"}, set())


# 두 JSON 값이 같은지 비교한다. 실수는 1e-12 안이면 같다고 본다(같은 연산이라 실제로는 비트 단위로 같아야
# 하지만, 커밋된 값은 Windows에서 만든 것이라 다른 플랫폼의 CI에서 부동소수점 끝자리가 흔들려도 깨지지 않게).
def _same(a, b, path="") -> None:
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), path
        for k in a:
            _same(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _same(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert math.isclose(a, b, rel_tol=0.0, abs_tol=1e-12), (path, a, b)
    else:
        assert a == b, (path, a, b)


# (c) 기본 동작: 학습 문장 여부 분할이 커밋된 결과와 같다(리팩터링으로 바뀌지 않았다는 확인).
def test_default_seen_unseen_is_unchanged():
    committed = json.loads(
        (REPO / "reports" / "final" / "zeroth_seen_unseen.json").read_text(encoding="utf-8")
    )
    _same(sealed_breakdown.seen_unseen(), committed)


# (c) 명령행: 인자가 없으면 seen/unseen 파일 하나만 쓰고(내용은 커밋된 것과 같음), 앵커 인자 하나만 주면
# argparse 오류로 멈춘다.
def test_main_without_anchor_arguments(tmp_path):
    sealed_breakdown.main(["--out-dir", str(tmp_path)])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["zeroth_seen_unseen.json"]
    committed = (REPO / "reports" / "final" / "zeroth_seen_unseen.json").read_text(encoding="utf-8")
    written = (tmp_path / "zeroth_seen_unseen.json").read_text(encoding="utf-8")
    _same(json.loads(written), json.loads(committed))
    with pytest.raises(SystemExit):
        sealed_breakdown.main(["--out-dir", str(tmp_path), "--anchor-report", "x.json"])


# (d) 실데이터: 행 번호 결합이 일대일이고 두 부분집합의 합이 봉인 보고 수치(707 / 19,288)와 같으며,
# docs/experiments.md 7단계 결과의 사후 분석에 적은 값(소수 둘째 자리, %·포인트)이 그대로 나온다.
@REAL
def test_real_anchor_notation_reproduces_expected_values():
    result = sealed_breakdown.anchor_analysis(ANCHOR, DIGITS, PARQUET_DIR)
    subsets = result["subsets"]
    whole = subsets["all"]
    assert (whole["n"], whole["edits_ours"], whole["length"]) == (457, 707, 19288)
    for key in ("edits_ours", "edits_anchor", "length"):
        assert subsets["digit_list"][key] + subsets["excluding_digit_list"][key] == whole[key]

    def pct(x: float) -> float:
        return round(x * 100, 2)

    expected = {
        "all": (457, 3.67, 4.48, -0.81, (-1.54, -0.13), (-1.43, -0.20)),
        "excluding_digit_list": (315, 3.69, 3.29, 0.39, (-0.39, 1.25), (-0.21, 1.02)),
        "excluding_anchor_digit_hypotheses": (384, 3.64, 3.17, 0.47, (-0.22, 1.18), (-0.03, 1.01)),
    }
    for name, (n, ours, anchor, diff, utt, spk) in expected.items():
        s = subsets[name]
        assert s["n"] == n, name
        assert (pct(s["rate_ours"]), pct(s["rate_anchor"])) == (ours, anchor), name
        assert pct(s["diff_ours_minus_anchor"]) == diff, name
        assert tuple(pct(x) for x in s["diff_ci95"]["utterance"]) == utt, name
        assert tuple(pct(x) for x in s["diff_ci95"]["speaker"]) == spk, name
    assert subsets["digit_list"]["n"] == 142 and pct(subsets["digit_list"]["rate_ours"]) == 3.63
    split = subsets["excluding_digit_list"]["split_by_train_sentence"]
    assert (split["sentence_in_train"]["n"], pct(split["sentence_in_train"]["rate"])) == (276, 2.07)
    assert (split["sentence_not_in_train"]["n"], pct(split["sentence_not_in_train"]["rate"])) == (39, 15.29)


# (d) 실데이터: 커밋된 reports/final/zeroth_anchor_notation.json의 수치를 다시 만들 수 있다(출처의 커밋은 다른
# 저장소가 나중에 바뀔 수 있어 수치 부분만 비교).
@REAL
def test_real_committed_anchor_report_is_reproducible():
    committed = json.loads(
        (REPO / "reports" / "final" / "zeroth_anchor_notation.json").read_text(encoding="utf-8")
    )
    result = json.loads(json.dumps(sealed_breakdown.anchor_analysis(ANCHOR, DIGITS, PARQUET_DIR)))
    _same(result["subsets"], committed["subsets"])
    assert committed["sources"]["anchor_report"]["sha256"] == result["sources"]["anchor_report"]["sha256"]


# ==== 입력 파일 출처(file_provenance) ====
# [방식] 임시 폴더에 진짜 git 저장소를 만들어 진짜 git으로 확인한다. 저장소 설정(줄바꿈 변환 끔, 시험용
# 사용자, 서명 끔)은 임시 저장소 안에 적어 사용자의 전역 설정에 기대지 않는다. 필드의 뜻은
# docs/experiments.md의 규칙 변경 31이 정한다: commit은 그 파일의 내용을 마지막으로 바꾼 커밋(이름·폴더만
# 옮긴 커밋은 건너뛴다), blob은 HEAD가 가진 그 파일의 git blob 해시, path는 저장소 뿌리 기준 경로,
# repository는 저장소 최상위 폴더의 이름이다.

# file_provenance가 돌려주는 키의 약속된 순서. 딕셔너리의 ==는 키 순서를 보지 않아 순서는 따로 견준다.
PROVENANCE_KEYS = ["repository", "path", "commit", "blob", "uncommitted_changes", "sha256"]


# 도우미: 임시 저장소(root)에서 git을 불러 표준 출력(앞뒤 공백 제거)을 돌려준다. 실패하면 git의 오류 글과 함께
# 시험이 멈춘다.
def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    assert done.returncode == 0, f"git {' '.join(args)} 실패: {done.stderr}"
    return done.stdout.strip()


# 도우미: root에 빈 git 저장소를 만든다.
def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "--quiet")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "config", "user.name", "Test User")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "commit.gpgsign", "false")


# 도우미: path에 LF 줄바꿈으로 text를 쓴다(상위 폴더가 없으면 만든다). 바이트가 플랫폼과 상관없이 같아야
# SHA-256과 blob을 견줄 수 있다.
def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


# 도우미: 입력 파일로 쓸 서른 줄짜리 본문. git은 내용이 비슷하면(유사도 50 % 이상) 옮기면서 고친 파일도 이름
# 바꾸기로 보므로, 한 줄만 고쳐도 같은 파일로 알아볼 만큼 길게 만든다. first_line으로 첫 줄만 바꿀 수 있고,
# word로 모든 줄의 첫 낱말을 바꿔 서로 닮지 않은 파일을 만들 수 있다(닮은 파일끼리는 이름 바꾸기를 따라가는
# git log가 복사로 넘나들 수 있어, 한 가지를 보려는 시험은 파일 내용을 다르게 둔다).
def _body(first_line: str = "line 00 of the input file", word: str = "line") -> str:
    rest = [
        f"{word} {n:02d} of the input file, long enough to stay recognisable after one edit"
        for n in range(1, 30)
    ]
    return "\n".join([first_line, *rest]) + "\n"


# 도우미: 경로를 하나씩 적어 스테이징하고(paths가 없으면 `git mv` 등이 이미 스테이징한 것만) 커밋한 뒤 새
# 커밋의 해시를 돌려준다.
def _commit(repo: Path, message: str, *paths: str) -> str:
    if paths:
        _git(repo, "add", *paths)
    _git(repo, "commit", "--quiet", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


# 도우미: 커밋 하나의 파일 변경 종류를 `git show --name-status`로 읽는다. 이름 바꾸기는 R과 유사도로 시작하고
# (R100은 내용이 한 글자도 안 바뀐 것) 새 파일은 A, 고친 파일은 M으로 시작한다.
def _name_status(repo: Path, commit: str) -> str:
    return _git(repo, "show", "--name-status", "--format=", "-M", commit)


# 고정물: 입력 파일 하나가 폴더를 옮겨 다닌 이력을 가진 임시 저장소(구성 요소를 한 저장소로 합치면서 입력
# 파일이 겪은 일을 흉내 낸다). 순서는 (1) r/a.json을 처음 커밋 (2) 그 내용을 고친 커밋 (3) 폴더를 comp/r로
# 옮기기만 한 커밋 (4) 다른 파일만 고친 커밋이다. 파일의 내용을 마지막으로 바꾼 것은 (2)이고 (3)은 이름만
# 바꾼 커밋이다. 돌려주는 값은 저장소 뿌리(repo)와 (2)·(3)의 커밋 해시(content_change, move_only)다.
@pytest.fixture
def moved_input(tmp_path: Path) -> dict:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "r" / "a.json", _body())
    _write(repo / "other.txt", "other\n")
    _commit(repo, "add the input file", "r/a.json", "other.txt")
    _write(repo / "r" / "a.json", _body("line 00 edited once"))
    content_change = _commit(repo, "change the content", "r/a.json")
    (repo / "comp").mkdir()
    _git(repo, "mv", "r", "comp/r")
    move_only = _commit(repo, "move the folder only")
    assert _name_status(repo, move_only).startswith("R100"), "전제 실패: 옮기기만 한 커밋이 R100이 아니다"
    _write(repo / "other.txt", "other changed\n")
    _commit(repo, "change another file", "other.txt")
    return {"repo": repo, "content_change": content_change, "move_only": move_only}


# 확인: commit은 파일의 '내용을 마지막으로 바꾼 커밋'이다. 폴더를 옮기기만 한 커밋은 건너뛰고 그 앞의 내용
# 변경 커밋을 가리킨다. 경로만 한정한 `git log`는 옮긴 커밋을 돌려주므로(전제로 단언) 옛 동작은 옮긴 커밋을
# 적었다. blob은 HEAD가 가진 그 파일의 git blob 해시, path는 저장소 뿌리 기준 경로, repository는 저장소
# 최상위 폴더의 이름이고, 키는 PROVENANCE_KEYS의 순서이며, 정상일 때는 경고가 없다. 왜: 입력 파일이 구성
# 요소를 합치며 다른 폴더로 옮겨졌어도 '이 내용이 언제 마지막으로 바뀌었나'가 이동 커밋에 가려지면 안 된다.
def test_provenance_names_the_last_content_change_not_the_move(moved_input, capsys):
    repo = moved_input["repo"]
    target = repo / "comp" / "r" / "a.json"
    # 전제: 경로만 한정한 log는 옮긴 커밋을 마지막 변경으로 답한다(그래서 이름 바꾸기를 따라가야 한다).
    assert _git(repo, "log", "-1", "--format=%H", "--", "comp/r/a.json") == moved_input["move_only"]
    got = sealed_breakdown.file_provenance(target)
    assert got == {
        "repository": "repo",
        "path": "comp/r/a.json",
        "commit": moved_input["content_change"],
        "blob": _git(repo, "rev-parse", "HEAD:comp/r/a.json"),
        "uncommitted_changes": False,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    assert list(got) == PROVENANCE_KEYS
    assert len(got["blob"]) == 40
    assert capsys.readouterr().err == ""


# 확인: 폴더를 옮기면서 내용을 한 줄 고친 커밋은 '내용을 바꾼 커밋'으로 센다. git의 기본 이름 바꾸기
# 감지(유사도 50 % 이상)는 이런 커밋도 이름 바꾸기(R 100 % 미만)로 보므로, 이름 바꾸기를 따라가는
# `git log`에 `-M100%`(내용이 한 글자도 안 바뀐 이동만 이름 바꾸기로 본다)가 없으면 이 커밋을 건너뛰고 그
# 앞의 커밋(처음 더한 커밋)을 돌려준다. 전제로 git이 이 커밋을 R 100 % 미만으로 본다는 것을 단언한다. 이어서
# 내용은 그대로 한 번 더 옮긴 커밋(R100) 뒤에도 commit은 옮기며 고친 그 커밋 그대로여야 한다.
def test_a_move_that_also_edits_counts_as_a_content_change(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "r" / "a.json", _body())
    added = _commit(repo, "add the input file", "r/a.json")

    (repo / "comp").mkdir()
    _git(repo, "mv", "r", "comp/r")
    _write(repo / "comp" / "r" / "a.json", _body("line 00 edited while moving"))
    content_change = _commit(repo, "move the folder and edit one line", "comp/r/a.json")
    status = _name_status(repo, content_change)
    assert status.startswith("R") and not status.startswith("R100"), f"전제 실패: {status!r}"

    got = sealed_breakdown.file_provenance(repo / "comp" / "r" / "a.json")
    assert got["commit"] == content_change
    assert got["commit"] != added
    assert got["blob"] == _git(repo, "rev-parse", "HEAD:comp/r/a.json")

    _git(repo, "mv", "comp/r", "comp/s")
    move_only = _commit(repo, "move the folder only")
    assert _name_status(repo, move_only).startswith("R100"), "전제 실패: 옮기기만 한 커밋이 R100이 아니다"
    after_move = sealed_breakdown.file_provenance(repo / "comp" / "s" / "a.json")
    assert after_move["path"] == "comp/s/a.json"
    assert after_move["commit"] == content_change
    assert after_move["blob"] == got["blob"]  # 옮겼을 뿐이라 같은 내용이면 blob도 그대로다


# 확인: 내용을 고쳤지만 커밋하지 않은 파일은 uncommitted_changes가 True이고 경고가 나온다. 이때
# commit·blob은 HEAD의 것 그대로이고(고친 내용은 아직 어느 커밋에도 없다) sha256만 지금 바이트를 가리킨다.
# 왜: blob과 sha256이 서로 다른 내용을 가리킬 수 있다는 사실이 uncommitted_changes에 남아야, 기록만 봐도
# 어느 쪽 내용으로 쟀는지 알 수 있다.
def test_uncommitted_change_is_flagged(moved_input, capsys):
    repo = moved_input["repo"]
    target = repo / "comp" / "r" / "a.json"
    committed_blob = _git(repo, "rev-parse", "HEAD:comp/r/a.json")
    _write(target, _body("line 00 edited but not committed"))
    assert _git(repo, "hash-object", "comp/r/a.json") != committed_blob  # 전제: 작업 트리의 내용이 달라졌다
    got = sealed_breakdown.file_provenance(target)
    assert got["uncommitted_changes"] is True
    assert got["commit"] == moved_input["content_change"]
    assert got["blob"] == committed_blob
    assert got["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert "has uncommitted changes" in capsys.readouterr().err


# 확인: 저장소 안이지만 git이 추적하지 않는 파일(HEAD에 없다)이면 repository와 path는 채워지고 commit·blob은
# None, uncommitted_changes는 True다. HEAD에 그 파일이 없어 blob을 못 구한 것이 '출처 없음'(모든 필드
# None)으로 번지지 않는다. 전제로 그 파일이 추적되지 않고 저장소에 커밋이 있다는 것을 단언한다. 왜: 아직
# 커밋하지 않은 새 입력 파일도 어느 저장소의 어느 경로인지와 SHA-256은 남아야 한다.
def test_untracked_file_in_a_repository_has_no_blob(moved_input):
    repo = moved_input["repo"]
    target = repo / "comp" / "r" / "new.json"
    _write(target, "{}\n")
    assert _git(repo, "ls-files", "--", "comp/r/new.json") == ""  # 전제: 추적하지 않는 파일이다
    assert len(_git(repo, "rev-parse", "HEAD")) == 40  # 전제: 커밋이 있는 저장소다
    got = sealed_breakdown.file_provenance(target)
    assert (got["repository"], got["path"]) == ("repo", "comp/r/new.json")
    assert got["commit"] is None
    assert got["blob"] is None
    assert got["uncommitted_changes"] is True
    assert got["sha256"] == hashlib.sha256(b"{}\n").hexdigest()
    assert list(got) == PROVENANCE_KEYS


# 확인: 얕은 복제(`--depth 1`)에서는 commit이 None이고 경고 한 줄이 표준 오류에 나온다. 나머지 필드(blob,
# repository, path, uncommitted_changes)는 정상으로 채워진다. 왜: 얕은 복제에서는 경계 커밋이 모든 파일을
# 처음 더한 것처럼 보여, `git log`가 그 파일을 바꾼 적 없는 경계 커밋을 '마지막으로 바꾼 커밋'이라고
# 답한다(전제로 단언). 거짓 값을 적느니 모른다고 적는다. 복제는 file:// 주소로 해야 한다(경로를 그대로 주면
# git이 깊이를 무시하고 전체를 복사한다).
def test_shallow_clone_gives_no_commit(moved_input, tmp_path, capsys):
    clone = tmp_path / "clone"
    source_url = moved_input["repo"].as_uri()
    _git(tmp_path, "clone", "--quiet", "--depth", "1", "-c", "core.autocrlf=false", source_url, str(clone))
    assert _git(clone, "rev-parse", "--is-shallow-repository") == "true"  # 전제: 정말 얕은 복제다
    # 전제: 경로만 한정한 log는 경계 커밋(복제의 HEAD)을 마지막 변경이라 답한다. 그래서 이 값은 믿을 수 없다.
    assert _git(clone, "log", "-1", "--format=%H", "--", "comp/r/a.json") == _git(clone, "rev-parse", "HEAD")
    got = sealed_breakdown.file_provenance(clone / "comp" / "r" / "a.json")
    assert got["commit"] is None
    assert got["blob"] == _git(clone, "rev-parse", "HEAD:comp/r/a.json")
    assert len(got["blob"]) == 40
    assert (got["repository"], got["path"], got["uncommitted_changes"]) == ("clone", "comp/r/a.json", False)
    assert list(got) == PROVENANCE_KEYS
    err = capsys.readouterr().err
    assert "shallow" in err and err.count("warning:") == 1


# 확인: git이 안 되는 곳에서는 멈추지 않고 sha256만 값이 있고 repository·commit·blob·uncommitted_changes는
# None이며 path는 파일 이름이다(지금까지의 기록 규약). 키 순서는 값이 있을 때와 같고 경고가 나온다. 둘을
# 본다: (가) 저장소 밖의 파일, (나) git이 PATH에 없을 때. 왜 GIT_CEILING_DIRECTORIES인가: pytest의 임시
# 폴더는 이 구성 요소의 .pytest-tmp 아래, 곧 이 저장소 안이라 보통 폴더를 만들면 git이 바깥 저장소를 찾아
# 성공해 버린다. 부모 폴더를 상한으로 주면 git이 그 위로 올라가지 못해 '저장소 밖'이 된다. 그 전제가 안
# 서면(git이 저장소를 찾으면) 조용히 통과하지 않고 여기서 실패한다. (나)는 같은 호출이 git이 되는 저장소의
# 파일에서는 값을 내므로, None은 파일이 아니라 git 부재 때문이다.
def test_outside_a_repository_only_the_hash_is_known(moved_input, tmp_path, monkeypatch, capsys):
    payload = b'{"k": 1}\n'
    plain = tmp_path / "plain"
    plain.mkdir()
    outside = plain / "a.json"
    outside.write_bytes(payload)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    premise = subprocess.run(
        ["git", "-C", str(plain), "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    assert premise.returncode != 0, (
        "전제 실패: git이 이 폴더에서 저장소를 찾았다(GIT_CEILING_DIRECTORIES가 먹지 않음)"
    )
    expected = {
        "repository": None,
        "path": "a.json",
        "commit": None,
        "blob": None,
        "uncommitted_changes": None,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    got = sealed_breakdown.file_provenance(outside)
    assert got == expected
    assert list(got) == PROVENANCE_KEYS
    assert "warning: no git provenance for a.json" in capsys.readouterr().err

    # (나) git이 PATH에 없을 때. 같은 호출이 저장소 안의 파일에서는 값을 낸다는 것을 먼저 확인한다.
    inside = moved_input["repo"] / "comp" / "r" / "a.json"
    assert sealed_breakdown.file_provenance(inside)["commit"] == moved_input["content_change"]
    capsys.readouterr()
    monkeypatch.setenv("PATH", "")
    inside_without_git = sealed_breakdown.file_provenance(inside)
    assert inside_without_git == {**expected, "sha256": hashlib.sha256(inside.read_bytes()).hexdigest()}
    assert list(inside_without_git) == PROVENANCE_KEYS
    assert "warning: no git provenance for a.json" in capsys.readouterr().err


# 확인: `rev-parse --verify`가 종료 코드 1(HEAD에 그 파일이 없음)이 아닌 값으로 실패하면 blob만 None으로
# 두지 않고 '출처 없음'(sha256만 값이 있고 경고)으로 닫는다. 왜: blob만 비우고 commit·uncommitted_changes를
# 채우면 진짜 실패(저장소 손상 등)가 일부 값이 있는 정상 기록처럼 보인다(종료 코드 1은 추적하지 않는 파일
# 시험이 확인한다). 가짜 run은 --verify가 든 호출만 실패시키고 나머지는 진짜 subprocess.run으로 보낸다(진짜는
# 가짜를 끼우기 전에 붙잡아 둔다). 이 시험은 subprocess.run을 전역으로 바꾸므로 그 뒤에는 _git 도우미를 쓰지
# 않는다.
def test_other_blob_lookup_failures_drop_the_provenance(moved_input, monkeypatch, capsys):
    target = moved_input["repo"] / "comp" / "r" / "a.json"
    assert sealed_breakdown.file_provenance(target)["blob"] is not None  # 전제: 진짜 git으로는 blob이 나온다
    expected = {
        "repository": None,
        "path": "a.json",
        "commit": None,
        "blob": None,
        "uncommitted_changes": None,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    real_run = subprocess.run

    def failing(exit_code: int):
        def run(cmd, *args, **kwargs):
            if "--verify" in cmd:
                raise subprocess.CalledProcessError(exit_code, cmd)
            return real_run(cmd, *args, **kwargs)

        return run

    capsys.readouterr()
    for exit_code in (2, 128):
        monkeypatch.setattr(sealed_breakdown.subprocess, "run", failing(exit_code))
        got = sealed_breakdown.file_provenance(target)
        assert got == expected, f"종료 코드 {exit_code}"
        assert list(got) == PROVENANCE_KEYS
        assert "warning: no git provenance for a.json" in capsys.readouterr().err


# 확인: blob은 인덱스(스테이징한 것)가 아니라 HEAD의 것이다. 고친 파일을 `git add`만 하고 커밋하지 않으면
# 인덱스의 blob은 HEAD의 것과 달라지는데(전제로 단언) blob은 HEAD의 것 그대로이고 uncommitted_changes가
# True다. 스테이징만 하고 커밋하지 않은 새 파일은 HEAD에 없으므로 commit·blob이 None이고
# uncommitted_changes가 True다. 왜: blob은 commit과 짝이 맞는 'HEAD가 가진 그 파일'의 이름이어야 한다.
# 인덱스의 blob을 적으면 아직 어느 커밋에도 없는 내용을 커밋된 것처럼 적게 된다.
def test_staged_changes_do_not_replace_the_head_blob(moved_input):
    repo = moved_input["repo"]
    target = repo / "comp" / "r" / "a.json"
    head_blob = _git(repo, "rev-parse", "HEAD:comp/r/a.json")
    _write(target, _body("line 00 edited and staged"))
    _git(repo, "add", "comp/r/a.json")
    assert _git(repo, "rev-parse", ":comp/r/a.json") != head_blob  # 전제: 인덱스는 다른 blob을 가진다
    got = sealed_breakdown.file_provenance(target)
    assert got["blob"] == head_blob
    assert got["commit"] == moved_input["content_change"]
    assert got["uncommitted_changes"] is True

    staged_new = repo / "comp" / "r" / "staged.json"
    _write(staged_new, "{}\n")
    _git(repo, "add", "comp/r/staged.json")
    assert _git(repo, "ls-files", "--stage", "--", "comp/r/staged.json") != ""  # 전제: 인덱스에는 있다
    got = sealed_breakdown.file_provenance(staged_new)
    assert (got["commit"], got["blob"], got["uncommitted_changes"]) == (None, None, True)


# 확인: 이름을 바꾸며 글자 하나만 고친 커밋도 내용 변경으로 센다. 큰 파일은 글자 하나를 고쳐도 git이 R099로
# 보는데(전제로 단언) 이름 바꾸기를 따라가는 `git log`의 유사도 기준이 100 %가 아니라 99 %나 98 %이면 이
# 커밋을 건너뛰고 그 앞의 커밋을 돌려준다. 왜: 실제 입력 같은 큰 파일의 한 글자 수정이 내용 변경으로 남아야
# 한다. 앞의 이동·수정 시험은 줄이 긴 서른 줄 파일이라 R098이어서 99 %를 가르지 못한다. 줄이 짧은 600줄
# 파일에서는 한 글자가 파일의 1 %에 못 미친다.
def test_a_one_character_edit_while_moving_counts_as_a_content_change(tmp_path):
    def short_lines(first_line: str) -> str:
        return "\n".join([first_line, *[f"row {n:04d}" for n in range(1, 600)]]) + "\n"

    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "r" / "a.json", short_lines("row 0000"))
    added = _commit(repo, "add the input file", "r/a.json")
    (repo / "comp").mkdir()
    _git(repo, "mv", "r", "comp/r")
    _write(repo / "comp" / "r" / "a.json", short_lines("row 0001"))
    content_change = _commit(repo, "move the folder and change one character", "comp/r/a.json")
    status = _name_status(repo, content_change)  # 이름 바꾸기면 첫 칸이 R과 세 자리 유사도(99 %는 099)다
    similarity = int(status.split("\t")[0][1:]) if status.startswith("R") else -1
    assert 90 <= similarity < 100, f"전제 실패: {status!r}"
    got = sealed_breakdown.file_provenance(repo / "comp" / "r" / "a.json")
    assert got["commit"] == content_change
    assert got["commit"] != added


# 확인: .gitignore에 든 추적하지 않는 파일도 HEAD에 없으므로 repository와 path는 채워지고 commit·blob은
# None, uncommitted_changes는 True다. `git status`는 무시된 파일을 세지 않으므로(전제로 단언) status만
# 믿으면 이 파일이 '깨끗함'으로 적힌다. 왜: HEAD에 없는 파일은 HEAD와 다르다. 읽는 사람이 commit None과
# uncommitted_changes False를 '커밋돼 있고 깨끗함'으로 읽으면 안 된다.
def test_ignored_file_counts_as_uncommitted(moved_input):
    repo = moved_input["repo"]
    _write(repo / ".gitignore", "ignored.json\n")
    _commit(repo, "ignore a scratch file", ".gitignore")
    ignored = repo / "comp" / "r" / "ignored.json"
    _write(ignored, "{}\n")
    # 전제: 무시 목록에 들고, 추적하지 않으며, `git status`는 이 파일을 세지 않는다.
    assert _git(repo, "check-ignore", "comp/r/ignored.json") == "comp/r/ignored.json"
    assert _git(repo, "ls-files", "--", "comp/r/ignored.json") == ""
    assert _git(repo, "status", "--porcelain", "--", "comp/r/ignored.json") == ""
    got = sealed_breakdown.file_provenance(ignored)
    assert (got["repository"], got["path"]) == ("repo", "comp/r/ignored.json")
    assert (got["commit"], got["blob"], got["uncommitted_changes"]) == (None, None, True)
    assert got["sha256"] == hashlib.sha256(b"{}\n").hexdigest()


# 확인: HEAD에서 지운 경로에 같은 이름의 새 파일을 추적 없이 다시 만들면 commit·blob은 None,
# uncommitted_changes는 True이고 지우기 전의 커밋을 commit으로 적지 않는다. 전제로 HEAD에 그 경로가 없고,
# 이름 바꾸기를 따라가는 `git log`는 그 경로의 옛 마지막 변경 커밋을 아직 돌려준다는 것을 단언한다. 왜: 그
# 옛 커밋은 지금 작업 트리에 있는 파일의 것이 아니다.
def test_recreated_path_does_not_borrow_the_deleted_files_commit(moved_input):
    repo = moved_input["repo"]
    target = repo / "comp" / "r" / "a.json"
    _git(repo, "rm", "--quiet", "comp/r/a.json")
    _commit(repo, "delete the input file")
    _write(target, _body("brand new content"))
    assert _git(repo, "ls-tree", "--name-only", "HEAD", "--", "comp/r/a.json") == ""  # 전제: HEAD에 없다
    assert _git(repo, "ls-files", "--", "comp/r/a.json") == ""  # 전제: 추적하지 않는다
    # 전제: 옛 이력이 남아 있어 그대로 물으면 지우기 전의 변경 커밋이 나온다.
    log_args = ["log", "-1", "--follow", "-M100%", "--diff-filter=AM", "--format=%H", "--", "comp/r/a.json"]
    assert _git(repo, *log_args) == moved_input["content_change"]
    got = sealed_breakdown.file_provenance(target)
    assert (got["repository"], got["path"]) == ("repo", "comp/r/a.json")
    assert (got["commit"], got["blob"], got["uncommitted_changes"]) == (None, None, True)
    assert got["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()


# 확인: 파일 이름의 `[`·`*`·`?` 같은 글자는 glob이 아니라 글자 그대로 읽는다. `a[1].json`을 glob으로 읽으면
# 이웃 `a1.json`과도 맞아 그 커밋과 고친 내용이 `a[1].json`의 commit·uncommitted_changes로 섞여
# 나온다(전제로 단언). `git log`에는 `--follow`가 같이 붙으므로 이 시험은 글자 그대로의 경로 지정이
# `--follow`와 함께 돈다는 것도 확인한다. 왜: 이름이 비슷한 입력 파일끼리 출처가 섞이면 안 된다.
def test_glob_characters_in_a_file_name_are_taken_literally(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "a[1].json", _body("bracket name", word="bracket"))
    bracket = _commit(repo, "add the bracket-named file", "a[1].json")
    _write(repo / "a1.json", _body("plain name", word="plain"))
    plain = _commit(repo, "add the file that the glob would also match", "a1.json")
    _write(repo / "a1.json", _body("plain name, edited", word="plain"))  # 고쳤지만 커밋하지 않은 이웃
    # 전제: glob으로 읽으면 이웃의 커밋과 변경이 섞여 나온다.
    assert _git(repo, "log", "-1", "--format=%H", "--", "a[1].json") == plain
    assert "a1.json" in _git(repo, "status", "--porcelain", "--", "a[1].json")
    got = sealed_breakdown.file_provenance(repo / "a[1].json")
    assert got["commit"] == bracket
    assert got["blob"] == _git(repo, "rev-parse", "HEAD:a[1].json")
    assert got["uncommitted_changes"] is False
    neighbour = sealed_breakdown.file_provenance(repo / "a1.json")
    assert neighbour["commit"] == plain
    assert neighbour["uncommitted_changes"] is True


# 확인: 이름에 공백이나 한글이 든 파일도 글자 그대로의 경로 지정에서 그대로 된다(commit은 그 파일을 더한
# 커밋, blob은 HEAD의 것, uncommitted_changes는 False). 왜: 경로를 글자 그대로 넘기도록 바꾼 것이 이런
# 이름을 깨뜨리지 않아야 한다.
def test_spaces_and_non_ascii_in_a_file_name_still_work(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    added = {}
    for index, name in enumerate(("with space.json", "한글 파일.json")):
        _write(repo / "comp" / name, _body("first line of " + name, word=f"file{index}"))
        added[name] = _commit(repo, "add a file with an unusual name", f"comp/{name}")
    for name, commit in added.items():
        got = sealed_breakdown.file_provenance(repo / "comp" / name)
        assert got["path"] == f"comp/{name}", name
        assert got["commit"] == commit, name
        assert got["blob"] == _git(repo, "rev-parse", f"HEAD:comp/{name}"), name
        assert got["uncommitted_changes"] is False, name


# 확인: 커밋이 하나도 없는 저장소(`git init`만 한 폴더)의 파일은 HEAD가 없어 '출처 없음'(sha256만 값이 있고
# 경고)이다. HEAD에 그 파일이 없는 경우(추적하지 않는 파일)와 다르다. 이 구분은 `log`를 blob 조회보다 먼저
# 부르는 순서에서 나온다: 커밋이 없으면 `log`가 실패해 '출처 없음'이 되고, blob 조회를 먼저 하면 HEAD가 없는
# 것이 종료 코드 1(없음)로 읽혀 repository·path가 채워진 기록이 된다. 전제로 그 폴더가 저장소 안이고 HEAD가
# 없다는 것을 단언한다.
def test_repository_without_commits_only_the_hash_is_known(tmp_path):
    fresh = tmp_path / "fresh"
    _init_repo(fresh)
    target = fresh / "a.json"
    target.write_bytes(b"{}\n")
    assert _git(fresh, "rev-parse", "--is-inside-work-tree") == "true"  # 전제: 저장소 안이다
    head = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], cwd=fresh, capture_output=True)
    assert head.returncode != 0, "전제 실패: 커밋이 없는 저장소인데 HEAD가 있다"
    got = sealed_breakdown.file_provenance(target)
    assert got == {
        "repository": None,
        "path": "a.json",
        "commit": None,
        "blob": None,
        "uncommitted_changes": None,
        "sha256": hashlib.sha256(b"{}\n").hexdigest(),
    }


# 확인: 사용자가 GIT_LITERAL_PATHSPECS=1을 환경에 걸어 두어도 출처가 그대로다. 경로 앞에 `:(literal)` 접두를
# 붙이는 방식은 그 환경에서 접두가 마법으로 읽히지 않아 `git log`가 오류 없이 빈 결과를 내고 `git status`도
# 비어, commit이 None으로 uncommitted_changes가 False로 조용히 틀린다. git의 --literal-pathspecs 옵션은 그
# 환경 변수를 이 호출에서 덮어쓴다. 고쳐 둔 파일로 log 쪽(commit)과 status 쪽(uncommitted_changes)을 함께
# 본다. 왜: 이 도구를 어떤 환경에서 돌릴지 모른다.
def test_literal_pathspecs_environment_variable_does_not_change_the_provenance(moved_input, monkeypatch):
    target = moved_input["repo"] / "comp" / "r" / "a.json"
    _write(target, _body("line 00 edited but not committed"))
    expected = sealed_breakdown.file_provenance(target)
    assert expected["commit"] == moved_input["content_change"]  # 전제: 환경 변수 없이는 값이 제대로 나온다
    assert expected["uncommitted_changes"] is True
    monkeypatch.setenv("GIT_LITERAL_PATHSPECS", "1")
    assert sealed_breakdown.file_provenance(target) == expected
