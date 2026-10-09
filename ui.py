"""GUI: 화면 아래 플로팅 알약(녹음·처리 상태, tkinter) + 트레이 '열기' 창(홈·기록·사전·설정, 웹 화면).

알약은 tkinter(표준 라이브러리). tk는 메인 스레드에서만 만지고, 다른 스레드는 post()로 부탁한다.
창은 web/ 의 TypeScript 화면을 127.0.0.1 로컬 서버로 내주고 Edge 앱 창으로 띄운다(설치할 것 없음).
"""
import ctypes, json, os, queue, secrets, subprocess, sys, threading, time, tkinter as tk, webbrowser
from collections import deque
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

user32 = ctypes.windll.user32
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
FONT = "Malgun Gothic"
BG, FG, DIM, RED, SIDE, KEY = "#1c1c1e", "#f2f2f2", "#8e8e93", "#ff453a", "#f2f2f7", "#010203"
WEB = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "web")
TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


class Pill:
    """화면 아래 가운데 알약. 포커스를 절대 뺏지 않아야 붙여넣기가 원래 앱에 들어감."""
    W, H, N = 228, 46, 18  # 96dpi 기준 크기, 막대 개수

    def __init__(self, app, s, on_cancel, on_stop):
        self.app, self.s, self.mode, self.t0 = app, s, None, 0.0
        self.levels = deque([0.0] * self.N, self.N)
        w = tk.Toplevel(app.root, bg=KEY)
        w.overrideredirect(True)
        w.geometry("+-2000+-2000")
        w.attributes("-topmost", True, "-transparentcolor", KEY)
        c = self.c = tk.Canvas(w, width=int(self.W * s), height=int(self.H * s), bg=KEY, highlightthickness=0)
        c.pack()
        W, H, S = self.W, self.H, lambda *v: [x * s for x in v]
        for box in ((0, 0, H, H), (W - H, 0, W, H)):
            c.create_oval(*S(*box), fill=BG, outline=BG)
        c.create_rectangle(*S(H / 2, 0, W - H / 2, H), fill=BG, outline=BG)
        c.create_oval(*S(9, 9, 37, 37), fill="#3a3a3c", outline="", tags=("rec", "cancel"))
        c.create_text(*S(23, 23), text="✕", fill=FG, font=(FONT, 9), tags=("rec", "cancel"))
        c.create_oval(*S(W - 37, 9, W - 9, 37), fill=RED, outline="", tags=("rec", "stop"))
        c.create_rectangle(*S(W - 28, 18, W - 18, 28), fill=FG, outline="", tags=("rec", "stop"))
        self.bars = [c.create_rectangle(0, 0, 0, 0, fill=FG, outline="", tags="rec") for _ in range(self.N)]
        self.clock = c.create_text(*S(W - 56, 23), text="0:00", fill=DIM, font=(FONT, 9), tags="rec")
        self.label = c.create_text(*S(W / 2, 23), text="", fill=FG, font=(FONT, 10))
        c.tag_bind("cancel", "<Button-1>", lambda e: on_cancel())
        c.tag_bind("stop", "<Button-1>", lambda e: on_stop())
        w.update()
        self.hwnd = int(w.wm_frame(), 16)
        ex = user32.GetWindowLongW(self.hwnd, -20)  # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        user32.SetWindowLongW(self.hwnd, -20, ex | 0x08000000 | 0x80)
        user32.ShowWindow(self.hwnd, 0)
        self._tick()

    def show(self, mode, text=""):
        """mode: rec(녹음) / busy(전사·다듬기) / msg(잠깐 알림)"""
        self.c.itemconfigure("rec", state="normal" if mode == "rec" else "hidden")
        self.c.itemconfigure(self.label, state="hidden" if mode == "rec" else "normal", text=text)
        if self.mode is None:  # tk의 deiconify는 창을 활성화하므로 Win32로 직접 띄움
            r = wintypes.RECT()
            user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)  # 작업 표시줄 뺀 영역
            x, y = (r.left + r.right - int(self.W * self.s)) // 2, r.bottom - int((self.H + 18) * self.s)
            user32.SetWindowPos(self.hwnd, -1, x, y, 0, 0, 0x1 | 0x10 | 0x40)  # TOPMOST, NOSIZE|NOACTIVATE|SHOW
        self.mode, self.t0 = mode, time.monotonic()
        self.levels.extend([0.0] * self.N)

    def hide(self, only=None):
        if only and self.mode != only:  # 처리 끝났을 때 이미 다음 녹음 중이면 그대로 둠
            return
        user32.ShowWindow(self.hwnd, 0)
        self.mode = None

    def _tick(self):
        el = time.monotonic() - self.t0
        if self.mode == "rec":
            self.levels.append(min(1.0, self.app.level * 15))
            s, H = self.s, self.H
            for i, (b, v) in enumerate(zip(self.bars, self.levels)):
                x, h = 46 + i * 6, 3 + v * 24
                self.c.coords(b, x * s, (H - h) / 2 * s, (x + 3) * s, (H + h) / 2 * s)
            self.c.itemconfigure(self.clock, text=f"{int(el) // 60}:{int(el) % 60:02d}")
        elif self.mode == "busy":
            n = int(el * 3) % 4
            self.c.itemconfigure(self.label, text="다듬는 중" + "." * n + " " * (3 - n))
        elif self.mode == "msg" and el > 1.5:
            self.hide()
        self.c.after(50, self._tick)


