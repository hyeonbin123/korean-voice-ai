"""공개 한국어 음성 코퍼스를 Hugging Face Hub에서 data/raw/ 아래로 내려받고, 받은 파일을 기록본과 대조한다.

출처(모두 Hugging Face Hub에서 게이트가 없는 저장소이며, 받기 전에 실행 중에 다시 확인한다):
- kresnik/zeroth_korean          Zeroth-Korean, CC BY 4.0, parquet(train 6조각 + test)
- google/fleurs  (ko_kr)         FLEURS 한국어, CC BY 4.0, refs/convert/parquet 브랜치의 parquet
- fsicoli/common_voice_17_0 (ko) Common Voice 17 한국어 미러, CC0 1.0, 오디오 tar + 전사 tsv
- fsicoli/common_voice_22_0 (ko) Common Voice 22 한국어 미러, CC0 1.0(실제로 씀, 17은 폴백으로 둠)

0단계 데이터 준비의 첫 명령이다(README).

사용법(경로는 현재 작업 폴더 기준이므로 stt-scratch 폴더에서 실행한다):
    uv run python scripts/download_data.py
        기록된 커밋으로 받고, 받은 파일을 기록본과 대조한다.
    uv run python scripts/download_data.py --only zeroth_korean
        일부 출처만 받는다(이름은 SOURCES의 name).
    uv run python scripts/download_data.py --dry-run
        받지 않고 출처마다 받을 커밋만 조회한다(기록된 커밋이 지금도 열리는지, 브랜치가 움직였는지).
    uv run python scripts/download_data.py --verify
        받지 않고(네트워크 없이) data/raw를 기록본과 대조한다.
    uv run python scripts/download_data.py --allow-new-revision
        기록된 커밋이 아니라 지금의 최신 커밋을 일부러 받는다(기록본과 다른 데이터).
출처마다 기록본(reports/data/download-manifest-2026-10-11.json)에 적힌 커밋을 SOURCES의 recorded_sha로 두고
기본으로 그 커밋을 받는다. 받은 모든 출처의 revision 이름·실제로 받은 커밋 sha·파일 목록·크기를
<dest>/manifest.json에 쓴다.
"""

