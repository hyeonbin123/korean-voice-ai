# [테스트 묶음] 측정 출처 검사의 범위와 닫힘을 임시 git 저장소로 확인한다.
# 범위: 공식 실행(--official)의 "추적 파일이 바뀌지 않았는가" 검사(evaluate, service_eval),
# scripts/ctx_probe.py의 같은 검사(tree_is_clean), 판정 요약(judge_run)의 git_dirty는 저장소 전체가 아니라
# 이 구성 요소 폴더만 보고, 기록의 git_tree는 이 폴더의 커밋된 내용의 트리 해시다(docs/experiments.md
# "측정 출처를 이 폴더 기준으로"). 효율 측정(bench) 기록의 같은 값은 tests/test_bench.py에서 확인한다.
# 닫힘: PROJECT_ROOT가 엉뚱한 폴더(저장소 밖, 또는 저장소 작업 트리 안의 추적하지 않는 폴더)를 가리키면 공식
# 검사가 통과하지 않고 멈춘다.
# [왜 중요한가] 이 폴더는 다른 구성 요소와 한 저장소에 함께 있다. 범위가 저장소 전체이면 다른 폴더의 바뀐
# 파일이 이 폴더의 공식 측정을 막고 기록의 git_dirty를 참으로 만든다. 반대로 범위를 현재 작업 폴더로
# 잡으면 하위 폴더에서 돌린 측정이 바뀐 src/를 놓친다. git을 쓸 수 없는 곳(압축 파일로 받은 사본,
# 컨테이너)에서는 공식 측정이 지금처럼 멈추고, 기록용 값은 지금까지의 규약대로 빈 글로 남아야 한다.
# [방법] 임시 저장소에 폴더 둘(comp = 이 구성 요소, other = 다른 구성 요소)을 만들고
# evaluate.PROJECT_ROOT를 comp로 바꿔 끼운다. 모델·서버·네트워크는 쓰지 않는다. 임시 저장소의 git 명령에는
# 시험용 사용자와 줄바꿈 변환 끔, 서명 끔을 명령마다 주어 이 PC나 CI의 전역 설정(서명 요구 등)에 기대지
# 않게 한다.

import json
import subprocess
from pathlib import Path

import httpx
import pytest

from call_summary import evaluate, judge_run, service_eval
from call_summary.dataset import write_jsonl

# 다른 시험 파일의 도우미: probe는 scripts/ctx_probe.py를 불러온 모듈, _runs·_Counting·_all_included는
# 판정 실행 시험이 쓰는 가짜 평가 실행과 가짜 판정 모델이다(_item처럼 가져다 쓴다).
from tests.test_ctx_probe import probe
from tests.test_judge_calib import _all_included, _Counting, _runs
from tests.test_scoring import _item

# 임시 저장소의 git 명령마다 주는 설정: 시험용 사용자(커밋에 필요), 줄바꿈 변환 끔(Windows에서 바이트가 바뀌지
# 않게), 서명 끔(서명을 켜 둔 PC에서 시험 커밋이 입력을 기다리며 멈추지 않게).
TEST_CONFIG = ("user.name=t", "user.email=t@t", "core.autocrlf=false", "commit.gpgsign=false")


# 임시 저장소 root에서 git을 실행하고 출력(앞뒤 공백을 뗀 글)을 돌려준다. 실패하면 예외가 나 시험이 멈춘다.
def git(root: Path, *args: str) -> str:
    options = [part for setting in TEST_CONFIG for part in ("-c", setting)]
    done = subprocess.run(["git", *options, *args], cwd=root, check=True, capture_output=True, text=True)
    return done.stdout.strip()


# 파일 하나를 UTF-8·LF로 쓴다(Windows에서 줄바꿈이 바뀌어 시험이 PC마다 달라지지 않게).
def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


# 파일을 고쳐 쓰고 그것만 스테이징해 커밋한다(rel은 저장소 뿌리 기준 경로).
def commit_file(repo: Path, rel: str, text: str) -> None:
    write(repo / rel, text)
    git(repo, "add", rel)
    git(repo, "commit", "--quiet", "-m", f"change {rel}")


