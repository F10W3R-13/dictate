"""Typeless 흉내 GUI: 화면 아래 플로팅 알약(녹음·처리 상태) + 트레이 '열기' 창(홈·기록·사전·설정).

tkinter(표준 라이브러리)만 씀. tk는 메인 스레드에서만 만지고, 다른 스레드는 post()로 부탁한다.
"""
import ctypes, json, queue, time, tkinter as tk
from collections import deque
from ctypes import wintypes
from datetime import datetime
from tkinter import ttk

user32 = ctypes.windll.user32
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
FONT = "Malgun Gothic"
BG, FG, DIM, RED, SIDE, KEY = "#1c1c1e", "#f2f2f2", "#8e8e93", "#ff453a", "#f2f2f7", "#010203"
TYPING_WPM = 40  # '아낀 시간' 계산용 타자 속도(어절/분)


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
    def __init__(self, cfg, save_cfg, mics, hist_path, on_cancel, on_stop):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except OSError:
            pass
        self.root = tk.Tk()
        self.root.withdraw()
        self.s = self.root.winfo_fpixels("1i") / 96
        self.cfg, self.save_cfg, self.mics, self.hist_path = cfg, save_cfg, mics, hist_path
        self.level, self.q, self.main = 0.0, queue.Queue(), None
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
        if self.main is None:
            self.main = Main(self)
        else:
            self.main.show(self.main.page)
            self.main.win.deiconify()
        self.main.win.lift()
        self.main.win.focus_force()

    def refresh(self):
        if self.main and self.main.win.state() == "normal" and self.main.page in ("홈", "기록"):
            self.main.show(self.main.page)


def label(parent, text, size=10, fg="#1c1c1e", bg="white", style=(), **kw):
    return tk.Label(parent, text=text, font=(FONT, size, *style), fg=fg, bg=bg, **kw)


def button(parent, text, cmd):
    return tk.Button(parent, text=text, command=cmd, font=(FONT, 9), relief="flat", bg="#e5e5ea",
                     activebackground="#d1d1d6", padx=12, pady=3, cursor="hand2")


