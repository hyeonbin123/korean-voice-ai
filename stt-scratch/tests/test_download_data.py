"""데이터 내려받기 스크립트(scripts/download_data.py)의 커밋 고정·기록본 대조·게이트 검사 테스트.

확인하는 성질:
(a) 기본은 출처마다 기록본(reports/data/download-manifest-2026-10-11.json)에 적힌 커밋으로 받는다. 출처의
    브랜치가 그 뒤 움직여 조회한 최신 커밋이 달라도 기록된 커밋으로 받고, 달라졌다는 알림만 낸다.
(b) 최신 커밋은 --allow-new-revision을 줬을 때만 받고, 그때는 기록본과 다르다는 것을 출력에 남긴다.
(c) 기록된 커밋이 허브에서 열리지 않거나 허브가 그 커밋을 확인해 주지 않으면, 어느 출처도 받기 전에 멈춘다.
    --dry-run은 같은 조회만 하고 받지 않는다.
(d) 받은 파일의 목록과 크기(기록본에 SHA-256이 있으면 그것도)가 기록본과 다르면 0이 아닌 종료로 멈춘다.
    --verify는 받지 않고(네트워크 없이) data/raw에 같은 대조만 한다.
(e) manifest.json의 revision은 사람이 읽는 이름(main, refs/convert/parquet)이고 commit_sha가 실제로 받은
    커밋이다. 파일 목록은 local_dir에 실제로 생긴 파일과 크기이고 huggingface_hub의 .cache 폴더는 뺀다.
(f) 게이트 저장소(gated가 "auto"·"manual")면 받지 않고 SystemExit로 멈추며 manifest.json도 쓰지 않는다.
(g) 스크립트에 상수로 박은 커밋이 기록본의 값과 같고, 기록본의 파일은 모두 받는 파일 패턴에 든다.

네트워크는 쓰지 않는다: HfApi와 snapshot_download를 가짜로 바꿔 호출 인자만 기록하고, 기록본은 작은 가짜
파일(출처마다 파일 하나, 7바이트)로 바꿔 끼운다. 가짜 기록본도 저장소·브랜치 이름·커밋은 실제 기록본의 값을
쓰고, (g)는 실제 기록본 파일을 그대로 대조한다.
"""

# [왜 필요한가] 이 스크립트는 받은 저장소의 커밋 sha를 manifest에 남겨 같은 데이터를 특정할 수 있게
# 한다(기록본 reports/data/download-manifest-2026-10-11.json). 그런데 출처 세 곳은 제3자가 올린 사본이거나
# 허브가 다시 만드는 변환 브랜치라, 다시 받을 때 '지금 브랜치가 가리키는 커밋'을 받으면 기록된 측정과 다른
# 데이터가 아무 경고 없이 들어올 수 있다. 그래서 기본 동작을 '기록된 커밋을 받고 기록본과 대조'로
# 고정하고, 새 판은 명시 옵션으로만 받게 했다. 데이터는 이미 받아 두었으므로 스크립트를 실제로 돌리지
# 않고, 호출 인자를 가짜 객체로 가로채 확인한다.
# [방식] scripts/는 패키지가 아니라서 파일 경로로 모듈을 불러온다(tests/test_sealed_breakdown.py와 같은
# 방식). main()은 sys.argv를 읽으므로 monkeypatch로 명령줄 인자를 넣는다. 기록본
# 경로(download_data.RECORD)는 임시 가짜 기록본으로 바꾼다.

from __future__ import annotations

import fnmatch
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

# httpx2: huggingface-hub 2.x가 쓰는 HTTP 클라이언트(uv.lock에 그 의존성으로 들어 있다). 라이브러리가 없는
# 커밋을 조회할 때 던지는 실제 오류 클래스(RevisionNotFoundError)를 만들려면 그 응답 객체가 필요하다.
import httpx2
import pytest
from huggingface_hub.errors import RevisionNotFoundError

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("download_data", REPO / "scripts" / "download_data.py")
download_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(download_data)

