"""루트 문서(docs/)가 저장소의 파일과 git 이력에 맞는지 보는 시험.

무엇을 지키나
    docs/notices.md   구성 요소 곳곳에 흩어진 제3자 고지(라이선스 원문, 사본의 출처,
                      데이터·모델 라이선스 표)의 자리를 모은 문서다. 고지 파일이나 고지 절 하나를
                      가리키는 링크가 빠지면, 저장소를 처음 보는 사람은 그 고지가 있다는 것을 알 길이
                      없다. 그래서 가리켜야 할 대상 목록(NOTICE_TARGETS)을 글자로 고정한다. 그 목록은
                      손으로 적은 것이라 새로 들어온 고지를 스스로 잡지 못하므로, 라이선스 원문의
                      표지 글(MIT·BSD·Apache-2.0)이 든 추적 파일을 git grep으로 찾아 notices.md가
                      그 파일을 모두 가리키는지도 본다.
    docs/history.md   다섯 저장소를 이 저장소의 같은 이름 폴더로 합친 기록이다. 원래 마지막 커밋의
                      전체 해시와 옛 주소, 합칠 때 만든 이동 커밋·병합 커밋의 전체 해시가 적혀 있어야
                      '원래 커밋을 해시 그대로 들였다'는 말을 누구나 이 저장소의 git만으로 다시 확인할
                      수 있다.

읽는 것
    실제 저장소의 문서, 추적 파일의 내용(git grep), git 이력(태그 archive/<이름>과 HEAD에서 닿는
    커밋). 시험용 가짜 저장소는 만들지 않는다. 이동·병합 커밋은 로컬 기록 파일이 아니라 저장소의
    git만으로 찾는다. 공개 저장소의 시험은 저장소 밖의 파일을 읽을 수 없기 때문이다.

주의
    태그와 전체 이력이 있어야 한다. 얕은 체크아웃이나 태그를 받지 않은 체크아웃에서는 실패한다
    (건너뛰지 않는다). 이 시험을 돌리는 CI는 전체 이력과 태그를 받아야 한다(actions/checkout의
    fetch-depth: 0). 브랜치 이름 main이 아니라 HEAD에서 찾는다. CI의 체크아웃(특히 PR)에는 로컬
    main 브랜치가 없을 수 있다.
"""

import subprocess
from urllib.parse import unquote

from check_links import iter_links
from conftest import REPO

# 합친 다섯 저장소의 이름. 이 저장소의 폴더 이름이고, 태그 archive/<이름>과 옛 주소의 마지막
# 부분이기도 하다.
NAMES = ("whisper-ko-ft", "stt-scratch", "call-summary", "support-agent", "voice-translator")

# 합친 시점에 각 저장소의 마지막 커밋(전체 해시). 태그 archive/<이름>이 이 커밋을 가리켜야 하고,
# docs/history.md의 표에도 이 글자가 그대로 있어야 한다. 태그가 다른 커밋으로 옮겨지면 이 시험이
# 잡는다.
ORIGINAL_HEADS = {
    "whisper-ko-ft": "2541ec6926904228d2c8d54ae9e786f5578352df",
    "stt-scratch": "3b729ad801f5da3a639223ad4fbb832326548b1c",
    "call-summary": "92b9601128412dda4a58604f29eeea9496727a48",
    "support-agent": "1315de6cb1c2500f1cab041f80178dd960604f75",
    "voice-translator": "43aaa3c79226074e8511027dc147eea1fcee1b1b",
}

