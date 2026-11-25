# 같은 발화로 본 한국어 인식 비교

## 무엇을 견주나

이 저장소의 세 구성 요소(whisper-ko-ft, stt-scratch, voice-translator)는 모두 FLEURS 한국어 test 382발화로 음성 인식을 잰 적이 있고, 그때의 발화별 정답과 가설을 리포트 파일로 커밋해 두었다. 이 문서는 그 가설들을 같은 발화끼리 짝지어 한 가지 규칙으로 다시 채점한 비교다.

- 왜 필요한가: 구성 요소마다 따로 적은 수치는 조건이 달라 그대로 나란히 놓을 수 없다. 같은 large-v3-turbo 모델인데 [whisper-ko-ft의 기록](../whisper-ko-ft/README.md)은 CER(글자 오류율) 5.21%이고 [voice-translator의 기록](../voice-translator/README.md)은 4.57%다. 두 구성 요소는 디코딩 방식이 다르다(아래 규칙 7). [stt-scratch의 대표 수치](../stt-scratch/README.md)는 한글만으로 된 발화만 센 값이라 범위부터 다르다. 같은 발화를 같은 정답과 같은 채점으로 다시 세면 이 수치들을 한 표에 놓고 견줄 수 있다.
- 무엇이 아닌가: 새로 디코딩하지 않는다(모델을 돌리지 않는다). 이미 저장된 가설을 다시 채점하는 사후 분석이고, 이 결과로 모델을 고르거나 구성 요소의 기록을 고치지 않는다.
- 도구: [`evaluation/asr`](../evaluation/asr/README.md). 재료를 읽기만 하고, 결과 파일은 `evaluation/asr/results/`에 둔다.

## 규칙 (2026-11-25, 재기 전)

아래 규칙을 먼저 커밋하고 그 뒤에 잰다. 결과는 이 문서의 아래쪽에 날짜를 붙여 덧붙이고, 이 절은 고치지 않는다(바꿀 일이 생기면 날짜를 붙인 덧붙임으로 남긴다).

1. 성격. 새 디코딩 없이, 세 구성 요소가 이미 커밋한 발화별 가설을 다시 채점하는 사후 분석이다. FLEURS 한국어 test 382발화는 세 구성 요소가 각자의 규칙으로 이미 한 번씩 잰 시험용 자료이고, 이 문서는 그때의 가설을 다시 쓴다. 이 결과를 새 모델을 고르는 데 쓰지 않는다.

