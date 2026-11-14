# 이력

2026-11-10에 아래 다섯 저장소를 이 저장소의 같은 이름 폴더로 합쳤다. 원래 커밋을 해시 그대로 들였고 이력을 다시 쓰지 않았다. 그래서 각 폴더의 문서·기록에 적힌 커밋 해시(측정 규칙을 먼저 커밋했다는 근거 등)가 이 저장소에서 그대로 열린다.

| 폴더 | 원래 저장소 | 합친 시점의 마지막 커밋 | 커밋 수 | 태그 |
|---|---|---|---|---|
| `whisper-ko-ft/` | https://github.com/hyeonbin123/whisper-ko-ft | `2541ec6926904228d2c8d54ae9e786f5578352df` | 94 | `archive/whisper-ko-ft` |
| `stt-scratch/` | https://github.com/hyeonbin123/stt-scratch | `3b729ad801f5da3a639223ad4fbb832326548b1c` | 109 | `archive/stt-scratch` |
| `call-summary/` | https://github.com/hyeonbin123/call-summary | `92b9601128412dda4a58604f29eeea9496727a48` | 144 | `archive/call-summary` |
| `support-agent/` | https://github.com/hyeonbin123/support-agent | `1315de6cb1c2500f1cab041f80178dd960604f75` | 156 | `archive/support-agent` |
| `voice-translator/` | https://github.com/hyeonbin123/voice-translator | `43aaa3c79226074e8511027dc147eea1fcee1b1b` | 212 | `archive/voice-translator` |

원래 저장소 열의 주소는 합칠 때 각 저장소가 있던 주소를 기록으로 남긴 것이다. 태그 `archive/<폴더>`는 합친 시점의 마지막 커밋을 가리키고, 커밋 수는 `git rev-list --count archive/<폴더>`로 다시 셀 수 있다.

## 합친 방법

1. 원래 저장소의 사본에서 추적 파일 전부를 `<폴더>/` 아래로 옮기기만 하는 커밋을 하나 만든다. 파일 내용과 모드는 그대로라, 이 커밋의 `<폴더>/` 트리 해시는 원래 마지막 커밋의 트리 해시와 같다.
2. 이 저장소에서 그 커밋을 `git merge --allow-unrelated-histories --no-ff`로 합친다. 폴더가 겹치지 않아 충돌이 없다.

폴더마다 만든 두 커밋은 아래와 같다. 이동 커밋의 `<폴더>/` 트리가 원래 마지막 커밋의 트리와 같다는 것은 `git rev-parse <이동 커밋>:<폴더>`와 `git rev-parse archive/<폴더>^{tree}`가 같은 값을 내는 것으로 다시 확인할 수 있다.

| 폴더 | 이동 커밋 | 병합 커밋 |
|---|---|---|
| `whisper-ko-ft/` | `9a5ff2a1fc2f1c97adf13a87de335490f5296973` | `164cd41f1ffba8228c09d4814dcbe84cfddd99d1` |
| `stt-scratch/` | `4c1dac2d165febfa86e1e9717530d52f246bf8b3` | `acdc25d0abbd8f7a3d493927c04e3be2da3a5173` |
| `call-summary/` | `5432507cdcf029ff684bdfb7efb7e8f2df4cbc37` | `28ef8dfaf3fb33a7c2e621e6ed5fc030d9681680` |
| `support-agent/` | `06edbe607119482eb39f0cb7df27cc906a48850a` | `e4c71b664d555ca316997a552f1fb55df81305c9` |
| `voice-translator/` | `345969b22645fc518340af7016c238ba36af3925` | `88707d36559433bbbc22c7082e73fd95528e6230` |

쓰지 않은 방법과 까닭:

- 하위 폴더로 옮기면서 모든 커밋을 다시 쓰는 방법(`git filter-repo --to-subdirectory-filter`), squash, rebase: 커밋 해시가 모두 바뀌어 문서에 적힌 해시가 이 저장소에서 열리지 않는다.
- `git subtree add`: 원래 해시는 남지만, 합친 뒤 `git log --follow -- <폴더>/<경로>`가 옮기기 전 커밋을 따라가지 못한다.
- 파일만 복사하기: 이력이 남지 않는다.

## 합칠 때 바꾼 것

