'use strict';

// [파일 역할] 관리 화면(admin.html)의 동작. 관리자 토큰 확인, 승인 대기열의 표시·승인·반려, 상담 세션 목록과
// 한 세션의 대화·상담 후처리 기록·감사 로그 표시, 후처리 기록 만들기를 맡는다.
// [연결] app.py의 관리자 API(/api/admin/approvals, /api/admin/approvals/{id}/decision, /api/admin/sessions,
// /api/admin/sessions/{id}, 후처리 기록을 만드는 POST /api/admin/sessions/{id}/summary)를 X-Admin-Token
// 헤더로 부른다. 토큰이 필요 없는 GET /healthz는 헤더 없이 따로 불러, 로그인한 뒤 후처리 서비스 연결이
// 켜져 있는지(응답의 summary 칸)를 한 번 읽는다.
// [설계 이유] 프레임워크 없이 DOM API만 쓴다. 서버에서 온 글(고객 메시지, 감사 로그, 후처리 서비스가 만든
// 기록)은 모두 textContent로 넣고 innerHTML은 쓰지 않아, 고객이 보낸 스크립트 문장이 화면에서 실행되지
// 않는다(docs/service.md 스캔 9의 판단 근거. tests/test_service.py의 test_admin_script_never_writes_html이
// 이 약속을 지킨다).
// 후처리 기록은 후처리 서비스가 만든 값을 서버가 최상위 다섯 칸의 형과 겹침 깊이만 확인해 저장한 것이라
// (service/summary.py) 안쪽 칸은 없거나 다른 형일 수 있다. 그래도 그리는 코드는 예외를 내면 안 된다
// (openSession 전체가 멈춰 대화와 감사 표까지 안 보인다). 그래서 칸을 읽을 때마다 형을 확인한다(isObject,
// textOf).
// 전체를 즉시 실행 함수로 감싸 전역 변수를 만들지 않는다.