2. 재료. 견주는 가설 묶음은 아래 열넷이다(표의 차례가 결과 표의 차례다). 묶음은 아래 키로 부른다.

   | 키 | 구성 요소 | 파일 |
   |---|---|---|
   | `voice-turbo-vad` | voice-translator | [`backend/eval/reports/stt_t14_test_20260913_055810.json`](../voice-translator/backend/eval/reports/stt_t14_test_20260913_055810.json) |
   | `voice-turbo` | voice-translator | [`backend/eval/reports/stt_t2_test_20260912_224129_rescored.json`](../voice-translator/backend/eval/reports/stt_t2_test_20260912_224129_rescored.json) |
   | `whisper-small` | whisper-ko-ft | [`reports/whisper-small/fleurs-ko-test.json`](../whisper-ko-ft/reports/whisper-small/fleurs-ko-test.json) |
   | `whisper-large-v3-turbo` | whisper-ko-ft | [`reports/whisper-large-v3-turbo/fleurs-ko-test.json`](../whisper-ko-ft/reports/whisper-large-v3-turbo/fleurs-ko-test.json) |
   | `small-a` | whisper-ko-ft | [`reports/small-a/fleurs-ko-test.json`](../whisper-ko-ft/reports/small-a/fleurs-ko-test.json) |
   | `turbo-l2` | whisper-ko-ft | [`reports/turbo-l2/fleurs-ko-test.json`](../whisper-ko-ft/reports/turbo-l2/fleurs-ko-test.json) |
   | `turbo-t` | whisper-ko-ft | [`reports/turbo-t/fleurs-ko-test.json`](../whisper-ko-ft/reports/turbo-t/fleurs-ko-test.json) |
   | `turbo-n` | whisper-ko-ft | [`reports/turbo-n/fleurs-ko-test.json`](../whisper-ko-ft/reports/turbo-n/fleurs-ko-test.json) |
   | `turbo-n2` | whisper-ko-ft | [`reports/turbo-n2/fleurs-ko-test.json`](../whisper-ko-ft/reports/turbo-n2/fleurs-ko-test.json) |
   | `qwen3-asr-1.7b` | whisper-ko-ft | [`reports/qwen3-asr-1.7b/fleurs-ko-test.json`](../whisper-ko-ft/reports/qwen3-asr-1.7b/fleurs-ko-test.json) |
   | `qwen3-asr-1.7b-qn` | whisper-ko-ft | [`reports/qwen3-asr-1.7b-qn/fleurs-ko-test.json`](../whisper-ko-ft/reports/qwen3-asr-1.7b-qn/fleurs-ko-test.json) |
   | `qwen3-asr-1.7b-qn-s050` | whisper-ko-ft | [`reports/qwen3-asr-1.7b-qn-s050/fleurs-ko-test.json`](../whisper-ko-ft/reports/qwen3-asr-1.7b-qn-s050/fleurs-ko-test.json) |
   | `stt-scratch-full` | stt-scratch | [`reports/final/test_fleurs-full.hyps.jsonl`](../stt-scratch/reports/final/test_fleurs-full.hyps.jsonl) |
   | `stt-scratch-streaming` | stt-scratch | [`reports/final/test_fleurs-streaming.hyps.jsonl`](../stt-scratch/reports/final/test_fleurs-streaming.hyps.jsonl) |

   - 각 묶음이 어떤 모델과 설정으로 낸 가설인지는 그 구성 요소의 문서에 있다([whisper-ko-ft](../whisper-ko-ft/docs/experiments.md), [stt-scratch](../stt-scratch/docs/experiments.md), [voice-translator](../voice-translator/docs/experiments.md)).
   - stt-scratch의 두 묶음은 발화의 문장 번호, 음성 길이, 한글 전용 표시를 [`manifests/test_fleurs.jsonl`](../stt-scratch/manifests/test_fleurs.jsonl)에서 함께 읽는다.
   - `voice-turbo`는 정답을 다시 정규화해 저장한 판(파일 이름 끝이 `_rescored`)을 읽는다. 고치기 전의 원본에는 작은따옴표가 남은 정답이 있어 쓰지 않는다.
   - whisper-ko-ft에는 가설이 글자까지 같은 리포트가 네 쌍 있다. 표에는 한쪽만 싣는다. 다른 쪽은 채점하지 않고, 같은 발화의 같은 가설인지만 확인한다(규칙 3의 첫째\~다섯째를 표의 묶음과 똑같이 받고, 일곱째가 가설이 글자까지 같은지를 본다): `turbo-n` = `turbo-n-d1a`, `qwen3-asr-1.7b` = `qwen3-asr-1.7b-fixed`, `qwen3-asr-1.7b-qn` = `qwen3-asr-1.7b-qn-fixed`, `qwen3-asr-1.7b-qn-s050` = `qwen3-asr-1.7b-qn-s050-fixed`.
   - 넣지 않는 것: whisper-ko-ft의 전화 채널 리포트(`fleurs-ko-test@telephone.json`). 음성을 전화 대역으로 바꿔 잰 다른 조건이다.
   - 그래서 읽는 재료 파일은 열아홉이다(표의 열넷, 같은 가설 리포트 넷, stt-scratch의 매니페스트 하나). 각 파일의 sha256은 [`evaluation/asr/inputs.sha256`](../evaluation/asr/inputs.sha256)에 있다. 이 값은 줄 끝의 CRLF를 LF로 바꾼 내용으로 센다(줄바꿈 변환을 켠 채 받은 복제본에서도 같은 값이 나오게 하려는 것이다. LF로 커밋된 파일은 파일을 그대로 센 값과 같고, CRLF로 커밋된 stt-scratch의 가설 파일 둘만 다르다).