# [왜 필요한가] 데이터 원칙은 "계정이나 약관 동의 없이 받을 수 있는 공개 한국어 음성만
# 쓴다"이다(docs/data.md). 그래서 받기 전에 저장소가 게이트(접근 승인·약관 동의 필요)인지 확인하고,
# 게이트면 받지 않고 멈춘다. 커밋 sha를 남기는 이유는 나중에 같은 데이터를 다시 받거나 결과를 재현할 때
# 버전을 특정하기 위해서다(기록본: reports/data/download-manifest-2026-10-11.json).
# [기록된 커밋으로 받는다] 출처 셋(Zeroth-Korean, Common Voice 17·22)은 제3자가 올린 사본이고 FLEURS는
# 허브가 원본을 다시 변환해 만드는 브랜치(refs/convert/parquet)다. 다시 받을 때 '브랜치가 지금 가리키는
# 커밋'을 받으면, 사본이 바뀌었거나 변환이 다시 돌았을 때 기록된 측정(학습·평가)과 다른 데이터가 아무 경고
# 없이 들어오고 새 manifest에는 그 커밋이 정상인 듯 적힌다. 이전에는 조회한 최신 커밋으로 받았으므로
# 기록본과 같은지는 사람이 commit_sha를 눈으로 대조해야 했다. 지금은 출처마다 기록본의 커밋을 SOURCES의
# recorded_sha 상수로 두고 기본으로 그 커밋을 받는다. 브랜치가 움직였으면 알리기만 하고, 최신 커밋은
# --allow-new-revision을 줬을 때만 받으며 그때는 기록본과 다르다는 것을 출력에 남긴다. 같은 저장소의
# whisper-ko-ft가 받은 파일을 커밋된 manifest와 대조하는 것(download --verify)과 같은 생각이다.
# [받은 파일의 대조] 받은 뒤(그리고 --verify로 따로) 출처 폴더의 파일 목록과 크기를 기록본과 견준다.
# 기록본에는 파일마다 경로와 크기만 있고 SHA-256이 없어서(2026-10-11 실행은 해시를 남기지 않았다) 지금
# 대조는 목록(빠진 파일·기록에 없는 파일)과 크기까지만 본다. 크기가 같은 채 내용만 바뀐 파일은 이 대조로
# 잡히지 않고, 그 부분은 기록된 커밋으로 받는 것이 맡는다(커밋 sha가 그 시점의 파일 목록과 내용을 정한다).
# 기록본의 파일 항목에 sha256이 있으면 크기가 같은 파일은 SHA-256도 견준다. 이 대조가 잡는 것은 받다가
# 끊긴 파일과 다른 커밋의 파일이 섞인 폴더다(snapshot_download는 파일을 지우지 않으므로, 전에 새 판을 받아
# 둔 폴더에는 새 판의 파일이 그대로 남는다).
# [커밋이 열리지 않을 때] 기록된 커밋이 허브에서 열리지 않게 되면(출처가 이력을 고쳐 쓰거나 변환 브랜치가
# 다시 만들어진 경우) 그 출처는 기록된 커밋으로 받을 수 없다. 기본 실행은 어느 출처도 받기 전에 멈춘다. 그
# 출처를 받으려면 --allow-new-revision으로 지금의 커밋을 받고 --verify로 파일 목록과 크기만 기록본과
# 견준다(이 경우 내용은 보증되지 않는다).
# [흐름] 출처 목록(SOURCES)마다 게이트 확인과 받을 커밋 조회를 먼저 모두 한 뒤(조회만 하는 --dry-run은
# 여기까지), 출처마다 그 커밋에서 허용 패턴에 맞는 파일만 snapshot_download → 받은 파일 목록과 크기를
# manifest에 추가하고 기록본과 대조 → 마지막에 manifest.json 저장. 조회를 모두 먼저 하는 이유는 어느 한
# 출처가 막혔을 때(게이트, 열리지 않는 커밋) 앞 출처를 몇 GB나 받은 뒤에야 멈추는 일이 없게 하려는 것이다.
# [연결] 받은 원본은 scripts/inventory_data.py(재고 조사)와 scripts/prepare_data.py(정규화·분할·PCM
# 저장소)가 읽는다. prepare_data.py는 원본을 기록본과 견주지 않으므로 그 전에 --verify로 확인한다.

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# huggingface_hub: HfApi.dataset_info로 저장소의 게이트 여부와 커밋 sha를 조회하고, snapshot_download로
# 필요한 파일만 골라 받는다(datasets 라이브러리로 전체를 불러오지 않고 원본 파일 그대로 받는다).
# HfHubHTTPError는 허브가 404·5xx 같은 HTTP 오류로 답했을 때의 예외 뿌리이고, 없는 커밋을 조회하면 그 하위
# RevisionNotFoundError가 난다.
from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.errors import HfHubHTTPError

# 기록본: 이 스크립트의 2026-10-11 실행이 남긴 출처별 커밋·파일 목록·크기(커밋된 파일, 고치지 않는다). 이
# 파일의 위치를 기준으로 찾으므로 작업 폴더와 무관하다. 시험은 이 값을 임시 가짜 기록본으로 바꿔 끼운다.
RECORD = Path(__file__).resolve().parents[1] / "reports" / "data" / "download-manifest-2026-10-11.json"

