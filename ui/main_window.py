import tkinter as tk
from tkinter import ttk, filedialog
import threading
import os
import sys
import yt_dlp
from core.enums import State, Priority
from core.engine import DownloadEngine
from core.task import DownloadTask
from core.history import AtomicHistory

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".sassi_history.json")

BG = "#0F1115"
BG_CARD = "#171B22"
BG_INPUT = "#1E222D"
FG = "#F0F0F0"
FG_DIM = "#9CA3AF"
ACCENT = "#3B82F6"
GREEN = "#22C55E"
YELLOW = "#EAB308"
ORANGE = "#F97316"
RED = "#EF4444"
BORDER = "#232833"


def fmt_size(b):
    if b < 1024: return f"{b} B"
    elif b < 1048576: return f"{b / 1024:.0f} KB"
    elif b < 1073741824: return f"{b / 1048576:.1f} MB"
    else: return f"{b / 1073741824:.2f} GB"


class SassiDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("Sassi")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(600, 500)

        # Fit to screen
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        wh = min(720, sh - 80)
        ww = min(700, sw - 100)
        x = (sw - ww) // 2
        y = (sh - wh) // 2
        self.root.geometry(f"{ww}x{wh}+{x}+{y}")

        self.engine = DownloadEngine()
        self.history = AtomicHistory(HISTORY_FILE)
        self.formats = []
        self.cards = {}
        self.video_info = None
        self.dl_path = self._default_path()
        self._build()

    def _build(self):
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)

        # ── Header ──
        hdr = tk.Frame(main, bg=BG)
        hdr.pack(fill=tk.X, padx=28, pady=(20, 0))
        tk.Label(hdr, text="SASSI", font=("Segoe UI", 24, "bold"),
                 fg=FG, bg=BG).pack(anchor=tk.W)
        tk.Label(hdr, text="Download videos from hundreds of websites",
                 font=("Segoe UI", 11), fg=FG_DIM, bg=BG).pack(anchor=tk.W, pady=(1, 0))
        tk.Label(hdr, text="YouTube \u00b7 TikTok \u00b7 Instagram \u00b7 X \u00b7 Facebook \u00b7 Reddit \u00b7 Vimeo",
                 font=("Segoe UI", 9), fg="#4B5563", bg=BG).pack(anchor=tk.W, pady=(4, 0))

        # ── URL Input ──
        url_frame = tk.Frame(main, bg=BG)
        url_frame.pack(fill=tk.X, padx=28, pady=(16, 0))

        url_box = tk.Frame(url_frame, bg=BG_INPUT, highlightbackground=BORDER,
                           highlightthickness=1)
        url_box.pack(fill=tk.X)

        self.url_entry = tk.Entry(url_box, font=("Segoe UI", 13), bg=BG_INPUT, fg=FG,
                                   insertbackground=FG, relief=tk.FLAT, highlightthickness=0)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 0), pady=10)
        self.url_entry.bind("<Return>", lambda e: self.analyze())

        self.analyze_btn = tk.Button(url_box, text="Fetch Info", font=("Segoe UI", 11, "bold"),
                                      bg=ACCENT, fg="#FFF", relief=tk.FLAT, cursor="hand2",
                                      activebackground="#2563EB", command=self.analyze,
                                      padx=14, pady=6)
        self.analyze_btn.pack(side=tk.RIGHT, padx=(0, 8), pady=8)

        # ── Status ──
        self.status_label = tk.Label(main, text="Paste a URL above to get started",
                                      font=("Segoe UI", 10), fg=FG_DIM, bg=BG)
        self.status_label.pack(anchor=tk.W, padx=28, pady=(6, 0))

        # ── Preview Card (hidden) ──
        self.preview_card = tk.Frame(main, bg=BG_CARD, highlightbackground=BORDER,
                                      highlightthickness=1)

        preview_inner = tk.Frame(self.preview_card, bg=BG_CARD)
        preview_inner.pack(fill=tk.X, padx=16, pady=12)

        self.preview_thumb = tk.Label(preview_inner, text="\U0001F3AC",
                                       font=("Segoe UI", 32), bg=BG_CARD, fg=FG_DIM,
                                       width=4, anchor=tk.CENTER)
        self.preview_thumb.pack(side=tk.LEFT, padx=(0, 12))

        preview_right = tk.Frame(preview_inner, bg=BG_CARD)
        preview_right.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.preview_title = tk.Label(preview_right, text="", font=("Segoe UI", 12, "bold"),
                                       fg=FG, bg=BG_CARD, anchor=tk.W, wraplength=360)
        self.preview_title.pack(anchor=tk.W)

        self.preview_meta = tk.Label(preview_right, text="", font=("Segoe UI", 10),
                                      fg=FG_DIM, bg=BG_CARD, anchor=tk.W)
        self.preview_meta.pack(anchor=tk.W, pady=(2, 0))

        # ── Options (hidden) ──
        self.opts_frame = tk.Frame(self.preview_card, bg=BG_CARD)
        opts_inner = tk.Frame(self.opts_frame, bg=BG_CARD)
        opts_inner.pack(fill=tk.X, padx=16, pady=(0, 12))

        tk.Label(opts_inner, text="Quality", font=("Segoe UI", 10), fg=FG_DIM, bg=BG_CARD).pack(side=tk.LEFT)
        self.quality_var = tk.StringVar(value="Best")
        self.q_menu = ttk.Combobox(opts_inner, textvariable=self.quality_var,
                                    state="readonly", width=14, font=("Segoe UI", 10))
        self.q_menu.pack(side=tk.LEFT, padx=(6, 0))

        self.dl_btn = tk.Button(opts_inner, text="Download", font=("Segoe UI", 11, "bold"),
                                 bg=GREEN, fg="#FFF", relief=tk.FLAT, cursor="hand2",
                                 activebackground="#16A34A", command=self.download,
                                 padx=18, pady=6)
        self.dl_btn.pack(side=tk.RIGHT)

        # ── Active Downloads ──
        dl_header = tk.Frame(main, bg=BG)
        dl_header.pack(fill=tk.X, padx=28, pady=(16, 6))
        tk.Label(dl_header, text="Active Downloads", font=("Segoe UI", 12, "bold"),
                 fg=FG, bg=BG).pack(side=tk.LEFT)

        dl_outer = tk.Frame(main, bg=BG)
        self.dl_canvas = tk.Canvas(dl_outer, bg=BG, highlightthickness=0)
        self.dl_scroll = tk.Scrollbar(dl_outer, orient=tk.VERTICAL, command=self.dl_canvas.yview)
        self.dl_frame = tk.Frame(self.dl_canvas, bg=BG)
        self.dl_frame.bind("<Configure>", lambda e: self.dl_canvas.configure(scrollregion=self.dl_canvas.bbox("all")))
        self.dl_canvas.create_window((0, 0), window=self.dl_frame, anchor=tk.NW)
        self.dl_canvas.configure(yscrollcommand=self.dl_scroll.set)
        self.dl_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.dl_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Empty state
        self.empty_frame = tk.Frame(self.dl_frame, bg=BG)
        self.empty_frame.pack(fill=tk.X, pady=16)
        tk.Label(self.empty_frame, text="\u2B07", font=("Segoe UI", 24), fg="#232833", bg=BG).pack()
        tk.Label(self.empty_frame, text="No active downloads", font=("Segoe UI", 11),
                 fg=FG_DIM, bg=BG).pack(pady=(4, 0))

        # ── History ──
        hist_header = tk.Frame(main, bg=BG)
        hist_header.pack(fill=tk.X, padx=28, pady=(12, 6))
        tk.Label(hist_header, text="Recent", font=("Segoe UI", 12, "bold"),
                 fg=FG, bg=BG).pack(side=tk.LEFT)

        self.hist_frame = tk.Frame(main, bg=BG_CARD, highlightbackground=BORDER,
                                    highlightthickness=1, height=120)
        self.hist_frame.pack(fill=tk.X, padx=28, pady=(0, 16))
        self.hist_frame.pack_propagate(False)

        self.hist_canvas = tk.Canvas(self.hist_frame, bg=BG_CARD, highlightthickness=0)
        self.hist_scroll = tk.Scrollbar(self.hist_frame, orient=tk.VERTICAL, command=self.hist_canvas.yview)
        self.hist_inner = tk.Frame(self.hist_canvas, bg=BG_CARD)
        self.hist_inner.bind("<Configure>", lambda e: self.hist_canvas.configure(scrollregion=self.hist_canvas.bbox("all")))
        self.hist_canvas.create_window((0, 0), window=self.hist_inner, anchor=tk.NW)
        self.hist_canvas.configure(yscrollcommand=self.hist_scroll.set)
        self.hist_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.hist_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._refresh_hist()

    def _default_path(self):
        if sys.platform == "win32":
            import winreg
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
                p = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")[0]
                winreg.CloseKey(k)
                return p
            except: pass
        return os.path.join(os.path.expanduser("~"), "Downloads")

    def _show_preview(self):
        self.preview_card.pack(fill=tk.X, padx=28, pady=(10, 0))
        self.opts_frame.pack(fill=tk.X)

    def _hide_preview(self):
        self.preview_card.pack_forget()
        self.opts_frame.pack_forget()

    def _refresh_hist(self):
        for w in self.hist_inner.winfo_children():
            w.destroy()
        items = self.history.items[:6]
        if not items:
            tk.Label(self.hist_inner, text="No downloads yet", font=("Segoe UI", 10),
                     fg="#4B5563", bg=BG_CARD).pack(pady=10)
            return
        for i, item in enumerate(items):
            row = tk.Frame(self.hist_inner, bg=BG_CARD)
            row.pack(fill=tk.X, padx=10, pady=(6 if i == 0 else 2, 0))
            tk.Label(row, text="\u2713", font=("Segoe UI", 10), fg=GREEN, bg=BG_CARD).pack(side=tk.LEFT, padx=(0, 6))
            title = item.get('title', 'Unknown')[:36]
            tk.Label(row, text=title, font=("Segoe UI", 9), fg=FG, bg=BG_CARD, anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True)
            size = fmt_size(item.get('size', 0)) if item.get('size', 0) > 0 else ""
            tk.Label(row, text=size, font=("Segoe UI", 9), fg=FG_DIM, bg=BG_CARD).pack(side=tk.RIGHT)

    def analyze(self):
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.config(text="Paste a URL first", fg=YELLOW)
            return
        self.analyze_btn.config(text="...", state=tk.DISABLED)
        self.status_label.config(text="Fetching info...", fg=ACCENT)
        self._hide_preview()

        def work():
            try:
                o = {'quiet': True, 'no_warnings': True, 'skip_download': True}
                with yt_dlp.YoutubeDL(o) as y:
                    info = y.extract_info(url, download=False)
                fmts = [("Best (auto)", "best")]
                seen = {"best"}
                for f in info.get('formats', []):
                    h = f.get('height')
                    ext = f.get('ext', '')
                    vc = f.get('vcodec', 'none')
                    if vc != 'none' and h and h >= 360:
                        l = f"{h}p ({ext.upper()})"
                        if l not in seen:
                            seen.add(l)
                            fmts.append((l, f['format_id']))
                fmts.sort(key=lambda x: int(x[0].split('p')[0]) if x[1] != "best" else 99999, reverse=True)
                self.formats = fmts
                self.video_info = info
                self.root.after(0, self._analyze_ok, info)
            except Exception as e:
                self.root.after(0, self._analyze_err, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _analyze_ok(self, info):
        self.analyze_btn.config(text="Fetch Info", state=tk.NORMAL)
        title = info.get('title', 'Unknown')
        dur = info.get('duration', 0)
        h = info.get('height', 0)
        w = info.get('width', 0)
        fs = info.get('filesize', 0) or info.get('filesize_approx', 0) or 0

        dur_s = f"{dur // 60}:{dur % 60:02d}" if dur else ""
        res = f"{w}x{h}" if h else ""
        sz = fmt_size(fs) if fs else ""
        ext = (info.get('ext', 'mp4') or 'mp4').upper()

        parts = [p for p in [ext, res, dur_s, sz] if p]

        self.preview_title.config(text=title)
        self.preview_meta.config(text="  \u00b7  ".join(parts))
        self.q_menu['values'] = [f[0] for f in self.formats]
        self.q_menu.current(0)
        self._show_preview()
        self.status_label.config(text="Ready to download", fg=GREEN)

    def _analyze_err(self, error):
        self.analyze_btn.config(text="Fetch Info", state=tk.NORMAL)
        self.status_label.config(text=f"Failed: {error[:60]}", fg=RED)

    def download(self):
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.config(text="Paste a URL first", fg=YELLOW)
            return
        if not self.formats:
            self.status_label.config(text="Fetch info first", fg=YELLOW)
            return

        self.dl_btn.config(text="Starting...", state=tk.DISABLED)
        self.status_label.config(text="Starting download...", fg=ACCENT)

        i = self.q_menu.current()
        q = self.formats[i][1] if i >= 0 else "best"
        pri = Priority.NORMAL

        self.empty_frame.pack_forget()

        try:
            task = DownloadTask(url, q, self.dl_path, pri)
            card = self._make_card(task)
            self.cards[task.id] = card
            self.engine.add(task)
            task._on_update = lambda t: self.root.after(0, self._upd_card, t)
            task._on_done = lambda t: self.root.after(0, self._done_card, t)
            task._on_error = lambda t: self.root.after(0, self._err_card, t)

            self.url_entry.delete(0, tk.END)
            self._hide_preview()
            self.formats = []
            self.status_label.config(text="Download started", fg=GREEN)
        except Exception as e:
            self.status_label.config(text=f"Error: {str(e)[:60]}", fg=RED)

        self.dl_btn.config(text="Download", state=tk.NORMAL)

    def _make_card(self, task):
        c = tk.Frame(self.dl_frame, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        c.pack(fill=tk.X, pady=(0, 6), ipady=2)

        inner = tk.Frame(c, bg=BG_CARD)
        inner.pack(fill=tk.X, padx=12, pady=8)

        top = tk.Frame(inner, bg=BG_CARD)
        top.pack(fill=tk.X)

        dot = tk.Label(top, text="\u25cf", font=("Segoe UI", 7), fg=FG_DIM, bg=BG_CARD)
        dot.pack(side=tk.LEFT, padx=(0, 6))

        title = tk.Label(top, text="Queued...", font=("Segoe UI", 11, "bold"),
                          fg=FG, bg=BG_CARD, anchor=tk.W)
        title.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ctrl = tk.Frame(top, bg=BG_CARD)
        ctrl.pack(side=tk.RIGHT)
        pause = tk.Button(ctrl, text="\u23f8", font=("Segoe UI", 10), bg=BG_CARD, fg=FG_DIM,
                           relief=tk.FLAT, cursor="hand2", width=2,
                           command=lambda: self._toggle_pause(task))
        pause.pack(side=tk.LEFT, padx=(0, 4))
        cancel = tk.Button(ctrl, text="\u2715", font=("Segoe UI", 10), bg=BG_CARD, fg=RED,
                            relief=tk.FLAT, cursor="hand2", width=2,
                            command=lambda: self._cancel_task(task))
        cancel.pack(side=tk.LEFT)

        prog = tk.Canvas(inner, bg="#232833", height=6, highlightthickness=0)
        prog.pack(fill=tk.X, pady=(6, 0))
        bar = prog.create_rectangle(0, 0, 0, 6, fill=ACCENT, width=0)

        info = tk.Label(inner, text="Waiting...", font=("Segoe UI", 10),
                         fg=FG_DIM, bg=BG_CARD, anchor=tk.W)
        info.pack(fill=tk.X, pady=(4, 0))

        return {"frame": c, "title": title, "dot": dot,
                "pause": pause, "cancel": cancel,
                "prog": prog, "bar": bar, "info": info}

    def _set_visuals(self, card, state):
        colors = {
            State.DOWNLOADING: ACCENT, State.CONNECTING: ACCENT,
            State.QUEUED: FG_DIM, State.PAUSED: YELLOW,
            State.RETRYING: ORANGE, State.COMPLETED: GREEN,
            State.FAILED: RED, State.CANCELLED: RED,
        }
        card["dot"].config(fg=colors.get(state, FG_DIM))
        bg = "#1E222D" if state in (State.COMPLETED, State.FAILED, State.CANCELLED) else BORDER
        card["frame"].config(highlightbackground=bg)

    def _upd_card(self, task):
        card = self.cards.get(task.id)
        if not card:
            return
        self._set_visuals(card, task.state)

        if task.state == State.PAUSED:
            card["title"].config(text=task.title[:42] or "Paused")
            card["info"].config(text="Paused", fg=YELLOW)
            return
        if task.state == State.RETRYING:
            card["title"].config(text=f"Retry {task.retries}/{task.max_retries}")
            card["info"].config(text=task.error[:46], fg=ORANGE)
            return
        if task.state == State.CONNECTING:
            card["title"].config(text="Connecting...")
            card["info"].config(text=task.host, fg=FG_DIM)
            return

        pct = task.progress / 100
        w = card["prog"].winfo_width()
        card["prog"].coords(card["bar"], 0, 0, max(w * pct, 2), 6)
        if task.title:
            card["title"].config(text=task.title[:42])

        parts = [f"{task.progress:.0f}%"]
        if task.speed > 0:
            parts.append(f"{fmt_size(int(task.speed))}/s")
        if task.filesize > 0 and task.downloaded > 0:
            rem = task.filesize - task.downloaded
            if rem > 0:
                parts.append(f"{fmt_size(rem)} left")
        if task.eta:
            parts.append(task.eta)
        card["info"].config(text="  \u00b7  ".join(parts), fg=FG_DIM)

    def _done_card(self, task):
        card = self.cards.get(task.id)
        if not card:
            return
        self._set_visuals(card, State.COMPLETED)
        w = card["prog"].winfo_width()
        card["prog"].coords(card["bar"], 0, 0, w, 6)
        card["prog"].itemconfig(card["bar"], fill=GREEN)

        actual = os.path.getsize(task.filename) if os.path.exists(task.filename) else 0
        valid, msg = self.engine.integrity.validate_file(task.filename, task.filesize)

        if valid:
            card["info"].config(text=f"Completed  \u00b7  {fmt_size(actual)}", fg=GREEN)
        else:
            card["info"].config(text=f"Error: {msg}", fg=RED)
        card["pause"].config(state=tk.DISABLED)
        card["cancel"].config(state=tk.DISABLED)
        self.engine.ui_updater.cleanup(task.id)
        if valid:
            self.history.add(task.title, task.filename, task.filesize)
            self._refresh_hist()

    def _err_card(self, task):
        card = self.cards.get(task.id)
        if not card:
            return
        self._set_visuals(card, State.FAILED)
        card["prog"].itemconfig(card["bar"], fill=RED)
        card["info"].config(text=task.error[:56], fg=RED)
        card["pause"].config(state=tk.DISABLED)
        self.engine.ui_updater.cleanup(task.id)

    def _toggle_pause(self, task):
        if task.state == State.PAUSED:
            task.resume()
        elif task.state in (State.DOWNLOADING, State.CONNECTING):
            task.pause()

    def _cancel_task(self, task):
        task.cancel()
        card = self.cards.get(task.id)
        if card:
            self._set_visuals(card, State.CANCELLED)
            card["prog"].itemconfig(card["bar"], fill=RED)
            card["info"].config(text="Cancelled", fg=RED)
            card["title"].config(text="Cancelled")
            card["pause"].config(state=tk.DISABLED)
            card["cancel"].config(state=tk.DISABLED)
        self.engine.ui_updater.cleanup(task.id)
