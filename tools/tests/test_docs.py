"""루트 문서(README.md, docs/)가 저장소의 파일과 git 이력에 맞는지 보는 시험.

무엇을 지키나
    README.md         첫 화면. 세 가지를 본다. (1) '실행과 테스트' 절에 줄바꿈 변환을 끄는 받기 명령
                      (git clone -c core.autocrlf=false ...)과 '각 구성 요소 폴더 안에서' 설치·테스트한다는
                      말이 있는지. Windows Git의 기본값(core.autocrlf=true)으로 받으면 .gitattributes가 없는
                      구성 요소의 파일이 CRLF로 풀려 기록에 해시가 남은 바이트가 달라지고, 루트에는 파이썬
                      프로젝트가 없어 저장소 뿌리에서 pytest나 uv sync를 돌리면 실패하거나 다섯 구성 요소의
                      시험을 한꺼번에 모으기 때문이다. (2) '통화 한 건의 흐름' 절의 Mermaid 그림에서 노드
                      이름이 ASCII 영숫자·밑줄뿐이고, 한글·괄호·쌍점 같은 글자가 든 노드 글과 선의 글이
                      큰따옴표로 감싸져 있는지. 따옴표 없는 특수 글자는 GitHub 화면에서 그림 대신 오류 상자가
                      보이게 하는 흔한 원인이다. 그림이 실제로 그려지는지는 이 시험이 증명하지 못한다(GitHub
                      화면에서 따로 본다). (3) 굵게 표시(`**`)가 줄마다 짝이 맞고, 여는 표시와 닫는 표시가
                      마크다운 규칙으로 굵게가 되는 자리에 있는지. 닫는 표시 앞이 문장 부호(%, 괄호 등)이고
                      바로 뒤가 한글이면 굵게가 풀려 별표가 화면에 그대로 보이는데(`**6.94%**로`), 수치 검사는
                      여는 표시만 글자로 대조해서 이것을 잡지 못한다.
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

import re
import subprocess
import unicodedata
from urllib.parse import unquote

from check_links import iter_links
from check_root_numbers import fence_mask, section_body
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
    # voice-translator: 공식 코드의 계산을 따라 쓴 MetricX-24 점수 스크립트. 머리 docstring에 따른
    # 코드의 커밋과 라이선스 이름만 있고 원문은 없어, 아래 표지 글 검색으로는 잡히지 않는다
    "../voice-translator/backend/eval/metricx_score.py",
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


# 첫 화면(README.md)에서 아래 두 시험이 읽는 절의 제목('## ' 뒤의 글). 바깥에서 이 제목의 앵커로 링크할 수 있어
# 고정한 글자다.
RUN_SECTION = "실행과 테스트"
FLOW_SECTION = "통화 한 건의 흐름"

# '실행과 테스트' 절에 그대로 있어야 하는 글. 받기 명령은 줄바꿈 변환을 끄는 옵션까지 글자 그대로 본다.
CLONE_COMMAND = "git clone -c core.autocrlf=false https://github.com/hyeonbin123/korean-voice-ai"
INSIDE_COMPONENTS = "각 구성 요소 폴더 안에서"

# Mermaid 노드 정의의 머리: 이름 바로 뒤에 여는 괄호([, (, {). 이름은 공백·큰따옴표·세로줄·괄호가 아닌 글자들로
# 넓게 읽는다. 이름에 쓰면 안 되는 글자(하이픈, 한글 등)가 든 이름도 일단 이름으로 읽어 아래 _NODE_ID 검사에서
# 걸리게 하려는 것이다. 그래서 화살표에 이름을 공백 없이 붙여 쓴 줄(a-->b[...])도 이름이 'a-->b'로 읽혀 걸린다.
# 그림에서는 화살표 앞뒤에 공백을 둔다.
_NODE_HEAD = re.compile(r'(?P<id>[^\s"|\[\](){}]+)(?P<open>[\[({])')
# 여는 괄호마다 닫는 괄호.
_CLOSERS = {"[": "]", "(": ")", "{": "}"}
# 선에 단 글(-->|글| 꼴)의 세로줄 사이.
_EDGE_LABEL = re.compile(r"\|([^|]*)\|")
# 큰따옴표로 감싼 글 하나.
_QUOTED = re.compile(r'"[^"]*"')
# 따옴표 없이 써도 되는 글: ASCII 영숫자, 공백, 하이픈, 밑줄, 슬래시, 점만.
_PLAIN = re.compile(r"[A-Za-z0-9 _./-]*")
# 노드 이름(ID): ASCII 영숫자와 밑줄만.
_NODE_ID = re.compile(r"[A-Za-z0-9_]+")


def readme_section(section: str) -> str:
    """README.md의 '## <section>' 절 본문(다음 같은 수준 이상의 제목 전까지).

    절을 자르는 규칙은 루트 수치 검사 도구의 check_root_numbers.section_body를 그대로 쓴다(코드 울타리 안의
    '#' 줄은 제목이 아니다). 해석을 두 벌 두지 않으려는 것이다. 그 제목이 정확히 한 번 나오지 않으면 실패한다.
    """
    text = (REPO / "README.md").read_text(encoding="utf-8")
    body, hits = section_body(text, section)
    assert hits == 1 and body is not None, (
        f"README.md에 '{section}' 제목이 {hits}번 나온다(정확히 한 번이어야 한다)"
    )
    return body


def fenced_blocks(text: str) -> list[tuple[str, list[str]]]:
    """글에 있는 코드 울타리마다 (정보 글, 안쪽 줄들)을 돌려준다.

    어느 줄이 울타리 안인지는 check_root_numbers.fence_mask가 정한다(여는 줄·안쪽 줄·닫는 줄이 모두 True). 그
    True가 이어진 덩어리 하나를 울타리 하나로 본다. 정보 글은 여는 줄에서 앞쪽 공백과 백틱·물결표를 뗀 나머지다
    (```mermaid면 'mermaid'). 안쪽 줄에서는 여는 줄과, 백틱이나 물결표 세 개 이상만으로 된 닫는 줄을 뺀다(닫히지
    않은 울타리는 글 끝까지가 안쪽이다).

    주의: 닫는 줄 바로 다음 줄에서 다른 울타리를 열면(사이에 빈 줄이 없으면) 두 울타리가 하나로 읽힌다. 정보
    글은 앞 울타리의 것이 되고, 앞 울타리의 닫는 줄과 뒤 울타리의 줄이 안쪽 줄에 섞인다. 첫 화면에는 그런 꼴이
    없다(울타리 앞뒤에 빈 줄을 둔다).
    """
    lines = text.splitlines()
    mask = fence_mask(text)
    blocks: list[tuple[str, list[str]]] = []
    start = 0
    while start < len(lines):
        if not mask[start]:
            start += 1
            continue
        end = start
        while end + 1 < len(lines) and mask[end + 1]:
            end += 1
        info = lines[start].strip().lstrip("`~").strip()
        inner = lines[start + 1 : end + 1]
        last = inner[-1].strip() if inner else ""
        if len(last) >= 3 and set(last) in ({"`"}, {"~"}):
            inner = inner[:-1]
        blocks.append((info, inner))
        start = end + 1
    return blocks


def mermaid_labels(lines: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Mermaid flowchart 줄들에서 노드 정의 (이름, 괄호 안 글) 목록과 선에 단 글 목록을 돌려준다.

    큰따옴표 안의 글은 괄호나 세로줄이 들어 있어도 그림의 문법이 아니므로, 먼저 그 안을 같은 길이의 공백으로
    가린 줄에서 노드 머리(_NODE_HEAD)와 선의 글(_EDGE_LABEL)을 찾고, 글 자체는 가리기 전의 줄에서 같은 자리를
    잘라 온다. 그래서 돌려주는 글에는 감싼 큰따옴표가 그대로 있다. '%%'로 시작하는 줄은 Mermaid 주석이라 읽지
    않는다.

    읽는 꼴: 노드 정의는 네모·둥근·마름모 괄호 하나로 감싼 것(id[...], id(...), id{...})만, 선의 글은
    -->|글| 꼴만 읽는다. 겹괄호 모양(id((...)), id[(...)] 등)은 안쪽 괄호까지 글로 읽혀 따옴표 검사에서 걸리고,
    -- 글 --> 꼴로 단 글은 읽지 않는다. 첫 화면의 그림은 읽는 꼴로만 쓴다.
    """
    nodes: list[tuple[str, str]] = []
    edge_labels: list[str] = []
    for line in lines:
        if line.strip().startswith("%%"):
            continue
        masked = _QUOTED.sub(lambda found: '"' + " " * (len(found.group(0)) - 2) + '"', line)
        for head in _NODE_HEAD.finditer(masked):
            close = masked.find(_CLOSERS[head["open"]], head.end())
            nodes.append((head["id"], line[head.end() : len(line) if close == -1 else close]))
        for label in _EDGE_LABEL.finditer(masked):
            edge_labels.append(line[label.start(1) : label.end(1)])
    return nodes, edge_labels


def needs_quotes(text: str) -> bool:
    """괄호 안이나 선에 단 글이 큰따옴표로 감싸야 하는데 감싸지 않았으면 True.

    글 전체가 큰따옴표 하나로 감싸져 있거나, ASCII 영숫자·공백·하이픈·밑줄·슬래시·점만으로 되어 있으면 False다.
    """
    return not (_QUOTED.fullmatch(text) or _PLAIN.fullmatch(text))


def test_readme_clone_keeps_bytes_and_runs_inside_components():
    body = readme_section(RUN_SECTION)
    assert CLONE_COMMAND in body, f"'{RUN_SECTION}' 절에 받기 명령 '{CLONE_COMMAND}'이 없다"
    assert INSIDE_COMPONENTS in body, f"'{RUN_SECTION}' 절에 '{INSIDE_COMPONENTS}'라는 말이 없다"


def test_readme_mermaid_labels_are_quoted():
    body = readme_section(FLOW_SECTION)
    # 먼저 검사할 그림이 있는지 본다. 울타리가 없거나 정보 글이 달라(```Mermaid 등) 아무것도 읽지 못한 채 아래
    # 검사가 모두 빈 목록으로 통과하는 일을 막으려는 것이다.
    blocks = [inner for info, inner in fenced_blocks(body) if info == "mermaid"]
    assert len(blocks) == 1, f"'{FLOW_SECTION}' 절의 mermaid 울타리가 {len(blocks)}개다(정확히 하나여야 한다)"
    content = [line for line in blocks[0] if line.strip()]
    assert content and content[0].strip() == "flowchart LR", (
        f"그림의 첫 줄이 'flowchart LR'이 아니다: {content[:1]}"
    )
    nodes, edge_labels = mermaid_labels(content[1:])
    assert nodes, "mermaid 그림에서 노드 정의를 하나도 읽지 못했다"
    bad_ids = [node_id for node_id, _ in nodes if not _NODE_ID.fullmatch(node_id)]
    assert bad_ids == [], f"ASCII 영숫자·밑줄이 아닌 글자가 든 노드 이름: {bad_ids}"
    texts = [text for _, text in nodes] + edge_labels
    unquoted = [text for text in texts if needs_quotes(text)]
    assert unquoted == [], f"큰따옴표로 감싸지 않은 글: {unquoted}"


# 인라인 코드(백틱 한 쌍으로 감싼 글). 그 안의 별표는 마크다운 문법이 아니라 글자다.
_CODE_SPAN = re.compile(r"`[^`]*`")
# 별표가 이어진 덩어리 하나. 굵게 표시는 별표 두 개(`**`)만 쓴다.
_STAR_RUN = re.compile(r"\*+")


def _is_blank(char: str) -> bool:
    """줄의 처음·끝(빈 글자)이거나 공백 글자면 True. 마크다운은 줄의 처음과 끝을 공백처럼 본다."""
    return char == "" or char.isspace()


def _is_punctuation(char: str, symbols_too: bool) -> bool:
    """마크다운이 문장 부호로 치는 글자면 True.

    ASCII 문장 부호(%, 괄호, 쉼표, 백틱 등)와 유니코드 범주 P(문장 부호)는 늘 문장 부호다. 유니코드 범주
    S(ASCII가 아닌 기호, 예: 화살표 →)는 CommonMark 0.30까지는 문장 부호로 치지 않고 0.31부터 쳐서, symbols_too로
    두 해석을 고른다(GitHub가 쓰는 변환기가 어느 쪽인지에 기대지 않으려고).
    """
    if char == "":
        return False
    if char.isascii():
        return not (char.isalnum() or char.isspace())
    category = unicodedata.category(char)
    return category.startswith("P") or (symbols_too and category.startswith("S"))


def bold_marker_problems(line: str) -> list[str]:
    """글 한 줄에서 굵게 표시(`**`)가 굵게 그려지지 않을 자리를 찾아, 자리마다 까닭 한 줄을 돌려준다.

    마크다운(CommonMark)은 별표 묶음의 앞뒤 글자를 보고 그 묶음이 굵게를 열 수 있는지, 닫을 수 있는지 정한다.
        열 수 있다: 바로 뒤가 공백이 아니고, 뒤가 문장 부호면 앞이 공백이나 문장 부호여야 한다.
        닫을 수 있다: 바로 앞이 공백이 아니고, 앞이 문장 부호면 뒤가 공백이나 문장 부호여야 한다.
    그래서 `**6.94%**로`의 닫는 표시는 앞이 문장 부호(%)이고 뒤가 한글이라 닫지 못하고, 화면에 별표가 그대로
    보인다. 한글에는 낱말 사이 공백이 없는 자리가 많아 이 꼴이 쉽게 생긴다.

    이 함수는 한 줄 안의 `**`를 차례대로 여는 표시, 닫는 표시, 여는 표시…로 읽는다(굵게 안에 굵게를 넣지 않는
    글을 가정한다). 링크 글의 경계, 표 칸의 경계, 역슬래시로 감춘 별표, 네 칸 들여쓴 줄(코드 블록)은 읽지
    않는다(첫 화면의 굵게는 링크 글의 경계나 표 칸의 경계를 넘지 않는다). 목록 표시 `*`도 별표 하나로 알리므로
    목록은 `-`로 쓴다. 인라인 코드 안의 별표는 세지 않는다. 알리는 것: 별표가 두 개가 아닌 묶음(`*`, `***`), 짝이
    맞지 않는 줄, 열 수 없는 자리의 여는 표시, 닫을 수 없는 자리의 닫는 표시. 기호(화살표 등)를 문장 부호로
    치는 해석과 치지 않는 해석 어느 쪽에서든 어긋나면 알린다.
    입력: 코드 울타리 밖의 글 한 줄. 출력: 문제 설명의 목록(없으면 빈 목록).
    """
    # 인라인 코드의 안쪽을 글자 x로 가린다. 백틱은 남겨서, 코드 옆에 붙은 표시가 문장 부호(백틱) 옆으로 읽히게 한다.
    masked = _CODE_SPAN.sub(lambda found: "`" + "x" * (len(found.group(0)) - 2) + "`", line)
    runs = list(_STAR_RUN.finditer(masked))
    problems = [
        f"{run.start() + 1}번째 글자: 별표가 {len(run.group(0))}개다(굵게 표시는 두 개만 쓴다)"
        for run in runs
        if len(run.group(0)) != 2
    ]
    marks = [run for run in runs if len(run.group(0)) == 2]
    if len(marks) % 2:
        problems.append(f"굵게 표시가 {len(marks)}개라 짝이 맞지 않는다")
    for index, mark in enumerate(marks):
        before = masked[mark.start() - 1] if mark.start() > 0 else ""
        after = masked[mark.end()] if mark.end() < len(masked) else ""
        around = masked[max(mark.start() - 6, 0) : mark.end() + 6]
        for symbols_too in (False, True):
            before_punct = _is_punctuation(before, symbols_too)
            after_punct = _is_punctuation(after, symbols_too)
            can_open = not _is_blank(after) and (not after_punct or _is_blank(before) or before_punct)
            can_close = not _is_blank(before) and (not before_punct or _is_blank(after) or after_punct)
            if index % 2 == 0 and not can_open:
                problems.append(f"{mark.start() + 1}번째 글자: 여는 표시가 굵게를 열지 못한다('{around}')")
                break
            if index % 2 == 1 and not can_close:
                problems.append(f"{mark.start() + 1}번째 글자: 닫는 표시가 굵게를 닫지 못한다('{around}')")
                break
    return problems


def test_bold_marker_problems_follow_the_markdown_rule():
    # 아래 실제 문서 시험이 기대는 함수를 손으로 따질 수 있는 사례로 고정한다. 문제가 없는 꼴과 있는 꼴을 함께 본다
    # (함수가 늘 빈 목록을 돌려주면 실제 문서 시험이 아무것도 보지 않은 채 통과하기 때문이다).
    fine = (
        "**굵게**",
        "FLEURS는 **5.21%** → **6.94%**(나빠졌다)",  # 닫는 표시 앞이 %여도 뒤가 공백이나 괄호면 닫힌다
        "한국어 원문 **1.86초 → 1.24초**(전 → 후)",  # 굵게 안의 화살표는 표시와 붙어 있지 않다
        "쓰기 호출도 **6 → 13건**으로 늘었다",  # 닫는 표시 앞뒤가 모두 한글이면 닫힌다
        "`qwen3.5:4b` **55.6%**.",  # 인라인 코드 뒤 공백, 닫는 표시 뒤 마침표
        "코드 안의 `**`는 세지 않는다",
        "별표가 없는 줄",
    )
    for line in fine:
        assert bold_marker_problems(line) == [], line
    broken = (
        "FLEURS는 **5.21%** → **6.94%**로 나빠졌다",  # 닫는 표시 앞이 %이고 뒤가 한글: 굵게가 풀린다
        "짝이 없는 **표시",
        "여는 표시 뒤가 공백인 ** 글**",
        "닫는 표시 앞이 공백인 **글 **",
        "한글에 붙여 괄호 앞에서 연 표시**(글)**",  # 여는 표시 뒤가 문장 부호인데 앞이 한글: 열지 못한다
        # 아래 줄은 화면에서 깨지는 꼴이 아니다(기울임과 굵은 기울임으로 그려진다). 첫 화면이 굵게에 별표 두 개만
        # 쓰기로 해서 알리는 것이다.
        "별표 하나 *기울임*과 셋 ***굵은 기울임***",
    )
    for line in broken:
        assert bold_marker_problems(line) != [], line
    # 화살표 같은 기호는 변환기에 따라 문장 부호일 수도 아닐 수도 있다. 닫는 표시가 기호 바로 뒤에 있고 그 뒤가
    # 한글이면 한쪽 해석에서 닫지 못하므로 알린다.
    assert bold_marker_problems("**전 →**후") != []


def test_readme_bold_markers_render_as_bold():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    # 코드 울타리 안의 줄은 마크다운으로 읽히지 않으므로 뺀다(울타리 해석은 수치 검사 도구의 fence_mask 한 벌만 쓴다).
    # strict=True: fence_mask가 줄 수와 다른 길이를 돌려주면 조용히 잘리지 않고 여기서 실패한다.
    numbered = enumerate(zip(lines, fence_mask(text), strict=True), start=1)
    outside = [(number, line) for number, (line, fenced) in numbered if not fenced]
    # 굵게 표시를 하나도 읽지 못하면 아래 검사는 아무것도 보지 않은 채 통과한다(닫히지 않은 울타리가 뒤의 줄을 모두
    # 가린 경우 등). 첫 화면은 표의 수치를 굵게 적으므로 표시가 하나도 없으면 읽기가 어긋난 것이다.
    assert any("**" in line for _, line in outside), "코드 울타리 밖에서 굵게 표시를 하나도 읽지 못했다"
    problems = [
        f"README.md:{number}: {problem}" for number, line in outside for problem in bold_marker_problems(line)
    ]
    assert problems == []