# 내려받을 출처 목록. 각 항목: name(로컬 폴더 이름), repo(HF 데이터셋 저장소), revision(커밋을 조회할
# 브랜치 이름, None이면 main), recorded_sha(기록된 커밋, 아래), allow(받을 파일 패턴),
# license(docs/data.md 표와 같은 라이선스 표기).
# - recorded_sha: 기록본(reports/data/download-manifest-2026-10-11.json)의 출처별 commit_sha를 그대로 옮긴
#   값이다. 기록된 학습·평가에 쓴 데이터를 받을 때 조회한 커밋이고, 그 커밋의 파일 크기가 기록본과 같고 그
#   뒤 브랜치가 움직이지 않았음을 메타데이터 조회로 확인했다(docs/data.md, docs/security.md). 기본으로 이
#   커밋을 받는다. 값을 바꾸려면 기록본도 함께 새로 정해야 하며, tests/test_download_data.py가 두 값이
#   같은지 본다.
# - Zeroth-Korean: README와 parquet(16 kHz FLAC 음성 포함)만.
# - FLEURS: HF가 parquet로 변환해 둔 refs/convert/parquet 브랜치에서 한국어(ko_kr) parquet만
#   받는다(docs/data.md 출처 표).
# - Common Voice 17·22: 공식 저장소는 계정이 필요해 CC0 미러(fsicoli)에서 ko 오디오 tar와 전사 tsv만
#   받는다. 실제로 쓰는 것은 22이고 17은 22를 못 쓰게 될 때의 폴백이다(docs/data.md).
SOURCES = [
    {
        "name": "zeroth_korean",
        "repo": "kresnik/zeroth_korean",
        "revision": None,
        "recorded_sha": "1fe937899f828af822293d05e086200946088bdf",
        "allow": ["README.md", "data/*.parquet"],
        "license": "CC BY 4.0",
    },
    {
        "name": "fleurs_ko",
        "repo": "google/fleurs",
        "revision": "refs/convert/parquet",
        "recorded_sha": "168de341b3db6859a9bac1c50a2ef5e3b47647e0",
        "allow": ["ko_kr/*/*.parquet"],
        "license": "CC BY 4.0",
    },
    {
        "name": "common_voice_17_ko",
        "repo": "fsicoli/common_voice_17_0",
        "revision": None,
        "recorded_sha": "8262c16bf297c87a9cd88c51997c4758ed7a8ba2",
        "allow": ["README.md", "audio/ko/*/*.tar", "transcript/ko/*.tsv"],
        "license": "CC0 1.0",
    },
    {
        "name": "common_voice_22_ko",
        "repo": "fsicoli/common_voice_22_0",
        "revision": None,
        "recorded_sha": "ae911de250fe9375d08e2daa2105b671d659d446",
        "allow": ["README.md", "audio/ko/*/*.tar", "transcript/ko/*.tsv"],
        "license": "CC0 1.0",
    },
]