# 실제 기록본. 출처 이름 → 항목. 가짜 기록본의 커밋과 (g)의 대조가 이 값을 쓴다.
REAL_RECORD = {
    entry["name"]: entry
    for entry in json.loads(
        (REPO / "reports" / "data" / "download-manifest-2026-10-11.json").read_text(encoding="utf-8")
    )
}
RECORDED = {name: entry["commit_sha"] for name, entry in REAL_RECORD.items()}
# 허브 저장소 이름 → 기록된 커밋(가짜 허브가 '브랜치가 아직 기록된 커밋에 있다'를 흉내 낼 때 쓴다).
UNMOVED = {entry["repo"]: entry["commit_sha"] for entry in REAL_RECORD.values()}
# 브랜치가 기록 뒤에 움직인 경우의 최신 커밋 sha(40자 16진수). 저장소마다 값이 달라 어느 출처의 sha가 어느
# 내려받기로 갔는지 구별된다.
MOVED = {entry["repo"]: str(n) * 40 for n, entry in enumerate(REAL_RECORD.values(), start=1)}

SHA_RE = re.compile(r"[0-9a-f]{40}")
# 가짜 내려받기가 만드는 파일. 가짜 기록본도 출처마다 이 파일 하나를 적는다.
FILE_PATH = "data/part-0.parquet"
FILE_SIZE = 7


def revision_not_found(repo: str, revision: str) -> RevisionNotFoundError:
    """허브가 없는 커밋을 조회했을 때 huggingface_hub가 던지는 오류(404, RevisionNotFound)를 만든다."""
    request = httpx2.Request("GET", f"https://huggingface.co/api/datasets/{repo}/revision/{revision}")
    response = httpx2.Response(404, request=request, headers={"X-Error-Code": "RevisionNotFound"})
    return RevisionNotFoundError("Revision Not Found", response=response)


class FakeHub:
    """HfApi.dataset_info와 snapshot_download를 대신하는 가짜.

    gated: 조회 결과의 gated 값(False면 공개 저장소). pinned_gated: 커밋 sha로 조회했을 때만 다른 gated
    값을 돌려주고 싶을 때의 값(None이면 gated와 같다). latest: 저장소 이름 → 브랜치 이름(main,
    refs/convert/parquet)으로 조회했을 때의 sha(없으면 None). unreachable: 커밋 sha로 조회하면 404를
    던질 저장소. pinned_sha: 커밋 sha로 조회했을 때 돌려줄 sha를 바꿀 저장소(기본은 조회한 sha 그대로).
    info_calls에는 (저장소, revision) 조회 인자를, download_calls에는 snapshot_download의 키워드 인자를
    부른 순서대로 쌓는다. 내려받기 흉내로 local_dir에 file_size바이트 데이터 파일 하나와
    huggingface_hub가 만드는 것과 같은 자리의 .cache 메타데이터 파일 하나를 만든다(manifest에서 .cache가
    빠지는지 보려고).
    """

    def __init__(
        self,
        gated: bool | str = False,
        latest: dict[str, str | None] | None = None,
        unreachable: set[str] | None = None,
        pinned_sha: dict[str, str | None] | None = None,
        file_size: int = FILE_SIZE,
        pinned_gated: bool | str | None = None,
    ) -> None:
        self.gated = gated
        self.pinned_gated = pinned_gated
        self.latest = MOVED if latest is None else latest
        self.unreachable = unreachable or set()
        self.pinned_sha = pinned_sha or {}
        self.file_size = file_size
        self.info_calls: list[tuple[str, str | None]] = []
        self.download_calls: list[dict] = []

    def api(self):
        # main()이 HfApi()로 만드는 객체 자리에 들어간다. main은 dataset_info만 쓴다.
        hub = self

        class _Api:
            def dataset_info(self, repo_id, revision=None, **kwargs):
                hub.info_calls.append((repo_id, revision))
                if revision is not None and SHA_RE.fullmatch(revision):
                    # 커밋 sha로 조회: 열리는 커밋이면 그 sha를 그대로 돌려준다.
                    if repo_id in hub.unreachable:
                        raise revision_not_found(repo_id, revision)
                    gated = hub.gated if hub.pinned_gated is None else hub.pinned_gated
                    return SimpleNamespace(sha=hub.pinned_sha.get(repo_id, revision), gated=gated)
                # 브랜치 이름(None = main)으로 조회: 지금 그 브랜치가 가리키는 커밋.
                return SimpleNamespace(sha=hub.latest.get(repo_id), gated=hub.gated)

        return _Api()

    def snapshot_download(self, **kwargs):
        self.download_calls.append(kwargs)
        local = Path(kwargs["local_dir"])
        (local / "data").mkdir(parents=True, exist_ok=True)
        (local / FILE_PATH).write_bytes(b"x" * self.file_size)
        (local / ".cache" / "huggingface").mkdir(parents=True, exist_ok=True)
        (local / ".cache" / "huggingface" / "meta").write_bytes(b"m")
        return str(local)


