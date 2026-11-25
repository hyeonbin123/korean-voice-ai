# 통화 한 건 리포트: 주문 하나를 취소하는 통화

> 모델 없는 오프라인 앱 두 개(support-agent의 규칙 대역, call-summary의 고정 답)를 HTTP로 이은 배선 시연이다. 상담 답과 후처리 기록은 모델이 만든 것이 아니므로 품질을 보여 주지 않는다.

- 대본: shop-cancel / 업종: shop / SHA-256: 478bc3bb7acc079b8a755f1e981eeddf295a46fc8d84aa5c28fac953c65432e3
- 검사: 5/5 통과
- 서비스 연결 확인: 일치 — 상담 서비스가 직접 후처리 서비스를 불러 만든 기록이 아래 기록과 같고, 감사 로그의 마지막 종류가 summary_created

## 상담 (support-agent)

| 차례 | 고객 | 부른 도구 | 답 |
| --- | --- | --- | --- |
| 1 | 안녕하세요, 주문을 취소하려고요. | 없음 | 본인 확인을 위해 성함과 가입하신 전화번호를 알려 주세요. |
| 2 | 정예준이고 010-0000-9005입니다. | find_customer (성공) | 처리했습니다. {"customer_id": "C-9005", "name": "정예준", "grade": "normal", "grade_label": "일반"} |
| 3 | O-90005 주문 취소해 주세요. | cancel_order (성공) | 처리했습니다. {"order_id": "O-90005", "status": "cancelled", "status_label": "취소됨", "refund_won": 89100, "refund_method": "simple_pay", "refund_method_label": "간편결제"} |

- 세션 상태: open
- 보내지 않은 발화: 0개
- 승인 대기: 0건

## 상담 후처리 기록 (call-summary)

- 응답 모델: offline:canned / 시도: 1
- 유형: 배송 문의
- 처리 결과: 해결
- 상담 중 처리: 없음
- 후속 조치: 없음
- 요약: 오프라인 모드의 고정 응답입니다.

| 핵심 값 유형 | 값 |
| --- | --- |
| 주문번호 | D7463343 |

## 확인이 필요한 번호

| 유형 | 값 | 이유 |
| --- | --- | --- |
| 주문번호 | D7463343 | not_in_transcript |

- 상담에서 도구가 다룬 주문 번호: O-90005
- 이유의 뜻: `format` = 업종 번호 형식과 다름, `not_in_transcript` = 통화 글에서 못 찾음

## 검사

| 검사 | 결과 | 설명 |
| --- | --- | --- |
| turns_completed | 통과 | 대본 발화 3개 가운데 3개를 보냄; end 없이 끝난 턴 0개, error 이벤트가 있는 턴 0개 |
| tool_calls | 통과 | 기대: find_customer(성공) → cancel_order(성공); 실제: find_customer(성공) → cancel_order(성공) |
| session_status | 통과 | 기대: open; 실제: open |
| transcript_matches_script | 통과 | 전사의 고객 말 3개와 대본 발화 3개가 차례대로 같음 |
| summary_model | 통과 | 기대: offline:canned; 실제: offline:canned |