# 임시 git 저장소 하나에 이 구성 요소 폴더 comp/(추적 파일 a.txt)와 다른 구성 요소 폴더 other/(추적 파일
# b.txt)를 첫 커밋으로 넣고, evaluate.PROJECT_ROOT를 comp/로 바꿔 끼운다. 저장소 뿌리 경로를 돌려준다.
# 주의: pytest의 tmp_path는 이 구성 요소의 .pytest-tmp 아래(진짜 저장소 안의, 추적하지 않는 폴더)다. 그 안에서
# git init한 폴더는 자기 .git이 먼저 잡히므로 진짜 저장소와 섞이지 않는다.
@pytest.fixture
def two_folders(tmp_path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    (repo / "comp").mkdir(parents=True)
    (repo / "other").mkdir()
    write(repo / "comp" / "a.txt", "a\n")
    write(repo / "other" / "b.txt", "b\n")
    git(repo, "init", "--quiet")
    git(repo, "add", "comp/a.txt", "other/b.txt")
    git(repo, "commit", "--quiet", "-m", "first")
    monkeypatch.setattr(evaluate, "PROJECT_ROOT", repo / "comp")
    return repo


# 다른 폴더(other/)의 추적 파일이 바뀌어도 이 폴더의 변경으로 세지 않고, 이 폴더(comp/)의 추적 파일이
# 바뀌면 센다. 전제로, 경로를 한정하지 않은 예전 검사(저장소 전체)는 other/의 변경을 센다는 것도 확인한다:
# 그렇지 않으면 이 시험은 범위를 좁히지 않아도 통과하는 시험이 된다.
def test_changes_in_another_folder_do_not_count(two_folders):
    repo = two_folders
    write(repo / "other" / "b.txt", "b changed\n")
    # 전제: 경로를 한정하지 않고 저장소 전체로 보면 이 변경이 센다
    assert evaluate._git("status", "--porcelain", "--untracked-files=no") != ""
    assert evaluate._git(*evaluate.SCOPED_STATUS) == ""
    write(repo / "comp" / "a.txt", "a changed\n")
    assert evaluate._git(*evaluate.SCOPED_STATUS) != ""


# 추적하지 않는 파일은 지금처럼 세지 않는다(--untracked-files=no). 전제로, 그 옵션 없이 보면 새 파일이
# 센다는 것을 확인한다.
def test_untracked_files_are_still_not_counted(two_folders):
    repo = two_folders
    write(repo / "comp" / "new.txt", "untracked\n")
    # 전제: --untracked-files=no 없이 같은 경로를 보면 이 새 파일이 센다
    assert evaluate._git("status", "--porcelain", "--", ".") != ""
    assert evaluate._git(*evaluate.SCOPED_STATUS) == ""


# git_tree의 값(TREE_REF)은 이 폴더의 커밋된 내용의 트리 해시다: 40자이고 git rev-parse HEAD:comp와 같다.
# 다른 폴더만 고친 커밋으로는 커밋 해시가 달라져도 트리 해시는 그대로이고, 이 폴더를 고친 커밋 뒤에는
# 달라진다. 작업 트리의 커밋하지 않은 변경은 트리 해시에 나타나지 않는다(그것은 SCOPED_STATUS가 본다).
def test_tree_is_the_folder_tree(two_folders):
    repo = two_folders
    tree = evaluate._git("rev-parse", evaluate.TREE_REF)
    assert len(tree) == 40
    assert tree == git(repo, "rev-parse", "HEAD:comp")

    commit = evaluate._git("rev-parse", "HEAD")
    commit_file(repo, "other/b.txt", "b changed\n")
    assert evaluate._git("rev-parse", "HEAD") != commit  # 커밋은 달라졌지만
    assert evaluate._git("rev-parse", evaluate.TREE_REF) == tree  # 이 폴더의 트리는 그대로다

    write(repo / "comp" / "a.txt", "a changed but not committed\n")
    assert evaluate._git("rev-parse", evaluate.TREE_REF) == tree  # 커밋하지 않은 변경은 가리키지 않는다

    commit_file(repo, "comp/a.txt", "a changed\n")
    changed = evaluate._git("rev-parse", evaluate.TREE_REF)
    assert changed != tree and changed == git(repo, "rev-parse", "HEAD:comp")


# 이 폴더가 저장소의 맨 위이면(이 폴더만 따로 받은 저장소) 같은 코드가 그대로 돈다: 트리 해시는 저장소 전체의
# 트리(HEAD^{tree})와 같고, 경로 한정(-- .)이 저장소 전체와 같아져 어느 폴더의 변경이든 센다.
def test_folder_at_the_repository_root_gives_the_root_tree(two_folders, monkeypatch):
    repo = two_folders
    monkeypatch.setattr(evaluate, "PROJECT_ROOT", repo)
    root_tree = evaluate._git("rev-parse", evaluate.TREE_REF)
    assert len(root_tree) == 40 and root_tree == git(repo, "rev-parse", "HEAD^{tree}")
    assert root_tree != git(repo, "rev-parse", "HEAD:comp")  # 하위 폴더의 트리와는 다르다
    write(repo / "other" / "b.txt", "b changed\n")
    assert evaluate._git(*evaluate.SCOPED_STATUS) != ""


# 범위는 프로세스의 작업 폴더가 아니라 코드가 있는 폴더(PROJECT_ROOT)로 잡는다. 도구를 다른 구성 요소 폴더나
# 하위 폴더, 임시 폴더에서 돌려도 같은 폴더를 보고, 작업 폴더 안의 변경은 이 폴더의 변경이 아니다. 트리 해시도
# 작업 폴더가 아니라 PROJECT_ROOT의 것이다.
def test_scope_follows_the_code_location_not_the_working_directory(two_folders, monkeypatch):
    repo = two_folders
    tree = evaluate._git("rev-parse", evaluate.TREE_REF)
    monkeypatch.chdir(repo / "other")
    write(repo / "other" / "b.txt", "b changed\n")  # 작업 폴더 안의 변경: 이 폴더의 변경이 아니다
    assert evaluate._git(*evaluate.SCOPED_STATUS) == ""
    write(repo / "comp" / "a.txt", "a changed\n")  # 작업 폴더 밖이어도 코드가 있는 폴더의 변경은 센다
    assert evaluate._git(*evaluate.SCOPED_STATUS) != ""
    assert evaluate._git("rev-parse", evaluate.TREE_REF) == tree == git(repo, "rev-parse", "HEAD:comp")


# 공식 실행은 이 폴더의 추적 파일이 바뀌었을 때만 멈춘다: other/만 바뀌었으면 검사를 지나 모델을 만드는 데까지
# 가고(OllamaProvider를 AssertionError를 던지는 함수로 바꿔 둔다), comp/가 바뀌었으면 argparse 오류(종료 코드
# 2)로 멈춘다. 준비는 tests/test_evaluate.py의 공식 실행 시험과 같고, 모델·서버를 부르지 않는다.
def test_official_run_refuses_only_when_this_folder_is_dirty(two_folders, tmp_path, monkeypatch, capsys):
    repo = two_folders
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "dev.jsonl"
    write_jsonl(data, [_item(0).to_dict()])

    def no_model(*a, **kw):
        raise AssertionError("the run got past the clean-tree check")

    monkeypatch.setattr(evaluate, "OllamaProvider", no_model)
    argv = ["--data", str(data), "--model", "m", "--official"]
    write(repo / "other" / "b.txt", "b changed\n")
    with pytest.raises(AssertionError, match="got past the clean-tree check"):
        evaluate.main(argv)
    write(repo / "comp" / "a.txt", "a changed\n")
    with pytest.raises(SystemExit) as stop:
        evaluate.main(argv)
    assert stop.value.code == 2
    assert "to be unchanged" in capsys.readouterr().err  # 이 폴더가 바뀐 것을 보고 멈췄다


# git 저장소가 아닌 곳(압축 파일로 받은 사본 등)에서는 공식 실행이 지금처럼 멈추고(종료 코드 2, 모델을
# 만들기 전), 기록용 값은 지금까지의 규약대로 빈 글이다(git_commit과 새 git_tree 모두).
# 저장소가 아닌 폴더 만들기: tmp_path는 이 구성 요소의 .pytest-tmp 아래라 진짜 저장소 안에 있다. 그래서
# .git이 없는 보통 폴더라도 git이 위 폴더로 올라가며 바깥의 진짜 저장소를 찾아 성공해 버린다.
# GIT_CEILING_DIRECTORIES에 그 폴더의 부모를 주면 git이 그 폴더에서 위로 올라가지 않으므로, .git이 없는 이
# 폴더는 저장소가 아닌 것이 된다. 이 전제가 어긋나면(git이 위로 올라가면) 시험이 아무것도 확인하지 못한 채
# 통과하지 않도록 먼저 단언한다.
def test_official_run_still_stops_when_git_fails(tmp_path, monkeypatch, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    probe = subprocess.run(["git", "rev-parse", "HEAD"], cwd=plain, capture_output=True, text=True)
    assert probe.returncode != 0, "premise failed: git found a repository above the plain folder"

    monkeypatch.setattr(evaluate, "PROJECT_ROOT", plain)
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "dev.jsonl"
    write_jsonl(data, [_item(0).to_dict()])

    def no_model(*a, **kw):
        raise AssertionError("the run got past the clean-tree check")

    monkeypatch.setattr(evaluate, "OllamaProvider", no_model)
    with pytest.raises(SystemExit) as stop:
        evaluate.main(["--data", str(data), "--model", "m", "--official"])
    assert stop.value.code == 2
    assert "--official needs git to verify" in capsys.readouterr().err  # git을 읽지 못해서 멈췄다
    assert evaluate._git("rev-parse", "HEAD") == ""
    assert evaluate._git("rev-parse", evaluate.TREE_REF) == ""


# 서비스 경로 측정의 공식 실행도 이 폴더의 추적 파일만 본다: other/만 바뀌었으면 git 검사를 지나 서비스의
# /ready를 확인하는 데까지 가고(서비스가 준비되지 않은 것으로 흉내 내므로 "needs a ready service"로
# 멈춘다), comp/가 바뀌었으면 서비스에 접속하기 전에 git 검사에서 멈춘다. 어느 쪽에서 멈췄는지는 오류 글과
# 클라이언트를 만든 횟수로 가른다.
def test_service_eval_official_refuses_only_when_this_folder_is_dirty(
    two_folders, tmp_path, monkeypatch, capsys
):
    repo = two_folders
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "dev.jsonl"
    write_jsonl(data, [_item(0).to_dict()])
    clients: list[dict] = []

    # 모델 서버에 닿지 못해 /ready가 503인 서비스를 흉내 내는 클라이언트(httpx.Client 대용). 만든 횟수를 센다.
    class NotReadyClient:
        def __init__(self, **kw):
            clients.append(kw)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, path):
            if path == "/ready":
                return httpx.Response(503, json={"status": "not_ready", "reason": "no_model_server"})
            return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "Client", NotReadyClient)
    argv = ["--data", str(data), "--official"]
    write(repo / "other" / "b.txt", "b changed\n")
    with pytest.raises(SystemExit) as stop:
        service_eval.main(argv)
    assert stop.value.code == 2 and len(clients) == 1  # git 검사를 지나 서비스까지 갔다
    assert "needs a ready service" in capsys.readouterr().err
    write(repo / "comp" / "a.txt", "a changed\n")
    with pytest.raises(SystemExit) as stop:
        service_eval.main(argv)
    assert stop.value.code == 2 and len(clients) == 1  # 서비스에 접속하기 전에 멈췄다
    assert "to be unchanged" in capsys.readouterr().err