(() => {
  // 승인 목록을 다시 읽는 주기(5초). 고객이 새로 요청한 승인이 따로 누르지 않아도 나타난다.
  const REFRESH_MS = 5000;
  // sessionStorage 키: 관리자 토큰과 담당자 이름. 탭을 닫으면 지워지는 저장소라 토큰이 브라우저에 오래 남지
  // 않는다.
  const TOKEN_KEY = 'support-agent.admin-token';
  const BY_KEY = 'support-agent.admin-by';
  // 서버의 승인·세션 상태 코드(store.py의 ApprovalStatus, SessionStatus) → 화면 표기.
  const APPROVAL_STATUS = {
    pending: '승인 대기',
    executing: '처리 중',
    approved: '처리됨',
    rejected: '반려됨',
    failed: '승인했지만 처리 실패',
  };
  const SESSION_STATUS = { open: '진행 중', handoff: '상담원 연결', closed: '종료' };
  const ROLE_NAMES = { customer: '고객', agent: '상담원' };
  // 후처리 기록의 '확인이 필요한 번호'가 걸린 사유(후처리 서비스의 값) → 화면 표기. 모르는 값은 받은 글 그대로
  // 보인다. 사유는 서버 밖에서 온 글이라 객체가 아니라 Map으로 찾는다(객체로 찾으면 'constructor' 같은 글이
  // 객체의 기본 속성에 걸려 엉뚱한 값이 나온다).
  const REASON_NAMES = new Map([
    ['format', '형식이 맞지 않음'],
    ['not_in_transcript', '대화에 없음'],
  ]);
  // 후처리 기록 묶음에 그리는 '확인이 필요한 번호'의 최대 개수. 정상 기록의 번호는 몇 개뿐이다. 서버는 그 목록의
  // 길이를 제한하지 않으므로(답 전체가 1 MiB 안이면 받는다) 화면이 여기서 끊는다: 원소가 수십만 개인 목록을
  // 다 그리면 브라우저가 멈춘다. 넘는 만큼은 몇 건이 더 있는지만 적는다(전부는 감사 표의 내용 칸에 있다).
  const MAX_FLAGS_SHOWN = 20;
  // 후처리 기록 만들기의 결과 문구: 성공 문구와, 실패했을 때의 안내(키는 HTTP 상태 코드). 서버가 주는 영어
  // detail은 화면에 옮기지 않고 상태 코드로 문구를 고른다. 401·503은 api()가 이미 로그인 화면으로 처리하므로
  // 여기 없다. 502와 504가 같은 문구인 까닭: 둘 다 후처리 서비스에 닿지 못했거나 제때 답을 받지 못한 경우다.
  // SUMMARY_FAILED는 표에 없는 상태 코드(404 등)와 네트워크 오류에 쓴다.
  const SUMMARY_CREATED = '후처리 기록을 만들었습니다.';
  const SUMMARY_FAILURES = {
    409: '요약할 대화가 없습니다.',
    422: '후처리 서비스가 이 대화를 받지 않았습니다(너무 길거나 받을 수 없는 글자).',
    429: '후처리 서비스가 바쁩니다. 잠시 뒤 다시 눌러 주세요.',
    501: '후처리 연결이 꺼져 있습니다.',
    502: '후처리 서비스에 닿지 못했습니다.',
    504: '후처리 서비스에 닿지 못했습니다.',
  };
  const SUMMARY_FAILED = '후처리 기록을 만들지 못했습니다.';

  const $ = (id) => document.getElementById(id);
  const els = {
    login: $('login'),
    loginMessage: $('login-message'),
    tokenInput: $('token'),
    logout: $('logout'),
    app: $('app'),
    pendingCount: $('pending-count'),
    by: $('by'),
    showDecided: $('show-decided'),
    updated: $('approvals-updated'),
    result: $('approvals-result'),
    approvalsError: $('approvals-error'),
    approvalsEmpty: $('approvals-empty'),
    approvals: $('approvals'),
    sessionsError: $('sessions-error'),
    sessionsEmpty: $('sessions-empty'),
    sessions: $('sessions'),
    detail: $('detail'),
    summaryCreate: $('summary-create'),
    summaryResult: $('summary-result'),
    summaryRecord: $('summary-record'),
  };
  const tabs = { approvals: $('tab-approvals'), sessions: $('tab-sessions') };
  const panels = { approvals: $('panel-approvals'), sessions: $('panel-sessions') };

  // 화면 상태: 토큰, 그려 둔 승인 목록, 같은 응답이면 다시 그리지 않으려고 기억하는 직렬화 결과(snapshot),
  // 겹친 요청을 막는 표시, 결정을 보내는 중인 승인, 고른 세션, 승인별로 입력 중인 메모, 후처리 기록 만들기의
  // 상태(연결이 켜졌는가, 요청이 진행 중인가, 상세에 그려진 세션).
  let token = read(TOKEN_KEY);
  let approvals = [];
  let snapshot = ''; // 승인 목록을 그린 근거. 응답이 같으면 DOM(과 입력 중인 글)을 그대로 둔다
  let loadingApprovals = false;
  let deciding = null; // 결정을 보내는 중인 승인의 id
  let selectedSession = null; // 고른 세션. 상세의 응답을 기다리는 중이면 아직 그려진 세션이 아닐 수 있다
  let shownSession = null; // 상세에 실제로 그려진 세션. 후처리 기록 만들기 단추가 만드는 대상이다
  let summaryEnabled = false; // 로그인한 뒤 /healthz로 읽은, 후처리 서비스 연결이 켜져 있는지
  let summaryBusy = false; // 후처리 기록 만들기 요청이 진행 중인지. 다른 세션을 열어도 끝날 때까지 이어진다
  const notes = new Map(); // 승인 id -> 입력 중인 메모

  // ------------------------------------------------------------ 도우미 (helpers)

  // sessionStorage 읽기·쓰기. 브라우저 설정으로 저장소가 막혀 있으면 예외가 나므로 잡고, 그때는 이 페이지를
  // 보는 동안만 값을 쓴다.
  function read(key) {
    try {
      return sessionStorage.getItem(key) || '';
    } catch {
      return '';
    }
  }

  function write(key, value) {
    try {
      if (value) sessionStorage.setItem(key, value);
      else sessionStorage.removeItem(key);
    } catch {
      // 저장소가 막혀 있을 수 있다. 그때 값은 이 페이지를 보는 동안만 산다
    }
  }

  // 요소를 만들고 글은 textContent로만 넣는 도우미. 화면의 모든 요소가 이것을 거친다.
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // 알림 줄에 글을 쓰고, 빈 글이면 숨긴다. tone(ok/warn)은 CSS에서 색을 고르는 데 쓴다.
  function say(node, text, tone) {
    node.textContent = text;
    node.hidden = !text;
    if (tone) node.dataset.tone = tone;
  }

  // 금액은 "108,200원"처럼, 시각은 한국 시간(Asia/Seoul) 24시간제로 보인다.
  const won = (amount) => (amount == null ? '-' : `${Number(amount).toLocaleString('ko-KR')}원`);
  const timeFormat = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  // 시각은 KST로 보인다. 오프셋이 없는 값은 UTC로 본다(DB는 UTC로 저장한다).
  function time(iso) {
    if (!iso) return '-';
    const date = new Date(/(Z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : `${iso}Z`);
    return Number.isNaN(date.getTime()) ? iso : timeFormat.format(date);
  }

  // 서버가 저장해 둔 값을 믿지 않고 읽는 도우미(후처리 기록). isObject: null과 목록이 아닌 객체인가.
  // textOf: 비어 있지 않은 글이면 그대로, 글이 아니거나(수·목록·객체·null·없음) 비었으면 '-'.
  const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
  const textOf = (value) => (typeof value === 'string' && value.trim() !== '' ? value : '-');

  // HTTP 상태 코드를 담은 오류. handled는 401(토큰 틀림)·503(관리자 API 꺼짐)처럼 api()가 이미 로그인
  // 화면으로 처리한 오류인지 가른다.
  class ApiError extends Error {
    constructor(status) {
      super(`HTTP ${status}`);
      this.status = status;
    }
  }
  const handled = (error) => error instanceof ApiError && (error.status === 401 || error.status === 503);

  // 관리자 API 호출. 모든 요청에 X-Admin-Token 헤더를 붙이고, body가 있으면 JSON POST로 보낸다.
  // 401이면 저장한 토큰을 지우고 로그인 화면으로, 503이면 관리자 기능이 꺼졌다고 알린다. 실패는 ApiError로
  // 던져 호출한 쪽이 문구를 고른다.
  async function api(path, body) {
    const options = { headers: { 'X-Admin-Token': token } };
    if (body !== undefined) {
      options.method = 'POST';
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    if (response.status === 401) {
      setToken('');
      showLogin('토큰이 올바르지 않습니다. 다시 입력해 주세요.');
    } else if (response.status === 503) showLogin('관리자 기능이 꺼져 있습니다.');
    if (!response.ok) throw new ApiError(response.status);
    return response.json();
  }

  // ------------------------------------------------------------ 로그인 (login)

  function setToken(value) {
    token = value;
    write(TOKEN_KEY, value);
  }

  function showLogin(message) {
    els.app.hidden = true;
    els.logout.hidden = true;
    els.login.hidden = false;
    say(els.loginMessage, message || '');
    els.tokenInput.focus();
  }

  // 토큰으로 대기열 API를 한 번 불러 보고, 통과하면 본 화면을 연다. 토큰을 따로 검사하는 끝점이 없으므로 실제
  // API로 확인한다. 본 화면을 연 뒤 후처리 연결이 켜져 있는지도 읽는데, 그 응답을 기다리지 않는다(본 화면
  // 열기가 늦어지지 않게).
  async function enter() {
    try {
      await api('/api/admin/approvals?status=pending');
    } catch (error) {
      if (!handled(error)) showLogin('서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.');
      return;
    }
    els.login.hidden = true;
    els.app.hidden = false;
    els.logout.hidden = false;
    snapshot = '';
    selectTab('approvals');
    loadApprovals();
    loadSummaryLink();
  }

  // ------------------------------------------------------------ 승인 대기열 (approval queue)

  // 승인 한 건의 카드를 만든다. 공통으로 번호·상태·도구 이름과 주문·고객·환불 예정액·요청 시각을 보이고,
  // 결정된 건은 결정 시각·담당자·메모를, 실패한 건은 도구의 응답을 보인다.
  // 대기 중인 건에만 메모 입력과 승인·반려 버튼이 있다. 반려 메모는 서버가 고객에게 "사유: …"로
  // 안내한다(core.py).
  function approvalCard(a) {
    const card = el('article', `card ${a.status}`);
    const head = el('header', 'card-head');
    head.append(
      el('strong', '', a.code),
      el('span', `badge ${a.status}`, APPROVAL_STATUS[a.status] || a.status),
      el('span', 'muted', a.label || a.tool),
    );
    const facts = el('dl', 'facts');
    const rows = [
      ['주문', (a.args && a.args.order_id) || '-'],
      ['고객', a.customer_id || '-'],
      ['환불 예정', won(a.refund_won)],
      ['요청 시각', time(a.created_at)],
    ];
    if (a.status !== 'pending') {
      rows.push(['결정', `${time(a.decided_at)} · ${a.decided_by || '-'}`]);
      if (a.note) rows.push(['메모', a.note]);
    }
    for (const [name, value] of rows) facts.append(el('dt', '', name), el('dd', '', String(value)));
    card.append(head, facts);
    if (a.status === 'failed' && a.result) card.append(el('pre', 'payload', a.result));

    const actions = el('div', 'actions');
    if (a.status === 'pending') {
      const field = el('div', 'field grow');
      const label = el('label', '', '메모 (선택, 반려 사유는 고객에게 안내됩니다)');
      label.htmlFor = `note-${a.id}`;
      const note = el('input');
      note.type = 'text';
      note.id = label.htmlFor;
      note.maxLength = 500;
      note.autocomplete = 'off';
      note.dataset.noteFor = String(a.id);
      note.value = notes.get(a.id) || '';
      note.addEventListener('input', () => notes.set(a.id, note.value));
      field.append(label, note);
      const approve = el('button', 'btn btn-primary', '승인');
      const reject = el('button', 'btn btn-danger', '반려');
      for (const [button, value] of [[approve, true], [reject, false]]) {
        button.type = 'button';
        // 결정 하나가 서버로 가는 동안에는 모든 카드의 버튼을 막아 두 번 누르기를 막는다(서버도 조건부
        // UPDATE로 한쪽만 실행한다).
        button.disabled = deciding !== null;
        button.addEventListener('click', () => decide(a, value));
      }
      actions.append(field, approve, reject);
    }
    // "상담 보기": 상담 기록 탭으로 옮겨 이 승인이 나온 세션의 대화와 감사 로그를 연다.
    const open = el('button', 'btn', '상담 보기');
    open.type = 'button';
    open.addEventListener('click', () => {
      selectTab('sessions');
      openSession(a.session_id);
    });
    actions.append(open);
    card.append(actions);
    return card;
  }

  // 카드 목록을 다시 그린다. 메모 입력칸에 커서가 있었으면 다시 그린 뒤 같은 승인의 입력칸으로 커서를
  // 돌려준다(입력 중인 글은 notes에 따로 둔다).
  function renderApprovals() {
    const active = document.activeElement;
    const focused = active && active.dataset ? active.dataset.noteFor : undefined;
    els.approvals.replaceChildren(...approvals.map(approvalCard));
    els.approvalsEmpty.hidden = approvals.length > 0;
    if (focused) {
      const again = els.approvals.querySelector(`[data-note-for="${Number(focused)}"]`);
      if (again) again.focus();
    }
  }

  // 승인 목록을 읽는다. 기본은 대기 중인 것만, "처리된 항목도 보기"면 전부다. 대기 중인 건을 위로, 그
  // 안에서는 최근 것부터 정렬하고 탭에 대기 건수를 보인다.
  // 응답이 지난번과 같으면(snapshot) DOM을 그대로 둬, 5초마다 갱신해도 입력 중인 메모와 커서가 흔들리지
  // 않는다.
  async function loadApprovals() {
    if (!token || loadingApprovals) return;
    loadingApprovals = true;
    try {
      const all = els.showDecided.checked;
      const list = await api(`/api/admin/approvals${all ? '' : '?status=pending'}`);
      list.sort((a, b) => (b.status === 'pending') - (a.status === 'pending') || b.id - a.id);
      const count = list.filter((a) => a.status === 'pending').length;
      els.pendingCount.textContent = String(count);
      els.pendingCount.hidden = count === 0;
      const next = JSON.stringify([list, deciding]);
      if (next !== snapshot) {
        snapshot = next;
        approvals = list;
        renderApprovals();
      }
      els.updated.textContent = `${time(new Date().toISOString())} 갱신`;
      say(els.approvalsError, '');
    } catch (error) {
      if (!handled(error)) say(els.approvalsError, '승인 목록을 불러오지 못했습니다. 자동으로 다시 시도합니다.');
    } finally {
      loadingApprovals = false;
    }
  }

  // 승인·반려를 보낸다. 담당자 이름이 비어 있으면 'admin'으로 보낸다. 409는 이미 처리됐거나 그 세션의 턴이
  // 도는 중이라는 뜻이라 잠시 뒤 다시 하라고 안내한다.
  // 성공하든 실패하든 끝나면 목록을 새로 읽어 서버의 실제 상태를 보인다.
  async function decide(a, approve) {
    if (deciding !== null) return;
    deciding = a.id;
    renderApprovals(); // 버튼을 막는다
    const by = els.by.value.trim() || 'admin';
    const note = (notes.get(a.id) || '').trim();
    try {
      const updated = await api(`/api/admin/approvals/${a.id}/decision`, { approve, by, note });
      notes.delete(a.id);
      const label = APPROVAL_STATUS[updated.status] || updated.status;
      say(els.result, `${updated.code}: ${label}`, updated.status === 'approved' ? 'ok' : 'warn');
    } catch (error) {
      if (handled(error)) return;
      const conflict = error instanceof ApiError && error.status === 409;
      say(
        els.result,
        conflict
          ? `${a.code}: 이미 처리되었거나 상담이 진행 중입니다. 잠시 후 다시 시도해 주세요.`
          : `${a.code}: 결정을 저장하지 못했습니다.`,
        'warn',
      );
    } finally {
      deciding = null;
      snapshot = '';
      if (token) {
        renderApprovals();
        await loadApprovals();
      }
    }
  }

  // ------------------------------------------------------------ 상담 기록 (sessions)

  // --- 상담 기록 탭 ---
  // 대화 말풍선 하나. 화면 낭독기를 위해 "고객: ", "상담원: "을 보이지 않는 글로 앞에 둔다.
  function bubble(message) {
    const node = el('div', `bubble ${message.role === 'customer' ? 'customer' : 'agent'}`);
    node.append(el('span', 'sr-only', `${ROLE_NAMES[message.role] || message.role}: `), el('span', '', message.text));
    return node;
  }

  // 세션 목록의 한 줄: 세션 번호 앞 10자, 상태, 턴 수, 본인 확인된 고객, 마지막 갱신 시각. 고른 세션은
  // aria-current로 표시한다.
  function sessionItem(s) {
    const item = el('li');
    const button = el('button', 'session-item');
    button.type = 'button';
    button.dataset.session = s.session_id;
    if (s.session_id === selectedSession) button.setAttribute('aria-current', 'true');
    const top = el('span', 'session-top');
    top.append(
      el('code', '', `${s.session_id.slice(0, 10)}…`),
      el('span', `badge ${s.status}`, SESSION_STATUS[s.status] || s.status),
    );
    const info = `${s.turns}턴 · 고객 ${s.customer_id || '미확인'} · ${time(s.updated_at)}`;
    button.append(top, el('span', 'muted', info));
    button.addEventListener('click', () => openSession(s.session_id));
    item.append(button);
    return item;
  }

  async function loadSessions() {
    try {
      const list = await api('/api/admin/sessions');
      els.sessions.replaceChildren(...list.map(sessionItem));
      els.sessionsEmpty.hidden = list.length > 0;
      say(els.sessionsError, '');
    } catch (error) {
      if (!handled(error)) say(els.sessionsError, '상담 목록을 불러오지 못했습니다.');
    }
  }

  // 한 세션의 대화(고객이 본 것), 대기 중인 승인, 후처리 기록, 감사 로그 표를 그린다. 응답을 기다리는 사이
  // 다른 세션을 골랐으면 늦게 온 응답은 버린다. 감사 로그의 payload는 JSON 문자열 그대로 pre에 넣는다.
  // 후처리 기록은 같은 응답의 감사 로그에서 꺼내 그린다(renderSummary).
  async function openSession(id) {
    selectedSession = id;
    for (const button of els.sessions.querySelectorAll('button')) {
      if (button.dataset.session === id) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    }
    let data;
    try {
      data = await api(`/api/admin/sessions/${encodeURIComponent(id)}`);
    } catch (error) {
      if (!handled(error)) say(els.sessionsError, '상담 내용을 불러오지 못했습니다.');
      return;
    }
    if (selectedSession !== id) return; // 그 사이 다른 세션을 골랐다
    say(els.sessionsError, '');
    const transcript = data.transcript;
    $('detail-title').textContent = `상담 ${id.slice(0, 10)}…`;
    const state = SESSION_STATUS[transcript.status] || transcript.status;
    $('detail-meta').textContent = `상태: ${state} · 세션 ID: ${id}`;
    $('detail-messages').replaceChildren(...transcript.messages.map(bubble));
    $('detail-chips').replaceChildren(
      ...transcript.pending_approvals.map((p) => el('li', 'chip', `승인 대기 ${p.code} · 환불 예정 ${won(p.refund_won)}`)),
    );
    $('audit').replaceChildren(
      ...data.audit.map((event) => {
        const row = el('tr');
        const payload = el('td');
        payload.append(el('pre', 'payload', JSON.stringify(event.payload)));
        row.append(el('td', 'nowrap', time(event.at)), el('td', '', event.kind), payload);
        return row;
      }),
    );
    renderSummary(data.audit);
    shownSession = id;
    els.detail.hidden = false;
    els.detail.scrollIntoView({ block: 'nearest' });
  }

  // ------------------------------------------------------------ 후처리 기록 (after-call record)

  // 후처리 서비스 연결이 켜져 있는지 /healthz에서 읽어 단추를 보이거나 숨긴다. 로그인에 성공할 때마다 한 번
  // 부른다(enter). 기다리지 않고 부르므로 본 화면이 먼저 열리고, 응답이 오기 전에는 단추가 숨겨져 있다.
  // /healthz는 토큰이 필요 없는 끝점이라 api()를 쓰지 않고 토큰 머리 없이 fetch로 읽는다(토큰이 필요 없는
  // 요청에 싣지 않는다). 서버를 다시 띄우면 값이 바뀔 수 있으므로 브라우저 캐시를 쓰지 않는다.
  // 읽지 못하면(네트워크 오류, 200이 아님, JSON이 아님) 단추를 숨긴 채 둔다. 예외를 여기서 삼키는 까닭: 이
  // 값이 정하는 것은 단추를 보일지뿐이고 화면의 다른 기능은 이 값 없이 돌며, 켜져 있다고 확인하지 못한
  // 연결의 단추를 보이지 않는 쪽이 안전하다.
  async function loadSummaryLink() {
    summaryEnabled = false;
    syncSummaryButton();
    try {
      const response = await fetch('/healthz', { cache: 'no-store' });
      if (response.ok) {
        const health = await response.json();
        summaryEnabled = isObject(health) && health.summary === true;
      }
    } catch {
      // 위에서 summaryEnabled를 false로 두었으므로 단추는 숨은 채로 남는다
    }
    syncSummaryButton();
  }

  // '후처리 기록 만들기' 단추의 모양을 상태에 맞춘다: 연결이 켜져 있을 때만 보이고(summaryEnabled), 요청이
  // 진행 중이면 잠근다(summaryBusy). 두 상태가 바뀌는 곳은 모두 이것을 거친다.
  function syncSummaryButton() {
    els.summaryCreate.hidden = !summaryEnabled;
    els.summaryCreate.disabled = summaryBusy;
  }

  // 확인이 필요한 번호 하나의 한 줄: "<유형> <값> (<사유>, <사유>)". 사유가 없으면 괄호를 붙이지 않는다. 유형과
  // 값이 글이 아니면 '-'이고, 객체가 아닌 원소는 '-' 한 줄이다. 사유는 글인 것만 보이고 아는 값(REASON_NAMES)은
  // 한국어로 바꾼다.
  function flagLine(flag) {
    if (!isObject(flag)) return '-';
    const reasons = (Array.isArray(flag.reasons) ? flag.reasons : [])
      .filter((reason) => typeof reason === 'string' && reason.trim() !== '')
      .map((reason) => REASON_NAMES.get(reason) || reason);
    const line = `${textOf(flag.type)} ${textOf(flag.value)}`;
    return reasons.length > 0 ? `${line} (${reasons.join(', ')})` : line;
  }

  // 후처리 기록 하나(감사 행 summary_created)를 dl로 그린다: 만든 때(시각 · 담당자 · 모델), 문의 유형, 처리
  // 결과, 요약, 확인이 필요한 번호. 만든 때를 보이는 까닭: 그 뒤 대화가 이어졌으면 기록이 낡았을 수 있어 언제
  // 만든 것인지 알아야 한다. entities·actions_taken·follow_up은 그리지 않는다(감사 표의 내용 칸에 그대로
  // 있다). 모든 칸을 형을 확인하며 읽으므로 어떤 값이 와도 예외 없이 그려진다.
  function summaryFacts(event) {
    const payload = isObject(event.payload) ? event.payload : {};
    const record = isObject(payload.record) ? payload.record : {};
    const flags = Array.isArray(payload.needs_confirmation) ? payload.needs_confirmation : [];
    // 번호는 하나씩 붙인다. 목록을 함수 인자로 펼치면(append(...목록)) 원소가 아주 많을 때 엔진의 인자 수 한도에
    // 걸려 RangeError가 나고, 그러면 openSession 전체가 멈춘다.
    const confirm = el('dd');
    if (flags.length === 0) confirm.textContent = '없음';
    else {
      for (const flag of flags.slice(0, MAX_FLAGS_SHOWN)) confirm.append(el('div', '', flagLine(flag)));
      const more = flags.length - MAX_FLAGS_SHOWN;
      if (more > 0) confirm.append(el('div', 'muted', `… 외 ${more}건`));
    }
    const when = time(typeof event.at === 'string' ? event.at : '');
    const made = `${when} · ${textOf(payload.by)} · ${textOf(payload.model)}`;
    const facts = el('dl', 'facts');
    facts.append(
      el('dt', '', '만든 때'),
      el('dd', '', made),
      el('dt', '', '문의 유형'),
      el('dd', '', textOf(record.category)),
      el('dt', '', '처리 결과'),
      el('dd', '', textOf(record.resolution)),
      el('dt', '', '요약'),
      el('dd', '', textOf(record.summary)),
      el('dt', '', '확인이 필요한 번호'),
      confirm,
    );
    return facts;
  }

  // 후처리 기록 묶음을 감사 로그(audit, 오래된 것이 먼저)에서 새로 그린다.
  // - 가장 최근 summary_created를 그린다. 없으면 '아직 없습니다'.
  // - 알림 줄: summary_created와 summary_failed 두 종류만 추린 것 가운데 가장 최근 것이 summary_failed면
  //   "마지막 시도(<시각>)는 실패했습니다: <error>"를 보인다. 감사 로그 전체의 마지막 행이 아니라 이 두 종류
  //   안에서 본다(그 뒤에 다른 종류의 행이 생겨도 마지막 시도의 결과는 같다). 앞서 만든 기록은 실패했다고
  //   지우지 않고 그대로 보인다. 그 밖에는 알림을 지운다.
  // 단추를 누른 결과 문구는 이 함수가 아니라 createSummary가 이 뒤에 쓴다.
  function renderSummary(audit) {
    const events = Array.isArray(audit) ? audit : [];
    const kinds = ['summary_created', 'summary_failed'];
    let latest = null; // 두 종류 가운데 가장 최근 것
    let created = null; // 가장 최근 summary_created
    for (let i = events.length - 1; i >= 0; i -= 1) {
      const event = events[i];
      if (!isObject(event) || !kinds.includes(event.kind)) continue;
      if (latest === null) latest = event;
      if (event.kind === 'summary_created') {
        created = event;
        break;
      }
    }
    els.summaryRecord.replaceChildren(created ? summaryFacts(created) : el('p', 'empty', '아직 없습니다'));
    if (latest !== null && latest.kind === 'summary_failed') {
      const payload = isObject(latest.payload) ? latest.payload : {};
      const when = time(typeof latest.at === 'string' ? latest.at : '');
      say(els.summaryResult, `마지막 시도(${when})는 실패했습니다: ${textOf(payload.error)}`, 'warn');
    } else say(els.summaryResult, '', 'warn');
  }

  // '후처리 기록 만들기' 단추. 상세에 그려진 세션(shownSession)의 후처리 기록을 만들어 달라고 서버에 청한다.
  // 담당자 이름은 승인 결정과 같은 값이다. 요청이 끝날 때까지 단추를 잠그고, 그동안 다른 세션을 열어도 잠긴 채다
  // (서버가 동시에 받는 후처리 요청 수는 제한되어 있고, 요청 하나가 모델 호출이라 오래 걸릴 수 있다).
  // 끝나면 성공이든 실패든, 그때도 같은 세션을 보고 있을 때만 그 세션을 다시 열어 감사 표와 기록을 새로 그리고,
  // 그 뒤에 이번 누름의 결과 문구를 알림 줄에 쓴다. 차례가 이런 까닭: 다시 열 때 renderSummary가 '마지막 시도는
  // 실패했습니다'(서버의 영어 문장)를 먼저 그리므로, 결과 문구를 그 앞에 쓰면 덮인다. 그 사이 다른 세션을
  // 골랐거나 로그아웃했으면 다시 열지도 알리지도 않는다(남의 세션 화면에 이 세션의 결과를 쓰지 않는다).
  // 문구는 상태 코드로 고른다(SUMMARY_FAILURES). 401·503은 api()가 이미 로그인 화면으로 처리했으므로 쓸 글이
  // 없다. 그 밖의 실패(409·422·429·501·502·504, 네트워크 오류)에서는 로그인이 풀리지 않는다. 501이면 연결이
  // 꺼진 것이므로 단추도 숨긴다.
  async function createSummary() {
    const id = shownSession;
    if (!id || summaryBusy || !summaryEnabled) return;
    summaryBusy = true;
    syncSummaryButton();
    const by = els.by.value.trim() || 'admin';
    let notice = { text: SUMMARY_CREATED, tone: 'ok' };
    try {
      await api(`/api/admin/sessions/${encodeURIComponent(id)}/summary`, { by });
    } catch (error) {
      const status = error instanceof ApiError ? error.status : 0;
      notice = handled(error) ? null : { text: SUMMARY_FAILURES[status] || SUMMARY_FAILED, tone: 'warn' };
      if (status === 501) summaryEnabled = false;
    } finally {
      summaryBusy = false;
      syncSummaryButton();
    }
    if (notice === null || !token || selectedSession !== id) return;
    await openSession(id);
    // 다시 여는 요청이 실패하면 화면에는 그 전에 그려 둔 세션이 그대로 남는다. 그것이 이 세션일 때만 결과를
    // 쓴다(shownSession은 상세를 실제로 그린 뒤에만 바뀐다). 그 사이 다른 세션의 상세가 그려져 있으면 쓰지 않는다.
    if (selectedSession === id && shownSession === id) say(els.summaryResult, notice.text, notice.tone);
  }

  // ------------------------------------------------------------ 탭과 이벤트 연결 (tabs and wiring)

  // 탭 전환. 선택된 탭만 tabIndex 0으로 두어 Tab 키로는 선택된 탭에만 닿고, 상담 기록 탭을 열 때마다 목록을
  // 새로 읽는다.
  function selectTab(name) {
    for (const key of Object.keys(tabs)) {
      const selected = key === name;
      tabs[key].setAttribute('aria-selected', String(selected));
      tabs[key].tabIndex = selected ? 0 : -1;
      panels[key].hidden = !selected;
    }
    if (name === 'sessions') loadSessions();
  }

  for (const [name, tab] of Object.entries(tabs)) {
    tab.addEventListener('click', () => selectTab(name));
    tab.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      const other = name === 'approvals' ? 'sessions' : 'approvals';
      selectTab(other);
      tabs[other].focus();
    });
  }

  // --- 이벤트 연결 ---
  // 토큰 제출: 입력칸은 바로 비우고, 출력 가능한 ASCII가 아닌 값은 서버에 보내지 않고 거절한다.
  $('login-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const value = els.tokenInput.value.trim();
    els.tokenInput.value = '';
    // 출력 가능한 ASCII 밖의 값은 헤더로 보낼 수 없으므로 토큰일 수도 없다.
    if (!value || /[^\x20-\x7e]/.test(value)) {
      showLogin('토큰이 올바르지 않습니다. 다시 입력해 주세요.');
      return;
    }
    say(els.loginMessage, '');
    setToken(value);
    enter();
  });
  els.logout.addEventListener('click', () => {
    setToken('');
    showLogin('');
  });
  // 담당자 이름은 탭 안에서 기억해 매번 다시 쓰지 않게 한다.
  els.by.value = read(BY_KEY);
  els.by.addEventListener('input', () => write(BY_KEY, els.by.value.trim()));
  els.showDecided.addEventListener('change', loadApprovals);
  $('sessions-refresh').addEventListener('click', () => {
    loadSessions();
    if (selectedSession) openSession(selectedSession);
  });
  // 후처리 기록 만들기 단추. 연결이 켜졌는지 확인하기 전의 모양(숨김)을 HTML의 hidden과 같게 맞춰 둔다.
  els.summaryCreate.addEventListener('click', createSummary);
  syncSummaryButton();

  // 로그인했고 본 화면이 보이며 탭이 앞에 있을 때만 주기적으로 대기열을 갱신한다(숨긴 탭에서는 요청하지
  // 않음).
  setInterval(() => {
    if (token && !els.app.hidden && !document.hidden) loadApprovals();
  }, REFRESH_MS);

  // 같은 탭에서 새로 고침하면 저장한 토큰으로 바로 들어가고, 없으면 로그인 화면을 보인다.
  if (token) enter();
  else showLogin('');
})();