3. 결합. 발화는 행 번호로만 짝짓는다. 행 번호는 FLEURS 한국어 test 안에서 발화가 놓인 자리다(0\~381). stt-scratch는 발화 id의 마지막 수가 행 번호다(그 파일 안의 차례는 행 번호 순이 아니다). voice-translator와 whisper-ko-ft의 리포트에는 행 번호가 없어서 리포트 안의 위치를 행 번호로 받아들인다(전제다 — 아래 '확인하지 못하는 것'). 아래 여덟 가지가 모두 맞아야 잰다([`join.py`](../evaluation/asr/src/asr_compare/join.py)의 `verify`).
   1. 묶음마다(같은 가설 리포트 포함) 발화가 382개이고 행 번호 0\~381이 한 번씩 나온다. 여기서 어긋나면 뒤의 검사는 하지 않는다(행으로 짝지을 수 없다).
   2. 행마다 문장 번호가 모든 묶음(같은 가설 리포트 포함)에서 같다.
   3. 행마다 음성 길이가 모든 묶음(같은 가설 리포트 포함)에서 같다(소수 둘째 자리로 반올림해 견준다).
   4. whisper-ko-ft 리포트(같은 가설 리포트 포함)의 발화 id가, 행 번호 순으로 그 문장의 첫 녹음이면 문장 번호 그대로이고 n번째 녹음이면 문장 번호 뒤에 `#n`이 붙은 꼴이다.
   5. voice-translator와 whisper-ko-ft 묶음(같은 가설 리포트 포함)의 정규화한 정답이 모든 행에서 공통 정답(규칙 4)과 같다.
   6. stt-scratch 묶음의 정규화한 정답이 공통 정답과 다른 행이 23과 57, 정확히 이 두 행이고, 두 행은 한글 전용이 아니다.
   7. 같은 가설이라고 적은 리포트의 가설이 모든 행에서 글자까지 같다(정규화하기 전의 저장된 글로 견준다).
   8. 한글 전용 표시가 382개이고 그 가운데 257개가 참이다.

   알려진 차이(여섯째): stt-scratch는 정답을 한글·영문자(A\~Z, a\~z)·숫자·공백만 남기는 학습용 정규화를 거친 글로 저장한다. 그래서 악센트가 붙은 글자가 든 두 발화(행 23, 57)의 정답이 공통 정답과 다르다. 두 발화 모두 한글 전용이 아니다. 이 비교는 모든 묶음을 공통 정답으로 채점하므로(규칙 4) 이 차이는 결과의 값을 바꾸지 않는다. 달라지는 것은 stt-scratch 자신의 기록이다(전체 범위의 정답 글자 수가 두 글자 적다).

   확인하지 못하는 것: voice-translator와 whisper-ko-ft는 리포트 안의 위치가 행 번호라는 것을 전제로 받아들이고, 위 둘째\~넷째가 그 증거다. 같은 문장을 두 번 이상 녹음한 문장이 105개 있지만 거의 모두 음성 길이가 달라 셋째가 구별한다. 문장 번호와 음성 길이(소수 둘째 자리)가 모두 같은 쌍은 하나다(행 64와 187). whisper-ko-ft는 이 쌍도 id의 `#n`이 순서를 말해 주고, stt-scratch는 id에 행 번호가 있다. voice-translator의 이 두 행만은 리포트가 원래 순서대로 저장됐다는 전제에 기댄다. 두 행은 같은 문장이라 정답이 같으므로, 이 전제가 틀려도 묶음의 오류율(합으로 내는 값)은 달라지지 않는다. 달라질 수 있는 것은 발화 단위로 내는 값이다: voice-translator 두 묶음의 구간, 그 묶음이 든 짝의 구간, 편집 수가 적은·많은 발화의 수.

4. 채점.
   - 공통 정답: 모든 묶음을 whisper-ko-ft 리포트(`whisper-large-v3-turbo`)에 저장된 정답으로 채점한다. voice-translator와 다른 whisper-ko-ft 리포트의 정답이 정규화하면 이것과 같다는 것은 규칙 3의 다섯째가 확인한다.
   - 정규화: 소문자로 바꾸고, 정규식 `[^\w\s']|_`에 맞는 글자를 공백으로 바꾸고, 작은따옴표를 공백으로 바꾼 뒤, 공백을 모두 지운다. 유니코드 정규화는 하지 않는다. 세 구성 요소의 한국어 채점 코드([whisper-ko-ft](../whisper-ko-ft/src/whisper_ko_ft/text_norm.py), [stt-scratch](../stt-scratch/src/stt_scratch/text.py), [voice-translator](../voice-translator/backend/eval/text_norm.py))와 같은 정규식, 같은 순서다. 세 파일의 정규식이 글자까지 같은지는 [`tests/test_scoring_rule.py`](../evaluation/asr/tests/test_scoring_rule.py)가 본다.
   - 글자 오류율(CER) = 편집 수의 합 ÷ 정답 글자 수의 합. 편집 수는 정규화한 정답과 가설 사이의 글자 단위 편집 거리다(치환·삭제·삽입을 하나씩 센다). 발화별 비율의 평균이 아니다.
   - 공백을 뺀 글자로만 잰다. voice-translator가 정규화된(공백이 없는) 글만 저장해서, 공백을 남기는 채점은 세 구성 요소에 함께 쓸 수 없다.