# scripts/ctx_probe.py의 시작 전 검사도 이 폴더만 본다: other/만 바뀌었으면 바뀌지 않은 것으로(참),
# comp/가 바뀌었으면 바뀐 것으로(거짓) 돌려준다. 전제로, 저장소 전체로 보면 other/의 변경이 센다는 것도
# 확인한다.
def test_ctx_probe_tree_check_is_folder_scoped(two_folders):
    repo = two_folders
    write(repo / "other" / "b.txt", "b changed\n")
    # 전제: 저장소 전체로 보면 이 변경이 센다
    assert git(repo, "status", "--porcelain", "--untracked-files=no") != ""
    assert probe.tree_is_clean() is True
    write(repo / "comp" / "a.txt", "a changed\n")
    assert probe.tree_is_clean() is False


# 판정 요약의 git_dirty와 git_tree도 이 폴더 기준이다. judge_run의 git 호출을 바꿔 끼우지 않고 임시
# 저장소의 진짜 git으로 본다: other/만 바뀌었으면 git_dirty가 거짓, comp/가 바뀌었으면 참이고, git_tree는
# 두 경우 모두 커밋된 comp의 트리다 (커밋하지 않은 변경은 트리 해시에 나타나지 않는다).
def test_judge_run_summary_git_state_is_folder_scoped(two_folders, tmp_path, monkeypatch):
    repo = two_folders
    _, runs = _runs(tmp_path, n=2)
    monkeypatch.setattr(judge_run, "make_judge", lambda **kw: _Counting(replies=_all_included))
    monkeypatch.setattr(judge_run, "model_fingerprint", lambda p: {})
    monkeypatch.setattr(judge_run, "loaded_models", lambda p: [])

    def summary(name):
        out = runs["A"] / f"judge-{name}.jsonl"
        assert judge_run.main(["--run", str(runs["A"]), "--out", str(out)]) == 0
        return json.loads((runs["A"] / f"judge-{name}_summary.json").read_text(encoding="utf-8"))

    tree = git(repo, "rev-parse", "HEAD:comp")
    write(repo / "other" / "b.txt", "b changed\n")
    first = summary("one")
    assert first["git_dirty"] is False and first["git_tree"] == tree
    write(repo / "comp" / "a.txt", "a changed\n")
    second = summary("two")
    assert second["git_dirty"] is True and second["git_tree"] == tree


