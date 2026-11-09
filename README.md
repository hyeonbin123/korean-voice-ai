# korean-voice-ai

한국어 콜센터 음성 AI. 음성 인식 파인튜닝, 처음부터 만든 스트리밍 음성 인식, 실시간 음성 번역, 고객센터 상담 에이전트, 상담 후처리 요약 모델을 한 저장소에 모았다. 이 첫 화면은 임시이며 곧 바뀐다.

| 폴더 | 내용 |
|---|---|
| [`whisper-ko-ft/`](whisper-ko-ft/) | 공개 한국어 음성 데이터로 Whisper를 파인튜닝하고, 미리 정한 규칙으로 전후를 측정한다 |
| [`stt-scratch/`](stt-scratch/) | 한국어 음성 인식 모델을 처음부터 설계·학습하고(청크 인과 Conformer-CTC, 공개 데이터), 미리 정한 규칙으로 측정해 스트리밍 자막 서비스로 묶는다 |
| [`voice-translator/`](voice-translator/) | 영어↔한국어 음성 번역 웹 서비스. 음성 인식·번역·음성 합성 모델을 측정해서 고름 (FastAPI, React, faster-whisper, CTranslate2, MeloTTS·Kokoro) |
| [`support-agent/`](support-agent/) | 한국어 고객센터 업무를 도구 호출로 처리하는 LLM 상담 에이전트와, 미리 정한 규칙으로 성공률을 재는 평가 환경 |
| [`call-summary/`](call-summary/) | 한국어 상담 대화를 상담 후처리 기록(JSON)으로 바꾸는 소형 LLM 파인튜닝·서빙과 사전 등록 측정 |

- 각 폴더는 원래 저장소의 커밋을 해시 그대로 가져왔다. 문서에 적힌 커밋 해시는 이 저장소에서 `git show <해시>`로 열린다. 합친 방법은 [docs/history.md](docs/history.md).
- 파일 이력은 `git log --follow -- <폴더>/<경로>`와 `git blame <폴더>/<경로>`로 옮기기 전 커밋까지 따라간다.
- 실행·테스트 명령은 각 폴더의 README.md에 있다.
