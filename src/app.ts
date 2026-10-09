// Dictate 창 화면. 데이터는 로컬 서버(ui.py의 Web)에서 받고, 바꾼 건 바로 돌려보낸다.
interface Item { t: string; sec: number; raw: string; text: string }
interface Cfg { hotkey: string; mic: string; cleanup: boolean; autostart: boolean; sounds: boolean; theme: Theme; words: string[] }
interface State { cfg: Cfg; mics: string[]; history: Item[]; status: string }
type Theme = "system" | "light" | "dark";
type Page = "home" | "history" | "dict" | "settings";

const TYPING_WPM = 40; // '아낀 시간' 계산용 타자 속도(어절/분)
const DEFAULT_MIC = "기본 장치";
const $ = <T extends HTMLElement = HTMLElement>(s: string, el: ParentNode = document) => el.querySelector(s) as T;
const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
const hk = (s: string) => s.split("+").map(k => (k.length === 1 ? k.toUpperCase() : k[0].toUpperCase() + k.slice(1))).join("+");
const when = (iso: string) => new Date(iso);
const hm = (iso: string) => iso.slice(11, 16);
const words = (h: Item) => h.text.split(/\s+/).filter(Boolean).length;
const dayStart = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
const DAY = 864e5;

let st: State;
let page: Page = "home";

async function api<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "X-Token": (window as any).TOKEN },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

let toastTimer: number;
function toast(msg: string, undo?: () => void) {
  const t = $("#toast"), b = $<HTMLButtonElement>("#toastUndo");
  $("#toastMsg").textContent = msg;
  b.hidden = !undo;
  b.onclick = () => { undo?.(); t.classList.remove("on"); };
  t.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => t.classList.remove("on"), 3500);
}

function applyTheme() {
  const r = document.documentElement;
  st.cfg.theme === "system" ? r.removeAttribute("data-theme") : r.setAttribute("data-theme", st.cfg.theme);
  $("#hkSide").textContent = hk(st.cfg.hotkey);
  $("#st").textContent = st.status;
}

async function saveCfg(patch: Partial<Cfg>, msg = "저장했어요", undo?: () => void): Promise<boolean> {
  try {
    const { err } = await api<{ err: string | null }>("/api/cfg", patch);
    if (err) { toast(err); return false; }
    st.cfg = { ...st.cfg, ...patch };
    applyTheme();
    toast(msg, undo);
    return true;
  } catch { toast("저장하지 못했어요"); return false; }
}

async function saveHistory(history: Item[], msg: string, undo?: () => void) {
  await api("/api/history", { history });
  st.history = history;
  go(page);
  toast(msg, undo);
}

// ---- 홈 ----
function streak(hist: Item[]) {
  const days = new Set(hist.map(h => dayStart(when(h.t))));
  const today = dayStart(new Date());
  let n = 0;
  for (let d = days.has(today) ? today : today - DAY; days.has(d); d -= DAY) n++;
  return n;
}

function heatmap(hist: Item[]) {
  const today = dayStart(new Date()), count = new Map<number, number>();
  for (const h of hist) { const d = dayStart(when(h.t)); count.set(d, (count.get(d) ?? 0) + 1); }
  return Array.from({ length: 21 }, (_, i) => {
    const n = count.get(today - (20 - i) * DAY) ?? 0;
    const lv = n === 0 ? 0 : n < 4 ? 1 : n < 10 ? 2 : 3;
    return `<i data-l="${lv}" title="${n}회"></i>`;
  }).join("");
}

function home(m: HTMLElement) {
  const hist = st.history;
  const w = hist.reduce((a, h) => a + words(h), 0), mins = hist.reduce((a, h) => a + h.sec, 0) / 60;
  const saved = Math.max(0, w / TYPING_WPM - mins);
  const today = dayStart(new Date());
  const todayN = hist.filter(h => dayStart(when(h.t)) === today).length;
  const time = saved < 60 ? `${saved.toFixed(0)}<small> 분</small>` : `${(saved / 60).toFixed(1)}<small> 시간</small>`;
  m.innerHTML = `
    <h1>${todayN ? `오늘 ${todayN}번 받아썼어요` : "오늘은 아직이에요"}</h1>
    <p class="sub"><kbd>${hk(st.cfg.hotkey)}</kbd> 를 누르고 말한 뒤 다시 누르면 커서 자리에 붙여넣어요.</p>
    <div class="stats">
      <div class="stat"><span>받아쓴 어절</span><strong>${w.toLocaleString()}</strong></div>
      <div class="stat"><span>아낀 시간</span><strong>${time}</strong></div>
      <div class="stat"><span>평균 속도</span><strong>${mins ? Math.round(w / mins) : "–"}<small> 어절/분</small></strong></div>
      <div class="stat"><span>연속 사용</span><strong>${streak(hist)}<small> 일</small></strong></div>
    </div>
    <h2>최근 3주</h2>
    <div class="heat" aria-label="최근 21일 사용량">${heatmap(hist)}</div>
    <h2>최근 받아쓰기</h2>
    ${hist.length ? `<div class="list">${[...hist].reverse().slice(0, 3).map(h => row(h, false)).join("")}</div>` : `<p class="empty">아직 기록이 없어요. 단축키를 눌러 첫 받아쓰기를 해 보세요.</p>`}`;
  bindRows(m);
}