# 패키지를 소스 폴더(<구성 요소 폴더>/src)가 아닌 곳에 설치한 사본에서 돌리면, 이 파일의 위치로 잡는
# PROJECT_ROOT가 엉뚱한 폴더를 가리킨다. 그 폴더가 저장소 작업 트리 안의 추적하지 않는 폴더(예: 이 구성 요소의
# 가상환경)인 경우를 흉내 낸다: 저장소 안에 커밋하지 않은 폴더를 만들어 PROJECT_ROOT로 주고, 추적 파일
# comp/a.txt는 바뀐 채로 둔다. 저장소 전체로는 바뀐 것이 보이지만 그 폴더 안에는 추적 파일이 없어서, 경로를
# 한정한 status는 늘 빈 글이다. 그 커밋하지 않은 폴더를 돌려준다.
@pytest.fixture
def uncommitted_folder(two_folders, monkeypatch) -> Path:
    repo = two_folders
    folder = repo / "venv" / "Lib"
    folder.mkdir(parents=True)
    write(folder / "installed_copy.txt", "not tracked\n")
    write(repo / "comp" / "a.txt", "a changed\n")
    # 시나리오 확인: 저장소 전체로 보면 바뀐 추적 파일이 보이고, 이 폴더는 HEAD에 없다(HEAD:./가 풀리지
    # 않는다).
    assert git(repo, "status", "--porcelain", "--untracked-files=no") != ""
    monkeypatch.setattr(evaluate, "PROJECT_ROOT", folder)
    assert evaluate._git("rev-parse", evaluate.TREE_REF) == ""
    return folder


