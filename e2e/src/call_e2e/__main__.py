"""python -m call_e2e를 설치된 call-e2e 명령과 같은 진입점으로 연결한다."""

from .cli import main

raise SystemExit(main())