def write_record(path: Path, files: dict[str, list[dict]] | None = None) -> Path:
    """작은 가짜 기록본을 쓴다. 출처마다 실제 기록본의 저장소·브랜치 이름·커밋을 쓰고 파일 목록만 바꾼다.

    files: 출처 이름 → 파일 항목 목록({path, bytes[, sha256]}). 없는 출처는 FILE_PATH 하나(FILE_SIZE바이트).
    """
    entries = []
    for name, real in REAL_RECORD.items():
        entry = {key: real[key] for key in ("name", "repo", "revision", "commit_sha", "license", "gated")}
        entry["files"] = (files or {}).get(name, [{"path": FILE_PATH, "bytes": FILE_SIZE}])
        entries.append(entry)
    path.write_text(json.dumps(entries, indent=1), encoding="utf-8")
    return path


@pytest.fixture
def record(tmp_path, monkeypatch):
    """download_data.RECORD를 작은 가짜 기록본으로 바꿔 끼우고 그 경로를 돌려준다."""
    path = write_record(tmp_path / "record.json")
    monkeypatch.setattr(download_data, "RECORD", path)
    return path


def run_cli(monkeypatch, *args: str) -> None:
    """`download_data.py <args...>`를 실행한다(허브는 건드리지 않는다)."""
    monkeypatch.setattr(sys, "argv", ["download_data.py", *args])
    download_data.main()


def run_main(monkeypatch, hub: FakeHub, dest: Path, *args: str) -> None:
    """가짜 허브를 끼우고 `download_data.py --dest <dest> <args...>`를 실행한다."""
    monkeypatch.setattr(download_data, "HfApi", hub.api)
    monkeypatch.setattr(download_data, "snapshot_download", hub.snapshot_download)
    run_cli(monkeypatch, "--dest", str(dest), *args)


def no_network(monkeypatch) -> None:
    """허브를 건드리는 순간 실패하게 한다(--verify는 네트워크를 쓰지 않는다)."""

    def boom(*args, **kwargs):
        raise AssertionError("this mode must not use the network")

    monkeypatch.setattr(download_data, "HfApi", boom)
    monkeypatch.setattr(download_data, "snapshot_download", boom)


def populate(dest: Path, names=("zeroth_korean",), content: bytes = b"x" * FILE_SIZE) -> None:
    """data/raw에 이미 받아 둔 것처럼 출처 폴더에 가짜 데이터 파일을 만든다."""
    for name in names:
        (dest / name / "data").mkdir(parents=True, exist_ok=True)
        (dest / name / FILE_PATH).write_bytes(content)


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# --- (a) 기록된 커밋으로 받는다 -------------------------------------------------------------------