# docs/notices.md가 링크로 가리켜야 하는 대상(문서가 있는 docs/ 기준 상대 경로, 퍼센트 해독한
# 글자). 파일은 사본·라이선스 원문·출처 기록·그 원문을 검사하는 시험이고, '#' 뒤는 고지 표나 귀속
# 절의 제목 앵커다.
NOTICE_TARGETS = (
    # whisper-ko-ft: 영미 철자 사전 사본과 그 출처·MIT 고지(머리 주석), 데이터·모델 라이선스 표
    "../whisper-ko-ft/src/whisper_ko_ft/en_norm.py",
    "../whisper-ko-ft/src/whisper_ko_ft/english.json",
    "../whisper-ko-ft/README.md#데이터와-모델",
    # voice-translator: 브라우저로 보내는 말소리 구간 검출 모델, 두 라이선스 원문, 출처 기록,
    # 두 원문을 내주는 웹 서버 설정을 검사하는 시험, 모델·데이터 라이선스 표
    "../voice-translator/frontend/src/conversation/assets/silero_vad_v6.onnx",
    "../voice-translator/frontend/src/conversation/assets/SILERO-LICENSE.txt",
    "../voice-translator/frontend/src/conversation/assets/ONNXRUNTIME-LICENSE.txt",
    "../voice-translator/frontend/src/conversation/assets/SOURCE.md",
    "../voice-translator/frontend/src/test/nginx.test.ts",
    "../voice-translator/README.md#모델과-데이터의-라이선스",
    # voice-translator: 참조 코드를 따라 옮겨 쓴 Supertonic 3 추론 코드(머리 docstring에 MIT 원문)
    "../voice-translator/backend/app/services/supertonic.py",
    # stt-scratch: 다시 배포하는 전사·가설의 데이터 귀속 절
    "../stt-scratch/docs/data.md#귀속-2026-10-24-확인",
)

# 라이선스 원문의 표지 글. MIT 원문의 "Permission is hereby granted, ...", BSD 원문의 "Redistribution
# and use in source and binary forms, ...", Apache-2.0의 머리 고지와 원문 부록에 함께 있는 "Licensed
# under the Apache License, ..."에서 땄다. 이 글이 든 추적 파일은 다른 곳의 코드·파일과 그 라이선스를
# 담고 있으므로 docs/notices.md가 그 파일을 가리켜야 한다. 위 NOTICE_TARGETS는 손으로 고정한 목록이라
# 새로 들어온 고지를 스스로 잡지 못해 이 검색으로 메운다. 다른 라이선스(GPL, CC 등)의 원문은 찾지 않는다.
LICENSE_TEXT_MARKERS = (
    "Permission is hereby granted",
    "Redistribution and use in source and binary forms",
    "Licensed under the Apache License",
)


def git(*args: str) -> str:
    """저장소 뿌리에서 git 명령을 돌려 표준 출력을 돌려준다(앞뒤 공백을 뗀다).

    실패하면 예외가 그대로 나간다. 출력은 UTF-8로 읽는다. 이 PC 같은 한국어 Windows의 기본
    인코딩(cp949)으로 읽으면 글자가 깨질 수 있다.
    """
    done = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, encoding="utf-8", check=True
    )
    return done.stdout.strip()


def git_or_none(*args: str) -> str | None:
    """git과 같지만 명령이 실패하면(예: 그 커밋에 없는 경로) None을 돌려준다."""
    try:
        return git(*args)
    except subprocess.CalledProcessError:
        return None


def original_head(name: str) -> str:
    """태그 archive/<name>이 가리키는 커밋의 전체 해시.

    '^{commit}'을 붙여 커밋으로 푼다. 지금 태그는 커밋을 바로 가리키는 가벼운 태그라 붙이지 않아도
    값이 같지만, 주석 달린 태그로 바뀌어도 태그 객체가 아니라 커밋의 해시를 얻으려는 것이다.
    """
    return git("rev-parse", f"archive/{name}^{{commit}}")


def read_history() -> str:
    """docs/history.md 전체 글(UTF-8)."""
    return (REPO / "docs" / "history.md").read_text(encoding="utf-8")


def test_notices_points_to_every_notice_file():
    text = (REPO / "docs" / "notices.md").read_text(encoding="utf-8")
    # iter_links는 글에 적힌 그대로(퍼센트 해독 전)를 돌려준다. 한글 앵커를 %EB…처럼 적어도 같은
    # 대상으로 본다.
    targets = {unquote(target) for _, target in iter_links(text)}
    missing = [target for target in NOTICE_TARGETS if target not in targets]
    assert missing == [], f"docs/notices.md가 가리키지 않는 고지: {missing}"


