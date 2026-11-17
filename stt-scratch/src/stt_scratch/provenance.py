"""측정 결과에 남기는 코드 출처(git_head·git_dirty·git_tree)를 코드가 있는 폴더 기준으로 구하는 헬퍼.

측정 도구(scripts/stage6.py, followup.py, confidence_eval.py, itn_eval.py; bias_eval.py와 final_pass_dump.py는
그 도구들의 함수를 불러 쓴다)는 결과 파일마다 '어떤 코드로 쟀는가'를 남긴다. 그 값을 정하는 코드가 도구마다
복사돼 있던 것을 이 모듈 하나로 모았다. 근거와 적용 시점은 docs/experiments.md의 규칙 변경 31이다.

돌려주는 세 필드(키 순서 고정):
  git_head   저장소의 HEAD 커밋 해시(`git rev-parse HEAD`, 40자). 저장소 전체의 커밋이라 이 폴더와 상관없는
             폴더의 커밋으로도 달라진다.
  git_dirty  이 폴더 안의 추적 파일에 커밋하지 않은 변경(작업 트리 또는 스테이징)이 있는지
             (`git status --porcelain --untracked-files=no -- .`의 출력이 있는가). 추적하지 않는 새 파일은
             세지 않는다(이전 복사본들과 같은 규약).
  git_tree   이 폴더의 git 트리 해시(`git rev-parse --verify --quiet HEAD:./`). 이 폴더의 커밋된 내용만
             반영하므로 다른 폴더의 커밋으로는 바뀌지 않는다. 이 폴더가 HEAD 커밋에 없으면 None.
"""

# [왜 폴더 기준인가] 이 폴더는 다른 구성 요소와 한 저장소에 들어 있다. 경로 없이 `git status`를 부르면
# 저장소 전체의 추적 파일을 보므로, 다른 구성 요소에서 바뀐 파일 때문에 이 폴더의 측정 기록에도 git_dirty가
# 참으로 남는다. 그러면 그 기록만으로는 이 폴더의 코드가 커밋된 것이었는지 알 수 없다. 그래서 `git status`에
# `-- .`를 줘 git을 부르는 작업 폴더(cwd) 아래로 좁히고, git_tree를 더해 '이 폴더의 커밋된 내용'을 다른
# 폴더의 커밋과 상관없이 가리킨다(git_tree가 같으면 폴더의 커밋된 내용이 같다). `HEAD:./`의 `./`는 git의 상대
# 경로 표기로 '지금 폴더'를 뜻한다(gitrevisions: `./`나 `../`로 시작하는 경로는 작업 폴더 기준). 그래서 폴더
# 이름이나 저장소 안의 위치를 알 필요가 없고, 폴더 하나가 저장소 전체인 경우에는 뿌리의 트리 해시
# (`HEAD^{tree}`)가 된다.
# [왜 root를 인자로 받나] 기준을 프로세스의 작업 폴더가 아니라 코드가 있는 폴더(각 스크립트의 ROOT)로
# 고정하려는 것이다. 작업 폴더를 기준으로 삼으면 저장소 뿌리나 하위 폴더에서 도구를 돌릴 때 범위가 엉뚱해져,
# 예를 들어 src/ 아래의 바뀐 파일을 놓친다. 부르는 쪽은 호출할 때의 ROOT를 넘겨야 한다(시험이 ROOT를 임시
# 폴더로 바꿔 끼운다).
# [실패할 때] 기록용 값이라 도구를 멈추지 않는다. git 실행 파일이 없거나(OSError) root가 저장소 밖이거나 HEAD
# 커밋이 없어서 `rev-parse HEAD`나 `status`가 실패하면 셋 다 None이다(git이 없는 곳에서도 측정 도구는 돌고,
# 기록에는 '출처를 모른다'가 남는다. 이전 복사본들의 규약과 같다). 그 폴더만 HEAD 커밋에 없는 경우(추적하지
# 않는 폴더)는 git_tree만 None이고 나머지 둘은 그대로 구한다. 어느 커밋 위에서 쟀는지는 여전히 알 수 있기
# 때문이다.

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(root: Path, *args: str) -> str:
    """`root`에서 `git <args>`를 실행해 표준 출력(앞뒤 공백 제거)을 돌려준다.

    git 실행 파일이 없거나 root를 작업 폴더로 쓸 수 없으면 OSError, 종료 코드가 0이 아니면
    subprocess.CalledProcessError가 올라온다. 두 예외를 잡는 것은 부르는 scoped_git_state의 몫이다.
    """
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def scoped_git_state(root: Path) -> dict[str, str | bool | None]:
    """`root` 폴더 기준의 코드 출처 `{"git_head", "git_dirty", "git_tree"}`를 돌려준다(이 순서).

    입력: root = 코드가 있는 폴더(스크립트의 ROOT). git 명령은 모두 이 폴더를 작업 폴더로 해서 부르므로
    프로세스의 작업 폴더와 무관하다. 저장소 뿌리여도 되고 저장소 안의 하위 폴더여도 된다.

    출력: git_head = 40자 해시, git_dirty = bool, git_tree = 40자 해시 또는 None. 각 필드의 뜻은 모듈
    설명을 본다.
    - git이 없거나 root가 저장소 밖이거나 HEAD 커밋이 없어 `rev-parse HEAD`나 `status`가 실패하면 셋 다 None.
    - 그 둘은 되는데 root 폴더가 HEAD 커밋에 없으면(추적하지 않는 폴더) git_tree만 None.
    git이 없거나 명령이 실패해도 예외를 올리지 않는다(기록용 값이라 측정을 멈추지 않는다).

    주의: git_head는 저장소 전체의 커밋이라 다른 폴더의 커밋으로도 달라진다. 이 폴더의 커밋된 내용이 같은지는
    git_tree로 비교하고, 커밋하지 않은 변경은 git_dirty로 본다.
    """
    try:
        head = _git(root, "rev-parse", "HEAD")
        status = _git(root, "status", "--porcelain", "--untracked-files=no", "--", ".")
    except (OSError, subprocess.CalledProcessError):
        return {"git_head": None, "git_dirty": None, "git_tree": None}
    try:
        # --verify --quiet: 그 폴더가 HEAD 커밋에 없으면 오류 글 없이 종료 코드 1로 끝난다(아래에서
        # None으로 바꾼다).
        tree = _git(root, "rev-parse", "--verify", "--quiet", "HEAD:./")
    except (OSError, subprocess.CalledProcessError):
        tree = ""
    return {"git_head": head, "git_dirty": bool(status), "git_tree": tree or None}