def test_downloads_the_recorded_commit_even_when_the_branch_has_moved(monkeypatch, tmp_path, record, capsys):
    hub = FakeHub(latest=MOVED)
    run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean", "fleurs_ko")

    # 최신 커밋은 브랜치 이름으로(main은 None), 기록된 커밋은 sha로 조회한다. 내려받기는 기록된 커밋으로 한다.
    assert ("kresnik/zeroth_korean", None) in hub.info_calls
    assert ("google/fleurs", "refs/convert/parquet") in hub.info_calls
    assert ("kresnik/zeroth_korean", RECORDED["zeroth_korean"]) in hub.info_calls
    assert ("google/fleurs", RECORDED["fleurs_ko"]) in hub.info_calls
    assert [c["repo_id"] for c in hub.download_calls] == ["kresnik/zeroth_korean", "google/fleurs"]
    assert [c["revision"] for c in hub.download_calls] == [RECORDED["zeroth_korean"], RECORDED["fleurs_ko"]]
    # 받는 파일 패턴·저장소 종류·저장 위치는 바뀌지 않는다.
    fleurs = hub.download_calls[1]
    assert fleurs["repo_type"] == "dataset"
    assert fleurs["allow_patterns"] == ["ko_kr/*/*.parquet"]
    assert Path(fleurs["local_dir"]) == tmp_path / "raw" / "fleurs_ko"

    # manifest: revision은 이름 그대로, commit_sha는 실제로 받은 커밋(= 기록된 커밋), 파일 목록에는
    # .cache가 없다.
    manifest = json.loads((tmp_path / "raw" / "manifest.json").read_text(encoding="utf-8"))
    assert [(m["name"], m["revision"], m["commit_sha"]) for m in manifest] == [
        ("zeroth_korean", "main", RECORDED["zeroth_korean"]),
        ("fleurs_ko", "refs/convert/parquet", RECORDED["fleurs_ko"]),
    ]
    assert all(m["commit_sha"] == c["revision"] for m, c in zip(manifest, hub.download_calls, strict=True))
    assert manifest[0]["files"] == [{"path": FILE_PATH, "bytes": FILE_SIZE}]

    # 브랜치가 움직였다는 알림은 나오되(어느 커밋으로 받는지, 새 판을 받는 옵션 이름과 함께) 실패하지 않는다.
    err = capsys.readouterr().err
    assert MOVED["kresnik/zeroth_korean"] in err and RECORDED["zeroth_korean"] in err
    assert "--allow-new-revision" in err
    assert "WARNING" not in err  # 기록된 커밋을 받았으니 '기록본과 다르다'는 마지막 경고는 없다


def test_no_note_when_the_branch_still_points_at_the_recorded_commit(monkeypatch, tmp_path, record, capsys):
    hub = FakeHub(latest=UNMOVED)
    run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean")

    assert [c["revision"] for c in hub.download_calls] == [RECORDED["zeroth_korean"]]
    assert "--allow-new-revision" not in capsys.readouterr().err


# --- (b) 새 판은 명시 옵션으로만 ------------------------------------------------------------------


def test_allow_new_revision_downloads_the_latest_commit_and_says_it_differs_from_the_record(
    monkeypatch, tmp_path, record, capsys
):
    hub = FakeHub(latest=MOVED, file_size=9)  # 새 판은 파일 크기도 다르다고 하자
    run_main(
        monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean", "fleurs_ko", "--allow-new-revision"
    )

    assert [c["revision"] for c in hub.download_calls] == [
        MOVED["kresnik/zeroth_korean"],
        MOVED["google/fleurs"],
    ]
    manifest = json.loads((tmp_path / "raw" / "manifest.json").read_text(encoding="utf-8"))
    assert [m["commit_sha"] for m in manifest] == [MOVED["kresnik/zeroth_korean"], MOVED["google/fleurs"]]

    # 기록본과 다르다는 것이 출력에 분명히 남는다: 바뀐 커밋 두 개(기록된 것과 받은 것), 파일 크기 차이,
    # 출처 이름.
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert "differs from the record" in text
    for name, repo in (("zeroth_korean", "kresnik/zeroth_korean"), ("fleurs_ko", "google/fleurs")):
        assert name in text and MOVED[repo] in text and RECORDED[name] in text
    assert f"{FILE_PATH}: 9 bytes, record {FILE_SIZE}" in text

    # 맨 마지막 줄은 도움말이 약속한 경고다: 기록본과 다른 출처 이름을 들어, 받은 데이터가 기록된 측정이 쓴
    # 것과 같지 않아 결과를 견줄 수 없다고 끝에서 다시 알린다(위 계획 단계의 NEW REVISION 줄과는 따로 나온다).
    last = captured.err.strip().splitlines()[-1]
    assert last.startswith("WARNING: zeroth_korean, fleurs_ko differ from the record")
    assert "not comparable with the recorded ones" in last


def test_allow_new_revision_is_quiet_when_the_branch_has_not_moved(monkeypatch, tmp_path, record, capsys):
    hub = FakeHub(latest=UNMOVED)
    run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean", "--allow-new-revision")

    assert [c["revision"] for c in hub.download_calls] == [RECORDED["zeroth_korean"]]
    captured = capsys.readouterr()
    assert "differs from the record" not in captured.out + captured.err
    assert "WARNING" not in captured.err  # 기록된 커밋을 받았으니 마지막 경고도 없다


