"""두 오프라인 서비스의 HTTP 계약을 재현하는 시험 대역.

모델과 네트워크 없이 요청 차례·인증·SSE·감사 로그를 함께 확인한다. 상태와 도구 결과를 턴별로 바꿀 수 있어
정상 통화뿐 아니라 도중 종료, 오류, 승인 대기도 실제 클라이언트를 거쳐 시험한다.
"""

import json
from copy import deepcopy
from pathlib import Path

import httpx

from call_e2e.script import load_script

TOKEN = "test-admin-token"
SUPPORT_URL = "http://support.test"
SUMMARY_URL = "http://summary.test"
SCRIPT_PATH = Path(__file__).parents[1] / "calls" / "shop-cancel.json"
# 실제 앱이 새 채팅 세션의 첫 줄로 넣는 상담원 인사말과 같은 글.
GREETING = "안녕하세요, 고객센터입니다. 무엇을 도와드릴까요?"


def sample_script():
    """저장소의 공개 예제 대본을 읽는다. 시험 중 원본 파일을 변경하지 않는다."""
    return load_script(SCRIPT_PATH)


class FakeServices:
    """MockTransport로 두 앱에 답하고 받은 요청을 순서대로 보관한다.

    end_statuses는 턴 끝 상태, tools는 턴별 도구 결과 목록이다. 감사 로그의 도구 인자는 SSE에 없으므로 따로
    audit에 기록한다. health_status와 failures로 준비 실패·HTTP 단계 실패를 재현할 수 있다.

    상담 서비스의 관리자 끝점 `POST /api/admin/sessions/{id}/summary`(서비스 연결 확인이 부른다)도 흉내 낸다.
    실제 서비스는 후처리 서비스를 직접 불러 기록을 만들고 감사 로그에 `summary_created` 행을 남긴다. 이 대역은
    후처리 대역과 같은 고정 기록을 돌려주고 감사 로그에 행을 더한다. 두 값으로 어긋남을 재현한다:
    linked_overrides는 201 답의 `summary` 칸을 덮어쓰고(다른 기록·모델·시도 횟수·번호 확인 표시),
    linked_audit_kind는 그 호출이 감사 로그에 남기는 행의 종류다(None이면 행을 남기지 않는다).
    """

    def __init__(self, *, end_statuses=None, tools=None, health_status=200, session_id="s-1"):
        self.requests: list[httpx.Request] = []
        self.end_statuses = end_statuses or ["open", "open", "open"]
        self.tools = (
            tools
            if tools is not None
            else [
                [],
                [{"name": "find_customer", "args": {"name": "정예준"}, "ok": True, "error_code": None}],
                [{"name": "cancel_order", "args": {"order_id": "O-90005"}, "ok": True, "error_code": None}],
            ]
        )
        self.health_status = health_status
        self.session_id = session_id
        self.request_id = "request-variable"
        self.latency_s = 0.01
        self.failures: dict[tuple[str, str], tuple[int, str]] = {}
        self.extra_events: dict[int, list[tuple[str, dict]]] = {}
        self.omit_end: set[int] = set()
        # 실제 앱의 새 채팅 세션은 상담원의 고정 인사말 한 줄로 시작한다(support-agent
        # `src/support_agent/config.py`의 FIRST_AGENT_MESSAGE). 전사와 후처리 요청에도 그 줄이 들어간다.
        self.messages: list[dict] = [{"role": "agent", "text": GREETING}]
        self.audit = [{"id": 1, "at": "2026-01-01", "kind": "session_started", "payload": {}}]
        self.pending_approvals: list[dict] = []
        self.model = "offline:canned"
        self.linked_overrides: dict = {}
        self.linked_audit_kind = "summary_created"
        self.turn = 0
        self.transport = httpx.MockTransport(self._handle)

    def canned_summary(self) -> dict:
        """후처리 서비스(대역)가 늘 주는 고정 기록의 네 칸. 호출마다 새 객체라 시험이 고쳐도 번지지 않는다."""
        return {
            "model": self.model,
            "attempts": 1,
            "record": {
                "category": "주문 취소",
                "resolution": "해결",
                "entities": [{"type": "주문번호", "value": "D1234567"}],
                "actions_taken": [],
                "follow_up": {"required": False, "codes": []},
                "summary": "오프라인 고정 답입니다.",
            },
            "needs_confirmation": [
                {"type": "주문번호", "value": "D1234567", "reasons": ["not_in_transcript"]}
            ],
        }

    def _handle(self, request: httpx.Request) -> httpx.Response:
        """공개 끝점의 상태·본문을 돌려준다. 정의하지 않은 요청은 즉시 시험 실패로 드러낸다."""
        self.requests.append(request)
        route = (request.method, request.url.path)
        expected_host = "summary.test" if request.url.path in {"/health", "/summarize"} else "support.test"
        assert request.url.host == expected_host
        if route in self.failures:
            status, body = self.failures[route]
            return httpx.Response(status, text=body)
        if route in {("GET", "/healthz"), ("GET", "/health")}:
            return httpx.Response(self.health_status, json={"status": "ok"})
        if route == ("POST", "/api/sessions"):
            return httpx.Response(201, json={"session_id": self.session_id, "status": "open"})
        if route == ("POST", f"/api/sessions/{self.session_id}/messages"):
            index = self.turn
            self.turn += 1
            text = json.loads(request.content)["text"]
            reply = f"답변 {self.turn}"
            self.messages.extend([{"role": "customer", "text": text}, {"role": "agent", "text": reply}])
            events = [("status", {"stage": "thinking"})]
            for tool in self.tools[index]:
                events.extend(
                    [
                        ("tool", {"name": tool["name"], "label": "도구 실행"}),
                        ("tool_result", {k: tool[k] for k in ("name", "ok", "error_code")}),
                    ]
                )
                self.audit.append(
                    {
                        "id": len(self.audit) + 1,
                        "at": "2026-01-01",
                        "kind": "tool_call",
                        "payload": {**deepcopy(tool), "arguments": {"ignored": True}},
                    }
                )
            events.extend(self.extra_events.get(index, []))
            events.append(("reply", {"text": reply}))
            if index not in self.omit_end:
                events.append(("end", {"status": self.end_statuses[index]}))
            body = "".join(
                f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n" for name, data in events
            )
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        if route == ("GET", f"/api/admin/sessions/{self.session_id}"):
            if request.headers.get("X-Admin-Token") != TOKEN:
                return httpx.Response(401, json={"detail": "invalid admin token"})
            transcript = {
                "session_id": self.session_id,
                "status": self.end_statuses[self.turn - 1],
                "messages": self.messages,
                "pending_approvals": self.pending_approvals,
            }
            return httpx.Response(200, json={"transcript": transcript, "audit": self.audit})
        if route == ("POST", "/summarize"):
            return httpx.Response(
                200,
                json={"request_id": self.request_id, "latency_s": self.latency_s, **self.canned_summary()},
            )
        if route == ("POST", f"/api/admin/sessions/{self.session_id}/summary"):
            if request.headers.get("X-Admin-Token") != TOKEN:
                return httpx.Response(401, json={"detail": "wrong admin token"})
            made = {**self.canned_summary(), **self.linked_overrides}
            # 실제 서비스가 감사 로그에 남기는 칸(support-agent `src/support_agent/service/core.py`의
            # create_summary)을 그대로 따른다. linked_audit_kind가 None이면 201을 주고도 행을 남기지
            # 않는 서비스를 흉내 낸다.
            if self.linked_audit_kind is not None:
                self.audit.append(
                    {
                        "id": len(self.audit) + 1,
                        "at": "2026-01-01",
                        "kind": self.linked_audit_kind,
                        "payload": {
                            "by": json.loads(request.content)["by"],
                            "session_status": self.end_statuses[self.turn - 1],
                            "turns": len(self.messages),
                            **deepcopy(made),
                            "request_id": "linked-request-variable",
                        },
                    }
                )
            return httpx.Response(201, json={"session_id": self.session_id, "summary": made})
        raise AssertionError(f"정의하지 않은 요청: {route}")
