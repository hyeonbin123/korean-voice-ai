# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""잠금 파일(uv.lock, package-lock.json)이 등록한 갱신으로만 바뀌었는지 git 이력으로 확인하는 검사 도구.

왜 있나
    잠금 파일은 구성 요소가 설치하는 패키지 판을 고정한다. 판이 하나만 올라가도 같은 코드가 다른 환경에서 도는 것이 되어,
    그 뒤의 측정과 시험 결과를 앞선 기록과 같은 조건에서 나온 값으로 읽을 수 없다. 그런데 잠금은 사람이 훑어서는 바뀐
    곳을 찾기 어려운 긴 글이고, 판 올림(예: 1.45.1 → 1.45.2)은 파일 크기를 바꾸지 않을 수도 있어 크기나 줄 수로는 조용한
    변경을 잡을 수 없다. 그래서 '어느 커밋이 어떤 판을 왜 바꿨는지'를 등록 파일(기본값 tools/locks.toml)에 글자로 남기고,
    이 도구가 그 등록을 git 이력과 견준다. 등록하지 않은 변경, 등록한 것보다 더 바뀐 판, 등록하지 않은 새 잠금 파일이
    있으면 실패해서 알려 준다. 잠금을 일부러 바꿀 때는 그 커밋을 등록 파일에 더하면 된다. 커밋 해시를 적어야 하므로
    등록은 잠금을 바꾼 커밋 뒤에 적는다.

등록 파일(TOML)
    [[lock]]       잠금 파일 하나.
        path       저장소 뿌리 기준 경로(`/` 구분). 이름이 uv.lock이나 package-lock.json이어야 한다.
        added      그 경로에 이 파일을 들인 커밋(40자 소문자 16진수). 다른 저장소의 이력을 폴더 아래로 옮겨 들인 구성
                   요소라면 그 폴더를 옮긴 커밋이다.
        base       added 커밋에서의 그 파일의 blob(40자). `git rev-parse <added>:<path>`가 내는 값이다.
        what       무엇의 잠금인지 한 줄.
        [[lock.update]]
                   added 뒤에 그 잠금을 바꾼 커밋 하나(바뀐 적이 없으면 생략). 일어난 순서대로, 옛것부터 적는다.
            commit  그 커밋(40자). 부모가 정확히 하나여야 한다.
            date    그 커밋의 커밋 날짜 YYYY-MM-DD(따옴표로 감싼 글). `git show -s --format=%cs <commit>`와 같아야 한다.
                    커밋에 기록된 시간대의 날짜이며, 등록 파일에 틀린 날짜가 남지 않게 하려는 확인이다.
            changes 그 커밋이 잠금에서 바꾼 (패키지, 판)의 목록. 한 건은 세 꼴 가운데 하나다: "<패키지> <옛 판> -> <새 판>"
                    (판이 바뀜), "+ <패키지> <판>"(새로 들어옴), "- <패키지> <판>"(빠짐). 낱말 사이는 공백 하나다.
                    package-lock.json은 패키지 자리에 packages의 경로(`node_modules/<이름>`)를 적고, 뿌리(빈 경로)는
                    `.`로 적는다. 판은 그대로이고 다른 것(주소, 해시)만 바뀐 갱신이면 빈 목록이다.
            why     왜 바꿨는지 공개 문서나 커밋 메시지를 가리키는 한 줄.
    모르는 꼭대기 키(`lock`만 받는다)와 읽을 수 없는 파일은 검사를 시작할 수 없다(종료 코드 2). 항목 안의 모르는 키, 빠진
    키, 빈 글, 꼴이 틀린 해시·날짜·changes는 그 항목의 문제로 알린다(종료 코드 1). 같은 path를 두 번 등록해도 문제다. 꼴이
    틀린 항목은 값을 믿을 수 없으므로 git과 견주지 않는다. 오타 때문에 등록이 조용히 빠지거나 검사가 느슨해지는 일을
    막으려는 것이다.

검사하는 것 (어긋날 때마다 문제 한 줄. 아래 다섯 규칙과 그에 딸린 확인)
    1. HEAD에서 추적되는 파일 가운데 이름이 uv.lock이나 package-lock.json인 것은 모두 등록돼 있고, 등록한 경로는 모두
       추적된다.
    2. `git rev-parse <added>:<path>`가 base와 같다.
    3. `git log --format=%H -- <path>`(이름 따라가기 없음, 새것부터)의 커밋 목록이 [마지막 update, ..., 첫 update, added]와
       정확히 같다. 등록하지 않은 변경 커밋이 있으면 문제이고, 어디가 다른지(등록하지 않은 커밋, 그 경로를 바꾸지 않았는데
       등록한 커밋, 순서)를 문제 줄에 적는다.
    4. `git rev-parse HEAD:<path>`가 마지막 update 커밋에서의 blob(update가 없으면 base)과 같다.
    5. update마다 그 커밋의 부모와 그 커밋에서 잠금을 읽어 (이름, 판)의 차이를 changes와 견준다. 실제 차이는 둘이다:
       부모의 것에서 그 커밋의 것을 뺀 '없어진 (이름, 판)'과, 반대인 '생긴 (이름, 판)'. changes 한 건은 화살표면 없어진
       쪽에 옛 판을 생긴 쪽에 새 판을 하나씩 보태고, `+`면 생긴 쪽에만, `-`면 없어진 쪽에만 보탠다. 이 둘이 실제 차이와
       각각 정확히 같아야 한다(순서는 상관없고, 같은 건을 두 번 적으면 두 건이다). 그래서 한 이름의 판 둘이 함께 바뀐
       갱신은 화살표 두 건으로, 새로 들어오거나 빠진 패키지는 `+`·`-`로 적고, 화살표 한 건 대신 `-`와 `+` 둘로 적어도
       같은 뜻이다. 어긋나면 등록에 없는 실제 차이와 등록에만 있는 차이를 같은 꼴로 보여 준다(같은 이름에 없어진 판 하나와
       생긴 판 하나뿐이면 화살표 한 건, 그 밖은 `-`·`+`). 그 글은 그대로 changes에 옮겨 적을 수 있다. 판이 없는
       항목(uv.lock에서 version이 없는 [[package]])이 낀 이름은 어느 꼴로도 적을 수 없으므로, 그 까닭을 밝히고 그대로
       문제로 둔다.
    update 커밋은 부모가 정확히 하나여야 하고(병합 커밋이나 뿌리 커밋으로 잠금을 바꾸지 않는다), date가 커밋 날짜와
    같아야 한다.