# 공식 실행은 PROJECT_ROOT가 HEAD에 있는 폴더인지도 확인해야 한다. 그러지 않으면 추적하지 않는 폴더에서는
# status가 늘 빈 글이라 추적 파일이 바뀌어 있어도 검사를 통과한다. 전제로 그 빈 글을 먼저 단언한다(그래서
# 이 확인이 필요하다). 오류 글로 어느 검사에서 멈췄는지도 가른다.
def test_official_run_stops_when_this_folder_is_not_in_head(
    uncommitted_folder, tmp_path, monkeypatch, capsys
):
    assert evaluate._git(*evaluate.SCOPED_STATUS) == ""  # 전제: status만 보면 바뀐 추적 파일을 놓친다
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "dev.jsonl"
    write_jsonl(data, [_item(0).to_dict()])

    def no_model(*a, **kw):
        raise AssertionError("the run got past the clean-tree check")

    monkeypatch.setattr(evaluate, "OllamaProvider", no_model)
    with pytest.raises(SystemExit) as stop:
        evaluate.main(["--data", str(data), "--model", "m", "--official"])
    assert stop.value.code == 2
    assert "--official needs git to verify" in capsys.readouterr().err


# 서비스 경로 측정의 공식 실행도 같다: 추적하지 않는 폴더에서는 서비스의 /ready를 확인하기
# 전에(httpx.Client를 만들기 전에) 멈춘다.
def test_service_eval_official_stops_when_this_folder_is_not_in_head(
    uncommitted_folder, tmp_path, monkeypatch, capsys
):
    assert evaluate._git(*evaluate.SCOPED_STATUS) == ""  # 전제: status만 보면 바뀐 추적 파일을 놓친다
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "dev.jsonl"
    write_jsonl(data, [_item(0).to_dict()])

    def no_client(**kw):
        raise AssertionError("the run got past the git check")

    monkeypatch.setattr(httpx, "Client", no_client)
    with pytest.raises(SystemExit) as stop:
        service_eval.main(["--data", str(data), "--official"])
    assert stop.value.code == 2
    assert "--official needs git to verify" in capsys.readouterr().err


# scripts/ctx_probe.py의 시작 전 검사도 같다: 추적하지 않는 폴더에서는 바뀐 것이 없다고 하지 않고 거짓을
# 돌려준다.
def test_ctx_probe_tree_check_fails_when_this_folder_is_not_in_head(uncommitted_folder):
    assert evaluate._git(*evaluate.SCOPED_STATUS) == ""  # 전제: status만 보면 바뀐 추적 파일을 놓친다
    assert probe.tree_is_clean() is False