다섯 병합 뒤 같은 날 main에 더한 커밋 가운데 구성 요소 폴더나 워크플로를 바꾼 것은 아래 여섯이다. 커밋 메시지에 바꾼 까닭이 있다(`git show <커밋>`).

- 워크플로 자리(`3603aec`, `7f06758`, `136dd4e`, `fa0628d`, `c93b094`): GitHub는 저장소 맨 위의 `.github/workflows`에 있는 워크플로만 읽는다. 그래서 구성 요소마다 `<폴더>/.github/workflows/ci.yml`을 `.github/workflows/<폴더>.yml`로 옮겼다. 옮긴 워크플로는 main push와 pull request로는 그 폴더나 그 워크플로 파일이 바뀌었을 때만 돌고, 단계는 그 폴더 안(voice-translator는 `backend/`·`frontend/` 안)에서 돈다. 작업, 액션, 권한, 취약점 검사의 예외 목록은 바꾸지 않았다.
- 워크플로를 읽는 시험 두 파일(`136dd4e`, `fa0628d`): call-summary `tests/test_container.py`와 support-agent `tests/test_deploy_config.py`는 이제 저장소 맨 위의 새 워크플로 파일을 읽고, 그 파일이 없을 때만 옛 경로(`.github/workflows/ci.yml`)를 읽는다. 검사하는 내용은 그대로다.
- call-summary 출처 검사의 건너뛰는 조건(`142f7cf`): `tests/test_asr_condition.py`에서 고정 사본(support-agent 커밋 `a5717ce`의 `verbalize.py`)을 원본과 견주는 검사는 전에는 형제 폴더에 `support-agent/.git`이 있을 때만 돌았다. 지금은 support-agent 폴더가 있고 git이 그 커밋을 찾을 수 있으면 돈다. 이력이 얕은 CI 체크아웃에서는 여전히 건너뛴다. 견주는 방법은 그대로다.

저장소 맨 위의 `.gitleaksignore`에는 비밀값 검사(gitleaks)가 찾지만 비밀값이 아닌 것의 지문이 있다. support-agent의 같은 파일에서 옮긴 한 줄과 voice-translator 이력의 아홉 줄이고, 줄마다 바로 위 주석에 까닭을 적었다.

구성 요소 폴더의 문서와 원래 커밋 메시지는 기록 그대로 두었다. 그래서 그 글 속의 경로는 옮기기 전 저장소의 맨 위를 기준으로 하고(예: whisper-ko-ft README가 말하는 `docs/experiments.md`는 이 저장소의 `whisper-ko-ft/docs/experiments.md`다), 그 글의 '이 저장소'는 원래 저장소를 뜻한다. 이 저장소로 옮겼다는 안내는 기존 글을 고치지 않고 각 구성 요소 README의 맨 끝에 날짜를 붙여 덧붙인다.

## 이력 따라가기

- `git log --follow -- <폴더>/<경로>`: 옮긴 커밋을 넘어 원래 커밋까지 보인다. 다만 옮기기 전 경로가 다른 구성 요소와 겹치는 파일(원래 저장소 맨 위에 있던 `README.md`, `pyproject.toml`, `uv.lock` 같은 것)은 옮긴 커밋을 지난 뒤 다른 구성 요소의 같은 경로 파일을 바꾼 커밋까지 함께 나온다. 예를 들어 `git log --follow -- whisper-ko-ft/README.md`에는 다섯 구성 요소의 `README.md` 이력이 섞인다.
- 한 구성 요소의 파일 이력만 보려면 아래 가운데 하나를 쓴다.
  - `git log archive/<폴더> -- <옛 경로>`: 원래 저장소 안의 이력을 옮기기 전 경로로 본다. 예: `git log archive/whisper-ko-ft -- README.md`.
  - `git log --follow <이동 커밋> -- <폴더>/<경로>`: 위 표의 이동 커밋에서 출발해 그 구성 요소의 원래 이력만 따라간다. 예: `git log --follow 9a5ff2a -- whisper-ko-ft/README.md`.
  - 옮긴 뒤 이 저장소에서 바뀐 것은 `git log -- <폴더>/<경로>`(`--follow` 없이)로 본다. 이 명령은 옮긴 커밋에서 멈춘다.
- `git blame <폴더>/<경로>`: 줄마다 원래 커밋이 보인다.
- `git log archive/<폴더>`: 원래 저장소의 마지막 커밋까지의 이력.
