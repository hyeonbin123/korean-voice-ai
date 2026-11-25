"""통화 배선 시연의 명령줄 진입점. 토큰은 환경 변수에서만 읽고 실패 출력에서 다시 가린다."""

import argparse
import json
import math
import os
import sys
from contextlib import ExitStack
from pathlib import Path

import httpx

from .clients import CallSummaryClient, StepError, SupportAgentClient, wait_until_ready
from .flow import check_expectations, run_call
from .report import build_report, write_report
from .script import load_script, script_sha256


def build_parser() -> argparse.ArgumentParser:
    """배선 시연에 필요한 대본·출력·주소·대기 옵션을 가진 한국어 도움말을 만든다."""
    parser = argparse.ArgumentParser(
        prog="call-e2e",
        description="모델 없는 두 오프라인 앱을 HTTP로 잇는 통화 배선 시연. 품질 측정이 아닙니다.",
        epilog=(
            "관리자 토큰은 명령줄 기록에 남지 않도록 환경 변수로만 받습니다. "
            "출력 리포트에 토큰은 넣지 않습니다."
        ),
    )
    parser.add_argument("--script", required=True, type=Path, help="UTF-8 JSON 통화 대본 파일 경로")
    parser.add_argument(
        "--out", required=True, type=Path, help="JSON·Markdown 리포트를 쓸 폴더; 없으면 부모까지 생성"
    )
    parser.add_argument(
        "--support-url", default="http://127.0.0.1:8062", help="상담 오프라인 앱 주소 (기본: %(default)s)"
    )
    parser.add_argument(
        "--summary-url", default="http://127.0.0.1:8072", help="후처리 오프라인 앱 주소 (기본: %(default)s)"
    )
    parser.add_argument(
        "--admin-token-env",
        default="E2E_ADMIN_TOKEN",
        help="관리자 토큰을 읽을 환경 변수 이름 (기본: %(default)s)",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=30.0,
        help="두 앱이 준비될 때까지 기다리는 최대 시간(초, 0 이상) (기본: %(default)s)",
    )
    parser.add_argument(
        "--service-link",
        action="store_true",
        help=(
            "서비스 연결 확인을 더한다(기본: 끔). 통화 한 건을 마친 뒤 상담 앱의 관리자 끝점 "
            "POST /api/admin/sessions/{id}/summary를 불러, 상담 앱이 스스로 후처리 앱을 불러 만든 "
            "기록이 이 시연이 직접 받은 기록(record·needs_confirmation·model·attempts)과 같은지, "
            "그 일이 감사 로그의 마지막 행(summary_created)으로 남았는지 본다. 다르면 리포트의 ok가 "
            "false가 되고 종료 코드는 1이다. 상담 앱을 SUPPORT_AGENT_SUMMARY_URL(같은 후처리 앱의 "
            "주소)로 띄워야 한다. 그러지 않으면 상담 앱이 501로 답해 종료 코드 2다. 두 앱이 모델 없는 "
            "오프라인 앱일 때만 뜻이 있다: 답이 정해져 있어 두 번 받은 기록이 같다. 진짜 모델이면 두 "
            "번의 답이 달라 어긋남으로 나온다. 상담 앱이 후처리 앱에 보내는 업종은 늘 shop이라, "
            "대본의 업종이 shop이 아니면 직접 보낸 요청과 업종이 달라 같은 기록을 기대할 수 없다"
        ),
    )
    return parser


def _hide_token(message: str, token: str) -> str:
    """오류 글에서 관리자 토큰을 가려서 돌려준다. 토큰이 비어 있으면 글을 그대로 돌려준다.

    서버가 오류 본문에 토큰을 되돌려 적을 수 있고, 그 본문의 앞부분이 단계 실패 글에 들어간다.
    본문이 JSON이면 토큰 안의 큰따옴표와 역슬래시 앞에 역슬래시가 붙고, 인코더에 따라 빗금 앞에도
    붙는다. 원래 글자만 찾으면 그런 꼴이 남으므로 JSON 문자열로 적은 꼴들도 함께 가린다. 긴 꼴부터
    바꿔서, 한 꼴이 다른 꼴 안에 들어 있어도 조각이 남지 않게 한다.
    주의: 서버가 다른 방식(예: base64, URL 인코딩)으로 바꿔 적은 토큰은 알아보지 못한다.
    """
    if not token:
        return message
    quoted = json.dumps(token, ensure_ascii=False)[1:-1]
    forms = {token, quoted, json.dumps(token)[1:-1], quoted.replace("/", "\\/")}
    for form in sorted(forms, key=len, reverse=True):
        message = message.replace(form, "[가림]")
    return message