class Main:
    PAGES = ("홈", "기록", "사전", "설정")

    def __init__(self, app):
        self.app, s = app, app.s
        w = self.win = tk.Toplevel(app.root, bg="white")
        w.title("Dictate")
        w.geometry(f"{int(760 * s)}x{int(500 * s)}")
        w.minsize(int(600 * s), int(400 * s))
        w.protocol("WM_DELETE_WINDOW", w.withdraw)  # 닫아도 트레이에서 계속 동작
        side = tk.Frame(w, bg=SIDE, width=int(150 * s))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        label(side, "Dictate", 13, bg=SIDE, style=("bold",)).pack(anchor="w", padx=16, pady=(18, 14))
        self.tabs = {}
        for p in self.PAGES:
            t = label(side, p, 10, bg=SIDE, anchor="w", padx=16, pady=7, cursor="hand2")
            t.pack(fill="x", padx=6)
            t.bind("<Button-1>", lambda e, p=p: self.show(p))
            self.tabs[p] = t
        self.body = tk.Frame(w, bg="white")
        self.body.pack(side="left", fill="both", expand=True)
        self.show("홈")

    def show(self, page):
        self.page = page
        for p, t in self.tabs.items():
            t.configure(bg="#dcdce4" if p == page else SIDE)
        for c in self.body.winfo_children():
            c.destroy()
        label(self.body, page, 16, style=("bold",)).pack(anchor="w", padx=24, pady=(18, 12))
        {"홈": self.home, "기록": self.history, "사전": self.dictionary, "설정": self.settings}[page](self.body)

    def home(self, f):
        hist = self.app.history()
        words = sum(len(h["text"].split()) for h in hist)
        mins = sum(h["sec"] for h in hist) / 60
        saved = max(0.0, words / TYPING_WPM - mins)
        today = datetime.now().strftime("%Y-%m-%d")
        stats = [("받아쓴 단어", f"{words:,}"),
                 ("평균 속도", f"{words / mins:.0f} WPM" if mins else "-"),
                 ("아낀 시간", f"{saved:.0f}분" if saved < 60 else f"{saved / 60:.1f}시간"),
                 ("오늘", f"{sum(h['t'].startswith(today) for h in hist)}회")]
        grid = tk.Frame(f, bg="white")
        grid.pack(anchor="w", padx=24)
        for i, (k, v) in enumerate(stats):
            card = tk.Frame(grid, bg=SIDE, padx=18, pady=12)
            card.grid(row=i // 2, column=i % 2, padx=(0, 12), pady=(0, 12), sticky="nsew")
            label(card, k, 9, fg=DIM, bg=SIDE, width=16, anchor="w").pack(anchor="w")
            label(card, v, 20, bg=SIDE, style=("bold",)).pack(anchor="w")
        label(f, f"{self.app.cfg['hotkey']} 로 말하기 시작, 다시 눌러 끝내면 커서 자리에 붙여넣어요.",
              9, fg=DIM).pack(anchor="w", padx=24, pady=6)

    def history(self, f):
        hist = self.app.history()[::-1]  # 최신 먼저
        box = tk.Frame(f, bg="white")
        box.pack(fill="both", expand=True, padx=24)
        lb = tk.Listbox(box, activestyle="none", font=(FONT, 10), relief="flat", bg=SIDE,
                        highlightthickness=0, selectbackground="#c7c7cc", selectforeground="#1c1c1e")
        sb = ttk.Scrollbar(box, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        for h in hist:
            lb.insert("end", f" {h['t'][5:16].replace('T', ' ')}   {h['text'][:80]}")
        txt = tk.Text(f, height=5, wrap="word", font=(FONT, 10), relief="flat", bg="#fafafa", padx=8, pady=6)
        txt.pack(fill="x", padx=24, pady=8)

        def picked():
            i = lb.curselection()
            return hist[i[0]] if i else None

        def select(_=None):
            txt.delete("1.0", "end")
            h = picked()
            if h:
                txt.insert("1.0", h["text"] + (f"\n\n원문: {h['raw']}" if h["raw"] != h["text"] else ""))

        def copy():
            h = picked()
            if h:
                self.win.clipboard_clear()
                self.win.clipboard_append(h["text"])

        def delete():
            h = picked()
            if h:
                hist.remove(h)
                self.app.save_history(hist[::-1])
                self.show("기록")

        lb.bind("<<ListboxSelect>>", select)
        row = tk.Frame(f, bg="white")
        row.pack(anchor="w", padx=24, pady=(0, 16))
        button(row, "복사", copy).pack(side="left", padx=(0, 8))
        button(row, "삭제", delete).pack(side="left")

    def dictionary(self, f):
        words = list(self.app.cfg["words"])
        label(f, "잘못 알아듣는 이름·전문용어를 넣어 두면 그 표기로 받아써요.", 9, fg=DIM).pack(anchor="w", padx=24)
        row = tk.Frame(f, bg="white")
        row.pack(anchor="w", padx=24, pady=10)
        e = ttk.Entry(row, width=30, font=(FONT, 10))
        e.pack(side="left", padx=(0, 8))
        lb = tk.Listbox(f, activestyle="none", font=(FONT, 10), relief="flat", bg=SIDE, highlightthickness=0,
                        selectbackground="#c7c7cc", selectforeground="#1c1c1e")
        lb.pack(fill="both", expand=True, padx=24)
        for w in words:
            lb.insert("end", f" {w}")

        def add(_=None):
            w = e.get().strip()
            if w and w not in words:
                self.app.save_cfg({**self.app.cfg, "words": words + [w]})
                self.show("사전")

        def delete():
            i = lb.curselection()
            if i:
                self.app.save_cfg({**self.app.cfg, "words": [w for j, w in enumerate(words) if j != i[0]]})
                self.show("사전")

        e.bind("<Return>", add)
        button(row, "추가", add).pack(side="left")
        button(f, "선택 삭제", delete).pack(anchor="w", padx=24, pady=(8, 16))
        e.focus_set()

    def settings(self, f):
        cfg = self.app.cfg
        form = tk.Frame(f, bg="white")
        form.pack(anchor="w", padx=24)
        hk = tk.StringVar(value=cfg["hotkey"])
        mic = tk.StringVar(value=cfg["mic"] or "기본 장치")
        clean, auto = tk.BooleanVar(value=cfg["cleanup"]), tk.BooleanVar(value=cfg["autostart"])
        rows = [("단축키", ttk.Entry(form, textvariable=hk, width=30, font=(FONT, 10))),
                ("마이크", ttk.Combobox(form, textvariable=mic, values=["기본 장치"] + self.app.mics(),
                                     state="readonly", width=38))]
        for i, (k, wdg) in enumerate(rows):
            label(form, k, 10, width=8, anchor="w").grid(row=i, column=0, sticky="w", pady=6)
            wdg.grid(row=i, column=1, sticky="w")
        label(form, "예: ctrl+shift+space, right ctrl, f9", 8, fg=DIM).grid(row=2, column=1, sticky="w")
        for i, (text, var) in enumerate([("AI로 다듬기 (군말 빼고 맞춤법·문장부호 정리)", clean),
                                         ("Windows 시작할 때 자동 실행", auto)], start=3):
            tk.Checkbutton(form, text=text, variable=var, font=(FONT, 10), bg="white", activebackground="white",
                           anchor="w").grid(row=i, column=0, columnspan=2, sticky="w", pady=4)
        msg = label(f, "", 9)

        def save():
            err = self.app.save_cfg({**cfg, "hotkey": hk.get().strip().lower(),
                                     "mic": "" if mic.get() == "기본 장치" else mic.get(),
                                     "cleanup": clean.get(), "autostart": auto.get()})
            msg.configure(text=err or "저장했어요", fg=RED if err else "#34c759")

        button(f, "저장", save).pack(anchor="w", padx=24, pady=(14, 4))
        msg.pack(anchor="w", padx=24)
