"""측정 도구가 결과에 남기는 코드 출처 헬퍼 scoped_git_state의 테스트(docs/experiments.md 규칙 변경 31).

확인하는 것: (1) git_dirty가 root 폴더 안의 추적 파일만 보고 같은 저장소의 다른 폴더에서 바뀐 파일과 추적하지
않는 새 파일은 세지 않는다, (2) git_tree가 root 폴더의 git 트리 해시이고 다른 폴더의 커밋으로는 바뀌지 않으며
git_head는 40자 커밋 해시다, (3) 기준이 프로세스의 작업 폴더가 아니라 root 인자(코드가 있는 폴더)다,
(4) 저장소 안이지만 커밋에 없는 폴더에서는 git_tree만 None이다, (5) git이 안 되는 곳(저장소 밖, git 실행 파일
없음)에서는 세 필드가 모두 None이다, (6) 측정 도구 넷이 같은 헬퍼를 쓰고 각자의 모듈 ROOT를 호출할 때 읽는다.
"""

# [방식] 임시 폴더에 진짜 git 저장소를 만들어 진짜 git으로 확인한다(가짜 subprocess는 git 실행 파일이 없는
# 경우에만 쓴다). 저장소는 구성 요소 두 폴더 comp/(측정 도구가 있는 쪽)와 other/(같은 저장소의 다른 구성
# 요소)에 추적 파일을 하나씩 커밋한 꼴이다. 저장소 설정(줄바꿈 변환 끔, 시험용 사용자, 서명 끔)은 임시
# 저장소 안에 적어 사용자의 전역 설정에 기대지 않는다.

from __future__ import annotations

import argparse
import hashlib
import importlib
import subprocess
import sys
from pathlib import Path

import pytest
import torch

import stt_scratch.provenance as provenance
from stt_scratch.provenance import scoped_git_state

REPO = Path(__file__).resolve().parents[1]
# scripts/는 패키지가 아니므로 경로를 더해 불러온다(다른 시험 파일과 같은 방식).
sys.path.insert(0, str(REPO / "scripts"))


# 도우미: path에 LF 줄바꿈으로 text를 쓴다(저장소 규칙: 줄바꿈 변환 없이 바이트 그대로).
def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


# 도우미: root에서 git을 부르고 표준 출력(앞뒤 공백 제거)을 돌려준다. 실패하면 시험이
# CalledProcessError로 멈춘다.
def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


# 헬퍼가 돌려주는 키의 약속된 순서. 딕셔너리의 ==는 키 순서를 보지 않으므로 순서는 이 목록과 따로 견준다.
KEYS = ["git_head", "git_dirty", "git_tree"]


# 도우미: state가 '아무것도 모름'(셋 다 None)이고 키 순서가 약속대로인지 확인한다.
def assert_nothing_known(state: dict) -> None:
    assert state == {"git_head": None, "git_dirty": None, "git_tree": None}
    assert list(state) == KEYS


# 고정물: 임시 git 저장소에 추적 파일 comp/a.txt와 other/b.txt를 커밋해 둔다. 돌려주는 값은 저장소 뿌리다.
# 폴더 둘은 한 저장소에 든 구성 요소 둘을 흉내 낸다.
@pytest.fixture
def two_folders(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "comp").mkdir(parents=True)
    (repo / "other").mkdir()
    write(repo / "comp" / "a.txt", "a\n")
    write(repo / "other" / "b.txt", "b\n")
    git(repo, "init", "--quiet")
    git(repo, "config", "core.autocrlf", "false")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "add", "comp/a.txt", "other/b.txt")
    git(repo, "commit", "--quiet", "-m", "init")
    return repo