// ---- 기록 ----
function row(h: Item, full: boolean) {
  const raw = full && h.raw !== h.text;
  return `<div class="item"><time>${hm(h.t)}</time><div style="min-width:0"><p>${esc(h.text)}</p>${raw ? `<p class="raw" hidden>${esc(h.raw)}</p>` : ""}</div>
    <div class="acts"><button class="iconbtn" data-a="copy" data-t="${h.t}">복사</button>${raw ? `<button class="iconbtn" data-a="raw">원문</button>` : ""}<button class="iconbtn danger" data-a="del" data-t="${h.t}">삭제</button></div></div>`;
}

function bindRows(el: HTMLElement) {
  el.querySelectorAll<HTMLButtonElement>(".iconbtn").forEach(b => b.onclick = () => {
    const h = st.history.find(x => x.t === b.dataset.t);
    if (b.dataset.a === "copy" && h) navigator.clipboard.writeText(h.text).then(() => toast("복사했어요"), () => toast("복사하지 못했어요"));
    if (b.dataset.a === "raw") {
      const r = b.closest(".item")!.querySelector<HTMLElement>(".raw")!;
      r.hidden = !r.hidden;
      b.textContent = r.hidden ? "원문" : "닫기";
    }
    if (b.dataset.a === "del" && h) {
      const prev = st.history;
      saveHistory(prev.filter(x => x !== h), "기록 1개를 삭제했어요", () => saveHistory(prev, "되돌렸어요"));
    }
  });
}

function historyPage(m: HTMLElement) {
  m.innerHTML = `<h1>기록</h1><p class="sub">받아쓴 글은 이 PC에만 저장돼요.</p>
    <label class="search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>
    <input id="q" placeholder="기록 검색"></label><div id="hl"></div>`;
  const draw = () => {
    const q = $<HTMLInputElement>("#q").value.trim().toLowerCase();
    const rows = [...st.history].reverse().filter(h => !q || (h.text + h.raw).toLowerCase().includes(q));
    const box = $("#hl");
    if (!rows.length) { box.innerHTML = `<p class="empty">${q ? `"${esc(q)}"가 들어간 기록이 없어요.` : "아직 기록이 없어요. 단축키를 눌러 첫 받아쓰기를 해 보세요."}</p>`; return; }
    const today = dayStart(new Date());
    let out = "", cur = -1;
    for (const h of rows) {
      const d = dayStart(when(h.t));
      if (d !== cur) {
        cur = d;
        const diff = Math.round((today - d) / DAY);
        out += `${out ? "</div>" : ""}<h2>${diff === 0 ? "오늘" : diff === 1 ? "어제" : when(h.t).toLocaleDateString("ko-KR")}</h2><div class="list">`;
      }
      out += row(h, true);
    }
    box.innerHTML = out + "</div>";
    bindRows(box);
  };
  $("#q").addEventListener("input", draw);
  draw();
}

// ---- 사전 ----
function dict(m: HTMLElement) {
  const ws = st.cfg.words;
  m.innerHTML = `<h1>사전</h1><p class="sub">자주 틀리게 받아쓰는 이름과 용어를 넣어 두면 그 표기로 받아써요.</p>
    <form class="row" id="addf"><input class="field" id="nw" placeholder="예: 유민우, EXAONE" autocomplete="off"><button class="btn">추가</button></form>
    <div class="chips">${ws.map((w, i) => `<span class="chip">${esc(w)}<button data-i="${i}" aria-label="${esc(w)} 삭제">✕</button></span>`).join("")}</div>
    ${ws.length ? "" : `<p class="empty">아직 등록한 단어가 없어요.</p>`}`;
  $<HTMLFormElement>("#addf").onsubmit = async e => {
    e.preventDefault();
    const w = $<HTMLInputElement>("#nw").value.trim();
    if (w && !ws.includes(w) && await saveCfg({ words: [...ws, w] }, `"${w}" 추가했어요`)) { dict(m); $("#nw").focus(); }
  };
  m.querySelectorAll<HTMLButtonElement>(".chip button").forEach(b => b.onclick = async () => {
    const w = ws[+b.dataset.i!];
    if (await saveCfg({ words: ws.filter(x => x !== w) }, `"${w}" 삭제했어요`,
      async () => { await saveCfg({ words: ws }, "되돌렸어요"); go("dict"); })) dict(m);
  });
}

