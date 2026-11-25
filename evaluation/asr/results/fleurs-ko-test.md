# 같은 발화 인식 비교 (fleurs-ko-test)

> 구성 요소가 이미 커밋한 발화별 가설을 같은 규칙으로 다시 채점한 결과다(새 디코딩 없음). 읽은 재료와 sha256은 같은 이름의 JSON 파일의 `inputs`에 있고, 규칙은 저장소의 `docs/asr-comparison.md`에 있다. 95% 구간은 발화를 다시 뽑는 부트스트랩이다(1000번, 시드 0).

## 전체 382발화

| 묶음 | 구성 요소 | 편집 수 | 정답 글자 수 | 글자 오류율(%) | 95% 구간(%) |
|---|---|---:|---:|---:|---|
| voice-turbo-vad | voice-translator | 808 | 17680 | 4.57 | [3.64, 5.58] |
| voice-turbo | voice-translator | 854 | 17680 | 4.83 | [3.86, 5.82] |
| whisper-small | whisper-ko-ft | 1348 | 17680 | 7.62 | [6.57, 8.71] |
| whisper-large-v3-turbo | whisper-ko-ft | 921 | 17680 | 5.21 | [4.25, 6.23] |
| small-a | whisper-ko-ft | 2048 | 17680 | 11.58 | [9.41, 14.94] |
| turbo-l2 | whisper-ko-ft | 1227 | 17680 | 6.94 | [5.82, 8.16] |
| turbo-t | whisper-ko-ft | 1211 | 17680 | 6.85 | [5.73, 8.03] |
| turbo-n | whisper-ko-ft | 981 | 17680 | 5.55 | [4.54, 6.68] |
| turbo-n2 | whisper-ko-ft | 1012 | 17680 | 5.72 | [4.70, 6.87] |
| qwen3-asr-1.7b | whisper-ko-ft | 790 | 17680 | 4.47 | [3.53, 5.52] |
| qwen3-asr-1.7b-qn | whisper-ko-ft | 1004 | 17680 | 5.68 | [4.62, 6.79] |
| qwen3-asr-1.7b-qn-s050 | whisper-ko-ft | 844 | 17680 | 4.77 | [3.80, 5.80] |
| stt-scratch-full | stt-scratch | 3490 | 17680 | 19.74 | [18.41, 21.18] |
| stt-scratch-streaming | stt-scratch | 4025 | 17680 | 22.77 | [21.44, 24.24] |

## 한글 전용 257발화

| 묶음 | 구성 요소 | 편집 수 | 정답 글자 수 | 글자 오류율(%) | 95% 구간(%) |
|---|---|---:|---:|---:|---|
| voice-turbo-vad | voice-translator | 175 | 11346 | 1.54 | [1.07, 2.14] |
| voice-turbo | voice-translator | 176 | 11346 | 1.55 | [1.06, 2.14] |
| whisper-small | whisper-ko-ft | 545 | 11346 | 4.80 | [4.07, 5.71] |
| whisper-large-v3-turbo | whisper-ko-ft | 172 | 11346 | 1.52 | [1.04, 2.11] |
| small-a | whisper-ko-ft | 562 | 11346 | 4.95 | [4.20, 5.79] |
| turbo-l2 | whisper-ko-ft | 210 | 11346 | 1.85 | [1.33, 2.53] |
| turbo-t | whisper-ko-ft | 197 | 11346 | 1.74 | [1.25, 2.40] |
| turbo-n | whisper-ko-ft | 208 | 11346 | 1.83 | [1.31, 2.50] |
| turbo-n2 | whisper-ko-ft | 224 | 11346 | 1.97 | [1.47, 2.62] |
| qwen3-asr-1.7b | whisper-ko-ft | 171 | 11346 | 1.51 | [1.04, 2.13] |
| qwen3-asr-1.7b-qn | whisper-ko-ft | 234 | 11346 | 2.06 | [1.52, 2.70] |
| qwen3-asr-1.7b-qn-s050 | whisper-ko-ft | 169 | 11346 | 1.49 | [1.03, 2.09] |
| stt-scratch-full | stt-scratch | 1659 | 11346 | 14.62 | [13.48, 15.97] |
| stt-scratch-streaming | stt-scratch | 2013 | 11346 | 17.74 | [16.57, 19.05] |

## 짝 비교

| 짝 | 앞 − 뒤 | 범위 | 차이(%p) | 95% 구간(%p) | 앞이 적은 발화 | 앞이 많은 발화 | 같은 발화 |
|---|---|---|---:|---|---:|---:|---:|
| decoding-path | whisper-large-v3-turbo − voice-turbo | 전체 | +0.38 | [+0.14, +0.61] | 13 | 29 | 340 |
| decoding-path | whisper-large-v3-turbo − voice-turbo | 한글 전용 | -0.04 | [-0.13, +0.05] | 10 | 6 | 241 |
| vad | voice-turbo − voice-turbo-vad | 전체 | +0.26 | [+0.04, +0.49] | 17 | 27 | 338 |
| vad | voice-turbo − voice-turbo-vad | 한글 전용 | +0.01 | [-0.10, +0.11] | 9 | 10 | 238 |
| both | whisper-large-v3-turbo − voice-turbo-vad | 전체 | +0.64 | [+0.33, +0.95] | 19 | 46 | 317 |
| both | whisper-large-v3-turbo − voice-turbo-vad | 한글 전용 | -0.03 | [-0.17, +0.12] | 12 | 10 | 235 |