def test_allow_new_revision_stops_when_the_lookup_has_no_commit_sha(monkeypatch, tmp_path, record):
    hub = FakeHub(latest={})  # 조회 결과에 sha가 없다
    with pytest.raises(SystemExit, match="commit sha"):
        run_main(monkeypatch, hub, tmp_path / "raw", "--only", "fleurs_ko", "--allow-new-revision")
    assert hub.info_calls == [("google/fleurs", "refs/convert/parquet")]
    assert hub.download_calls == []
    assert not (tmp_path / "raw" / "manifest.json").exists()


# --- (c) 기록된 커밋이 열리지 않으면 받기 전에 멈춘다 ---------------------------------------------


def test_unreachable_recorded_commit_stops_before_anything_is_downloaded(monkeypatch, tmp_path, record):
    hub = FakeHub(unreachable={"google/fleurs"})
    with pytest.raises(SystemExit) as info:
        run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean", "fleurs_ko")

    # 둘째 출처의 커밋이 없어도 첫째 출처를 받기 전에 멈춘다. 메시지는 어느 커밋이 안 열리는지와 다음 길을
    # 알린다.
    message = str(info.value)
    assert RECORDED["fleurs_ko"] in message and "google/fleurs" in message
    assert "--allow-new-revision" in message and "--verify" in message
    assert hub.download_calls == []
    assert not (tmp_path / "raw" / "manifest.json").exists()


def test_a_commit_the_hub_does_not_confirm_stops_the_download(monkeypatch, tmp_path, record):
    # 허브가 다른 sha(또는 sha 없음)를 돌려주면 그 커밋을 받는지 알 수 없으므로 받지 않는다.
    for answer in ("e" * 40, None):
        hub = FakeHub(pinned_sha={"kresnik/zeroth_korean": answer})
        with pytest.raises(SystemExit, match="did not confirm"):
            run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean")
        assert hub.download_calls == []


def test_dry_run_looks_up_the_commits_and_downloads_nothing(monkeypatch, tmp_path, record, capsys):
    hub = FakeHub(latest={"kresnik/zeroth_korean": RECORDED["zeroth_korean"], "google/fleurs": "2" * 40})
    run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean", "fleurs_ko", "--dry-run")

    assert hub.download_calls == []
    assert not (tmp_path / "raw").exists()  # 폴더도 만들지 않는다
    assert ("google/fleurs", RECORDED["fleurs_ko"]) in hub.info_calls
    captured = capsys.readouterr()
    assert RECORDED["zeroth_korean"] in captured.out and RECORDED["fleurs_ko"] in captured.out
    assert "dry run" in captured.out
    assert "2" * 40 in captured.err  # 브랜치가 움직였다는 알림


def test_dry_run_fails_when_a_recorded_commit_does_not_open(monkeypatch, tmp_path, record):
    hub = FakeHub(unreachable={"kresnik/zeroth_korean"})
    with pytest.raises(SystemExit, match="cannot be opened"):
        run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean", "--dry-run")


# --- (d) 받은 파일을 기록본과 대조한다 ------------------------------------------------------------


def test_download_stops_when_a_downloaded_file_differs_from_the_record(monkeypatch, tmp_path, record):
    hub = FakeHub(file_size=8)  # 기록본은 7바이트
    with pytest.raises(SystemExit) as info:
        run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean")

    assert f"{FILE_PATH}: 8 bytes, record {FILE_SIZE}" in str(info.value)
    assert not (tmp_path / "raw" / "manifest.json").exists()


def test_download_stops_when_the_folder_holds_a_file_the_record_does_not_list(monkeypatch, tmp_path, record):
    # 전에 --allow-new-revision으로 받은 새 판의 파일이 남은 것처럼, 기록본에 없는 파일이 폴더에 있으면
    # 받은 뒤 대조에서 멈춘다(snapshot_download는 파일을 지우지 않는다).
    populate(tmp_path / "raw")
    (tmp_path / "raw" / "zeroth_korean" / "data" / "old.parquet").write_bytes(b"old")
    with pytest.raises(SystemExit) as info:
        run_main(monkeypatch, FakeHub(), tmp_path / "raw", "--only", "zeroth_korean")

    assert "data/old.parquet: not in the record" in str(info.value)
    assert not (tmp_path / "raw" / "manifest.json").exists()


