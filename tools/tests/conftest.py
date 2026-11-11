"""루트 도구(`tools/*.py`) 시험이 함께 쓰는 설정과 고정물.

루트에는 파이썬 프로젝트(pyproject.toml, uv.lock)가 없다. 그래서 이 시험들은 프로젝트 환경이 아니라
`uv run --no-project --with pytest==9.1.1 --with pyyaml==6.0.3 pytest tools/tests` 같은 임시 환경에서 돈다.
루트 도구는 의존성 없는 한 장짜리 스크립트라 설치할 패키지가 없고, 시험이 부르는 모듈은 이 폴더의 부모인
`tools/`에서 바로 가져온다. 구성 요소 코드나 구성 요소의 환경은 건드리지 않는다.

제공하는 것:
    REPO       저장소 뿌리 경로. 이 파일(tools/tests/conftest.py)에서 두 단계 위다. 실제 저장소 문서를
               대상으로 하는 시험이 쓴다.
    git_repo   시험마다 새로 만드는 빈 git 저장소(고정물). 줄바꿈 변환을 끄고 시험용 신원을 넣어 두어,
               이 PC의 전역 git 설정과 상관없이 같은 결과가 나온다.
"""

import subprocess
import sys
from pathlib import Path

import pytest

# tools/tests/conftest.py → parents[0] = tools/tests, parents[1] = tools, parents[2] = 저장소 뿌리.
REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"

# 시험 파일이 `import check_root_numbers`처럼 도구 모듈을 바로 가져올 수 있게 tools 폴더를 맨 앞에 넣는다.
# 루트에 패키지 설정이 없으므로 설치 대신 경로로 찾는다. 이미 들어 있으면 다시 넣지 않는다.
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """빈 git 저장소를 tmp_path 안에 만들어 그 경로를 돌려준다.

    설정과 이유:
        core.autocrlf=false   Windows의 git 기본값(true)이면 커밋·체크아웃 때 줄바꿈이 바뀌어 바이트를 다루는
                              시험이 PC마다 달라진다. 이 저장소의 규칙(기록 파일은 바이트 그대로)과 같게 끈다.
        user.name/user.email  커밋을 만드는 시험이 신원 없음으로 멈추지 않게 하는 시험용 값이다.
        commit.gpgsign=false  서명을 켜 둔 PC에서 시험 커밋이 서명 입력을 기다리며 멈추지 않게 한다.
        초기 브랜치 main      git 설정에 따라 master가 되는 일을 막아 브랜치 이름을 고정한다.

    주의: 반환한 경로는 tmp_path 그대로라 같은 시험에서 tmp_path 고정물과 함께 쓰면 같은 폴더를 가리킨다.
    """

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True)

    git("init", "--quiet", "--initial-branch=main")
    git("config", "core.autocrlf", "false")
    git("config", "user.name", "Test User")
    git("config", "user.email", "test@example.com")
    git("config", "commit.gpgsign", "false")
    return tmp_path
