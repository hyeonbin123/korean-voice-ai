# 고지 모음

구성 요소 폴더에는 다른 곳에서 가져오거나 다른 곳의 코드를 옮겨 쓴 파일이 몇 개 들어 있다. 또 whisper-ko-ft, voice-translator, stt-scratch는 학습·평가·서비스에 쓰는 공개 데이터와 모델의 라이선스를 각자의 문서에 표나 절로 적어 두었다. 이 문서는 그 고지가 있는 자리만 모은다. 고지의 원문과 내용은 각 자리에 있는 그대로이고, 여기로 옮겨 적거나 고치지 않았다.

이 저장소 자체의 라이선스 파일(`LICENSE`)은 아직 없다.

## 다른 곳에서 가져오거나 옮겨 쓴 파일

| 구성 요소 | 파일 | 무엇인가 | 고지가 있는 곳 |
|---|---|---|---|
| whisper-ko-ft | [`src/whisper_ko_ft/english.json`](../whisper-ko-ft/src/whisper_ko_ft/english.json) | Hugging Face `openai/whisper-small` 저장소가 `normalizer.json`으로 배포하는 영미 철자 사전(영국 철자 → 미국 철자 1,740쌍)의 사본. 영어 보조 지표의 정규화에 쓴다 | 같은 폴더 [`en_norm.py`](../whisper-ko-ft/src/whisper_ko_ft/en_norm.py)의 머리 주석: '사전 사본의 출처'와 MIT 라이선스 고지 |
| voice-translator | [`frontend/src/conversation/assets/silero_vad_v6.onnx`](../voice-translator/frontend/src/conversation/assets/silero_vad_v6.onnx) | 대화 모드가 브라우저에서 돌리는 말소리 구간 검출 모델(Silero VAD v6). faster-whisper 1.2.1에 들어 있는 같은 이름의 파일을 바이트 그대로 복사했다 | 같은 폴더의 [`SILERO-LICENSE.txt`](../voice-translator/frontend/src/conversation/assets/SILERO-LICENSE.txt)(모델, MIT), [`ONNXRUNTIME-LICENSE.txt`](../voice-translator/frontend/src/conversation/assets/ONNXRUNTIME-LICENSE.txt)(브라우저 추론에 쓰는 onnxruntime-web, MIT), 출처와 SHA-256을 적은 [`SOURCE.md`](../voice-translator/frontend/src/conversation/assets/SOURCE.md) |
| voice-translator | [`backend/app/services/supertonic.py`](../voice-translator/backend/app/services/supertonic.py) | 비교용 한국어 음성 합성 Supertonic 3를 돌리는 코드. 글 전처리와 추론 단계는 보관된 참조 코드(supertone-oss-archive/supertonic의 `py/helper.py`)를 따른다 | 같은 파일 머리 docstring: 참조 코드의 커밋과 MIT 라이선스 원문(Supertone Inc.) |
| voice-translator | [`backend/eval/metricx_score.py`](../voice-translator/backend/eval/metricx_score.py) | 번역 모델 Hy-MT2 시험의 오염 점검에 쓰는 MetricX-24 참조 없는(QE) 문장 점수 스크립트. 순전파(입력 꼴, 토큰화, 디코더 한 단계에서 점수 읽기)는 공식 코드(google-research/metricx의 `metricx24/models.py`와 `predict.py`)를 따른다 | 같은 파일 머리 docstring: 따른 코드의 커밋과 라이선스 이름(Apache-2.0), 같은 폴더의 [`METRICX-LICENSE.txt`](../voice-translator/backend/eval/METRICX-LICENSE.txt)(google-research/metricx의 라이선스 파일 원문, Apache-2.0) |

voice-translator의 화면을 내주는 nginx 설정에는 두 라이선스 파일의 자리가 따로 있다(없는 파일을 화면 HTML로 대체하지 않고 404, `Cache-Control: no-cache`). 그 설정은 [`frontend/src/test/nginx.test.ts`](../voice-translator/frontend/src/test/nginx.test.ts)가 검사한다.

## 데이터와 모델의 라이선스

- whisper-ko-ft: [README의 '데이터와 모델' 표](../whisper-ko-ft/README.md#데이터와-모델). 학습·평가 데이터 Zeroth-Korean과 FLEURS(CC BY 4.0), 모델 Whisper(MIT)와 Qwen3-ASR(Apache 2.0).
- voice-translator: [README의 '모델과 데이터의 라이선스' 표](../voice-translator/README.md#모델과-데이터의-라이선스). 음성 인식·번역·음성 합성 모델과 평가 데이터 FLEURS의 라이선스이고, 번역 모델 opus-mt-tc-big은 CC-BY-4.0이다. 비교용 설정으로만 쓰는 음성 합성 모델 Supertonic 3(BigScience OpenRAIL-M)의 이용 제한 고지도 같은 절에 있다.
- stt-scratch: [`docs/data.md`의 '귀속 (2026-10-24 확인)' 절](../stt-scratch/docs/data.md#귀속-2026-10-24-확인). 학습·평가 데이터 Zeroth-Korean·FLEURS(CC BY 4.0)와 Common Voice(CC0)의 저작자 표시와 변경 표시다. 그 구성 요소가 다시 배포하는 전사문과 모델 출력(가설)이 이 데이터의 파생물이라는 것도 그 절에 적혀 있다.