def test_download_compares_sha256_when_the_record_lists_it(monkeypatch, tmp_path):
    # 기록본에 해시가 있으면 받은 뒤 대조도 크기만이 아니라 SHA-256까지 본다(가짜 내려받기의 내용은
    # 7바이트 'x').
    content = b"x" * FILE_SIZE
    for digest, ok in ((sha(content), True), (sha(b"y" * FILE_SIZE), False)):
        record_path = write_record(
            tmp_path / "record.json",
            files={"zeroth_korean": [{"path": FILE_PATH, "bytes": FILE_SIZE, "sha256": digest}]},
        )
        monkeypatch.setattr(download_data, "RECORD", record_path)
        raw = tmp_path / ("ok" if ok else "bad")
        hub = FakeHub()
        if ok:
            run_main(monkeypatch, hub, raw, "--only", "zeroth_korean")
            assert (raw / "manifest.json").exists()
        else:
            with pytest.raises(SystemExit, match=f"{FILE_PATH}: SHA-256 differs from the record"):
                run_main(monkeypatch, hub, raw, "--only", "zeroth_korean")
            assert not (raw / "manifest.json").exists()


def test_verify_passes_when_the_files_match_the_record_and_uses_no_network(
    monkeypatch, tmp_path, record, capsys
):
    populate(tmp_path / "raw", names=("zeroth_korean", "fleurs_ko"))
    no_network(monkeypatch)
    run_cli(monkeypatch, "--dest", str(tmp_path / "raw"), "--only", "zeroth_korean", "fleurs_ko", "--verify")

    out = capsys.readouterr().out
    assert "zeroth_korean" in out and "fleurs_ko" in out
    # 이 기록본에는 SHA-256이 없어 크기까지만 본다는 것, 따라서 못 잡는 것이 무엇인지를 출력이 말한다.
    assert "the record has no SHA-256" in out and "size" in out


def test_verify_reports_missing_extra_and_wrong_sized_files(monkeypatch, tmp_path):
    record_path = write_record(
        tmp_path / "record.json",
        files={
            "zeroth_korean": [
                {"path": "data/a.parquet", "bytes": 3},
                {"path": "data/b.parquet", "bytes": 4},
                {"path": "data/c.parquet", "bytes": 5},
            ]
        },
    )
    monkeypatch.setattr(download_data, "RECORD", record_path)
    folder = tmp_path / "raw" / "zeroth_korean" / "data"
    folder.mkdir(parents=True)
    (folder / "a.parquet").write_bytes(b"123")  # 맞다
    (folder / "b.parquet").write_bytes(b"12345")  # 크기가 다르다
    (folder / "extra.parquet").write_bytes(b"1")  # 기록에 없다
    no_network(monkeypatch)

    with pytest.raises(SystemExit) as info:
        run_cli(monkeypatch, "--dest", str(tmp_path / "raw"), "--only", "zeroth_korean", "--verify")
    message = str(info.value)
    assert "data/b.parquet: 5 bytes, record 4" in message
    assert "data/c.parquet: missing" in message
    assert "data/extra.parquet: not in the record" in message
    assert "data/a.parquet" not in message


def test_verify_compares_sha256_when_the_record_lists_it(monkeypatch, tmp_path, capsys):
    good = b"abcdefg"
    record_path = write_record(
        tmp_path / "record.json",
        files={"zeroth_korean": [{"path": FILE_PATH, "bytes": len(good), "sha256": sha(good)}]},
    )
    monkeypatch.setattr(download_data, "RECORD", record_path)
    no_network(monkeypatch)
    args = ("--dest", str(tmp_path / "raw"), "--only", "zeroth_korean", "--verify")

    # 크기는 같고 내용만 다른 파일은 SHA-256만 잡는다.
    populate(tmp_path / "raw", content=b"abcdefh")
    with pytest.raises(SystemExit, match=f"{FILE_PATH}: SHA-256 differs from the record"):
        run_cli(monkeypatch, *args)
    capsys.readouterr()  # 실패한 실행의 출력은 버리고, 아래 통과 실행의 출력만 본다

    populate(tmp_path / "raw", content=good)
    run_cli(monkeypatch, *args)
    out = capsys.readouterr().out
    assert "SHA-256 compared for 1 of 1 files" in out
    assert "the record has no SHA-256" not in out