5. 범위. 전체 382발화와 한글 전용 257발화, 두 범위의 값을 함께 싣는다. 한글 전용은 stt-scratch 매니페스트의 `hangul_only` 표시이고, 정답에 숫자와 라틴 문자가 없는 발화다. stt-scratch는 어휘에 숫자와 라틴 문자가 없어서 전체 범위에서는 그 글자가 모두 오류로 센다. 그래서 그 구성 요소의 기록은 한글 전용 범위가 대표 수치다.

6. 구간. 발화 단위 부트스트랩 1,000번이다.
   - 다시 뽑기 번호는 시드 0으로 만든 파이썬 `random.Random`에서 `int(rng.random() * n)`으로 n개씩 1,000벌을 뽑는다. n은 전체 범위 382, 한글 전용 범위 257이다. 범위마다 번호를 한 번 만들고, 범위마다 시드 0에서 새로 시작한다(두 범위가 난수 생성기 하나를 이어 쓰지 않는다). 한글 전용 범위의 번호는 한글 전용 발화를 행 번호 순으로 늘어놓은 목록의 위치다.
   - 모든 묶음과 모든 짝이 같은 번호를 쓴다.
   - 발화를 하나씩 따로 뽑는다. 같은 문장을 다시 녹음한 발화가 있어도(그런 문장이 105개다) 문장 단위로 묶어 뽑지 않는다. 그래서 문장 단위로 뽑을 때보다 구간이 좁게 나올 수 있다.
   - 다시 뽑기 하나의 값은 뽑힌 발화들의 편집 수 합 ÷ 정답 글자 수 합이다. 1,000개 값을 작은 것부터 늘어놓아 25번째와 975번째 값을 구간의 두 끝으로 삼는다(95% 구간).
   - 결과 파일(JSON)에 저장하는 글자 오류율, 짝의 차이, 구간의 두 끝은 퍼센트가 아니라 비율이고(0.05가 5%다) 소수 여섯째 자리로 반올림한다. 표의 퍼센트는 반올림하기 전의 값에서 소수 둘째 자리로 적는다.
   - 이 구간은 이 도구의 것이다. 구성 요소 기록의 구간과는 난수를 만드는 방법이 달라 자릿수까지 같지는 않다.

7. 짝 비교 셋. 모두 '앞 − 뒤', 곧 앞 묶음의 CER에서 뒤 묶음의 CER을 뺀 값이다(퍼센트포인트).
   - 디코딩 경로: `whisper-large-v3-turbo` − `voice-turbo`. 같은 large-v3-turbo 모델을 whisper-ko-ft는 Hugging Face Transformers로 greedy, 재시도 없이, 배치로 디코딩했고, voice-translator는 faster-whisper(CTranslate2 변환본)로 beam 5에 온도를 올려 다시 푸는 재시도를 켜고 한 발화씩 디코딩했다. 두 쪽 모두 VAD(음성 구간 검출)는 쓰지 않았다. 이 차이 안에서 엔진, 탐색 방법, 재시도, 모델 사본 가운데 무엇 때문인지는 가르지 못한다(가르려면 새 디코딩이 필요하다).
   - VAD: `voice-turbo` − `voice-turbo-vad`. voice-translator의 같은 디코딩 설정에서 VAD만 켠 설정 차이다. 다만 두 묶음은 날짜가 다른 별개의 실행(2026-09-12와 2026-09-13)에서 나왔다. 온도를 올려 다시 푸는 재시도처럼 실행마다 달라질 수 있는 부분도 이 차이에 섞여 있고, 이 자료로는 그것을 VAD의 효과와 가르지 못한다.
   - 둘을 합친 것: `whisper-large-v3-turbo` − `voice-turbo-vad`. 구성 요소 문서에 기록된 5.21%와 4.57%의 차이다.
   - 짝의 구간은 같은 다시 뽑기에서 두 묶음의 값의 차이를 내어 규칙 6과 같은 방법으로 구한다. 앞 묶음의 편집 수가 뒤 묶음보다 적은 발화, 많은 발화, 같은 발화의 수도 함께 싣는다.

