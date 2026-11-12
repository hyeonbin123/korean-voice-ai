"""통화 배선 시연 결과를 같은 입력이면 같은 바이트인 JSON·Markdown 리포트로 저장한다."""

import json
from copy import deepcopy
from pathlib import Path

from .script import CallScript

WIRING_NOTICE = (
    "모델 없는 오프라인 앱 두 개(support-agent의 규칙 대역, call-summary의 고정 답)를 "
    "HTTP로 이은 배선 시연이다. "
    "상담 답과 후처리 기록은 모델이 만든 것이 아니므로 품질을 보여 주지 않는다."
)


def build_report(script: CallScript, script_sha256: str, result: dict, checks: list[dict]) -> dict:
    """대본 메타데이터·정제된 실행 결과·검사를 공개 스키마의 고정 키 순서로 조립한다.

    result는 flow.run_call의 결과다. 그 함수가 HTTP 응답에서 세션·요청·감사 식별자와 시간을 제외한다.
    결과와 검사는 깊게 복사하므로 리포트를 표시용으로 바꿔도 원래 실행 결과에 영향을 주지 않는다.
    """
    support = result["support_agent"]
    summary = result["call_summary"]
    return {
        "report": "call-e2e/1",
        "wiring_only": True,
        "notice": WIRING_NOTICE,
        "script": {
            "call_id": script.call_id,
            "title": script.title,
            "domain": script.domain,
            "sha256": script_sha256,
        },
        "support_agent": deepcopy(
            {
                k: support[k]
                for k in (
                    "turns",
                    "unsent_turns",
                    "session_status",
                    "transcript",
                    "tool_calls",
                    "pending_approvals",
                )
            }
        ),
        "call_summary": deepcopy(
            {k: summary[k] for k in ("request", "model", "attempts", "record", "needs_confirmation")}
        ),
        "checks": [{"name": c["name"], "ok": c["ok"], "detail": c["detail"]} for c in checks],
        "ok": all(c["ok"] for c in checks),
    }


def _cell(value: object) -> str:
    """표 구분자인 파이프를 이스케이프하고 모든 줄바꿈을 셀 안의 읽기 쉬운 구분자로 바꾼다."""
    return str(value).replace("|", "\\|").replace("\r\n", "\n").replace("\r", "\n").replace("\n", " / ")


def _row(*values: object) -> str:
    """표 한 행을 만든다. 모든 값을 같은 규칙으로 이스케이프해 대화 글이 표를 깨지 않게 한다."""
    return "| " + " | ".join(_cell(v) for v in values) + " |"


def render_markdown(report: dict) -> str:
    """리포트의 상담 턴·후처리 기록·번호 확인·검사를 네 절의 Markdown으로 렌더링한다.

    번호 확인은 후처리 서비스의 표시를 그대로 보여 주며 상담 도구의 주문 번호도 함께 적는다. 두 번호가 달라도
    여기서 보정하지 않는다. 모든 표 칸은 파이프와 줄바꿈을 이스케이프하며 끝에 LF 하나를 붙인다.
    표가 아닌 줄은 목록(`- `)으로 쓴다. Markdown은 빈 줄 없이 이어진 보통 줄을 한 문단으로 붙여 보여
    주기 때문이다.
    """
    script, support, summary = report["script"], report["support_agent"], report["call_summary"]
    checks = report["checks"]
    record = summary["record"]
    follow_up = record["follow_up"]
    lines = [
        f"# 통화 한 건 리포트: {_cell(script['title'])}",
        "",
        f"> {report['notice']}",
        "",
        f"- 대본: {_cell(script['call_id'])} / 업종: {_cell(script['domain'])} / SHA-256: {script['sha256']}",
        f"- 검사: {sum(c['ok'] for c in checks)}/{len(checks)} 통과",
        "",
        "## 상담 (support-agent)",
        "",
        _row("차례", "고객", "부른 도구", "답"),
        _row("---", "---", "---", "---"),
    ]
    for number, turn in enumerate(support["turns"], start=1):
        tools = [
            f"{t['name']} ({'성공' if t['ok'] else '실패'}"
            + (f", {t['error_code']}" if t["error_code"] else "")
            + ")"
            for t in turn["tools"]
        ]
        lines.append(_row(number, turn["customer"], " / ".join(tools) or "없음", " / ".join(turn["replies"])))
    lines.extend(
        [
            "",
            f"- 세션 상태: {_cell(support['session_status'])}",
            f"- 보내지 않은 발화: {support['unsent_turns']}개",
            f"- 승인 대기: {len(support['pending_approvals'])}건",
            "",
            "## 상담 후처리 기록 (call-summary)",
            "",
            f"- 응답 모델: {_cell(summary['model'])} / 시도: {summary['attempts']}",
            f"- 유형: {_cell(record['category'])}",
            f"- 처리 결과: {_cell(record['resolution'])}",
            f"- 상담 중 처리: {_cell(' / '.join(record['actions_taken'])) or '없음'}",
            f"- 후속 조치: {'필요' if follow_up['required'] else '없음'}"
            + (f" ({_cell(' / '.join(follow_up['codes']))})" if follow_up["codes"] else ""),
            f"- 요약: {_cell(record['summary'])}",
            "",
            _row("핵심 값 유형", "값"),
            _row("---", "---"),
        ]
    )
    lines.extend(_row(e["type"], e["value"]) for e in record["entities"])
    lines.extend(["", "## 확인이 필요한 번호", "", _row("유형", "값", "이유"), _row("---", "---", "---")])
    flags = summary["needs_confirmation"]
    lines.extend(_row(f["type"], f["value"], " / ".join(f["reasons"])) for f in flags)
    if not flags:
        lines.append(_row("없음", "—", "—"))
    orders = [
        str(t["args"]["order_id"])
        for t in support["tool_calls"]
        if isinstance(t["args"], dict) and "order_id" in t["args"]
    ]
    lines.extend(
        [
            "",
            "- 상담에서 도구가 다룬 주문 번호: " + (_cell(" / ".join(dict.fromkeys(orders))) or "없음"),
            "- 이유의 뜻: `format` = 업종 번호 형식과 다름, `not_in_transcript` = 통화 글에서 못 찾음",
            "",
            "## 검사",
            "",
            _row("검사", "결과", "설명"),
            _row("---", "---", "---"),
        ]
    )
    lines.extend(_row(c["name"], "통과" if c["ok"] else "실패", c["detail"]) for c in checks)
    return "\n".join(lines) + "\n"


def write_report(report: dict, out_dir: Path) -> tuple[Path, Path]:
    """출력 폴더를 만들고 call-report.json·call-report.md를 UTF-8(BOM 없음)·LF로 쓴다.

    입력 폴더가 아직 없어도 부모까지 만든다. JSON은 키 순서를 유지하고 들여쓰기 두 칸과 마지막 줄바꿈을
    사용한다. 파일 쓰기 실패는 OSError로 호출자에게 알려 성공한 것처럼 보고하지 않는다.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "call-report.json"
    md_path = out_dir / "call-report.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return json_path, md_path