def main(argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    """대본을 실행하고 리포트 경로·검사 개수를 출력한다. 성공 0, 검사 실패 1, 실행 불가 2를 반환한다.

    준비 확인은 별도의 짧은 제한 시간 클라이언트로 수행한다. 모든 클라이언트는 실행 끝까지 열어 공유된 시험
    transport가 조기에 닫히지 않게 한다. HTTP 오류의 본문에도 토큰이 있을 수 있어 stderr 출력 직전에 가린다.

    `--service-link`를 주면 서비스 연결 확인을 더한다. 리포트에 `service_link` 묶음이 생기고, 표준 출력의
    `검사 N/N 통과` 줄 다음에 `서비스 연결 확인: 일치` 또는 `서비스 연결 확인: 어긋남` 한 줄이 더해진다.
    어긋나면 검사가 모두 통과해도 리포트의 `ok`가 false라 반환값이 1이다. 그 확인이 부르는 끝점이
    실패하면(후처리 연결이 꺼진 상담 앱의 501 포함) 다른 단계의 실패처럼 2다. 인자를 주지 않으면 출력과
    요청이 이전과 같다.
    """
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        # argparse는 --help에 0, 잘못된 인자에 2를 준다. 정수가 아닌 값이 오면 실행 불가(2)로 본다.
        return exc.code if isinstance(exc.code, int) else 2
    token = os.environ.get(args.admin_token_env, "")
    try:
        if not math.isfinite(args.wait) or args.wait < 0:
            raise ValueError("--wait는 0 이상의 유한한 수(초)여야 한다")
        if not token:
            raise ValueError(f"관리자 토큰 환경 변수 {args.admin_token_env}가 비어 있거나 없다")
        script = load_script(args.script)
        digest = script_sha256(args.script)
        with ExitStack() as stack:
            support = SupportAgentClient(args.support_url, token, transport=transport)
            stack.callback(support.close)
            summary = CallSummaryClient(args.summary_url, transport=transport)
            stack.callback(summary.close)
            # 한 번의 준비 요청이 사용자가 정한 전체 대기보다 과도하게 길어지지 않도록 상한을 낮춘다.
            probe_timeout = min(5.0, max(0.001, args.wait))
            support_probe = SupportAgentClient(
                args.support_url, token, transport=transport, timeout_s=probe_timeout
            )
            stack.callback(support_probe.close)
            summary_probe = CallSummaryClient(args.summary_url, transport=transport, timeout_s=probe_timeout)
            stack.callback(summary_probe.close)
            if not wait_until_ready([support_probe, summary_probe], args.wait):
                raise ValueError("준비 확인 실패: 제한 시간 안에 두 서비스가 준비되지 않았다")
            result = run_call(script, support, summary, service_link=args.service_link)
        checks = check_expectations(script, result)
        report = build_report(script, digest, result, checks)
        paths = write_report(report, args.out)
    except (ValueError, OSError, StepError, httpx.InvalidURL) as exc:
        print(_hide_token(str(exc), token), file=sys.stderr)
        return 2
    for check in checks:
        if not check["ok"]:
            print(check["name"])
    for path in paths:
        print(f"리포트: {path}")
    print(f"검사 {sum(c['ok'] for c in checks)}/{len(checks)} 통과")
    if "service_link" in report:
        print("서비스 연결 확인: " + ("일치" if report["service_link"]["status"] == "matched" else "어긋남"))
    return 0 if report["ok"] else 1
