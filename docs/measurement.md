# 측정 원칙

다섯 구성 요소는 측정을 같은 원칙으로 했다. 규칙의 원문과 모든 수치는 각 구성 요소의 `docs/experiments.md`에 있고, 이 문서는 그 원칙과 자리를 모은다.

## 공통 원칙

1. **측정 규칙과 판정 기준을 먼저 커밋한다.** 후보, 지표, 고르는 규칙, 판정 기준을 재기 전에 그 구성 요소의 `docs/experiments.md`에 적어 커밋하고 잰다. 그 문서의 규칙 절에는 '측정 전', '재기 전'처럼 언제 적었는지가 붙어 있다.
2. **개발용 묶음으로 고르고, 시험용 묶음은 한 번만 잰다.** 후보는 개발용(validation, dev) 묶음으로 고른다. 시험용(test) 묶음은 그 실험에서 고른 것(과 견줄 기준선 등)만 한 번 재고, 그 결과를 보고 고른 것을 바꾸지 않는다. 시험용 묶음으로 무엇을 재는지는 구성 요소의 규칙마다 다르다(아래 표의 마지막 열). 이것은 실험 하나 안의 규칙이다. 실험을 건너서 같은 시험용 묶음을 다시 쓴 구성 요소도 있고, 그 사실을 기록에 남겼다(아래 표의 support-agent와 call-summary 줄).
3. **기록한 수치는 고치지 않고, 바로잡거나 더 확인한 것은 날짜를 붙여 덧붙인다.** 예: whisper-ko-ft README의 '2026-10-24 추가 확인'(기록된 수치·판정은 그대로 두고 조건을 더함), voice-translator README의 '2026-11-03 덧붙임'(설정이 바뀐 뒤에도 표의 test 수치는 바뀌기 전 설정으로 잰 값으로 둠), call-summary README의 '2026-10-29 바로잡음'.
4. **부정적 결과도 공개한다.** 개선이 없거나 기준을 넘지 못한 판정도 같은 자리에 적는다. 예: support-agent의 '판정: 개선 없음', whisper-ko-ft의 '도메인 전용' 판정, call-summary가 음성 인식기를 바꿔 보고 바꾸지 않은 판정.
5. **수치 옆에 조건을 적는다.** 어떤 데이터와 설정에서 잰 값인지를 수치와 같은 자리에 둔다. 예: whisper-ko-ft의 Zeroth 수치는 처음 듣는 화자가 학습에서 본 문장을 읽는 조건이다. call-summary 결과 요약에는 모델마다 양자화와 실행 방식이 적혀 있다.

## 구성 요소별 자리