// ---- 설정 ----
function settings(m: HTMLElement) {
  const c = st.cfg;
  const sw = (k: "cleanup" | "sounds" | "autostart", t: string, s: string) =>
    `<div class="opt"><div><b>${t}</b><small>${s}</small></div><button class="sw" role="switch" aria-checked="${c[k]}" data-k="${k}" aria-label="${t}"></button></div>`;
  m.innerHTML = `<h1>설정</h1><p class="sub">바꾸면 바로 저장돼요.</p>
    <h2>받아쓰기</h2><div class="set">
      <div class="opt"><div><b>단축키</b><small>누르면 녹음 시작, 다시 누르면 끝내고 붙여넣어요.</small></div><button class="key" id="key">${hk(c.hotkey)}</button></div>
      <div class="opt"><div><b>마이크</b><small>말소리가 작게 잡히면 다른 장치를 골라 보세요.</small></div>
        <select class="field" id="mic">${[DEFAULT_MIC, ...st.mics].map(x => `<option ${x === (c.mic || DEFAULT_MIC) ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div>
      ${sw("cleanup", "AI로 다듬기", "군말을 빼고 맞춤법과 문장부호를 정리해요. 끄면 들은 그대로 붙여넣어요.")}
      ${sw("sounds", "시작·끝 알림음", "녹음을 시작하고 끝낼 때 짧은 소리를 내요.")}
    </div>
    <h2>앱</h2><div class="set">
      ${sw("autostart", "Windows 시작할 때 자동 실행", "켜 두면 처음 로딩(약 40초)을 기다릴 일이 없어요.")}
      <div class="opt"><div><b>화면 모드</b><small>시스템을 고르면 Windows 설정을 따라가요.</small></div>
        <div class="seg" id="theme">${([["system", "시스템"], ["light", "라이트"], ["dark", "다크"]] as const).map(([v, t]) => `<button data-v="${v}" aria-pressed="${c.theme === v}">${t}</button>`).join("")}</div></div>
    </div>`;
  m.querySelectorAll<HTMLButtonElement>(".sw").forEach(b => b.onclick = async () => {
    const on = b.getAttribute("aria-checked") !== "true", k = b.dataset.k as "cleanup";
    if (await saveCfg({ [k]: on })) b.setAttribute("aria-checked", String(on));
  });
  $<HTMLSelectElement>("#mic").onchange = e => saveCfg({ mic: (e.target as HTMLSelectElement).value === DEFAULT_MIC ? "" : (e.target as HTMLSelectElement).value });
  m.querySelectorAll<HTMLButtonElement>("#theme button").forEach(b => b.onclick = async () => {
    if (await saveCfg({ theme: b.dataset.v as Theme }))
      m.querySelectorAll("#theme button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
  });
  const key = $<HTMLButtonElement>("#key");
  key.onclick = () => {
    key.classList.add("listening");
    key.textContent = "새 단축키를 누르세요";
    const done = async (v: string) => {
      removeEventListener("keydown", on, true);
      key.classList.remove("listening");
      if (v !== st.cfg.hotkey) await saveCfg({ hotkey: v }, `단축키를 ${hk(v)}로 바꿨어요`);
      key.textContent = hk(st.cfg.hotkey);
    };
    const on = (e: KeyboardEvent) => {
      e.preventDefault();
      if (e.key === "Escape") return done(st.cfg.hotkey);
      if (["Control", "Shift", "Alt", "Meta"].includes(e.key)) return;
      const parts = [e.ctrlKey && "ctrl", e.altKey && "alt", e.shiftKey && "shift"].filter(Boolean) as string[];
      done([...parts, e.code === "Space" ? "space" : e.key.toLowerCase()].join("+"));
    };
    addEventListener("keydown", on, true);
  };
}

// ---- 이동·갱신 ----
const pages: Record<Page, (m: HTMLElement) => void> = { home, history: historyPage, dict, settings };

function go(p: Page) {
  page = p;
  document.querySelectorAll<HTMLElement>("nav button").forEach(b =>
    b.dataset.page === p ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
  pages[p]($("#main"));
}

async function poll() { // 열려 있는 동안 3초마다 새 받아쓰기를 반영(입력 중인 화면은 건드리지 않음)
  if (document.hidden) return;
  try {
    const n = st.history.length, now = await api<State>("/api/state");
    st.status = now.status;
    $("#st").textContent = st.status;
    if (now.history.length !== n) { st.history = now.history; if (page === "home") go("home"); }
  } catch { $("#st").textContent = "앱이 꺼졌어요"; }
}

document.querySelectorAll<HTMLElement>("nav button").forEach(b => b.onclick = () => go(b.dataset.page as Page));
api<State>("/api/state").then(s => { st = s; applyTheme(); go("home"); setInterval(poll, 3000); },
  () => { $("#main").innerHTML = `<p class="empty">Dictate 앱에 연결하지 못했어요. 트레이 아이콘에서 다시 열어 주세요.</p>`; });