8. 판정 문구. 문구는 둘뿐이다.
   - 차이의 95% 구간이 0을 포함하지 않으면 '차이가 있다'라고 쓰고 방향을 적는다(차이가 0보다 크면 앞 묶음의 오류율이 더 높다, 작으면 더 낮다).
   - 0을 포함하면 '이 자료로는 차이를 말할 수 없다'라고 쓴다.
   - '차이가 있다'는 저장된 두 가설 묶음 사이에 차이가 있다는 말이다. 그 까닭은 규칙 7에 적은 단서 안에서만 읽는다.
   - 0을 포함한다는 것은 저장한 구간(소수 여섯째 자리로 반올림한 두 끝)의 아래 끝이 0 이하이고 위 끝이 0 이상이라는 뜻이다. 판정 문구는 도구가 만들지 않는다. 결과 파일(JSON)의 저장된 구간을 읽어 이 규칙대로 결과 절에 적는다. 표의 퍼센트는 소수 둘째 자리까지라 0.00으로 보이는 끝도 저장된 값은 0이 아닐 수 있다. 그때도 저장된 값을 따른다.
   - 판정은 전체 382발화의 구간으로 한다(기록된 5.21%와 4.57%가 전체 382발화 기준이다). 한글 전용 257발화의 구간은 같은 문구로 따로 적고, 두 범위의 문구가 다르면 둘 다 적는다. 어느 쪽도 골라 내세우지 않는다.
   - 짝 비교 셋 밖의 묶음끼리는 판정하지 않는다. 값과 구간만 싣는다.
   - 채점 규칙과 정답이 같다는 것은 결합 검증(규칙 3)과 기록값 재현으로 보인다. `asr-compare check`는 각 구성 요소가 이미 기록한 값을 그 구성 요소 자기 정답으로 다시 세어 같은지 본다: voice-translator는 리포트의 오류율을 이루는 편집 수 합과 정답 글자 수 합, whisper-ko-ft는 리포트에 저장된 발화별 편집 수·글자 수와 요약 오류율, stt-scratch는 전체와 한글 전용의 편집 수 합과 정답 글자 수 합.

9. 한 번만. 이 규칙을 커밋한 뒤, 이 규칙을 커밋한 시점의 도구 코드와 재료 그대로 `asr-compare run`을 한 번 돌려 나온 파일을 그대로 커밋한다. 결과가 어떻든 싣는다. 도구의 잘못이 뒤에 드러나면 결과를 지우지 않고, 날짜를 붙여 바로잡은 값과 함께 둔다. `asr-compare run`은 차례로 셋을 보고 하나라도 걸리면 결과 파일을 쓰지 않는다: 재료가 고정 목록(`inputs.sha256`)과 같은지, 규칙 3의 여덟 가지가 모두 맞는지, 규칙 8의 기록값 재현이 통과하는지.
   - 여기서 도구 코드는 `evaluation/asr`의 `src/`, `pyproject.toml`, `uv.lock`, `inputs.sha256`이다.
   - `asr-compare run`이 결과 파일을 쓰지 못하고 끝나면(위 셋 가운데 하나에 걸리거나 파일을 읽거나 쓰지 못한 경우) 값이 나오지 않았으므로 잰 것으로 치지 않는다. 그때는 까닭과 고친 것을 날짜를 붙여 이 문서에 적은 뒤에 다시 돌린다.
   - 결과 절은 결과 파일의 표 셋(전체, 한글 전용, 짝 비교)을 줄이거나 고르지 않고 그대로 싣는다.
   - 이 규칙에 없는 계산(발화를 빼고 다시 세기, 다른 구간 방법, 다른 정답)은 판정에 쓰지 않는다. 뒤에 그런 계산을 덧붙이게 되면 날짜를 붙이고 규칙 밖의 사후 분석이라고 밝힌다.

10. 이 규칙을 적기 전의 일.
    - 재료를 조사하던 과정에서 같은 채점으로 낸 표가 한 번 계산됐다(2026-11-16). 그 수치는 저장하지 않았고, 이 규칙을 정한 쪽에 전달되지 않았으며, 이 규칙을 적는 데 쓰지 않았다.
    - 도구를 만드는 동안 채점·구간·결과 파일의 시험은 지어낸 자료로만 했다. 실제 재료로 한 것은 읽기(파일의 꼴 확인과 sha256 계산), 구조 세기(같은 문장을 다시 녹음한 발화의 수, 규칙 3의 두 행이 같은 정답인지), 결합 검증, 기록값 재현뿐이다(`asr-compare check`와 그것을 부르는 시험). 공통 정답으로 묶음을 서로 견주는 값, 한글 전용 범위의 새 값, 구간, 짝의 차이는 내지 않았다.

11. 데이터 고지. 재료의 음성과 전사는 FLEURS(CC BY 4.0)에서 왔다. 귀속 표시는 [고지 모음](notices.md)이 가리키는 각 구성 요소의 문서에 있다. 이 문서와 결과 파일은 정답 전사와 가설 글을 싣지 않고 수치만 싣는다.