def test_verify_ignores_the_download_cache_folder(monkeypatch, tmp_path, record):
    populate(tmp_path / "raw")
    (tmp_path / "raw" / "zeroth_korean" / ".cache" / "huggingface").mkdir(parents=True)
    (tmp_path / "raw" / "zeroth_korean" / ".cache" / "huggingface" / "meta").write_bytes(b"m")
    no_network(monkeypatch)
    run_cli(monkeypatch, "--dest", str(tmp_path / "raw"), "--only", "zeroth_korean", "--verify")


def test_verify_stops_when_a_source_folder_is_missing_and_creates_nothing(monkeypatch, tmp_path, record):
    populate(tmp_path / "raw", names=("zeroth_korean",))
    no_network(monkeypatch)
    both = ("--only", "zeroth_korean", "fleurs_ko", "--verify")
    with pytest.raises(SystemExit, match="fleurs_ko"):
        run_cli(monkeypatch, "--dest", str(tmp_path / "raw"), *both)
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, "--dest", str(tmp_path / "nothing"), "--only", "zeroth_korean", "--verify")
    assert not (tmp_path / "nothing").exists()


def test_verify_flags_a_manifest_that_names_another_commit(monkeypatch, tmp_path, record):
    # manifest.json은 통과의 근거로 쓰지 않는다. 다만 기록과 다른 커밋을 적었다면(새 판을 일부러 받은
    # 흔적) 실패시킨다.
    populate(tmp_path / "raw")
    no_network(monkeypatch)
    manifest = tmp_path / "raw" / "manifest.json"
    args = ("--dest", str(tmp_path / "raw"), "--only", "zeroth_korean", "--verify")

    same = [{"name": "zeroth_korean", "commit_sha": RECORDED["zeroth_korean"]}]
    manifest.write_text(json.dumps(same), encoding="utf-8")
    run_cli(monkeypatch, *args)

    other = [{"name": "zeroth_korean", "commit_sha": "1" * 40}]
    manifest.write_text(json.dumps(other), encoding="utf-8")
    with pytest.raises(SystemExit, match="manifest.json"):
        run_cli(monkeypatch, *args)


# --- (f) 게이트 -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode",
    [(), ("--allow-new-revision",), ("--dry-run",)],
    ids=["default", "allow-new-revision", "dry-run"],
)
@pytest.mark.parametrize("gated", ["auto", "manual"])
def test_gated_repository_stops_before_download(monkeypatch, tmp_path, record, gated, mode):
    # 동의가 필요한 저장소는 기본 실행, 새 판을 받는 실행, 조회만 하는 실행 어디서든 받지 않고 멈춘다.
    hub = FakeHub(gated=gated)
    with pytest.raises(SystemExit, match="gated") as info:
        run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean", *mode)

    # 0이 아닌 종료: SystemExit의 값이 문자열 메시지이면 프로세스 종료 상태는 1이다(0도 None도 아니다).
    assert info.value.code not in (None, 0)
    # 게이트는 브랜치 이름(main은 None)으로 한 첫 조회의 결과로 바로 판정한다. 기록된 커밋의 조회와 내려받기는
    # 그 뒤라서, 게이트 저장소에는 어느 모드에서든 조회가 정확히 이 한 번뿐이다. 호출 목록을 정확히 비교해야
    # 첫 조회의 게이트 검사가 빠져 둘째 검사(기록된 커밋 조회)가 대신 막는 경우도 잡힌다.
    assert hub.info_calls == [("kresnik/zeroth_korean", None)]
    assert hub.download_calls == []
    assert not (tmp_path / "raw").exists()  # 폴더도 manifest도 만들지 않는다