# 확인: git_dirty는 root 폴더 안의 추적 파일만 본다. 같은 저장소의 다른 폴더(other/)에서 바뀐 추적 파일은 세지
# 않고(경로 없이 `git status`를 부르던 옛 동작은 셌다), root 폴더(comp/)의 바뀐 추적 파일은 작업 트리에서든
# 인덱스(스테이징)에서든 센다. 추적하지 않는 새 파일은 어느 쪽이든 세지 않는다(옛 동작과 같은 규약). 왜: 측정
# 기록이 다른 구성 요소의 작업 때문에 '커밋하지 않은 변경 있음'으로 남으면 그 기록만으로는 이 폴더의 코드가
# 커밋된 것이었는지 알 수 없다.
def test_changes_in_another_folder_do_not_count(two_folders: Path) -> None:
    repo = two_folders
    comp, other = repo / "comp", repo / "other"
    assert scoped_git_state(comp)["git_dirty"] is False

    write(other / "b.txt", "b changed\n")
    # 전제: 경로 없이 부르면 other/의 변경이 comp/에서도 보인다. 이 줄이 있어서 이 시험은 옛 동작과 구별된다.
    assert "other/b.txt" in git(comp, "status", "--porcelain", "--untracked-files=no")
    assert scoped_git_state(comp)["git_dirty"] is False
    assert scoped_git_state(other)["git_dirty"] is True  # 같은 변경을 other/ 기준으로 보면 센다

    write(comp / "new.txt", "untracked\n")  # 추적하지 않는 새 파일은 세지 않는다
    assert scoped_git_state(comp)["git_dirty"] is False

    write(comp / "a.txt", "a changed\n")
    assert scoped_git_state(comp)["git_dirty"] is True
    git(repo, "add", "comp/a.txt")  # 스테이징만 하고 커밋하지 않은 변경도 센다
    assert scoped_git_state(comp)["git_dirty"] is True


# 확인: git_tree는 root 폴더의 git 트리 해시(`git rev-parse HEAD:comp`)이고, 돌려주는 키는 git_head,
# git_dirty, git_tree 순서다. other/만 바꾼 커밋으로는 git_tree가 그대로이고(git_head는 달라진다) comp/를
# 바꾼 커밋은 git_tree도 바꾼다. 저장소 뿌리를 root로 주면(폴더 하나가 저장소 전체인 경우) 뿌리의 트리
# 해시(HEAD^{tree})다. 왜: git_tree가 같으면 다른 구성 요소의 커밋이 끼어 있어도 이 폴더의 커밋된 내용이
# 같다고 말할 수 있다.
def test_tree_is_the_folder_tree(two_folders: Path) -> None:
    repo = two_folders
    comp, other = repo / "comp", repo / "other"
    first = scoped_git_state(comp)
    assert list(first) == KEYS
    assert len(first["git_head"]) == 40 and first["git_head"] == git(repo, "rev-parse", "HEAD")
    assert first["git_tree"] == git(repo, "rev-parse", "HEAD:comp")
    assert scoped_git_state(repo)["git_tree"] == git(repo, "rev-parse", "HEAD^{tree}")

    write(other / "b.txt", "b changed\n")
    git(repo, "add", "other/b.txt")
    git(repo, "commit", "--quiet", "-m", "change the other folder only")
    after_other = scoped_git_state(comp)
    assert after_other["git_head"] != first["git_head"]
    assert after_other["git_tree"] == first["git_tree"]

    write(comp / "a.txt", "a changed\n")
    git(repo, "add", "comp/a.txt")
    git(repo, "commit", "--quiet", "-m", "change comp")
    after_comp = scoped_git_state(comp)
    assert after_comp["git_tree"] != first["git_tree"]
    assert after_comp["git_tree"] == git(repo, "rev-parse", "HEAD:comp")
    assert after_comp["git_dirty"] is False