class App:
    def __init__(self, cfg, save_cfg, mics, hist_path, on_cancel, on_stop, status):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except OSError:
            pass
        self.root = tk.Tk()
        self.root.withdraw()
        self.s = self.root.winfo_fpixels("1i") / 96
        self.cfg, self.save_cfg, self.mics, self.hist_path, self.status = cfg, save_cfg, mics, hist_path, status
        self.level, self.q = 0.0, queue.Queue()
        self.web = Web(self)
        self.pill = Pill(self, self.s, on_cancel, on_stop)
        self._poll()

    def post(self, fn, *args):
        """다른 스레드에서 tk 작업 부탁"""
        self.q.put((fn, args))

    def _poll(self):
        while not self.q.empty():
            fn, args = self.q.get()
            fn(*args)
        self.root.after(30, self._poll)

    def run(self):
        self.root.mainloop()

    def history(self):
        try:
            with open(self.hist_path, encoding="utf-8") as f:
                return [json.loads(l) for l in f if l.strip()]
        except (OSError, ValueError):
            return []

    def save_history(self, hist):
        with open(self.hist_path, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(h, ensure_ascii=False) + "\n" for h in hist)

    def open_main(self):
        self.web.open()

    def refresh(self):
        pass  # 열려 있는 창이 3초마다 스스로 새로 읽음


class Web:
    """web/ 정적 파일 + JSON API를 127.0.0.1 임의 포트로. 토큰이 맞는 요청만 받음."""

    def __init__(self, app):
        self.token = secrets.token_urlsafe(16)
        web = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, code, body, kind="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", kind + "; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def ok(self):  # DNS 리바인딩·다른 사이트의 요청 막기
                return self.headers.get("Host", "").split(":")[0] == "127.0.0.1"

            def do_GET(self):
                if not self.ok():
                    return self.send(403, b"")
                path, _, query = self.path.partition("?")
                if path == "/api/state":
                    if self.headers.get("X-Token") != web.token:
                        return self.send(403, b"")
                    st = {"cfg": app.cfg, "mics": app.mics(), "history": app.history(), "status": app.status()}
                    return self.send(200, json.dumps(st, ensure_ascii=False).encode())
                if path == "/":
                    if query != "k=" + web.token:
                        return self.send(403, b"")
                    path = "/index.html"
                f = os.path.join(WEB, os.path.basename(path))
                if os.path.splitext(f)[1] not in TYPES or not os.path.isfile(f):
                    return self.send(404, b"")
                with open(f, "rb") as fh:
                    body = fh.read()
                self.send(200, body.replace(b"__TOKEN__", web.token.encode()), TYPES[os.path.splitext(f)[1]])

            def do_POST(self):
                if not self.ok() or self.headers.get("X-Token") != web.token:
                    return self.send(403, b"")
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/api/cfg":
                    err = app.save_cfg({**app.cfg, **req})
                    return self.send(200, json.dumps({"err": err}, ensure_ascii=False).encode())
                if self.path == "/api/history":  # 통째로 다시 씀(삭제·되돌리기)
                    app.save_history(req["history"])
                    return self.send(200, b"{}")
                self.send(404, b"")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def open(self):
        url = f"http://127.0.0.1:{self.server.server_port}/?k={self.token}"
        try:  # Edge는 Windows에 기본으로 깔려 있음. 앱 창(주소창 없는 창)으로 띄움
            subprocess.Popen(["cmd", "/c", "start", "", "msedge", f"--app={url}", "--window-size=920,640"],
                             creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError:
            webbrowser.open(url)