# 알림·경고는 표준 오류로 낸다. 진행 상황(표준 출력)과 섞여도 눈에 띄고, 출력을 파일로 돌려도 경고만 따로
# 볼 수 있다.
def warn(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


# 파일 내용의 SHA-256(16진수 64자). hashlib.file_digest가 조각 단위로 읽으므로 수백 MB짜리 parquet도
# 메모리에 한꺼번에 올리지 않는다.
def sha256_file(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


# 출처 폴더 안의 데이터 파일을 '/'로 구분한 상대 경로 → 실제 경로로 돌려준다. huggingface_hub가 local_dir
# 안에 만드는 .cache 폴더(다운로드 메타데이터와 받는 중인 파일)는 데이터가 아니므로 뺀다. 폴더가 없으면 빈
# dict다. .cache는 폴더 안의 상대 경로에서만 찾는다(--dest 자체가 .cache 아래에 있어도 모든 파일이 빠지지
# 않게).
def local_files(local: Path) -> dict[str, Path]:
    if not local.is_dir():
        return {}
    found: dict[str, Path] = {}
    for path in local.rglob("*"):
        relative = path.relative_to(local)
        if path.is_file() and ".cache" not in relative.parts:
            found[relative.as_posix()] = path
    return found


# 기록본을 읽어 출처 이름 → 항목(name·repo·revision·commit_sha·files …)으로 돌려준다. 커밋된 파일이라 늘
# 있어야 하고, 없으면 대조할 기준이 없으므로 받지도 대조하지도 않고 멈춘다. 시험이 RECORD를 바꿔 끼울 수
# 있게 호출할 때마다 읽는다.
def load_record() -> dict[str, dict]:
    if not RECORD.exists():
        raise SystemExit(
            f"{RECORD} is missing; it is committed with the code and is the reference for downloads"
        )
    return {entry["name"]: entry for entry in json.loads(RECORD.read_text(encoding="utf-8"))}


# SOURCES의 recorded_sha와 repo가 기록본과 같은지 본다. 둘 중 하나만 고쳐지면 '기록된 커밋으로 받는다'가
# 기록본이 아닌 다른 커밋을 받게 되므로, 그런 어긋남은 받기 전에 멈춘다(시험도 같은 것을 본다).
def check_pins(sources: list[dict], record: dict[str, dict]) -> None:
    for src in sources:
        entry = record.get(src["name"])
        if entry is None or entry["commit_sha"] != src["recorded_sha"] or entry["repo"] != src["repo"]:
            have = entry and f"{entry['repo']} {entry['commit_sha']}"
            raise SystemExit(
                f"{src['name']}: the script pins {src['repo']} {src['recorded_sha']}"
                f" but the record {RECORD.name} has {have or 'no entry'};"
                " make SOURCES and the record agree before downloading"
            )


# 출처 하나의 받은 파일을 기록본의 파일 목록(recorded: 항목의 files, 파일마다 path·bytes[·sha256])과
# 견준다. 돌려주는 값: (다른 점의 목록, SHA-256까지 견준 파일 수). 항목 꼴: 'missing'(기록본에만 있음),
# 'not in the record'(디스크에만 있음), 'N bytes, record M'(크기 차이), 'SHA-256 differs from the
# record'(기록본에 해시가 있고 크기는 같은데 내용이 다름). SHA-256은 기록본에 sha256이 있고 크기가 같은
# 파일만 계산한다(크기가 다르면 이미 다른 것이고, 큰 파일을 쓸데없이 읽지 않으려는 것이다). 기록본에
# sha256이 없는 파일은 크기까지만 본다(이 대조의 한계는 위 머리말).
def check_files(recorded: list[dict], local: Path) -> tuple[list[str], int]:
    on_disk = local_files(local)
    expected = {file["path"]: file for file in recorded}
    problems: list[str] = []
    hashed = 0
    for path in sorted(set(on_disk) | set(expected)):
        if path not in expected:
            problems.append(f"{path}: not in the record")
        elif path not in on_disk:
            problems.append(f"{path}: missing")
        elif (size := on_disk[path].stat().st_size) != expected[path]["bytes"]:
            problems.append(f"{path}: {size:,} bytes, record {expected[path]['bytes']:,}")
        elif digest := expected[path].get("sha256"):
            hashed += 1
            if sha256_file(on_disk[path]) != digest:
                problems.append(f"{path}: SHA-256 differs from the record")
    return problems, hashed


# <dest>/manifest.json(이 스크립트가 쓴 '무엇을 받았나' 기록)가 기록본과 다른 커밋을 적고 있으면 그 줄을
# 돌려준다. 이 파일은 대조를 통과시키는 근거로는 쓰지 않는다(디스크의 파일이 근거다). 다만 새 판을 일부러
# 받은 흔적(다른 커밋)이면 크기가 우연히 같아도 대조가 실패해야 하므로 실패의 근거로만 쓴다. 파일이 없으면
# 아무것도 돌려주지 않는다.
def manifest_problems(dest: Path, sources: list[dict]) -> list[str]:
    path = dest / "manifest.json"
    if not path.exists():
        return []
    try:
        written = {m["name"]: m["commit_sha"] for m in json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, ValueError, KeyError, TypeError) as error:
        return [f"manifest.json: cannot be read ({error!r})"]
    return [
        f"manifest.json: records commit {written[src['name']]} for {src['name']},"
        f" the record has {src['recorded_sha']} (a newer revision was downloaded on purpose?)"
        for src in sources
        if src["name"] in written and written[src["name"]] != src["recorded_sha"]
    ]


# --verify: 받지 않고(네트워크 없이) <dest> 아래 출처 폴더를 기록본과 견준다. 다른 점이 하나라도 있으면
# 목록을 적고 0이 아닌 종료로 멈춘다. 폴더가 아예 없으면 그 한 줄만 적는다(파일마다 'missing'을 늘어놓지
# 않으려고). dest를 만들지 않는다.
def verify_local(sources: list[dict], dest: Path, record: dict[str, dict]) -> None:
    problems: list[str] = []
    files_checked = hashed_total = 0
    for src in sources:
        name = src["name"]
        local = dest / name
        if not local.is_dir():
            problems.append(f"[{name}] {local} does not exist; download it first")
            continue
        found, hashed = check_files(record[name]["files"], local)
        if found:
            problems.extend(f"[{name}] {item}" for item in found)
            continue
        count = len(record[name]["files"])
        files_checked += count
        hashed_total += hashed
        print(f"[{name}] {count} files match the record (file list and sizes)", flush=True)
    problems.extend(manifest_problems(dest, sources))
    if problems:
        raise SystemExit("data differs from the record:\n  " + "\n  ".join(problems))
    # 무엇을 견주지 못했는지를 출력에 남긴다: 기록본에 SHA-256이 없는 파일은 크기까지만 본 것이다.
    limit = ""
    if hashed_total < files_checked:
        limit = (
            "; the record has no SHA-256 for the others, so a file whose content changed without changing its"
            " size is not detected here (downloading the recorded commit is what keeps the content fixed)"
        )
    print(
        f"all {len(sources)} sources match the record;"
        f" SHA-256 compared for {hashed_total} of {files_checked} files{limit}",
        flush=True,
    )


# 출처 하나에서 받을 커밋을 정한다(게이트 확인 포함, 아무것도 받지 않는다). 돌려주는 값은 출처(src)·받을 커밋
# sha(sha)·조회한 gated 값(gated)을 담은 dict.
# 1) revision 이름(main, refs/convert/parquet)이 지금 가리키는 커밋과 게이트 여부를 조회한다. gated가
#    참("auto"·"manual")이면 접근 승인이나 약관 동의가 필요한 저장소이므로 사용자의 동의 없이 받지 않도록
#    여기서 멈춘다.
# 2) 기본은 기록된 커밋(recorded_sha)이다. 그 커밋이 지금도 열리는지 sha로 조회해 확인하고(열리지 않거나
#    허브가 같은 sha를 확인해 주지 않으면 멈춘다), 브랜치가 그 사이 움직였으면 알리기만 한다.
# 3) allow_new_revision이면 1)에서 조회한 최신 커밋을 받는다(조회 결과에 커밋 sha가 없으면 고정할 커밋이
#    없으므로 멈춘다). 기록된 커밋과 다르면 기록본과 다른 데이터를 받는다는 것을 알린다. 받는 것은 그 커밋
#    sha이므로 이 조회 뒤 브랜치가 움직여도 받은 파일과 manifest의 commit_sha는 어긋나지 않는다.
def resolve_commit(api: HfApi, src: dict, allow_new_revision: bool) -> dict:
    name, repo, revision, recorded = src["name"], src["repo"], src["revision"], src["recorded_sha"]
    label = revision or "main"
    latest = api.dataset_info(repo, revision=revision)
    if latest.gated:
        raise SystemExit(f"{repo} is gated ({latest.gated}); refusing to download without the user's consent")
    if allow_new_revision:
        if not latest.sha:
            raise SystemExit(f"{repo}: no commit sha for revision {label}; not downloading")
        if latest.sha != recorded:
            warn(
                f"[{name}] NEW REVISION: {label} now points to {latest.sha},"
                f" not the recorded commit {recorded}; the data differs from the record"
            )
        return {"src": src, "sha": latest.sha, "gated": latest.gated}
    try:
        pinned = api.dataset_info(repo, revision=recorded)
    except HfHubHTTPError as error:
        raise SystemExit(
            f"{repo}: the recorded commit {recorded} cannot be opened on the Hub"
            f" ({type(error).__name__}: {error}); nothing is downloaded. Only the file list and sizes can"
            " then be compared with the record: take the current version on purpose with"
            " --allow-new-revision and check it with --verify"
        ) from error
    if pinned.gated:
        raise SystemExit(f"{repo} is gated ({pinned.gated}); refusing to download without the user's consent")
    if pinned.sha != recorded:
        raise SystemExit(
            f"{repo}: the Hub did not confirm the recorded commit {recorded}"
            f" (it answered {pinned.sha!r}); not downloading"
        )
    if latest.sha != recorded:
        warn(
            f"[{name}] note: {label} now points to {latest.sha or 'an unknown commit'},"
            f" not the recorded commit {recorded}; downloading the recorded commit"
            " (pass --allow-new-revision to take the new version on purpose)"
        )
    return {"src": src, "sha": recorded, "gated": latest.gated}


# 명령줄 정의. 도움말은 한국어로 자세히 쓰고, 옵션 이름은 영어 그대로 둔다. (argparse 도움말의 퍼센트
# 기호는 두 번 써야 하므로 도움말에 퍼센트를 쓰지 않는다.)
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "공개 한국어 음성 코퍼스(Zeroth-Korean, FLEURS ko, Common Voice 17·22 ko)를\n"
            "Hugging Face Hub에서 data/raw/로 받는다. 기본 동작은 출처마다 기록본\n"
            "(reports/data/download-manifest-2026-10-11.json)에 적힌 커밋을 받고, 받은 파일의\n"
            "목록과 크기를 기록본과 견주는 것이다. 출처의 브랜치가 그 뒤 움직였어도 기록된\n"
            "커밋을 받고 알리기만 한다. 목록이나 크기가 기록본과 다르면 0이 아닌 종료 코드로\n"
            "멈춘다."
        ),
        epilog=(
            "대조의 한계: 기록본에는 파일마다 경로와 크기만 있고 SHA-256이 없다. 그래서 대조는\n"
            "파일 목록(빠진 파일, 기록에 없는 파일)과 크기까지만 보며, 크기가 같은 채 내용만\n"
            "바뀐 파일은 잡지 못한다. 그 부분은 기록된 커밋으로 받는 것이 맡는다(커밋이 그\n"
            "시점의 파일 목록과 내용을 정한다). 기록본의 파일 항목에 sha256이 생기면 크기가\n"
            "같은 파일은 SHA-256도 견준다.\n"
            "기록된 커밋이 허브에서 열리지 않게 되면 그 출처는 기록된 커밋으로 받을 수 없으므로\n"
            "기본 실행이 받기 전에 멈춘다. 그때는 --allow-new-revision으로 지금의 커밋을 받고\n"
            "--verify로 목록과 크기만 견줄 수 있다(내용은 보증되지 않는다).\n"
            "prepare_data.py는 원본을 기록본과 견주지 않으므로, 준비 단계 전에 --verify로\n"
            "확인한다."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dest",
        default="data/raw",
        help=(
            "저장 폴더. 출처마다 이 아래에 이름 폴더를 만든다(기본 data/raw). 현재 작업 폴더"
            " 기준이므로 stt-scratch 폴더에서 실행한다"
        ),
    )
    parser.add_argument(
        "--only",
        nargs="*",
        choices=[src["name"] for src in SOURCES],
        metavar="NAME",
        help=(
            "내려받을(또는 --verify로 대조할) 출처 이름 일부. 주지 않으면 전부: "
            + ", ".join(src["name"] for src in SOURCES)
            + ". 이 밖의 이름은 오류다(오타 때문에 아무것도 대조하지 않은 채 통과하는 일이 없도록)"
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--verify",
        action="store_true",
        help=(
            "받지 않고(네트워크 없이) --dest 아래 출처 폴더를 기록본과 견준다: 빠진 파일, 기록에"
            " 없는 파일, 크기 차이(기록본에 sha256이 있으면 SHA-256 차이도). 하나라도 다르면 0이"
            " 아닌 종료 코드로 멈춘다. 지금의 기록본에는 SHA-256이 없어 크기까지만 본다."
            " --dest의 manifest.json이 기록본과 다른 커밋을 적고 있어도 실패한다"
        ),
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "받지 않고 출처마다 게이트 여부와 받을 커밋만 조회해 보여 준다(기록된 커밋이 지금도"
            " 열리는지, 브랜치가 움직였는지). 열리지 않는 커밋이나 게이트 저장소가 있으면 실제"
            " 실행처럼 0이 아닌 종료 코드로 멈춘다"
        ),
    )
    parser.add_argument(
        "--allow-new-revision",
        action="store_true",
        help=(
            "기록된 커밋이 아니라 revision 이름(main, refs/convert/parquet)이 지금 가리키는"
            " 최신 커밋을 일부러 받는다. 최신 커밋이 기록된 커밋과 다르면 기록본과 다른 데이터를"
            " 받는다는 경고와 기록본과 다른 파일의 목록을 출력에 남기고, 기록된 측정과 같은"
            " 데이터가 아니라고 마지막에 다시 알린다(manifest.json에는 새 커밋이 적힌다)."
            " --verify와는 함께 쓸 수 없다. 폴더에 전에 받은 파일이 남아 있으면 새 판의 파일과"
            " 섞일 수 있으므로 폴더를 비우고 받는 편이 안전하다"
        ),
    )
    return parser


# 출처를 차례로 내려받고 manifest.json을 갱신한다(--verify·--dry-run이면 받지 않는다). 기존
# manifest.json이 있으면 읽어 두고, 이번에 받은 출처의 항목만 새것으로 바꾼다. 그래서 --only로 일부만 다시
# 받아도 다른 출처의 기록은 남는다. 받은 출처가 기록된 커밋이면 파일 목록·크기가 기록본과 같아야 하고
# 다르면 manifest를 쓰기 전에 멈춘다(앞 출처의 기록도 이번 실행에서는 저장되지 않으므로 원인을 고친 뒤
# 다시 실행한다. 이미 받은 파일은 다시 받지 않아 금방 끝난다). 새 판이면 기록본과 다른 점을 경고로 남기고
# 끝까지 간다.
def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.verify and args.allow_new_revision:
        parser.error("--allow-new-revision chooses what to download; it does nothing with --verify")
    dest = Path(args.dest)
    selected = [src for src in SOURCES if not args.only or src["name"] in args.only]
    record = load_record()
    check_pins(selected, record)

    if args.verify:
        verify_local(selected, dest, record)
        return

    # 받기 전에 모든 출처의 게이트와 받을 커밋을 정한다. 한 출처가 막혀 있으면 어느 출처도 받지 않고 멈춘다.
    api = HfApi()
    plan = [resolve_commit(api, src, args.allow_new_revision) for src in selected]
    if args.dry_run:
        for item in plan:
            src, sha = item["src"], item["sha"]
            if sha == src["recorded_sha"]:
                kind = "recorded commit"
            else:
                kind = f"NEW revision, not the recorded {src['recorded_sha']}"
            print(
                f"[{src['name']}] {src['repo']} rev={src['revision'] or 'main'}:"
                f" would download {sha} ({kind})"
            )
        print("dry run: nothing was downloaded")
        return

    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    differing: list[str] = []
    for item in plan:
        src, sha = item["src"], item["sha"]
        name = src["name"]
        # 이 출처의 예전 기록을 지우고 아래에서 새 기록으로 넣는다(같은 이름이 두 번 들어가지 않게).
        manifest = [m for m in manifest if m["name"] != name]
        local = dest / name
        recorded_commit = sha == src["recorded_sha"]
        print(
            f"[{name}] {src['repo']} rev={src['revision'] or 'main'} sha={sha}"
            f" ({'recorded commit' if recorded_commit else 'NEW revision'}) -> {local}",
            flush=True,
        )
        # 정해 둔 커밋(sha)에서 허용 패턴에 맞는 파일만 local_dir에 실제 파일로 받는다. 이름 대신 커밋을
        # 넘기므로 브랜치가 움직여도 manifest에 적는 커밋의 파일이 들어온다. 이미 받은 파일은 다시 받지
        # 않으므로 중간에 끊겨도 다시 실행하면 이어서 받는다. 같은 폴더에 다른 커밋의 파일이 있었으면 그
        # 커밋과 내용(etag)이 다른 파일만 다시 받고, 새 커밋에서 없는 파일은 local_dir에 그대로
        # 남는다(snapshot_download는 파일을 지우지 않는다). 동시 다운로드 4개.
        snapshot_download(
            repo_id=src["repo"],
            repo_type="dataset",
            revision=sha,
            allow_patterns=src["allow"],
            local_dir=str(local),
            max_workers=4,
        )
        # 받은 파일 목록을 정렬해 기록한다. huggingface_hub가 local_dir 안에 만드는 .cache 폴더(다운로드
        # 메타데이터)는 데이터가 아니므로 뺀다. 경로는 OS와 무관하게 '/'로 적는다.
        files = [
            {"path": path.relative_to(local).as_posix(), "bytes": path.stat().st_size}
            for path in sorted(local_files(local).values())
        ]
        # 출처별 파일 수와 총 용량(GB)을 찍어 받은 양을 확인한다(전체 약 5.5 GB, docs/data.md).
        total = sum(f["bytes"] for f in files)
        print(f"[{name}] {len(files)} files, {total / 1e9:.2f} GB", flush=True)
        # 받은 파일을 기록본과 견준다(로컬 디스크만 읽는다).
        problems, hashed = check_files(record[name]["files"], local)
        if recorded_commit:
            if problems:
                raise SystemExit(
                    f"[{name}] the downloaded files differ from the record although the recorded"
                    f" commit {sha} was downloaded (a file cut short, or files left from an earlier"
                    " --allow-new-revision run: snapshot_download never deletes files; remove the"
                    " listed files or the folder and run again):\n  " + "\n  ".join(problems)
                )
            print(
                f"[{name}] matches the record: {len(files)} files (file list and sizes;"
                f" SHA-256 compared for {hashed})",
                flush=True,
            )
        else:
            differing.append(name)
            if problems:
                warn(f"[{name}] files differ from the record:\n  " + "\n  ".join(problems))
        # revision은 사람이 읽는 브랜치 이름(main, refs/convert/parquet), commit_sha는 실제로 받은 커밋이다.
        manifest.append(
            {
                "name": name,
                "repo": src["repo"],
                "revision": src["revision"] or "main",
                "commit_sha": sha,
                "license": src["license"],
                "gated": item["gated"],
                "files": files,
            }
        )
    # 모든 출처를 처리한 뒤 한 번에 저장한다. 중간에 실패하면 이번 실행의 기록은 저장되지 않으므로 다시
    # 실행해야 한다.
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("manifest written:", manifest_path)
    if differing:
        warn(
            f"WARNING: {', '.join(differing)} differ from the record ({RECORD.name}): this is not"
            " the data the recorded measurements used, so results made with it are not comparable"
            " with the recorded ones. --verify lists the differences"
        )


if __name__ == "__main__":
    main()