# 확인: 범위는 프로세스의 작업 폴더가 아니라 root 인자(코드가 있는 폴더)가 정한다. 작업 폴더가 같은 저장소의
# 다른 폴더(other/)이든, 저장소 뿌리이든, 임시 저장소 밖의 폴더(tmp_path; 이 시험에서는 이 구성 요소의
# .pytest-tmp 아래라 바깥 저장소 안의 추적하지 않는 폴더다)이든 comp/의 변경은 보이고, git_head·git_tree도
# 임시 저장소의 comp/ 것이다(작업 폴더를 기준으로 삼으면 바깥 저장소의 값이 나온다). 왜: 측정 도구는 어느
# 폴더에서 돌릴지 모른다(저장소 뿌리, scripts/ 안, 임시 폴더). 작업 폴더를 기준으로 삼으면 하위 폴더에서 돌릴
# 때 더러운 src/를 놓친다.
def test_scope_follows_the_code_location_not_the_working_directory(
    two_folders: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = two_folders
    comp, other = repo / "comp", repo / "other"
    write(comp / "a.txt", "a changed\n")
    for cwd in (other, repo, tmp_path):
        monkeypatch.chdir(cwd)
        state = scoped_git_state(comp)
        assert state["git_dirty"] is True, f"작업 폴더 {cwd}에서 comp/의 변경을 놓쳤다"
        assert state["git_head"] == git(repo, "rev-parse", "HEAD"), f"작업 폴더 {cwd}"
        assert state["git_tree"] == git(repo, "rev-parse", "HEAD:comp"), f"작업 폴더 {cwd}"
        assert scoped_git_state(other)["git_dirty"] is False, f"작업 폴더 {cwd}에서 other/가 더럽다고 나왔다"


# 확인: 저장소 안이지만 HEAD 커밋에 없는 폴더(커밋하지 않은 새 폴더)에서는 git_head가 40자 커밋 해시이고
# git_dirty는 False(추적 파일이 없으니 바뀐 것도 없다)이며 git_tree만 None이다. 트리 해시를 못 구한 것이 다른
# 두 필드를 None으로 만들지 않는다. 왜: 이 폴더가 통째로 아직 커밋되지 않았다는 사실이 git_tree의 null로
# 남아야 하고, 그래도 어느 커밋 위에서 쟀는지는 알 수 있어야 한다.
def test_untracked_folder_has_no_tree(two_folders: Path) -> None:
    repo = two_folders
    folder = repo / "tmp"
    folder.mkdir()
    write(folder / "x.txt", "x\n")
    assert git(repo, "ls-files", "--", "tmp") == ""  # 전제: 이 폴더의 파일은 하나도 추적되지 않는다
    state = scoped_git_state(folder)
    assert len(state["git_head"]) == 40 and state["git_head"] == git(repo, "rev-parse", "HEAD")
    assert state["git_dirty"] is False
    assert state["git_tree"] is None


# 확인: git이 안 되는 곳에서는 멈추지 않고 세 필드가 모두 None이고 키 순서는 값이 있을 때와 같다(지금까지의
# 기록 규약; 딕셔너리 ==는 순서를 보지 않으므로 순서는 따로 견준다). 둘을 본다: (가) 저장소 밖의 폴더, (나)
# git 실행 파일이 없을 때(subprocess.run이 FileNotFoundError를 던짐). 이 헬퍼는 기록용이라 git이 없어도 측정
# 도구를 멈추지 않는다. 왜 GIT_CEILING_DIRECTORIES인가: pytest의 임시 폴더는 이 구성 요소의 .pytest-tmp 아래,
# 곧 이 저장소 안이라 그냥 보통 폴더를 만들면 git이 바깥 저장소를 찾아 성공해 버린다. 부모 폴더를 상한으로
# 주면 git이 그 위로 올라가지 못해 '저장소 밖'이 된다. 그 전제가 안 서면(git이 저장소를 찾으면) 조용히
# 통과하지 않고 여기서 실패한다.
def test_outside_a_repository_every_field_is_none(
    two_folders: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    premise = subprocess.run(["git", "rev-parse", "HEAD"], cwd=plain, capture_output=True, text=True)
    assert premise.returncode != 0, (
        "전제 실패: git이 이 폴더에서 저장소를 찾았다(GIT_CEILING_DIRECTORIES가 먹지 않음)"
    )
    assert_nothing_known(scoped_git_state(plain))

    # (나) git 실행 파일이 없을 때. 같은 호출이 git이 되는 폴더에서는 값을 내므로, None은 폴더가 아니라 git
    # 부재 때문이다. 이 아래에서는 subprocess.run을 쓰지 않는다(전역으로 바뀌어 있다).
    comp = two_folders / "comp"
    assert scoped_git_state(comp)["git_head"] is not None

    def no_git(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(provenance.subprocess, "run", no_git)
    assert_nothing_known(scoped_git_state(comp))


# 확인: 커밋이 하나도 없는 저장소(`git init`만 한 폴더)에서는 HEAD가 아직 없어 `git rev-parse HEAD`가
# 실패하므로 셋 다 None이다. 어느 커밋 위에서 쟀는지조차 알 수 없는 경우라 '폴더만 커밋에 없는'
# 경우(git_tree만 None)와 다르다. 전제로 그 폴더가 저장소 안인지(그래서 '저장소 밖'과 구별되는지)와 HEAD가
# 없는지를 먼저 단언한다.
def test_repository_without_commits_every_field_is_none(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    git(fresh, "init", "--quiet")
    write(fresh / "a.txt", "a\n")  # 파일은 있어도 추적하지 않고 커밋도 없다
    assert git(fresh, "rev-parse", "--is-inside-work-tree") == "true"  # 전제: 저장소 안이다
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=fresh, capture_output=True, text=True)
    assert head.returncode != 0, "전제 실패: 커밋이 없는 저장소인데 HEAD가 있다"
    assert_nothing_known(scoped_git_state(fresh))


# 확인: 어느 git 호출이 실패하느냐가 잃는 필드를 정한다. 트리를 묻는 셋째 호출(`HEAD:./`)이 OSError로 실패하면
# git_head·git_dirty는 그대로이고 git_tree만 None이다(트리를 못 구한 것이 다른 두 값을 지우지 않는다). 반대로
# 상태를 묻는 호출(`status`)이 실패하면 읽지 못한 상태를 '깨끗함'(git_dirty False)으로 적지 않고 셋 다
# None이다. 가짜 run은 지정한 낱말이 든 호출만 실패시키고 나머지는 진짜 subprocess.run으로 보낸다(진짜는
# 가짜를 끼우기 전에 붙잡아 둔다). 이 시험은 subprocess.run을 전역으로 바꾸므로 그 뒤에는 git 도우미를 쓰지
# 않는다.
def test_only_a_failing_tree_lookup_keeps_the_other_two_fields(
    two_folders: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    comp = two_folders / "comp"
    write(comp / "a.txt", "a changed\n")  # git_dirty가 True라 기본값 False와 구별된다
    full = scoped_git_state(comp)
    assert len(full["git_head"]) == 40 and full["git_dirty"] is True and len(full["git_tree"]) == 40
    real_run = subprocess.run

    def failing(word: str):
        def run(cmd: list[str], *args: object, **kwargs: object):
            if word in cmd:
                raise OSError(f"{word}: 일부러 실패시킨 호출")
            return real_run(cmd, *args, **kwargs)

        return run

    monkeypatch.setattr(provenance.subprocess, "run", failing("HEAD:./"))
    tree_lost = scoped_git_state(comp)
    assert tree_lost == {"git_head": full["git_head"], "git_dirty": True, "git_tree": None}
    assert list(tree_lost) == KEYS

    monkeypatch.setattr(provenance.subprocess, "run", failing("status"))
    assert_nothing_known(scoped_git_state(comp))


# 확인: 측정 도구 넷(stage6·confidence_eval·itn_eval의 git_state(), followup.provenance()의 git 부분)이
# 같은 헬퍼의 값을 내고, 그때 기준 폴더는 호출할 때의 모듈 ROOT다(import할 때의 값을 박아 두지 않았다). ROOT를
# comp/로 바꿔 끼우면 comp/의 변경을 따르고 other/로 바꿔 끼우면 따르지 않는다. followup.provenance의 키
# 순서는 체크포인트 두 키 다음에 git_head·git_dirty·git_tree가 오고 device가 이어진다(git_tree만 새 키).
# 왜: 헬퍼 단위 시험은 도구가 그 헬퍼를 제대로 부르는지까지는 보장하지 않는다.
def test_each_script_records_the_state_of_its_own_root(
    two_folders: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = two_folders
    comp, other = repo / "comp", repo / "other"
    write(comp / "a.txt", "a changed\n")
    expected = scoped_git_state(comp)
    assert expected["git_dirty"] is True and expected["git_tree"] is not None
    clean = scoped_git_state(other)
    assert clean["git_dirty"] is False

    stage6 = importlib.import_module("stage6")
    confidence_eval = importlib.import_module("confidence_eval")
    itn_eval = importlib.import_module("itn_eval")
    for module in (stage6, confidence_eval, itn_eval):
        monkeypatch.setattr(module, "ROOT", comp)
        assert module.git_state() == expected, module.__name__
        monkeypatch.setattr(module, "ROOT", other)
        assert module.git_state() == clean, module.__name__

    followup = importlib.import_module("followup")
    checkpoint = b"checkpoint bytes"
    args = argparse.Namespace(checkpoint="m.pt", limit=0)
    for root, want in ((comp, expected), (other, clean)):
        (root / "m.pt").write_bytes(checkpoint)  # provenance가 SHA-256을 구할 체크포인트(추적하지 않는 파일)
        monkeypatch.setattr(followup, "ROOT", root)
        record = followup.provenance(args, torch.device("cpu"))
        assert list(record)[:6] == [
            "checkpoint",
            "checkpoint_sha256",
            "git_head",
            "git_dirty",
            "git_tree",
            "device",
        ]
        assert record["checkpoint_sha256"] == hashlib.sha256(checkpoint).hexdigest()
        assert {key: record[key] for key in want} == want