def test_notices_points_to_every_file_with_license_text():
    # 추적 파일에서 표지 글을 찾는다. git grep 옵션: -l 파일 이름만, -I 바이너리 제외, -F 글자 그대로,
    # -z 이름을 NUL로 나눠 내보낸다(한글 경로도 따옴표·8진 이스케이프 없이 받으려고). 이 시험 파일은 표지
    # 글을 상수로 담고 있어 뺀다. 저장소 밖 파일과 추적하지 않는 파일은 git grep이 보지 않는다.
    args = ["grep", "-l", "-I", "-F", "-z"]
    for marker in LICENSE_TEXT_MARKERS:
        args += ["-e", marker]
    args += ["--", ".", ":(exclude)tools/tests/test_docs.py"]
    done = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, encoding="utf-8")
    # 종료 코드 0 = 찾음, 1 = 찾은 것 없음, 그 밖 = git grep 자체의 실패.
    assert done.returncode in (0, 1), f"git grep 실패({done.returncode}): {done.stderr}"
    found = sorted(path for path in done.stdout.split("\0") if path)
    # 지금 저장소에는 표지 글이 든 파일이 있다. 하나도 못 찾으면 검색이 제대로 돌지 않은 것으로 보고
    # 실패시킨다(빈 결과로 조용히 통과하지 않게).
    assert found, "라이선스 원문의 표지 글이 든 추적 파일을 하나도 찾지 못했다"
    text = (REPO / "docs" / "notices.md").read_text(encoding="utf-8")
    targets = {unquote(target) for _, target in iter_links(text)}
    # git grep은 저장소 뿌리 기준 경로를 내고, notices.md는 docs/ 아래에 있어 링크 앞에 ../가 붙는다.
    missing = [path for path in found if f"../{path}" not in targets]
    assert missing == [], f"라이선스 원문이 든 파일을 docs/notices.md가 가리키지 않는다: {missing}"


def test_history_names_every_original_head_and_address():
    history = read_history()
    for name in NAMES:
        head = original_head(name)
        expected = ORIGINAL_HEADS[name]
        assert head == expected, f"archive/{name}이 {head}를 가리킨다(기대: {expected})"
        assert head in history, f"docs/history.md에 {name}의 원래 마지막 커밋 {head}가 없다"
        address = f"https://github.com/hyeonbin123/{name}"
        assert address in history, f"docs/history.md에 옛 주소 {address}가 없다"


def test_history_names_the_move_and_merge_commits():
    history = read_history()
    # HEAD에서 닿는 모든 커밋의 (커밋, 부모들). 'git rev-list --parents'는 한 줄에 커밋과
    # 부모들을 공백으로 적는다.
    rows = [line.split() for line in git("rev-list", "--parents", "HEAD").splitlines()]
    merges = [line.split() for line in git("rev-list", "--merges", "--parents", "HEAD").splitlines()]
    for name in NAMES:
        head = original_head(name)
        tree = git("rev-parse", f"{head}^{{tree}}")
        # 이동 커밋: 부모가 원래 마지막 커밋 하나뿐이고, 그 커밋의 <name>/ 폴더 트리가 원래 마지막
        # 커밋의 트리와 같다(파일을 옮기기만 하고 내용·모드는 그대로 둔 커밋). 그 경로가 없는 커밋은
        # rev-parse가 실패해 None이다.
        moves = [
            row[0]
            for row in rows
            if row[1:] == [head] and git_or_none("rev-parse", f"{row[0]}:{name}") == tree
        ]
        assert len(moves) == 1, f"{name}의 이동 커밋이 정확히 하나가 아니다: {moves}"
        move = moves[0]
        # 병합 커밋: 둘째 부모가 그 이동 커밋인 병합(git merge --allow-unrelated-histories --no-ff로
        # 들인 것).
        merged = [row[0] for row in merges if len(row) >= 3 and row[2] == move]
        assert len(merged) == 1, f"{name}의 이동 커밋 {move}를 들인 병합 커밋이 하나가 아니다: {merged}"
        assert move in history, f"docs/history.md에 {name}의 이동 커밋 {move}가 없다"
        assert merged[0] in history, f"docs/history.md에 {name}의 병합 커밋 {merged[0]}가 없다"
