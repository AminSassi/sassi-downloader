import tkinter as tk
from tkinter import ttk, filedialog
import threading
import os
import sys
import yt_dlp
from core.enums import State, Priority
from core.engine import DownloadEngine
from core.history import AtomicHistory

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".sassi_history.json")

BG = "#0d1117"
BG_CARD = "#161b22"
BG_GLASS = "#1c2333"
BG_INPUT = "#21262d"
FG = "#e6edf3"
FG_DIM = "#7d8590"
FG_BRIGHT = "#f0f6fc"
ACCENT = "#58a6ff"
GREEN = "#3fb950"
YELLOW = "#d29922"
RED = "#f85149"
ORANGE = "#db6d28"
BORDER = "#30363d"
BORDER_DONE = "#1a3a2a"
BORDER_ACTIVE = "#1a2a3a"
BORDER_RETRY = "#3a3a1a"
BORDER_FAIL = "#3a1a1a"

STATE_COLORS = {
    State.DOWNLOADING: ACCENT,
    State.CONNECTING: ACCENT,
    State.QUEUED: FG_DIM,
    State.PAUSED: YELLOW,
    State.RETRYING: ORANGE,
    State.COMPLETED: GREEN,
    State.FAILED: RED,
    State.CANCELLED: RED,
}

STATE_BORDERS = {
    State.DOWNLOADING: BORDER_ACTIVE,
    State.CONNECTING: BORDER_ACTIVE,
    State.QUEUED: BORDER,
    State.PAUSED: BORDER_RETRY,
    State.RETRYING: BORDER_RETRY,
    State.COMPLETED: BORDER_DONE,
    State.FAILED: BORDER_FAIL,
    State.CANCELLED: BORDER_FAIL,
}


def fmt_size(b):
    if b < 1024:
        return f"{b}B"
    elif b < 1048576:
        return f"{b / 1024:.0f}KB"
    elif b < 1073741824:
        return f"{b / 1048576:.1f}MB"
    else:
        return f"{b / 1073741824:.2f}GB"


class SassiDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("Sassi Downloader")
        self.root.geometry("740x750")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.engine = DownloadEngine()
        self.history = AtomicHistory(HISTORY_FILE)
        self.formats = []
        self.cards = {}
        self._build()

    def _build(self):
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill=tk.X, padx=20, pady=(12, 2))
        tk.Label(hdr, text="Sassi", font=("Segoe UI", 22, "bold"),
                 fg=FG_BRIGHT, bg=BG).pack(side=tk.LEFT)
        tk.Label(hdr, text="Downloader", font=("Segoe UI", 22),
                 fg=FG_DIM, bg=BG).pack(side=tk.LEFT, padx=(4, 0))
        tk.Label(hdr, text="v4.2", font=("Segoe UI", 9),
                 fg=FG_DIM, bg=BG).pack(side=tk.LEFT, padx=(8, 0), pady=(6, 0))

        card = tk.Frame(self.root, bg=BG_GLASS, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill=tk.X, padx=20, pady=(8, 4))
        tk.Label(card, text="URL", font=("Segoe UI", 9, "bold"),
                 fg=FG_DIM, bg=BG_GLASS).pack(anchor=tk.W, padx=12, pady=(10, 2))
        row = tk.Frame(card, bg=BG_GLASS)
        row.pack(fill=tk.X, padx=12, pady=(0, 10))
        self.url_entry = tk.Entry(row, font=("Consolas", 10), bg=BG_INPUT, fg=FG,
                                   insertbackground=FG, relief=tk.FLAT,
                                   highlightbackground=BORDER, highlightthickness=1)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, ipadx=6)
        self.url_entry.bind("<Return>", lambda e: self.fetch())
        self.fetch_btn = tk.Button(row, text="Fetch", font=("Segoe UI", 9, "bold"),
                                    bg=ACCENT, fg=BG, relief=tk.FLAT, cursor="hand2",
                                    activebackground="#79c0ff", command=self.fetch)
        self.fetch_btn.pack(side=tk.RIGHT, padx=(6, 0), ipadx=10, ipady=5)

        opts = tk.Frame(self.root, bg=BG_GLASS, highlightbackground=BORDER, highlightthickness=1)
        opts.pack(fill=tk.X, padx=20, pady=4)
        orow = tk.Frame(opts, bg=BG_GLASS)
        orow.pack(fill=tk.X, padx=12, pady=8)

        tk.Label(orow, text="Quality", font=("Segoe UI", 9), fg=FG_DIM, bg=BG_GLASS).pack(side=tk.LEFT)
        self.quality_var = tk.StringVar(value="Best")
        self.q_menu = ttk.Combobox(orow, textvariable=self.quality_var, state="readonly",
                                    width=20, font=("Segoe UI", 9))
        self.q_menu.pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(orow, text="Priority", font=("Segoe UI", 9), fg=FG_DIM, bg=BG_GLASS).pack(side=tk.LEFT, padx=(12, 0))
        self.priority_var = tk.StringVar(value="Normal")
        self.p_menu = ttk.Combobox(orow, textvariable=self.priority_var, state="readonly",
                                    width=8, font=("Segoe UI", 9),
                                    values=["High", "Normal", "Low"])
        self.p_menu.pack(side=tk.LEFT, padx=(4, 0))

        tk.Label(orow, text="Save to", font=("Segoe UI", 9), fg=FG_DIM, bg=BG_GLASS).pack(side=tk.LEFT, padx=(12, 0))
        self.dl_path = self._default_path()
        self.folder_btn = tk.Button(orow, text=os.path.basename(self.dl_path),
                                     font=("Segoe UI", 9), bg=BG_INPUT, fg=ACCENT,
                                     relief=tk.FLAT, cursor="hand2", command=self.pick_folder)
        self.folder_btn.pack(side=tk.LEFT, padx=(4, 0), ipadx=4, ipady=1)

        self.dl_btn = tk.Button(orow, text="Download", font=("Segoe UI", 9, "bold"),
                                 bg=GREEN, fg=BG, relief=tk.FLAT, cursor="hand2",
                                 activebackground="#56d364", command=self.download)
        self.dl_btn.pack(side=tk.RIGHT, ipadx=12, ipady=3)

        self.status_label = tk.Label(self.root, text="", font=("Segoe UI", 9),
                                      fg=FG_DIM, bg=BG)
        self.status_label.pack(anchor=tk.W, padx=20, pady=(2, 0))

        tk.Label(self.root, text="Active Downloads", font=("Segoe UI", 10, "bold"),
                 fg=FG, bg=BG).pack(anchor=tk.W, padx=20, pady=(8, 2))

        dl_outer = tk.Frame(self.root, bg=BG)
        dl_outer.pack(fill=tk.BOTH, expand=True, padx=(20, 20))
        self.dl_canvas = tk.Canvas(dl_outer, bg=BG, highlightthickness=0)
        self.dl_scroll = tk.Scrollbar(dl_outer, orient=tk.VERTICAL, command=self.dl_canvas.yview)
        self.dl_frame = tk.Frame(self.dl_canvas, bg=BG)
        self.dl_frame.bind("<Configure>", lambda e: self.dl_canvas.configure(scrollregion=self.dl_canvas.bbox("all")))
        self.dl_canvas.create_window((0, 0), window=self.dl_frame, anchor=tk.NW)
        self.dl_canvas.configure(yscrollcommand=self.dl_scroll.set)
        self.dl_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.dl_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        hh = tk.Frame(self.root, bg=BG)
        hh.pack(fill=tk.X, padx=20, pady=(6, 0))
        tk.Label(hh, text="History", font=("Segoe UI", 10, "bold"), fg=FG, bg=BG).pack(side=tk.LEFT)
        tk.Button(hh, text="Clear", font=("Segoe UI", 8), fg=RED, bg=BG,
                  relief=tk.FLAT, cursor="hand2", command=self.clear_hist).pack(side=tk.RIGHT)

        hist_card = tk.Frame(self.root, bg=BG_GLASS, highlightbackground=BORDER, highlightthickness=1)
        hist_card.pack(fill=tk.BOTH, expand=True, padx=20, pady=(2, 12))
        self.hist_list = tk.Listbox(hist_card, bg=BG_GLASS, fg=FG_DIM,
                                     font=("Consolas", 8), highlightthickness=0,
                                     selectbackground=BORDER, selectforeground=FG,
                                     relief=tk.FLAT, bd=0)
        self.hist_list.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self.hist_list.bind("<Double-1>", self.open_hist)
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

    def pick_folder(self):
        f = filedialog.askdirectory(initialdir=self.dl_path)
        if f:
            self.dl_path = f
            self.folder_btn.config(text=os.path.basename(f))

    def _refresh_hist(self):
        self.hist_list.delete(0, tk.END)
        for i in self.history.items[:40]:
            size = fmt_size(i.get('size', 0)) if i.get('size', 0) > 0 else ""
            cs = i.get('checksum', '')[:8]
            label = f"  {i['title'][:40]}"
            if size:
                label += f"  {size}"
            if cs:
                label += f"  {cs}"
            self.hist_list.insert(tk.END, label)

    def open_hist(self, e):
        s = self.hist_list.curselection()
        if s:
            p = self.history.items[s[0]]['path']
            if os.path.exists(p):
                os.startfile(os.path.dirname(p))

    def clear_hist(self):
        self.history.clear()
        self._refresh_hist()

    def fetch(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        self.fetch_btn.config(text="...", state=tk.DISABLED)
        self.status_label.config(text="Fetching available qualities...", fg=ACCENT)
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
                self.root.after(0, self._fetch_ok)
            except Exception as e:
                self.root.after(0, lambda: self._fetch_err(str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _fetch_ok(self):
        self.fetch_btn.config(text="Fetch", state=tk.NORMAL)
        self.q_menu['values'] = [f[0] for f in self.formats]
        self.q_menu.current(0)
        self.status_label.config(text=f"Found {len(self.formats)} qualities", fg=GREEN)

    def _fetch_err(self, error=""):
        self.fetch_btn.config(text="Fetch", state=tk.NORMAL)
        self.status_label.config(text=f"Fetch failed: {error[:50]}", fg=RED)

    def download(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        if not self.formats:
            self.fetch()
            self.root.after(2000, lambda: self._retry_download(url))
            return
        i = self.q_menu.current()
        q = self.formats[i][1] if i >= 0 else "best"
        p = self.priority_var.get().lower()
        pri = Priority.HIGH if p == "high" else Priority.LOW if p == "low" else Priority.NORMAL
        task = DownloadTask(url, q, self.dl_path, pri)
        card = self._make_card(task)
        self.cards[task.id] = card
        self.engine.add(task)
        task._on_update = lambda t: self.root.after(0, self._upd_card, t)
        task._on_done = lambda t: self.root.after(0, self._done_card, t)
        task._on_error = lambda t: self.root.after(0, self._err_card, t)
        self.url_entry.delete(0, tk.END)

    def _retry_download(self, url):
        if not self.formats:
            return
        i = self.q_menu.current()
        q = self.formats[i][1] if i >= 0 else "best"
        p = self.priority_var.get().lower()
        pri = Priority.HIGH if p == "high" else Priority.LOW if p == "low" else Priority.NORMAL
        task = DownloadTask(url, q, self.dl_path, pri)
        card = self._make_card(task)
        self.cards[task.id] = card
        self.engine.add(task)
        task._on_update = lambda t: self.root.after(0, self._upd_card, t)
        task._on_done = lambda t: self.root.after(0, self._done_card, t)
        task._on_error = lambda t: self.root.after(0, self._err_card, t)
        self.url_entry.delete(0, tk.END)

    def _make_card(self, task):
        pri_labels = {Priority.HIGH: "HIGH", Priority.NORMAL: "", Priority.LOW: "LOW"}
        pri_text = pri_labels.get(task.priority, "")
        title_text = f"[{pri_text}] Queued..." if pri_text else "Queued..."

        c = tk.Frame(self.dl_frame, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        c.pack(fill=tk.X, padx=2, pady=2, ipady=4)

        top = tk.Frame(c, bg=BG_CARD)
        top.pack(fill=tk.X, padx=8, pady=(4, 0))

        state_dot = tk.Label(top, text="\u25cf", font=("Segoe UI", 8), fg=FG_DIM, bg=BG_CARD)
        state_dot.pack(side=tk.LEFT, padx=(0, 4))

        title = tk.Label(top, text=title_text, font=("Segoe UI", 9), fg=FG, bg=BG_CARD, anchor=tk.W)
        title.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ctrl = tk.Frame(top, bg=BG_CARD)
        ctrl.pack(side=tk.RIGHT)
        pause = tk.Button(ctrl, text="\u23f8", font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM,
                           relief=tk.FLAT, cursor="hand2", width=3,
                           command=lambda: self._toggle_pause(task))
        pause.pack(side=tk.LEFT)
        cancel = tk.Button(ctrl, text="\u2715", font=("Segoe UI", 9), bg=BG_CARD, fg=RED,
                            relief=tk.FLAT, cursor="hand2", width=3,
                            command=lambda: self._cancel_task(task))
        cancel.pack(side=tk.LEFT)

        prog = tk.Canvas(c, bg=BORDER, height=3, highlightthickness=0)
        prog.pack(fill=tk.X, padx=8, ipady=0)
        bar = prog.create_rectangle(0, 0, 0, 3, fill=ACCENT, width=0)

        info = tk.Label(c, text="Waiting...", font=("Consolas", 8), fg=FG_DIM, bg=BG_CARD, anchor=tk.W)
        info.pack(fill=tk.X, padx=8, pady=(3, 0))

        return {"frame": c, "title": title, "state_dot": state_dot,
                "pause": pause, "cancel": cancel,
                "prog": prog, "bar": bar, "info": info}

    def _set_state_visuals(self, card, state):
        color = STATE_COLORS.get(state, FG_DIM)
        border = STATE_BORDERS.get(state, BORDER)
        card["state_dot"].config(fg=color)
        card["frame"].config(highlightbackground=border)
        if state == State.COMPLETED:
            card["title"].config(fg=FG_DIM)
            card["info"].config(fg="#2a6e3f")
        elif state == State.FAILED or state == State.CANCELLED:
            card["title"].config(fg=FG_DIM)
        elif state == State.QUEUED:
            card["title"].config(fg=FG_DIM)
        else:
            card["title"].config(fg=FG)

    def _upd_card(self, task):
        card = self.cards.get(task.id)
        if not card:
            return

        self._set_state_visuals(card, task.state)

        if task.state == State.PAUSED:
            card["title"].config(text=f"{task.title[:44] or 'Paused'}")
            card["info"].config(text="Paused", fg=YELLOW)
            return

        if task.state == State.RETRYING:
            ecls = task.error_class.value if task.error_class else ""
            card["title"].config(text=f"Retry {task.retries}/{task.max_retries}")
            card["info"].config(text=f"{ecls}: {task.error[:40]}", fg=ORANGE)
            return

        if task.state == State.CONNECTING:
            card["title"].config(text=f"Connecting... ({task.host})")
            card["info"].config(text="Detecting server capabilities", fg=ACCENT)
            return

        pct = task.progress / 100
        w = card["prog"].winfo_width()
        card["prog"].coords(card["bar"], 0, 0, max(w * pct, 2), 3)

        if task.title:
            card["title"].config(text=task.title[:48])

        parts = [f"{task.progress:.1f}%"]
        if task.speed > 0:
            parts.append(f"{fmt_size(int(task.speed))}/s")
        if task.filesize > 0 and task.downloaded > 0:
            remaining = task.filesize - task.downloaded
            if remaining > 0:
                parts.append(f"{fmt_size(remaining)} left")
        if task.eta:
            parts.append(task.eta)

        conf = self.engine.server_cache.get_confidence(task.host)
        if conf < 0.5:
            parts.append("unstable")
        elif conf < 0.8:
            parts.append(f"conf:{conf:.0%}")

        share = self.engine.bandwidth.get_share(task.id)
        if share < 0.5:
            parts.append(f"share:{share:.0%}")

        card["info"].config(text="  \u00b7  ".join(parts), fg=FG_DIM)

    def _done_card(self, task):
        card = self.cards.get(task.id)
        if not card:
            return
        self._set_state_visuals(card, State.COMPLETED)

        w = card["prog"].winfo_width()
        card["prog"].coords(card["bar"], 0, 0, w, 3)
        card["prog"].itemconfig(card["bar"], fill=GREEN)

        actual_size = os.path.getsize(task.filename) if os.path.exists(task.filename) else 0
        size_ok, size_msg = self.engine.integrity.validate_file(task.filename, task.filesize)
        chunk_ok, chunk_msg = self.engine.chunk_verifier.validate_completion(task.id, actual_size)
        cs = self.engine.integrity.compute_checksum(task.filename)[:8] if os.path.exists(task.filename) else ""

        if not size_ok:
            card["info"].config(text=f"Corrupt: {size_msg}", fg=RED)
            card["title"].config(text=f"{task.title[:46]}")
            self._set_state_visuals(card, State.FAILED)
        elif not chunk_ok:
            card["info"].config(text=f"Chunk error: {chunk_msg}", fg=RED)
            card["title"].config(text=f"{task.title[:46]}")
            self._set_state_visuals(card, State.FAILED)
        else:
            card["info"].config(text=f"Done \u00b7 {fmt_size(actual_size)} \u00b7 {cs}", fg="#2a6e3f")
            card["title"].config(text=f"{task.title[:46]}")

        card["pause"].config(state=tk.DISABLED)
        card["cancel"].config(state=tk.DISABLED)
        self.engine.ui_updater.cleanup(task.id)
        if size_ok and chunk_ok:
            self.history.add(task.title, task.filename, task.filesize, cs)
            self._refresh_hist()

    def _err_card(self, task):
        card = self.cards.get(task.id)
        if not card:
            return
        self._set_state_visuals(card, State.FAILED)
        card["prog"].itemconfig(card["bar"], fill=RED)
        ecls = task.error_class.value if task.error_class else ""
        card["info"].config(text=f"Failed ({ecls}): {task.error[:50]}", fg=RED)
        card["title"].config(text=f"{task.title[:46] or 'Error'}")
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
            self._set_state_visuals(card, State.CANCELLED)
            card["prog"].itemconfig(card["bar"], fill=RED)
            card["info"].config(text="Cancelled", fg=RED)
            card["title"].config(text="Cancelled")
            card["pause"].config(state=tk.DISABLED)
            card["cancel"].config(state=tk.DISABLED)
        self.engine.ui_updater.cleanup(task.id)