읽는 방법과 이유
    - 잠금의 내용과 이력은 git 객체(blob, 커밋, 트리)에서만 읽는다. 작업 트리의 잠금 파일은 읽지 않는다. Windows에서
      줄바꿈 변환을 켠 채 받은 복제본이나 아직 커밋하지 않은 변경에 결과가 흔들리지 않게 하려는 것이다. 등록 파일만
      작업 트리에서 읽는다(--registry로 다른 파일을 줄 수 있다).
    - 크기가 아니라 blob 해시로 견준다. 판이 달라도 크기가 같은 잠금이 있기 때문이다.
    - 판의 차이는 uv.lock은 tomllib로 읽은 [[package]]의 (name, version), package-lock.json은 json으로 읽은 packages의
      (경로, version)을 센 것(Counter)끼리 뺀다. uv.lock에는 같은 패키지가 서로 다른 판으로 여러 번 나올 수 있어서
      이름만 세지 않고 (이름, 판) 쌍을 센다. 판이 없는 항목은 uv.lock에서는 빈 판으로 세고 package-lock.json에서는 세지
      않는다. 판이 아닌 것(해시, 주소 같은 나머지 내용)의 변경은 이 비교가 보지 못한다. 판이 함께 바뀐 갱신 안에 섞여
      있어도 마찬가지다. 이 도구가 지키는 것은 '잠금은 등록한 커밋으로만 바뀌고(규칙 3과 4), 그 커밋의 판 변경은
      등록과 같다(규칙 5)'까지다. 바이트가 UTF-8이 아니거나 문법이 깨진 잠금은 그 항목의 문제다.
    - 이름 따라가기(`git log --follow`)를 쓰지 않는다. 다른 저장소의 이력을 폴더 아래로 옮겨 들인 구성 요소들은 옛
      저장소에서 같은 경로(저장소 뿌리의 uv.lock)를 썼으므로, 이름을 따라가면 옮기기 전의 옛 경로를 거슬러 올라가다 다른
      구성 요소의 이력으로 넘어간다. 따라가지 않으면 폴더를 옮긴 커밋에서 이력이 멈추므로 그 커밋을 added로 등록한다.
      git 설정 `log.follow=true`(단일 경로의 git log가 이름을 따라간다)를 켠 PC에서도 이 결정이 뒤집히지 않도록, git log를
      부를 때 `-c log.follow=false`를 준다.
    - git 경로는 글자 그대로 읽는다(`:(literal)`). 폴더 이름에 `[` 같은 글자가 있어도 다른 경로와 섞이지 않는다.
    - --repo는 저장소 뿌리여야 한다. 안쪽 폴더를 주면 git이 경로를 그 폴더 기준으로 읽어 결과가 달라지고, 등록이 비어
      있으면 조용히 통과하기까지 한다. 그래서 뿌리가 아니면 검사를 시작하지 않는다(종료 코드 2).
    - 얕은 복제(깊이를 제한해 받은 복제)에서는 이력이 잘려 added 커밋이 없거나 목록이 틀리게 나온다. 그것을 '등록이
      틀림'으로 알리면 거짓 경고이므로 문제가 아니라 검사를 끝낼 수 없음(종료 코드 2)과 안내로 알린다. HEAD가 없는
      저장소도 같다. git이 '모른다'고 답하는 경우(등록한 커밋이 이 저장소에 없음, 그 커밋에 경로가 없음)는 그 항목의 문제로
      알리고, 그 밖에 예상하지 못한 git 실패는 검사를 끝낼 수 없음으로 알린다. 읽지 못했는데 통과가 되는 길을 두지 않으려는
      것이다.
    - 40자 해시를 쓰므로 SHA-1 저장소만 다룬다.

종료 코드와 출력
    0 = 문제 없음, 1 = 문제가 있음, 2 = 검사를 시작하거나 끝낼 수 없음(등록 파일이 없거나 읽을 수 없음, 저장소 폴더가
    아니거나 git 저장소가 아니거나 저장소 뿌리가 아님, git을 실행할 수 없음, 얕은 복제, HEAD 없음, 예상하지 못한 git
    실패). 문제는 한 줄에 하나씩 `<경로>: <이유>` 꼴로 경로 순으로 쓰고(등록 항목의 꼴 오류는 경로 자리에 등록 파일
    경로를 쓴다), 마지막 줄은 `잠금 N개, 문제 M개`다(N은 등록한 [[lock]] 수). 판정은 끝 줄 글자가 아니라 종료 코드로 한다.

실행
    uv run --no-project tools/check_lock_drift.py [--repo <저장소>] [--registry <toml>]
    전체 이력이 있어야 한다(CI 체크아웃은 `fetch-depth: 0`, 얕은 복제는 `git fetch --unshallow`).