| 구성 요소 | 규칙과 결과 | 기록 수치를 지키는 시험 | 시험용 묶음을 쓰는 방식 |
|---|---|---|---|
| whisper-ko-ft | [`docs/experiments.md`](../whisper-ko-ft/docs/experiments.md) | [`tests/test_recorded_reports.py`](../whisper-ko-ft/tests/test_recorded_reports.py): 커밋된 리포트(`reports/`)의 발화별 채점과 요약 오류율을 지금 코드로 다시 계산해 기록과 같은지 본다 | README 결과 표의 'test (단계마다 한 번 측정)': 규칙은 단계가 끝날 때 기준선과 고른 모델 하나만 test에서 한 번 재는 것이다 |
| stt-scratch | [`docs/experiments.md`](../stt-scratch/docs/experiments.md), AI가 만든 코드를 어떻게 검증했는지의 기록 [`docs/ai-verification.md`](../stt-scratch/docs/ai-verification.md) | [`tests/test_sealed_breakdown.py`](../stt-scratch/tests/test_sealed_breakdown.py): 저장된 봉인 test 가설로 사후 분석을 다시 계산해 커밋된 결과와 같은지 본다 | 봉인 test를 2026-10-14에 한 번 쟀다. 두 번째 시작과 다른 구성으로의 재개를 막고 실행 중에는 잠그는 보호 장치([`scripts/stage7.py`](../stt-scratch/scripts/stage7.py), 시험 [`tests/test_stage7_guards.py`](../stt-scratch/tests/test_stage7_guards.py))가 있다 |
| voice-translator | [`docs/experiments.md`](../voice-translator/docs/experiments.md) | [`backend/tests/test_eval_metrics.py`](../voice-translator/backend/tests/test_eval_metrics.py): 기록된 말 끝 판정·동시통역 자막 수치를 만든 지표 함수를 손으로 계산할 수 있는 사례로 고정한다 | README '측정해서 고른 결과': 선택은 FLEURS validation으로, 확인은 고른 설정만 test로 한 번 |
| support-agent | [`docs/experiments.md`](../support-agent/docs/experiments.md) | [`tests/test_recorded_numbers.py`](../support-agent/tests/test_recorded_numbers.py): README와 `docs/experiments.md`의 기록 수치를 커밋된 `reports/` 기록에서 다시 계산해 글과 맞춰 본다 | 규칙은 실험이 끝날 때 고른 후보만 시험용 40과제로 한 번 잰다는 것이다. 실험을 건너서는 같은 40과제를 다시 썼고, 시험용을 쓴 기록을 모두 [시험용 사용 장부](../support-agent/docs/experiments.md#시험용-사용-장부-2026-10-29부터-적음-측정-없음)에 적는다(위 시험이 장부를 실행 기록과 맞춰 본다) |
| call-summary | [`docs/experiments.md`](../call-summary/docs/experiments.md) | [`docs/numbers.toml`](../call-summary/docs/numbers.toml)과 `python -m call_summary.compare --check docs/numbers.toml`: README의 평가 수치를 실행 기록의 건별 점수에서 다시 계산해 README에 적힌 소수 자리까지 같은지 본다(`tests/test_numbers.py`가 같은 검사를 CI에서 돌린다) | README 결과 요약: 표의 각 모델을 test 세트마다 한 번 쟀다. 같은 절의 2026-10-29 바로잡음대로 test-a는 단계마다 다른 모델로 여러 번 쟀다 |

세 구성 요소(whisper-ko-ft, stt-scratch, voice-translator)가 같은 발화에 남긴 가설을 견주는 비교는 구성 요소 밖에 있다. 그 규칙과 결과는 [`docs/asr-comparison.md`](asr-comparison.md)에 있고, 재계산은 [`evaluation/asr`](../evaluation/asr/README.md)의 시험과 CI 단계(`repo-checks`)가 한다.

## 이 저장소에서 달라진 것

- **공식 측정은 그 구성 요소 폴더의 추적 파일이 바뀌지 않았을 때 돈다.** call-summary의 공식 측정(`--official`)은 call-summary 폴더 안에 바뀐 추적 파일이 있으면 시작하지 않고([`src/call_summary/evaluate.py`](../call-summary/src/call_summary/evaluate.py#L416), [`src/call_summary/service_eval.py`](../call-summary/src/call_summary/service_eval.py#L158)), 서비스의 컨텍스트 초과 동작을 확인하는 스크립트도 같은 검사로 시작을 막는다([`scripts/ctx_probe.py`](../call-summary/scripts/ctx_probe.py#L256), 시험 실행용 `--allow-dirty`를 주지 않으면). 다른 구성 요소 폴더의 바뀐 파일은 보지 않는다. call-summary와 stt-scratch의 결과에는 저장소의 커밋과 함께 그 폴더의 트리 해시(`git_tree`)가 남고, stt-scratch는 그 폴더의 추적 파일이 바뀌었는지를 `git_dirty`로 남긴다([`src/stt_scratch/provenance.py`](../stt-scratch/src/stt_scratch/provenance.py#L67)). 다른 구성 요소의 코드를 실행에 쓰는 스크립트는 그 코드 경로도 함께 본다(call-summary의 음성 조건 스크립트는 support-agent의 `src`, `pyproject.toml`, `uv.lock`). 규칙은 call-summary [`docs/experiments.md`의 '측정 출처를 이 폴더 기준으로' 절](../call-summary/docs/experiments.md#측정-출처를-이-폴더-기준으로-2026-11-18-규칙-변경-측정-없음)과 stt-scratch [`docs/experiments.md`의 '규칙 변경' 31번](../stt-scratch/docs/experiments.md#규칙-변경)에 있다. 2026-11-18 전에는 저장소 전체를 봤다. 그 전의 기록은 구성 요소가 저장소 하나였을 때 남긴 것이라 뜻이 같다.
- **stt-scratch 사후 분석은 입력 파일의 내용을 마지막으로 바꾼 커밋과 blob 해시를 남긴다.** stt-scratch의 [`scripts/sealed_breakdown.py`](../stt-scratch/scripts/sealed_breakdown.py)는 읽은 whisper-ko-ft 보고서의 출처로 저장소 최상위 폴더 이름, 저장소 뿌리 기준 경로, 그 파일의 내용을 마지막으로 바꾼 커밋(이름만 바꾼 커밋은 건너뛴다), 그 파일의 git blob 해시를 남긴다. 커밋된 기록([`reports/final/zeroth_anchor_notation.json`](../stt-scratch/reports/final/zeroth_anchor_notation.json))의 출처 값은 합치기 전 저장소에서 남긴 그대로다(폴더 이름 `whisper-ko-ft`, 그 저장소 기준 경로, blob 없음). 이 저장소에서 다시 돌리면 폴더 이름은 이 저장소를 받은 폴더의 이름이 되고 경로 앞에 `whisper-ko-ft/`가 붙지만, 커밋은 기록에 적힌 것과 같은 값이 나온다. 그 커밋은 이 저장소에서도 그대로 열린다([history.md](history.md)). 2026-11-18 전의 도구는 경로만 한정해 마지막 커밋을 물어서, 이 저장소에서 돌리면 그 파일을 이 폴더로 옮긴 이동 커밋을 냈다.
- **루트 문서의 수치는 구성 요소 기록 글자와 대조한다.** 첫 화면과 `docs/`에 옮겨 적은 수치는 [`root-numbers.toml`](../root-numbers.toml)이 수마다 출처 파일과 그 자리의 글을 짝지어 두고, [`tools/check_root_numbers.py`](../tools/check_root_numbers.py)가 두 쪽의 글자가 여전히 같은지 대조한다. 수를 다시 계산하지는 않는다. 기록을 다시 계산하는 일은 위 표의 각 구성 요소 시험이 한다.

## 증거 검사

문서와 코드는 근거를 커밋 해시로 가리킨다. 해시는 글자일 뿐이라 오타이거나 이력에 없는 커밋이어도 읽는 사람은 알 수 없다. [`tools/check_evidence.py`](../tools/check_evidence.py)가 main에 올릴 때와 pull request마다 그 글자를 이 저장소의 이력과 맞춰 본다. 등록 파일은 [`tools/evidence.toml`](../tools/evidence.toml)이다.

- **적힌 해시.** 추적 파일에서 7자에서 40자의 16진수 낱말을 뽑아, 이 저장소의 커밋으로 풀리는 낱말은 지금 브랜치의 이력에 있는 커밋이어야 한다. 문서(`.md`)가 커밋이라고 밝혀 적은 낱말(백틱 한 쌍 안에 그 낱말만 있거나 '커밋'·'commit' 바로 뒤에 온 것)은 반드시 풀려야 한다. 다른 프로젝트의 커밋이나 모델·데이터 저장소의 revision처럼 이 저장소의 커밋이 아닌 해시는 적힌 파일과 함께 등록해 둔다.
- **기록 파일의 커밋 값.** 등록한 측정 기록(네 구성 요소의 `reports/` 기록 등)이 '이 코드로 쟀다'고 남긴 커밋 값이 이 저장소의 이력에 있는 커밋인지 본다. 기록에 폴더의 트리 해시(`git_tree`)가 있으면 그 커밋에서의 그 구성 요소 폴더의 트리와 같은지도 본다.
- **규칙이 결과보다 먼저.** 등록한 '규칙 커밋 → 결과 커밋' 짝마다 규칙 커밋이 결과 커밋의 조상인지, 커밋 시각이 앞서거나 같은지, 그 순서를 적은 문서에 두 해시가 있는지 본다.

보지 않는 것도 있다. 등록한 짝만 보므로 모든 측정의 순서를 망라하지 않는다. 다른 저장소의 해시가 그 저장소에 실제로 있는지는 보지 않는다. 문서가 커밋이라고 밝히지 않고 적은 낱말은 풀리지 않아도 문제로 보지 않는다(데이터 해시나 숫자와 가를 수 없어서다). 잠금 파일은 [`tools/check_lock_drift.py`](../tools/check_lock_drift.py)가 따로 본다([environments.md](environments.md#하나의-잠금으로-묶지-않는-이유)).

이 검사는 2026-11-25에 더했다. 처음 두 주는 문제를 보고만 하고(CI가 실패하지 않는다), 그 뒤에는 문제가 있으면 CI가 실패하게 바꾼다.