def test_a_gate_reported_only_for_the_recorded_commit_also_stops(monkeypatch, tmp_path, record):
    # 브랜치 이름으로 한 조회는 공개로 답하고 기록된 커밋으로 한 조회만 게이트로 답해도 그 커밋을 받지 않는다.
    # 허브가 한 저장소에 두 조회를 다르게 답하는 경우는 보지 못했지만, 코드는 두 결과를 각각 본다.
    hub = FakeHub(gated=False, pinned_gated="auto")
    with pytest.raises(SystemExit, match="gated"):
        run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean")

    assert hub.info_calls == [
        ("kresnik/zeroth_korean", None),
        ("kresnik/zeroth_korean", RECORDED["zeroth_korean"]),
    ]
    assert hub.download_calls == []
    assert not (tmp_path / "raw").exists()


# --- (g) 스크립트 상수와 기록본 -------------------------------------------------------------------


def test_pinned_commits_are_the_recorded_ones():
    sources = {src["name"]: src for src in download_data.SOURCES}
    assert set(sources) == set(REAL_RECORD)
    for name, entry in REAL_RECORD.items():
        src = sources[name]
        assert src["recorded_sha"] == entry["commit_sha"], name
        assert SHA_RE.fullmatch(src["recorded_sha"]), name
        assert src["repo"] == entry["repo"] and (src["revision"] or "main") == entry["revision"], name
        assert src["license"] == entry["license"] and entry["gated"] is False, name


def test_a_record_that_disagrees_with_the_pinned_commit_stops_before_any_lookup(
    monkeypatch, tmp_path, record
):
    # 스크립트의 상수와 기록본 가운데 하나만 고쳐지면 '기록된 커밋으로 받는다'가 기록본이 아닌 커밋을
    # 받게 되므로, 허브를 부르기 전에 멈춘다(--verify도 같은 이유로 멈춘다).
    entries = json.loads(record.read_text(encoding="utf-8"))
    entries[0]["commit_sha"] = "f" * 40
    record.write_text(json.dumps(entries), encoding="utf-8")
    hub = FakeHub()
    with pytest.raises(SystemExit, match="agree"):
        run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean")
    assert hub.info_calls == [] and hub.download_calls == []
    no_network(monkeypatch)
    with pytest.raises(SystemExit, match="agree"):
        run_cli(monkeypatch, "--dest", str(tmp_path / "raw"), "--only", "zeroth_korean", "--verify")


def test_a_missing_record_stops_because_there_is_nothing_to_compare_with(monkeypatch, tmp_path):
    monkeypatch.setattr(download_data, "RECORD", tmp_path / "no-such-record.json")
    hub = FakeHub()
    with pytest.raises(SystemExit, match="is missing"):
        run_main(monkeypatch, hub, tmp_path / "raw", "--only", "zeroth_korean")
    assert hub.info_calls == [] and hub.download_calls == []


def test_every_recorded_file_matches_an_allowed_pattern():
    # 받는 파일 패턴을 고치면 기록본의 파일이 빠지거나 기록에 없는 파일이 들어와 대조가 실패한다. 그 전에
    # 잡는다.
    for src in download_data.SOURCES:
        for file in REAL_RECORD[src["name"]]["files"]:
            assert any(fnmatch.fnmatch(file["path"], pattern) for pattern in src["allow"]), (
                src["name"],
                file["path"],
            )


# --- 명령줄 ---------------------------------------------------------------------------------------


def test_help_describes_the_new_options(monkeypatch, capsys):
    with pytest.raises(SystemExit) as info:
        run_cli(monkeypatch, "--help")
    assert info.value.code == 0
    out = capsys.readouterr().out
    for option in ("--allow-new-revision", "--verify", "--dry-run", "--only", "--dest"):
        assert option in out


@pytest.mark.parametrize(
    "args",
    [
        ("--verify", "--allow-new-revision"),
        ("--verify", "--dry-run"),
        ("--only", "no_such_source"),
    ],
)
def test_conflicting_or_unknown_arguments_are_rejected(monkeypatch, tmp_path, capsys, args):
    no_network(monkeypatch)
    with pytest.raises(SystemExit) as info:
        run_cli(monkeypatch, "--dest", str(tmp_path / "raw"), *args)
    assert info.value.code == 2  # argparse의 사용법 오류
    assert not (tmp_path / "raw").exists()