이 도구는 읽기만 한다. git은 읽기 명령(--no-optional-locks)만 부르고, 등록 파일과 저장소의 어떤 파일도 고치지 않는다.
"""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# 이 파일은 <저장소>/tools/check_lock_drift.py에 있다. parents[0] = tools, parents[1] = 저장소 뿌리.
DEFAULT_REPO = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_FILE = "tools/locks.toml"

# 이 이름의 추적 파일이 잠금 파일이다. 이름이 정확히 같아야 한다(`my-uv.lock`, `uv.lock.md`는 잠금이 아니다).
LOCK_NAMES = ("uv.lock", "package-lock.json")

# 등록 표마다 받는 키. 여기에 없는 키는 오타일 가능성이 커서 조용히 무시하지 않고 문제로 알린다(꼭대기 키는 읽기를
# 멈추고 종료 코드 2로 알린다).
TOP_KEYS = ("lock",)
LOCK_KEYS = ("path", "added", "base", "what", "update")
UPDATE_KEYS = ("commit", "date", "changes", "why")

# 커밋·blob으로 받아들이는 꼴: 40자 소문자 16진수(SHA-1 전체 해시). 줄임 해시나 브랜치·태그 이름은 시간이 지나면 다른
# 객체를 가리킬 수 있어 '고정'이 아니다. 이 꼴을 통과한 값만 git에 인자로 넘기므로, 정규식이 넓어도 옵션처럼 읽히는 글
# (`-`로 시작하는 글)이 git 인자로 닿지 않는다.
_FULL_HASH = re.compile(r"[0-9a-f]{40}", re.ASCII)
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
# changes 한 건의 세 꼴. 낱말 사이는 공백 하나, 낱말 안에는 공백이 없다.
#   "<패키지> <옛 판> -> <새 판>": 판이 바뀜
#   "+ <패키지> <판>":             새로 들어옴
#   "- <패키지> <판>":             빠짐
_CHANGE_ARROW = re.compile(r"(\S+) (\S+) -> (\S+)")
_CHANGE_ADDED = re.compile(r"\+ (\S+) (\S+)")
_CHANGE_DROPPED = re.compile(r"- (\S+) (\S+)")

_UNKNOWN_COMMIT = "이 저장소에서 커밋으로 풀 수 없다"

# 문제 하나: (경로, 이유). 경로 자리에는 잠금 경로나(등록 항목의 꼴 오류는) 등록 파일 경로가 온다.
Problem = tuple[str, str]
# changes 한 건: (패키지, 옛 판, 새 판). 새로 들어온 건(`+`)은 옛 판이, 빠진 건(`-`)은 새 판이 빈 글이다. 등록에 적는 판은
# 비어 있을 수 없으므로 빈 글은 '그쪽에 없음'이라는 뜻으로만 쓰인다.
Change = tuple[str, str, str]


class GitError(Exception):
    """이력을 읽을 수 없어 검사를 끝낼 수 없다는 뜻. main이 종료 코드 2로 바꾼다.

    얕은 복제, HEAD 없음, git이 예상하지 못한 방식으로 실패한 경우에 던진다. '등록이 틀림'이라는 문제와 달리 읽지 못했다는
    사실이라 문제 목록에 섞지 않는다.
    """


@dataclass(frozen=True)
class Update:
    """잠금을 바꾼 커밋 하나([[lock.update]]). changes는 읽어 둔 (패키지, 옛 판, 새 판) 목록이다."""

    commit: str
    date: str
    changes: tuple[Change, ...]
    why: str


@dataclass(frozen=True)
class Lock:
    """잠금 파일 하나의 등록([[lock]]).

    problems는 읽는 단계에서 찾은 꼴 오류다(경로 자리에는 등록 파일 경로가 들어 있다). 비어 있지 않은 항목은 값을 믿을
    수 없어 check가 git과 견주지 않는다. 읽지 못한 값은 빈 글이다(path가 빈 글이면 어느 잠금도 등록하지 않은 항목이다).
    꼴이 맞지 않는 항목을 객체에서 빼지 않고 이유와 함께 남기는 것은, 조용히 빠져 검사가 느슨해지는 일을 막으려는 것이다.
    """

    path: str
    added: str
    base: str
    what: str
    updates: tuple[Update, ...] = ()
    problems: tuple[Problem, ...] = ()


# ---------------------------------------------------------------------------------------------
# 등록 파일 읽기
# ---------------------------------------------------------------------------------------------


class _EntryReader:
    """등록 항목 하나를 읽는 동안 꼴 오류를 모은다. 오류는 (등록 파일 경로, `<위치>: <키> - <이유>`)로 쌓인다."""

    def __init__(self, registry: str, where: str, problems: list[Problem] | None = None) -> None:
        self.registry = registry
        self.where = where
        self.problems: list[Problem] = [] if problems is None else problems

    def child(self, label: str) -> "_EntryReader":
        """같은 항목 안의 하위 표(update)를 읽는 도우미. 오류는 같은 목록에 쌓인다."""
        return _EntryReader(self.registry, f"{self.where} {label}", self.problems)

    def report(self, key: str, reason: str) -> None:
        self.problems.append((self.registry, f"{self.where}: {key} - {reason}"))

    def unknown_keys(self, table: dict, allowed: tuple[str, ...]) -> None:
        for key in table:
            if key not in allowed:
                self.report(key, "모르는 키(오타일 수 있다)")

    def text(self, table: dict, key: str) -> str:
        """table[key]가 비어 있지 않은 글이면 그 글을 돌려주고, 아니면 이유를 적고 빈 글을 돌려준다.

        공백뿐인 글도 비었다고 본다. 빈 값은 어떤 대조도 의미 없게 만들기 때문이다.
        """
        if key not in table:
            self.report(key, "없다")
            return ""
        value = table[key]
        if not isinstance(value, str):
            self.report(key, "글이어야 한다")
            return ""
        if not value.strip():
            self.report(key, "비어 있다")
            return ""
        return value

    def full_hash(self, table: dict, key: str) -> str:
        """table[key]가 40자 소문자 16진수 해시면 그 글을, 아니면 이유를 적고 빈 글을 돌려준다."""
        value = self.text(table, key)
        if value and not _FULL_HASH.fullmatch(value):
            self.report(key, f"40자 소문자 16진수 해시여야 한다: {value}")
            return ""
        return value

    def date(self, table: dict) -> str:
        """table["date"]가 따옴표로 감싼 YYYY-MM-DD 글이면 그 글을, 아니면 이유를 적고 빈 글을 돌려준다.

        TOML은 따옴표 없는 2026-11-15를 글이 아니라 날짜 값으로 읽는다. 등록의 date는 글로 통일하므로 따옴표를
        요구하고, 그 안내를 문제 줄에 적는다.
        """
        if "date" not in table:
            self.report("date", "없다")
            return ""
        value = table["date"]
        if not isinstance(value, str):
            self.report("date", "따옴표로 감싼 YYYY-MM-DD 글이어야 한다")
            return ""
        if not _DATE.fullmatch(value):
            self.report("date", f"YYYY-MM-DD 꼴이 아니다: {value}")
            return ""
        return value

    def changes(self, table: dict) -> tuple[Change, ...]:
        """table["changes"]를 (패키지, 옛 판, 새 판) 목록으로 읽는다. 키가 없거나 꼴이 틀리면 이유를 적고 빈 목록이다.

        한 건은 세 꼴 가운데 하나다: 화살표("<패키지> <옛 판> -> <새 판>"), `+`("+ <패키지> <판>", 옛 판이 빈 글),
        `-`("- <패키지> <판>", 새 판이 빈 글). 빈 목록 자체는 올바른 값이다(판은 그대로인 갱신). 그래서 키가 빠진 것과 빈
        목록을 구분해 빠진 쪽만 문제로 본다.
        """
        if "changes" not in table:
            self.report("changes", "없다")
            return ()
        value = table["changes"]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            self.report("changes", "글의 목록이어야 한다")
            return ()
        parsed: list[Change] = []
        for item in value:
            if not item.strip():
                self.report("changes", "빈 글이 들어 있다")
                continue
            if match := _CHANGE_ARROW.fullmatch(item):
                name, old, new = match.groups()
            elif match := _CHANGE_ADDED.fullmatch(item):
                name, new = match.groups()
                old = ""
            elif match := _CHANGE_DROPPED.fullmatch(item):
                name, old = match.groups()
                new = ""
            else:
                self.report(
                    "changes",
                    f"'<패키지> <옛 판> -> <새 판>', '+ <패키지> <판>', '- <패키지> <판>' 가운데 하나의 꼴이 아니다: {item}",
                )
                continue
            parsed.append((name, old, new))
        return tuple(parsed)


def _parse_updates(reader: _EntryReader, raw: object) -> list[Update]:
    """[[lock.update]] 배열을 읽는다. 없으면 빈 목록, 표의 배열이 아니면 이유를 적고 빈 목록이다."""
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        reader.report("update", "[[lock.update]] 표의 배열이어야 한다")
        return []
    updates = []
    for number, item in enumerate(raw, 1):
        sub = reader.child(f"update {number}번째")
        sub.unknown_keys(item, UPDATE_KEYS)
        commit = sub.full_hash(item, "commit")
        date = sub.date(item)
        changes = sub.changes(item)
        why = sub.text(item, "why")
        updates.append(Update(commit=commit, date=date, changes=changes, why=why))
    return updates


def _parse_lock(entry: dict, number: int, registry: str, seen: dict[str, int]) -> Lock:
    """[[lock]] 표 하나를 읽는다. 꼴 오류는 던지지 않고 Lock.problems에 남긴다.

    seen은 지금까지 읽은 항목이 등록한 경로(경로 → 몇 번째)다. 같은 경로를 다시 등록하면 뒤의 항목이 문제다.
    """
    reader = _EntryReader(registry, f"[[lock]] {number}번째")
    reader.unknown_keys(entry, LOCK_KEYS)
    path = reader.text(entry, "path")
    if path:
        if PurePosixPath(path).name not in LOCK_NAMES:
            reader.report("path", f"이름이 uv.lock이나 package-lock.json이어야 한다: {path}")
        if path in seen:
            reader.report("path", f"{seen[path]}번째 항목이 이미 등록한 경로다")
        else:
            seen[path] = number
    added = reader.full_hash(entry, "added")
    base = reader.full_hash(entry, "base")
    what = reader.text(entry, "what")
    updates = _parse_updates(reader, entry.get("update"))
    return Lock(
        path=path,
        added=added,
        base=base,
        what=what,
        updates=tuple(updates),
        problems=tuple(reader.problems),
    )


def load_registry(path: Path) -> list[Lock]:
    """등록 파일(TOML)을 읽어 [[lock]] 항목마다 Lock 하나를 돌려준다.

    파일이 없거나 읽을 수 없으면 OSError, TOML 문법이나 인코딩이 틀리면 ValueError(tomllib.TOMLDecodeError,
    UnicodeDecodeError), 모르는 꼭대기 키가 있거나 lock이 표의 배열이 아니면 ValueError가 그대로 나간다. main이 모두
    종료 코드 2(검사를 시작할 수 없음)로 바꾼다. 항목 안의 꼴 오류는 던지지 않고 Lock.problems에 담는다.
    """
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    unknown = [key for key in raw if key not in TOP_KEYS]
    if unknown:
        raise ValueError(f"모르는 꼭대기 키: {', '.join(unknown)}(받는 꼭대기 키는 lock뿐이다)")
    entries = raw.get("lock", [])
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        raise ValueError("lock은 [[lock]] 표의 배열이어야 한다")
    seen: dict[str, int] = {}
    return [_parse_lock(entry, number, str(path), seen) for number, entry in enumerate(entries, 1)]


# ---------------------------------------------------------------------------------------------
# 잠금 파일에서 판 읽기
# ---------------------------------------------------------------------------------------------


def _uv_versions(parsed: dict) -> Counter[tuple[str, str]]:
    """uv.lock을 읽은 dict에서 [[package]]의 (name, version)을 센다. version이 없는 항목은 빈 판으로 센다."""
    packages = parsed.get("package")
    if not isinstance(packages, list) or not packages or not all(isinstance(item, dict) for item in packages):
        raise ValueError("[[package]] 표가 하나도 없거나 표의 배열이 아니다")
    counts: Counter[tuple[str, str]] = Counter()
    for package in packages:
        name = package.get("name")
        version = package.get("version", "")
        if not isinstance(name, str) or not name:
            raise ValueError("이름(name)이 없는 [[package]]가 있다")
        if not isinstance(version, str):
            raise ValueError(f"[[package]] {name}의 version이 글이 아니다")
        counts[(name, version)] += 1
    return counts


def _npm_versions(parsed: object) -> Counter[tuple[str, str]]:
    """package-lock.json을 읽은 값에서 packages의 (경로, version)을 센다.

    뿌리(빈 경로 "")는 등록의 changes에 적을 수 있도록 `.`로 센다. version이 없는 항목(링크 등)은 세지 않는다. packages가
    없는 옛 형식(lockfileVersion 1)은 읽지 못한다: 읽은 척하면 모든 판 변경이 조용히 사라진다.
    """
    packages = parsed.get("packages") if isinstance(parsed, dict) else None
    if not isinstance(packages, dict):
        raise ValueError("packages 객체가 없다(lockfileVersion 2 이상의 잠금만 읽는다)")
    counts: Counter[tuple[str, str]] = Counter()
    for key, entry in packages.items():
        if not isinstance(entry, dict):
            raise ValueError(f"packages의 {key!r} 항목이 객체가 아니다")
        if "version" not in entry:
            continue
        version = entry["version"]
        if not isinstance(version, str):
            raise ValueError(f"packages의 {key!r} 항목의 version이 글이 아니다")
        counts[(key or ".", version)] += 1
    return counts


def lock_versions(data: bytes, name: str) -> Counter[tuple[str, str]]:
    """잠금 파일의 바이트에서 (이름, 판)의 개수를 센다.

    name은 파일 이름이거나 경로이고 마지막 낱말(uv.lock, package-lock.json)로 읽는 방법을 고른다. 바이트가 UTF-8이
    아니거나 문법이 깨졌거나 모르는 이름이거나 꼴이 기대와 다르면 ValueError다(UnicodeDecodeError, tomllib.TOMLDecodeError,
    json.JSONDecodeError도 ValueError의 한 갈래다). 읽지 못한 잠금을 '판 변경 없음'으로 읽으면 변경이 조용히 사라지므로,
    호출한 쪽이 그 항목의 문제로 알려야 한다.
    """
    kind = PurePosixPath(name).name
    if kind not in LOCK_NAMES:
        raise ValueError(f"읽을 수 없는 잠금 파일 이름이다: {name}")
    text = data.decode("utf-8")
    if kind == "uv.lock":
        return _uv_versions(tomllib.loads(text))
    return _npm_versions(json.loads(text))


# ---------------------------------------------------------------------------------------------
# git 읽기
# ---------------------------------------------------------------------------------------------


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    """repo에서 git 읽기 명령을 부른다. --no-optional-locks로 색인 잠금 파일을 만들지 않는다.

    출력은 바이트로 받는다(잠금 파일 본문을 풀기 전의 바이트 그대로 읽어야 하므로). git 실행 파일이 없으면 OSError가
    나간다. 종료 코드가 0이 아닌 것은 호출한 쪽이 판단한다(check=False).
    """
    return subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )


def _failure(args: tuple[str, ...], done: subprocess.CompletedProcess[bytes]) -> str:
    """실패한 git 명령을 알리는 글: 명령, 종료 코드, 표준 오류의 첫 줄."""
    lines = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
    detail = f": {lines[0]}" if lines else ""
    return f"git {' '.join(args)}: 종료 코드 {done.returncode}{detail}"


class _Git:
    """저장소 하나에 대한 git 읽기를 모은 도우미. 같은 커밋을 되풀이해 묻지 않도록 결과를 기억한다."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self._commits: dict[str, bool] = {}

    def output(self, *args: str) -> bytes:
        """git을 불러 표준 출력(바이트)을 돌려준다. 종료 코드가 0이 아니면 GitError다."""
        done = _run(self.repo, *args)
        if done.returncode != 0:
            raise GitError(_failure(args, done))
        return done.stdout

    def text(self, *args: str) -> str:
        """output을 UTF-8 글로 푼 것(깨진 바이트는 대체 글자)."""
        return self.output(*args).decode("utf-8", errors="replace")

    def lookup(self, *args: str) -> str | None:
        """`rev-parse --verify --quiet` 꼴의 질문. 있으면 그 글, git이 '없다'고 답하면(종료 코드 1) None.

        그 밖의 실패(저장소가 깨졌거나 git이 예상하지 못한 방식으로 실패)는 '없다'가 아니라 읽지 못한 것이므로 GitError다.
        """
        done = _run(self.repo, *args)
        if done.returncode == 1:
            return None
        if done.returncode != 0:
            raise GitError(_failure(args, done))
        return done.stdout.decode("utf-8", errors="replace").strip()

    def require_history(self) -> None:
        """이 검사는 전체 이력이 있어야 한다. 얕은 복제거나 HEAD가 없으면 GitError."""
        if self.text("rev-parse", "--is-shallow-repository").strip() == "true":
            raise GitError(
                "얕은 복제라 이력이 모자라 잠금의 이력을 읽을 수 없다(전체 이력을 받아야 한다: git fetch --unshallow)"
            )
        if self.lookup("rev-parse", "--verify", "--quiet", "HEAD^{commit}") is None:
            raise GitError("HEAD가 없다(커밋이 하나도 없는 저장소는 검사할 수 없다)")

    def tracked_locks(self) -> set[str]:
        """HEAD의 트리에 있는 파일 가운데 이름이 잠금 파일인 것의 경로. 색인과 작업 트리는 보지 않는다."""
        names = self.text("ls-tree", "-r", "--name-only", "-z", "HEAD").split("\0")
        return {name for name in names if name and PurePosixPath(name).name in LOCK_NAMES}

    def is_commit(self, commit: str) -> bool:
        """commit이 이 저장소에서 커밋으로 풀리는지."""
        if commit not in self._commits:
            found = self.lookup("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
            self._commits[commit] = found is not None
        return self._commits[commit]

    def blob_id(self, rev: str, path: str) -> str | None:
        """`git rev-parse <rev>:<path>`. 그 커밋에 경로가 없으면 None."""
        return self.lookup("rev-parse", "--verify", "--quiet", f"{rev}:{path}")

    def history(self, path: str) -> list[str]:
        """HEAD에서 닿는 이력 가운데 path를 바꾼 커밋(새것부터). 이름을 따라가지 않고 경로를 글자 그대로 읽는다.

        사용자의 git 설정에 결과가 기대지 않게, 설정에 따라 출력이 달라질 수 있는 둘을 이 호출에서 끈다.
        - `-c log.follow=false`: log.follow=true는 경로 하나를 준 git log가 이름을 따라가게 한다. 그러면 폴더를 옮긴 잠금의
          이력이 옮기기 전의 옛 경로(다른 구성 요소의 이력일 수 있다)까지 이어져, 이 도구의 핵심 결정('이름 따라가기 없음')을
          설정 하나가 뒤집고 거짓으로 실패한다. `--no-follow` 같은 새 옵션과 달리, 옛 git도 `-c`로 받은 모르는 설정은 그냥
          무시하므로 어느 git에서나 안전하다.
        - `--no-show-signature`: log.showSignature를 켠 PC에서 서명된 커밋을 읽을 때 서명 확인 줄이 해시 줄 사이에 끼지
          않게 한다(그 설정이 꺼져 있으면 아무 영향이 없다).
        """
        out = self.text(
            "-c", "log.follow=false", "log", "--no-show-signature", "--format=%H", "--", f":(literal){path}"
        )
        commits = out.split()
        for commit in commits:
            if not _FULL_HASH.fullmatch(commit):
                raise GitError(f"git log의 출력이 40자 해시가 아니다(SHA-1 저장소만 다룬다): {commit}")
        return commits

    def commit_info(self, commit: str) -> tuple[str, list[str]]:
        """(커밋 날짜 YYYY-MM-DD, 부모 커밋 목록). 날짜는 커밋에 기록된 시간대의 날짜다(%cs).

        출력은 날짜 줄, 부모 줄(뿌리 커밋은 빈 줄) 순이다. --no-show-signature의 까닭은 history와 같다.
        """
        lines = self.text("show", "-s", "--no-show-signature", "--format=%cs%n%P", commit).split("\n")
        parents = lines[1].split() if len(lines) > 1 else []
        return lines[0], parents

    def read_blob(self, blob: str) -> bytes:
        """blob 객체의 바이트."""
        return self.output("cat-file", "blob", blob)


# ---------------------------------------------------------------------------------------------
# 검사
# ---------------------------------------------------------------------------------------------


def _short(commits: list[str]) -> str:
    """커밋 목록을 앞 7자로 줄여 쉼표로 이은 글."""
    return ", ".join(commit[:7] for commit in commits) or "(없음)"


def _describe_history(actual: list[str], expected: list[str]) -> str:
    """이력(새것부터)과 등록한 목록이 어디서 다른지 한 줄로 풀어 쓴다."""
    parts = []
    extra = [commit for commit in actual if commit not in expected]
    missing = [commit for commit in expected if commit not in actual]
    if extra:
        parts.append(f"등록하지 않은 변경 커밋 {_short(extra)}")
    if missing:
        parts.append(f"등록했지만 이 경로를 바꾸지 않은 커밋 {_short(missing)}")
    if not parts:
        parts.append(
            "커밋은 같지만 순서나 개수가 다르다(갱신은 옛것부터 적는다): "
            f"이력(새것부터) {_short(actual)}, 등록(새것부터) {_short(expected)}"
        )
    return "이 경로를 바꾼 커밋 목록이 등록과 다르다: " + "; ".join(parts)


def _render_changes(gone: Counter[tuple[str, str]], came: Counter[tuple[str, str]]) -> list[str]:
    """없어진 (이름, 판)과 생긴 (이름, 판)을 changes에 그대로 옮겨 적을 수 있는 글로 쓴다. 이름 순이다.

    같은 이름에 없어진 판 하나와 생긴 판 하나뿐이면 화살표 한 건("<이름> <옛 판> -> <새 판>")으로 묶어 읽기 좋게 한다. 그
    밖에는 없어진 판마다 "- <이름> <판>", 생긴 판마다 "+ <이름> <판>"으로 쓴다(한 이름의 판 둘이 함께 바뀐 경우의 짝은
    정해지지 않으므로 억지로 묶지 않는다. 어느 짝으로 적어도 견주는 결과는 같다).
    """
    lines: list[str] = []
    for name in sorted({key[0] for key in gone} | {key[0] for key in came}):
        olds = sorted(version for (other, version) in gone.elements() if other == name)
        news = sorted(version for (other, version) in came.elements() if other == name)
        if len(olds) == 1 and len(news) == 1:
            lines.append(f"{name} {olds[0]} -> {news[0]}")
        else:
            lines += [f"- {name} {version}" for version in olds]
            lines += [f"+ {name} {version}" for version in news]
    return lines


def _compare_changes(
    tag: str,
    old: Counter[tuple[str, str]],
    new: Counter[tuple[str, str]],
    registered: tuple[Change, ...],
) -> list[str]:
    """실제 차이가 등록한 changes와 같은지 본다. 같으면 빈 목록, 다르면 문제 한 줄을 담은 목록이다.

    실제 차이는 둘이다: 부모의 것(old)에서 그 커밋의 것(new)을 뺀 '없어진 (이름, 판)'과 반대인 '생긴 (이름, 판)'(Counter라
    같은 쌍이 여러 번이면 그 수까지 센다). 등록한 한 건은 화살표면 없어진 쪽에 (이름, 옛 판)을 생긴 쪽에 (이름, 새 판)을
    하나씩, `+`면 생긴 쪽에만, `-`면 없어진 쪽에만 보탠다. 이 둘이 실제 차이와 각각 정확히 같아야 한다. 건을 짝지어 견주지
    않으므로 한 이름의 판 둘이 함께 바뀐 갱신도 어느 짝으로 적든 같고, 화살표 한 건 대신 `-`·`+` 둘로 적어도 통한다. 순서는
    상관없고, 같은 건을 두 번 적으면 두 건이다.

    판이 없는 항목(빈 판)이 낀 이름은 changes에 적을 수 없다. 그 이름은 견주지 않고 까닭을 밝혀 그대로 문제로 둔다(그대로
    두고 견주면 적을 수 없는 건을 적으라는 안내가 나온다).
    """
    gone, came = old - new, new - old
    blocked = {name for name, version in [*gone, *came] if not version}
    gone = Counter({pair: count for pair, count in gone.items() if pair[0] not in blocked})
    came = Counter({pair: count for pair, count in came.items() if pair[0] not in blocked})
    listed_gone: Counter[tuple[str, str]] = Counter()
    listed_came: Counter[tuple[str, str]] = Counter()
    for name, before, after in registered:
        if before:
            listed_gone[(name, before)] += 1
        if after:
            listed_came[(name, after)] += 1
    parts = []
    unlisted = _render_changes(gone - listed_gone, came - listed_came)
    if unlisted:
        parts.append("등록에 없는 실제 차이 " + "; ".join(unlisted))
    unreal = _render_changes(listed_gone - gone, listed_came - came)
    if unreal:
        parts.append("등록에만 있는 차이 " + "; ".join(unreal))
    if blocked:
        parts.append("판이 없는 항목이 낀 이름은 changes에 적을 수 없다 " + ", ".join(sorted(blocked)))
    return [f"{tag}: 변경이 등록과 다르다: " + ", ".join(parts)] if parts else []


def _read_versions(git: _Git, blob: str, path: str, label: str, found: list[str]) -> Counter[tuple[str, str]] | None:
    """blob의 잠금을 읽어 (이름, 판)을 센다. 읽을 수 없으면 그 이유를 found에 적고 None을 돌려준다."""
    try:
        return lock_versions(git.read_blob(blob), path)
    except ValueError as error:
        found.append(f"{label}을 읽을 수 없다: {type(error).__name__}: {error}")
        return None


def _check_update(git: _Git, path: str, update: Update) -> tuple[list[str], str | None]:
    """갱신 하나를 검사한다. (문제 목록, 그 커밋에서의 잠금 blob 또는 읽지 못했으면 None)."""
    tag = f"갱신 {update.commit[:7]}"
    if not git.is_commit(update.commit):
        return [f"{tag}: {_UNKNOWN_COMMIT}"], None
    found: list[str] = []
    date, parents = git.commit_info(update.commit)
    if date != update.date:
        found.append(f"{tag}: date가 커밋 날짜와 다르다: 등록한 값 {update.date}, 커밋 날짜 {date}")
    blob = git.blob_id(update.commit, path)
    if blob is None:
        found.append(f"{tag}: 그 커밋에 {path} 파일이 없다")
    if len(parents) != 1:
        kind = "부모가 없는 뿌리 커밋이다" if not parents else f"부모가 {len(parents)}개인 병합 커밋이다"
        found.append(f"{tag}: {kind}(병합 커밋이나 뿌리 커밋으로 잠금을 바꾸지 않는다)")
        return found, blob
    if blob is None:
        return found, None
    parent_blob = git.blob_id(parents[0], path)
    if parent_blob is None:
        found.append(f"{tag}: 부모 {parents[0][:7]}에 {path} 파일이 없다")
        return found, blob
    old = _read_versions(git, parent_blob, path, f"{tag}: 부모의 잠금", found)
    new = _read_versions(git, blob, path, f"{tag}: 이 커밋의 잠금", found)
    if old is not None and new is not None:
        found += _compare_changes(tag, old, new, update.changes)
    return found, blob


def _check_lock(git: _Git, lock: Lock) -> list[str]:
    """꼴이 맞고 HEAD에서 추적되는 잠금 하나를 git 이력과 견준다. 문제의 이유를 한 줄씩 돌려준다."""
    found: list[str] = []

    # 규칙 2: added 커밋에서의 blob이 base와 같다.
    if not git.is_commit(lock.added):
        found.append(f"added {lock.added[:7]}: {_UNKNOWN_COMMIT}")
    else:
        added_blob = git.blob_id(lock.added, lock.path)
        if added_blob is None:
            found.append(f"added {lock.added[:7]}: 그 커밋에 {lock.path} 파일이 없다")
        elif added_blob != lock.base:
            found.append(f"base가 다르다: 등록한 값 {lock.base}, added {lock.added[:7]}에서의 실제 값 {added_blob}")

    # 규칙 3: 이 경로를 바꾼 커밋의 목록이 등록과 정확히 같다(등록은 옛것부터, 이력은 새것부터).
    actual = git.history(lock.path)
    expected = [update.commit for update in reversed(lock.updates)] + [lock.added]
    if actual != expected:
        found.append(_describe_history(actual, expected))

    # 규칙 5와 갱신에 딸린 확인. 마지막으로 읽은 갱신의 blob이 규칙 4가 HEAD와 견줄 값이다.
    last_blob: str | None = lock.base
    last_name = "base"
    for update in lock.updates:
        problems, blob = _check_update(git, lock.path, update)
        found += problems
        last_blob, last_name = blob, f"갱신 {update.commit[:7]}"

    # 규칙 4: HEAD의 잠금이 등록한 마지막 상태와 같다. 마지막 갱신을 읽지 못했으면(위에서 이미 알렸다) 견주지 않는다.
    if last_blob is not None:
        head_blob = git.blob_id("HEAD", lock.path)
        if head_blob != last_blob:
            found.append(f"HEAD의 잠금(blob {head_blob})이 등록한 마지막 상태({last_name}의 blob {last_blob})와 다르다")
    return found


def check(repo: Path, locks: list[Lock]) -> list[str]:
    """repo(git 저장소 뿌리)의 HEAD 이력이 등록한 locks와 맞는지 보고, 문제를 한 줄씩 돌려준다. 통과면 빈 목록.

    줄은 `<경로>: <이유>` 꼴이고 경로 순이다(같은 경로 안에서는 찾은 순서). 먼저 등록 항목의 꼴 오류(Lock.problems)를
    싣고, 이어 추적되는 잠금과 등록의 짝, 항목마다 이력 대조 순서로 본다.

    이력을 읽을 수 없으면(얕은 복제, HEAD 없음, git이 예상하지 못한 방식으로 실패) 문제 목록을 돌려주지 않고 GitError를
    던진다. 읽지 못한 채로 빈 목록(통과)이 되지 않게 하려는 것이다. git을 실행할 수 없으면 OSError가 나간다.
    """
    git = _Git(repo)
    git.require_history()
    tracked = git.tracked_locks()
    found: list[Problem] = []
    for lock in locks:
        found += lock.problems
    registered = {lock.path for lock in locks if lock.path}
    for path in sorted(tracked - registered):
        found.append((path, "등록하지 않은 잠금 파일이다(등록 파일에 [[lock]]으로 등록해야 한다)"))
    for path in sorted(registered - tracked):
        found.append((path, "등록했지만 HEAD에서 추적되지 않는 경로다(지운 잠금은 등록에서도 뺀다)"))
    for lock in locks:
        if lock.problems or lock.path not in tracked:
            continue
        found += [(lock.path, reason) for reason in _check_lock(git, lock)]
    found.sort(key=lambda problem: problem[0])  # sort는 안정적이라 같은 경로의 문제는 찾은 순서를 지킨다
    return [f"{path}: {reason}" for path, reason in found]


# ---------------------------------------------------------------------------------------------
# 명령줄
# ---------------------------------------------------------------------------------------------


def _use_utf8_output() -> None:
    """표준 출력·오류를 UTF-8로 다시 연다. 인코딩할 수 없는 글자는 \\uXXXX로 바꿔 죽지 않게 한다.

    한국어 Windows(코드 페이지 949)의 파이썬은 출력이 파이프나 파일이면 cp949로 써서 한글 출력이 깨진다.
    Linux CI는 이미 UTF-8이라 바뀌는 것이 없다.

    모듈을 가져올 때가 아니라 main이 시작할 때 한다: 시험이 출력을 가로채는 중에 import만으로 표준
    출력을 바꾸지 않으려는 것이다. reconfigure가 없는 스트림(가로채기용 객체)이거나 이미 닫혔으면
    건너뛴다. 출력 인코딩은 보조 수단이라 실패해도 검사 자체를 막지 않는다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            continue


def _cannot_start(repo: Path) -> str | None:
    """repo에서 git 검사를 시작할 수 없으면 이유를, 시작할 수 있으면 None을 돌려준다.

    git 저장소가 아닌 폴더에서는 모든 질문이 실패하므로, 검사에 들어가기 전에 한 번 확인해 '시작할 수 없음'으로
    알린다. 이력이 모자란 경우(얕은 복제, HEAD 없음)는 check가 GitError로 알린다.

    저장소 뿌리가 아닌 안쪽 폴더도 시작할 수 없다. git은 안쪽 폴더에서도 작업 트리 안이라고 답하지만 경로를 그 폴더 기준으로
    읽으므로, 트리 목록과 이력이 뿌리에서와 달라지고 등록이 비어 있으면 잠금이 있는데도 조용히 통과한다. `rev-parse
    --show-cdup`은 뿌리에서는 빈 줄, 안쪽 폴더에서는 뿌리까지 올라가는 경로(`../`)를 낸다(한 번의 호출로 둘을 함께 묻는다).
    """
    if not repo.is_dir():
        return f"저장소 폴더가 아니다: {repo}"
    try:
        done = _run(repo, "rev-parse", "--is-inside-work-tree", "--show-cdup")
    except OSError as error:
        return f"git을 실행할 수 없다: {type(error).__name__}: {error}"
    lines = done.stdout.decode("utf-8", errors="replace").split("\n")
    if done.returncode != 0 or lines[0].strip() != "true":
        reasons = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
        reason = f": {reasons[0]}" if reasons else ""
        return f"git 저장소가 아니다: {repo}{reason}"
    cdup = lines[1].strip() if len(lines) > 1 else ""
    if cdup:
        return f"저장소 뿌리가 아니라 안쪽 폴더다: {repo}(--repo에는 저장소 뿌리를 줘야 한다. 뿌리는 이 폴더에서 `{cdup}`다)"
    return None


def _build_parser() -> argparse.ArgumentParser:
    """명령줄 인자 해석기. 도움말은 한국어다."""
    parser = argparse.ArgumentParser(
        prog="check_lock_drift.py",
        add_help=False,  # 기본 -h 설명이 영어라서 아래에서 한국어 설명으로 직접 더한다
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "저장소가 추적하는 잠금 파일(uv.lock, package-lock.json)이 등록한 갱신으로만 바뀌었는지 본다.\n"
            "\n"
            "등록 파일(기본값: <저장소>/tools/locks.toml)의 [[lock]]마다 잠금을 처음 들인 커밋(added)과 그 시점의\n"
            "blob(base), 그 뒤 잠금을 바꾼 커밋들([[lock.update]]: commit, date, changes, why)을 적어 둔다.\n"
            "이 도구는 잠금의 내용과 이력을 git 객체에서만 읽어 등록과 견준다. 작업 트리의 잠금 파일은 읽지 않는다.\n"
            "\n"
            "이 도구는 읽기만 한다. 등록 파일과 저장소의 파일을 고치지 않는다."
        ),
        epilog=(
            "검사하는 것(어긋날 때마다 문제 한 줄):\n"
            "  1. HEAD에서 추적되는 파일 가운데 이름이 uv.lock이나 package-lock.json인 것은 모두 등록돼 있고,\n"
            "     등록한 경로는 모두 추적된다.\n"
            "  2. git rev-parse <added>:<path>가 base와 같다. 내용은 크기가 아니라 blob 해시로 견준다.\n"
            "  3. git log --format=%H -- <path>(이름 따라가기 없음)의 목록이 [마지막 update, ..., 첫 update, added]와\n"
            "     정확히 같다. 등록하지 않은 변경 커밋이 있으면 문제다. 갱신은 옛것부터 적는다.\n"
            "  4. git rev-parse HEAD:<path>가 마지막 update 커밋에서의 blob(update가 없으면 base)과 같다.\n"
            "  5. update마다 그 커밋의 부모와 그 커밋에서 잠금을 읽어 '없어진 (이름, 판)'과 '생긴 (이름, 판)'이 각각 changes와\n"
            "     정확히 같다. changes 한 건은 세 꼴이다: '<패키지> <옛 판> -> <새 판>'(판이 바뀜), '+ <패키지> <판>'(새로\n"
            "     들어옴), '- <패키지> <판>'(빠짐). 순서는 상관없다. 어긋나면 등록에 없는 실제 차이와 등록에만 있는 차이를\n"
            "     같은 꼴로 보여 준다. 판이 없는 항목이 낀 이름은 적을 수 없어 그대로 문제다.\n"
            "     update 커밋은 부모가 하나여야 하고, date는 커밋 날짜(git show -s --format=%cs)와 같아야 한다.\n"
            "\n"
            "종료 코드: 0 = 문제 없음, 1 = 문제가 있음(한 줄씩 출력), 2 = 검사를 시작하거나 끝낼 수 없음(등록 파일이\n"
            "없거나 읽을 수 없음, 저장소 폴더가 아니거나 git 저장소가 아니거나 저장소 뿌리가 아님, git을 실행할 수\n"
            "없음, 얕은 복제, HEAD 없음, 예상하지 못한 git 실패). 출력의 끝 줄은 '잠금 N개, 문제 M개'이며, 통과 여부는\n"
            "끝 줄 글자가 아니라 종료 코드로 판정한다.\n"
            "\n"
            "전체 이력이 필요하다(얕은 복제에서는 git fetch --unshallow). 이름을 따라가지 않으므로(git 설정 log.follow가\n"
            "켜져 있어도 끈다), 폴더를 옮겨 들인 잠금은 옮긴 커밋을 added로 등록한다. --repo는 저장소 뿌리여야 한다.\n"
            "\n"
            "예: uv run --no-project tools/check_lock_drift.py\n"
            "    uv run --no-project tools/check_lock_drift.py --registry <다른 등록 파일>"
        ),
    )
    parser.add_argument("-h", "--help", action="help", help="이 도움말을 보여 주고 끝낸다")
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        metavar="<저장소>",
        help="경로의 기준이 되는 git 저장소 뿌리. 안쪽 폴더는 받지 않는다 (기본값: 이 파일에서 두 단계 위 폴더)",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        metavar="<toml>",
        help="등록 파일 (기본값: <저장소>/tools/locks.toml). 작업 트리의 파일을 읽는다",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """등록을 읽어 검사하고 문제를 출력한다. 종료 코드는 0(통과), 1(문제), 2(검사를 시작하거나 끝낼 수 없음)."""
    _use_utf8_output()
    args = _build_parser().parse_args(argv)
    repo = args.repo if args.repo is not None else DEFAULT_REPO
    registry = args.registry if args.registry is not None else repo / DEFAULT_REGISTRY_FILE
    try:
        locks = load_registry(registry)
    except (OSError, ValueError) as error:
        # ValueError에는 tomllib.TOMLDecodeError(문법 오류)와 UnicodeDecodeError(UTF-8이 아님)가 든다.
        print(f"등록 파일을 읽을 수 없다: {registry}: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    reason = _cannot_start(repo)
    if reason is not None:
        print(f"검사를 시작할 수 없다: {reason}", file=sys.stderr)
        return 2
    try:
        problems = check(repo, locks)
    except (GitError, OSError) as error:
        print(f"검사를 끝낼 수 없다: {error}", file=sys.stderr)
        return 2
    for problem in problems:
        print(problem)
    print(f"잠금 {len(locks)}개, 문제 {len(problems)}개")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
