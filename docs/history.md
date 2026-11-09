# 이력

2026-11-10에 아래 다섯 저장소를 이 저장소의 같은 이름 폴더로 합쳤다. 원래 커밋을 해시 그대로 들였고 이력을 다시 쓰지 않았다. 그래서 각 폴더의 문서·기록에 적힌 커밋 해시(측정 규칙을 먼저 커밋했다는 근거 등)가 이 저장소에서 그대로 열린다.

| 폴더 | 원래 저장소 | 합친 시점의 마지막 커밋 | 커밋 수 | 태그 |
|---|---|---|---|---|
| `whisper-ko-ft/` | https://github.com/hyeonbin123/whisper-ko-ft | `2541ec6926904228d2c8d54ae9e786f5578352df` | 94 | `archive/whisper-ko-ft` |
| `stt-scratch/` | https://github.com/hyeonbin123/stt-scratch | `3b729ad801f5da3a639223ad4fbb832326548b1c` | 109 | `archive/stt-scratch` |
| `call-summary/` | https://github.com/hyeonbin123/call-summary | `92b9601128412dda4a58604f29eeea9496727a48` | 144 | `archive/call-summary` |
| `support-agent/` | https://github.com/hyeonbin123/support-agent | `1315de6cb1c2500f1cab041f80178dd960604f75` | 156 | `archive/support-agent` |
| `voice-translator/` | https://github.com/hyeonbin123/voice-translator | `43aaa3c79226074e8511027dc147eea1fcee1b1b` | 212 | `archive/voice-translator` |

## 합친 방법

1. 원래 저장소의 사본에서 추적 파일 전부를 `<폴더>/` 아래로 옮기기만 하는 커밋을 하나 만든다. 파일 내용과 모드는 그대로라, 이 커밋의 `<폴더>/` 트리 해시는 원래 마지막 커밋의 트리 해시와 같다.
2. 이 저장소에서 그 커밋을 `git merge --allow-unrelated-histories --no-ff`로 합친다. 폴더가 겹치지 않아 충돌이 없다.

## 이력 따라가기

- `git log --follow -- <폴더>/<경로>`: 옮긴 커밋을 넘어 원래 커밋까지 보인다.
- `git blame <폴더>/<경로>`: 줄마다 원래 커밋이 보인다.
- `git log archive/<폴더>`: 원래 저장소의 마지막 커밋까지의 이력.
