# 모델 선택

수치는 각 구성 요소 기록에서 옮긴 것이고 `tools/check_root_numbers.py`가 글자를 대조한다(선언은 [`root-numbers.toml`](../root-numbers.toml)).

구성 요소마다 무엇을 골랐는지, 무엇과 견줬는지, 어떤 규칙으로 골랐는지, 결과가 어떤 조건에서 잰 값인지를 적는다. 고르는 규칙은 재기 전에 커밋했고, 시험용 묶음은 고른 것만 쟀다([measurement.md](measurement.md)). 전체 표와 한계는 각 근거 링크에 있다.

## whisper-ko-ft

공개 한국어 음성 데이터(Zeroth-Korean)로 Whisper를 파인튜닝한다.

- 고른 것: whisper-large-v3-turbo에 LoRA를 붙이고, 학습 정답의 숫자 표기를 아라비아 숫자로 바꿔 학습한 모델. 서빙 기본으로는 CTranslate2 int8_float16을 권한다. Transformers로 디코딩할 때는 재시도 디코딩을 켜고, 출력의 숫자 표기를 아라비아 숫자로 바꾸는 후처리를 쓴다.
- 비교한 대안: whisper-small 전체 파인튜닝과 숫자 표기를 바꾸지 않은 turbo LoRA(둘 다 다른 도메인이 허용 폭보다 나빠져 '도메인 전용'으로 판정), 더 오래 학습, 계열이 다른 공개 모델 Qwen3-ASR-1.7B. Qwen3-ASR-1.7B는 학습 없이도 FLEURS 한국어에서 기준선 turbo보다 낮아 '다른 도메인에서 더 나은 기준 모델'로 판정했지만(그 모델의 학습 데이터에 FLEURS가 들어 있었을 수 있다), 같은 방식으로 LoRA를 학습하자 다른 도메인의 이점을 잃어 고른 모델을 유지했다. 그 LoRA의 갱신량을 절반으로 줄여 합친 모델은 같은 도메인의 오류율이 고른 모델보다 높아 다른 도메인용 기준 모델로만 둔다.
- 고른 규칙: 후보와 판정 규칙을 학습 전에 적고 validation으로 판정했다. 같은 도메인(Zeroth)의 이득을 지키면서 다른 도메인(FLEURS 한국어)의 악화가 미리 정한 허용 폭 안이어야 범용으로 본다. test는 고른 모델만 한 번 쟀다.
- 결과(Zeroth 공식 test, 처음 듣는 화자가 학습에서 본 문장을 읽는 조건, 숫자 표기를 맞춘 CER): 기준선 turbo 4.22% → 고른 모델 2.68%. 한 발화의 되풀이 오류가 든 값이고, 재시도 디코딩을 켜면 1.98%다.
- 결과(다른 도메인, FLEURS 한국어 test의 CER): 기준선 turbo 5.21% → 고른 모델 5.55%.
- 근거: [README '지금까지의 결과'](../whisper-ko-ft/README.md#지금까지의-결과), [README '한계'](../whisper-ko-ft/README.md#한계), [`docs/experiments.md`](../whisper-ko-ft/docs/experiments.md).

## stt-scratch

한국어 스트리밍 음성 인식 모델을 사전학습 가중치 없이 처음부터 만든다.

- 고른 것: 청크 인과 Conformer-CTC(약 21M 파라미터)를 공개 데이터로 처음부터 학습한 모델. 최종 모델은 6층 중간 CTC(InterCTC) 헤드와 TrimTail 이어 학습을 쓴다.
- 비교한 대안: 구조를 정하기 전에 문헌 조사로 Zipformer, E-Branchformer, transducer 계열 등을 견줬다([조사 종합](../stt-scratch/docs/survey/README.md)의 '결정' 절). 그 뒤 같은 학습 예산의 비교 실험으로 손실(자기조건 CTC와 InterCTC, CR-CTC)과 블록(E-Branchformer)을 쟀다.
- 고른 규칙: 후보는 dev 묶음(FLEURS validation과 Common Voice dev)으로 견주고, 처음 보는 문장만 모은 Zeroth dev가 미리 정한 폭보다 나빠지는 후보는 채택하지 않는다. 봉인 test는 마지막에 한 번 쟀다.
- 결과(봉인 test, 전체 문맥 greedy, 한글 전용 발화의 공백 제외 CER): Zeroth 공식 test 3.67%, 처음 보는 문장만 15.55%, FLEURS 한국어 14.62%, Common Voice 한국어 28.19%. Zeroth 공식 test는 문장 대부분이 학습 세트에도 있어 문장 암기와 일관된 값이다.
- 근거: [README '결과 (봉인 test, 2026-10-14 1회)'](../stt-scratch/README.md#결과-봉인-test-2026-10-14-1회), [`docs/experiments.md`](../stt-scratch/docs/experiments.md), [`docs/survey/README.md`](../stt-scratch/docs/survey/README.md).

## voice-translator

영어↔한국어 음성 번역 웹 서비스의 모델을 단계마다 측정해서 골랐다.

- 고른 것: 음성 인식 Whisper large-v3-turbo(faster-whisper) + VAD, 번역 opus-mt-tc-big(한→영·영→한, CTranslate2로 변환), 음성 합성 MeloTTS(한국어)와 Kokoro-82M(영어), 글자로 입력한 영어의 오타 교정 qwen2.5 1.5B, 대화 모드의 말 끝 판정 Silero VAD(1초 쉼).
- 비교한 대안: 음성 인식 small·large-v3, 번역 opus-mt-ko-en·NLLB-200(distilled 600M)·qwen2.5 7B, 음성 합성 MMS-TTS. 한국어 음성 합성은 뒤에 Supertonic 3도 시험했지만 채택하지 않아 비교용 설정으로만 남았다.
- 고른 규칙: 모델마다 후보와 판단 규칙을 측정 전에 적고 FLEURS validation으로 골랐다. 예를 들어 음성 인식은 지연 예산 안에 드는 후보 가운데 한국어 CER과 영어 WER의 평균이 가장 낮은 것을 고르되, 그 값과 차이가 작은 후보가 여럿이면 가장 빠른 것을 고른다. 확인은 고른 설정만 test로 한 번 했다.
- 결과(FLEURS test): 음성 인식 한국어 CER 4.57%, 영어 WER 4.95%. 번역 chrF(정답 전사를 번역) 한→영 55.7, 영→한 36.1.
- 한→영 번역의 기본 디코딩은 나중에 바뀌었고(2026-11-03 덧붙임), 위 한→영 test 수치는 바뀌기 전 설정으로 잰 값이다.
- 근거: [README '측정해서 고른 결과'](../voice-translator/README.md#측정해서-고른-결과), [`docs/experiments.md`](../voice-translator/docs/experiments.md).

## support-agent

가상 쇼핑몰 고객센터 업무를 도구 호출로 처리하는 한국어 상담 에이전트의 모델을 골랐다.

- 고른 것: 서비스 기본 모델 `qwen3.5:4b`(사고 모드를 끔). 규정을 프롬프트에 적는 데 더해 도구 안에서도 막는 구성(P1)에서 쓴다.
- 비교한 대안: 이전 기본 모델 qwen2.5 7B, qwen2.5 14B, `qwen3:4b-instruct-2507`. 7B에서 규정 적용 방식, 추론 절차, 멈춤 가드, 모델 크기, 완료 주장 가드를 바꿔 본 실험은 모두 '개선 없음'이었다.
- 고른 규칙: 개발용 24과제 × 4회로 후보를 고르고 시험용 40과제 × 4회로 판정했다. 개선으로 보려면 기준과의 차이 구간이 0보다 위이고, 규정 위반이 통과되지 않고, 정답에 없는 쓰기가 규정을 프롬프트에만 적은 7B 참조 이하여야 한다(재기 전에 커밋).
- 결과(시험용 40과제 × 4회, P1 구성): pass^1이 qwen2.5 7B 18.1%에서 `qwen3.5:4b` 55.6%로 올랐다(차이 +37.5%p). 대신 과제가 요구하지 않은 쓰기가 6건에서 13건으로 늘었다.
- 근거: [README](../support-agent/README.md)의 새 세대 소형 모델 측정 결과 절, [`docs/experiments.md`](../support-agent/docs/experiments.md), 서비스 설정 [`src/support_agent/service/settings.py`](../support-agent/src/support_agent/service/settings.py#L28-L31).

## call-summary

상담 대화 전사를 상담 후처리 기록(JSON)으로 바꾸는 소형 모델을 학습하고 서빙한다.

- 고른 것: Qwen3-4B를 QLoRA로 학습한 모델. 학습 데이터 절반을 음성 인식을 거친 전사로 바꿔 학습했고, GGUF q8_0으로 바꿔 Ollama로 서빙한다.
- 비교한 대안: 프롬프트만 쓴 qwen2.5 7B·14B(14B는 기록 관례를 덧붙인 프롬프트로도), 학습하지 않은 Qwen3-4B, 2026년 기준 같은 크기의 지시 모델 둘(`qwen3:4b-instruct-2507`, 생각을 끈 `qwen3.5:4b`), 서빙 양자화 q4_K_M.
- 고른 규칙: 측정 규칙을 먼저 커밋하고 dev로 고른 뒤, test 세트는 모델마다 한 번 쟀다. 두 모델은 같은 건끼리 짝지은 부트스트랩 구간으로 견준다. 주 지표 exact는 구조 필드(유형, 처리 결과, 핵심 값, 처리 목록, 후속 조치)가 모두 맞은 비율이다.
- 결과(서빙 모델 GGUF q8_0의 exact, 생성한 가상 데이터): test-a(같은 생성기) 95.7, test-c(학습에 없던 업종) 49.5, test-d v2(합성 음성을 전화 음질로 바꿔 Whisper로 다시 받아 적은 전사) 79.3. 같은 분할에서 프롬프트만 쓴 `qwen3.5:4b`는 18.7, 4.5, 13.3이었다.
- 결과(양자화, dev 240건의 exact): GGUF q8_0 94.6(학습한 모델 그대로와 같음), q4_K_M 66.2.
- 근거: [README](../call-summary/README.md)의 결과 요약 절들, [`docs/experiments.md`](../call-summary/docs/experiments.md).
