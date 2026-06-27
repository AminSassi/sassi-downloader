import customtkinter as ctk
from tkinter import filedialog, messagebox  # noqa: F401
import os
import sys
import yt_dlp  # noqa: F401
from core.enums import State, Priority
from core.engine import DownloadEngine
from core.task import DownloadTask
from core.history import AtomicHistory
from core.utils import fmt_size, fmt_speed

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".sassi_history.json")
AUDIT_LOG = os.path.join(os.path.expanduser("~"), ".sassi_audit.log")

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

FG = "#333333"
FG_DIM = "#888888"
ACCENT = "#3B82F6"
GREEN = "#22C55E"
YELLOW = "#EAB308"
ORANGE = "#F97316"
RED = "#EF4444"
BORDER = "#E0E0E0"
BG_MAIN = "#F5F5F5"
BG_CARD = "#FFFFFF"
BG_SIDEBAR = "#FAFAFA"
BG_INPUT = "#F0F0F0"
ROW_ALT = "#FAFAFA"
ROW_HOVER = "#F0F4FF"
TAG_COLORS = {
    "Application": "#3B82F6",
    "Movie": "#EF4444",
    "Music": "#22C55E",
    "Picture": "#F59E0B",
    "Other": "#8B5CF6",
}


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self._show)
        self.widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(fg_color="#333333")
        label = ctk.CTkLabel(tw, text=self.text, font=ctk.CTkFont(size=11),
                              text_color="white", fg_color="#333333",
                              padx=8, pady=4, wraplength=400, anchor="w", justify="left")
        label.pack()

    def _hide(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class DownloadRow(ctk.CTkFrame):
    def __init__(self, master, task, on_pause, on_cancel, **kwargs):
        super().__init__(master, fg_color=BG_CARD, corner_radius=6, height=52, **kwargs)
        self.pack_propagate(False)
        self.task = task
        self.selected = False

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

        self.checkbox_var = ctk.BooleanVar(value=False)
        self.checkbox = ctk.CTkCheckBox(self, text="", variable=self.checkbox_var,
                                         width=20, checkbox_width=18, checkbox_height=18,
                                         fg_color=ACCENT, hover_color=ACCENT,
                                         border_color=BORDER)
        self.checkbox.pack(side="left", padx=(12, 8), pady=0)

        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.title_label = ctk.CTkLabel(info_frame, text="Queued...",
                                         font=ctk.CTkFont(size=12, weight="bold"),
                                         text_color=FG, anchor="w")
        self.title_label.pack(fill="x")
        self._title_tooltip = None

        self.status_label = ctk.CTkLabel(info_frame, text="Waiting...",
                                           font=ctk.CTkFont(size=10),
                                           text_color=FG_DIM, anchor="w")
        self.status_label.pack(fill="x")

        prog_frame = ctk.CTkFrame(self, fg_color="transparent", width=160)
        prog_frame.pack(side="left", padx=(0, 12))
        prog_frame.pack_propagate(False)

        self.progress_bar = ctk.CTkProgressBar(prog_frame, width=150, height=8,
                                                fg_color="#E8E8E8", progress_color=ACCENT,
                                                corner_radius=4)
        self.progress_bar.pack(pady=(8, 2))
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(prog_frame, text="0%",
                                            font=ctk.CTkFont(size=10),
                                            text_color=FG_DIM)
        self.progress_label.pack()

        self.speed_label = ctk.CTkLabel(self, text="",
                                         font=ctk.CTkFont(size=11),
                                         text_color=FG_DIM, width=80, anchor="e")
        self.speed_label.pack(side="left", padx=(0, 12))

        self.size_label = ctk.CTkLabel(self, text="",
                                        font=ctk.CTkFont(size=11),
                                        text_color=FG_DIM, width=70, anchor="e")
        self.size_label.pack(side="left", padx=(0, 8))

        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent", width=70)
        ctrl_frame.pack(side="right", padx=(0, 8))
        ctrl_frame.pack_propagate(False)

        btn_row = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        btn_row.pack(expand=True)

        self.pause_btn = ctk.CTkButton(btn_row, text="\u23f8", width=28, height=28,
                                        fg_color="transparent", hover_color="#F0F0F0",
                                        text_color=FG_DIM, font=ctk.CTkFont(size=14),
                                        command=lambda: on_pause(task))
        self.pause_btn.pack(side="left", padx=(0, 2))

        self.cancel_btn = ctk.CTkButton(btn_row, text="\u2715", width=28, height=28,
                                         fg_color="transparent", hover_color="#FEE2E2",
                                         text_color=RED, font=ctk.CTkFont(size=14),
                                         command=lambda: on_cancel(task))
        self.cancel_btn.pack(side="left")

        self._on_pause = on_pause
        self._on_cancel = on_cancel
        self._update_icons()

    def _update_icons(self):
        if self.task.state == State.PAUSED:
            self.pause_btn.configure(text="\u25b6")
        elif self.task.state in (State.COMPLETED, State.FAILED, State.CANCELLED):
            self.pause_btn.configure(text="\u23f8")
        else:
            self.pause_btn.configure(text="\u23f8")

    def _on_enter(self, event=None):
        if not self.selected:
            self.configure(fg_color=ROW_HOVER)

    def _on_leave(self, event=None):
        if not self.selected:
            self.configure(fg_color=BG_CARD)

    def update_task(self, task):
        self.task = task
        self._update_icons()

        if task.title:
            display_title = task.title[:50]
            self.title_label.configure(text=display_title)
            if len(task.title) > 50:
                if self._title_tooltip:
                    self._title_tooltip.text = task.title
                else:
                    self._title_tooltip = ToolTip(self.title_label, task.title)

        if task.state == State.DOWNLOADING:
            pct = task.progress / 100
            self.progress_bar.set(pct)
            self.progress_label.configure(text=f"{task.progress:.0f}%")
            self.progress_bar.configure(progress_color=ACCENT)
            self.status_label.configure(text="Downloading", text_color=ACCENT)
            self.speed_label.configure(text=fmt_speed(task.speed) if task.speed > 0 else "")
            self.size_label.configure(text=fmt_size(task.filesize) if task.filesize > 0 else "")
        elif task.state == State.COMPLETED:
            self.progress_bar.set(1)
            self.progress_bar.configure(progress_color=GREEN)
            self.progress_label.configure(text="100%")
            self.status_label.configure(text="Completed", text_color=GREEN)
            self.speed_label.configure(text="")
            actual = 0
            if task.filename and os.path.exists(task.filename):
                actual = os.path.getsize(task.filename)
            elif task.filesize > 0:
                actual = task.filesize
            self.size_label.configure(text=fmt_size(actual) if actual > 0 else "")
        elif task.state in (State.FAILED, State.CANCELLED):
            self.progress_bar.configure(progress_color=RED)
            self.status_label.configure(text=task.error[:40] if task.error else str(task.state.value).title(),
                                         text_color=RED)
            self.speed_label.configure(text="")
        elif task.state == State.PAUSED:
            self.status_label.configure(text="Paused", text_color=YELLOW)
            self.speed_label.configure(text="")
        elif task.state == State.RETRYING:
            self.status_label.configure(text=f"Retrying... ({task.retries}/{task.max_retries})", text_color=ORANGE)
            self.speed_label.configure(text="")
        elif task.state == State.CONNECTING:
            self.status_label.configure(text="Connecting...", text_color=ACCENT)
            self.speed_label.configure(text="")
        else:
            self.status_label.configure(text=str(task.state.value).title(), text_color=FG_DIM)
            self.speed_label.configure(text="")

        if task.state in (State.COMPLETED, State.FAILED, State.CANCELLED):
            self.pause_btn.configure(state="disabled")
            self.cancel_btn.configure(state="disabled")
        else:
            self.pause_btn.configure(state="normal")
            self.cancel_btn.configure(state="normal")


class SassiDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("Sassi Downloader")
        self.root.configure(fg_color=BG_MAIN)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        ww = min(950, sw - 100)
        wh = min(650, sh - 80)
        x = (sw - ww) // 2
        y = (sh - wh) // 2
        self.root.geometry(f"{ww}x{wh}+{x}+{y}")
        self.root.minsize(750, 500)

        self.engine = DownloadEngine()
        self.history = AtomicHistory(HISTORY_FILE)
        self.formats = []
        self.video_info = None
        self.dl_path = self._default_path()
        self.rows = {}
        self.tasks = []
        self.active_filter = "All"
        self.active_tag_filter = None
        self._search_after = None
        self._build()
        self._load_history()

    def audit_log(self, event_type, task_id=None, url="", folder="", outcome="", error=""):
        import time as _time
        import json
        entry = {
            "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%S"),
            "event": event_type,
            "task_id": task_id,
            "url": url[:200] if url else "",
            "folder": folder,
            "outcome": outcome,
        }
        if error:
            entry["error"] = error[:200]
        try:
            with open(AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _default_path(self):
        if sys.platform == "win32":
            import winreg
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
                p = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")[0]
                winreg.CloseKey(k)
                return p
            except Exception:
                pass
        return os.path.join(os.path.expanduser("~"), "Downloads")

    def _build(self):
        container = ctk.CTkFrame(self.root, fg_color=BG_MAIN)
        container.pack(fill="both", expand=True)

        self.sidebar = ctk.CTkFrame(container, fg_color=BG_SIDEBAR, width=200, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        content = ctk.CTkFrame(container, fg_color=BG_MAIN)
        content.pack(side="left", fill="both", expand=True)

        self._build_sidebar()
        self._build_content(content)

    def _build_sidebar(self):
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=16, pady=(20, 24))

        ctk.CTkLabel(logo_frame, text="SASSI",
                      font=ctk.CTkFont(size=20, weight="bold"),
                      text_color=ACCENT, anchor="w").pack(anchor="w")

        tasks_header = ctk.CTkLabel(self.sidebar, text="Tasks",
                                      font=ctk.CTkFont(size=11, weight="bold"),
                                      text_color=FG_DIM, anchor="w")
        tasks_header.pack(fill="x", padx=16, pady=(0, 4))

        self.sidebar_items = {}
        task_filters = [
            ("\u2630", "All"),
            ("\u25b6", "Running"),
            ("\u23f8", "Suspended"),
            ("\u2713", "Complete"),
            ("\u2717", "Incomplete"),
        ]
        for icon, label in task_filters:
            item = SidebarItem(self.sidebar, icon, label, active=(label == "All"))
            item.pack(fill="x")
            item.on_click = self._filter_changed
            self.sidebar_items[label] = item

        tags_header = ctk.CTkLabel(self.sidebar, text="Tags",
                                     font=ctk.CTkFont(size=11, weight="bold"),
                                     text_color=FG_DIM, anchor="w")
        tags_header.pack(fill="x", padx=16, pady=(16, 4))

        self.tag_items = {}
        all_tag = SidebarItem(self.sidebar, "", "All Tags", active=True)
        all_tag.pack(fill="x")
        all_tag.on_click = self._tag_changed
        self.tag_items["All Tags"] = all_tag

        for tag, color in TAG_COLORS.items():
            item = SidebarItem(self.sidebar, "", tag, tag_color=color)
            item.pack(fill="x")
            item.on_click = self._tag_changed
            self.tag_items[tag] = item

    def _build_content(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 0))

        left_header = ctk.CTkFrame(header, fg_color="transparent")
        left_header.pack(side="left")

        self.filter_label = ctk.CTkLabel(left_header, text="All",
                                           font=ctk.CTkFont(size=18, weight="bold"),
                                           text_color=FG)
        self.filter_label.pack(side="left")

        self.count_label = ctk.CTkLabel(left_header, text="0",
                                          font=ctk.CTkFont(size=18, weight="bold"),
                                          text_color=FG_DIM)
        self.count_label.pack(side="left", padx=(8, 0))

        search_frame = ctk.CTkFrame(header, fg_color="transparent")
        search_frame.pack(side="left", padx=(20, 0))

        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="Search",
                                          width=200, height=32,
                                          fg_color=BG_CARD, border_color=BORDER,
                                          text_color=FG, font=ctk.CTkFont(size=12))
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", self._on_search)

        right_header = ctk.CTkFrame(header, fg_color="transparent")
        right_header.pack(side="right")

        btn_style = {"width": 32, "height": 32, "corner_radius": 6,
                      "fg_color": BG_CARD, "hover_color": "#E8E8E8",
                      "border_width": 1, "border_color": BORDER}

        ctk.CTkButton(right_header, text="+", font=ctk.CTkFont(size=16, weight="bold"),
                       text_color=ACCENT, command=self._add_task, **btn_style).pack(side="left", padx=(0, 4))

        ctk.CTkButton(right_header, text="\u2715", font=ctk.CTkFont(size=12),
                       text_color=RED, command=self._delete_selected, **btn_style).pack(side="left", padx=(0, 4))

        ctk.CTkButton(right_header, text="\u21bb", font=ctk.CTkFont(size=14),
                       text_color=FG_DIM, command=self._refresh_view, **btn_style).pack(side="left")

        sep = ctk.CTkFrame(parent, fg_color=BORDER, height=1)
        sep.pack(fill="x", padx=20, pady=(12, 0))

        table_header = ctk.CTkFrame(parent, fg_color="transparent", height=36)
        table_header.pack(fill="x", padx=20, pady=(8, 0))
        table_header.pack_propagate(False)

        ctk.CTkLabel(table_header, text="", width=28).pack(side="left")
        ctk.CTkLabel(table_header, text="Filename",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=FG_DIM, anchor="w").pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(table_header, text="Status",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=FG_DIM, width=160, anchor="w").pack(side="left")
        ctk.CTkLabel(table_header, text="Speed",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=FG_DIM, width=80, anchor="e").pack(side="left", padx=(0, 12))
        ctk.CTkLabel(table_header, text="Size",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=FG_DIM, width=70, anchor="e").pack(side="left", padx=(0, 8))

        list_frame = ctk.CTkFrame(parent, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=20, pady=(8, 16))

        self.scrollable = ctk.CTkScrollableFrame(list_frame, fg_color="transparent",
                                                   scrollbar_fg_color="transparent",
                                                   scrollbar_button_color=BORDER,
                                                   scrollbar_button_hover_color="#CCCCCC")
        self.scrollable.pack(fill="both", expand=True)

        self._show_empty()

    def _show_empty(self):
        for w in self.scrollable.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.scrollable,
                      text="No downloads yet\nClick + to add a new download",
                      font=ctk.CTkFont(size=13),
                      text_color=FG_DIM).pack(pady=60)

    def _load_history(self):
        for item in self.history.items[:5]:
            task = DownloadTask(item.get('path', ''), "best", "", Priority.NORMAL)
            task.title = item.get('title', 'Unknown')
            task.state = State.COMPLETED
            task.filesize = item.get('size', 0)
            task.filename = item.get('path', '')
            task.progress = 100
            task.tag = "Other"
            self.tasks.append(task)
        self._refresh_view()

    def _filter_changed(self, filter_name):
        self.active_filter = filter_name
        self.filter_label.configure(text=filter_name)
        for name, item in self.sidebar_items.items():
            item.set_active(name == filter_name)
        self._refresh_view()

    def _tag_changed(self, tag_name):
        if tag_name == "All Tags":
            self.active_tag_filter = None
        else:
            self.active_tag_filter = tag_name
        for name, item in self.tag_items.items():
            item.set_active(name == tag_name)
        self._refresh_view()

    def _get_filtered_tasks(self):
        tasks = self.tasks

        if self.active_filter == "Running":
            tasks = [t for t in tasks if t.state in (State.DOWNLOADING, State.CONNECTING, State.QUEUED)]
        elif self.active_filter == "Suspended":
            tasks = [t for t in tasks if t.state in (State.PAUSED, State.RETRYING)]
        elif self.active_filter == "Complete":
            tasks = [t for t in tasks if t.state == State.COMPLETED]
        elif self.active_filter == "Incomplete":
            tasks = [t for t in tasks if t.state in (State.FAILED, State.CANCELLED)]

        if self.active_tag_filter:
            tasks = [t for t in tasks if getattr(t, 'tag', None) == self.active_tag_filter]

        search = self.search_entry.get().strip().lower() if hasattr(self, "search_entry") and self.search_entry.winfo_exists() else ""
        if search:
            tasks = [t for t in tasks if search in (t.title or "").lower() or search in t.url.lower()]

        return tasks

    def _refresh_view(self):
        filtered = self._get_filtered_tasks()

        for w in self.scrollable.winfo_children():
            w.destroy()
        self.rows.clear()

        if not filtered:
            ctk.CTkLabel(self.scrollable,
                          text="No downloads found",
                          font=ctk.CTkFont(size=13),
                          text_color=FG_DIM).pack(pady=60)
        else:
            for i, task in enumerate(filtered):
                row = DownloadRow(self.scrollable, task,
                                   on_pause=self._toggle_pause,
                                   on_cancel=self._cancel_task)
                row.pack(fill="x", pady=(0, 2))
                if i % 2 == 1:
                    row.configure(fg_color=ROW_ALT)
                self.rows[task.id] = row
                row.update_task(task)

        self.count_label.configure(text=str(len(filtered)))

        counts = {
            "All": len(self.tasks),
            "Running": len([t for t in self.tasks if t.state in (State.DOWNLOADING, State.CONNECTING, State.QUEUED)]),
            "Suspended": len([t for t in self.tasks if t.state in (State.PAUSED, State.RETRYING)]),
            "Complete": len([t for t in self.tasks if t.state == State.COMPLETED]),
            "Incomplete": len([t for t in self.tasks if t.state in (State.FAILED, State.CANCELLED)]),
        }
        for name, item in self.sidebar_items.items():
            item.set_count(counts.get(name, 0))

    def _on_search(self, event=None):
        if self._search_after:
            self.root.after_cancel(self._search_after)
        self._search_after = self.root.after(150, self._refresh_view)

    def _add_task(self):
        self._dialog = AddTaskDialog(self.root, self.dl_path, self._handle_new_task)

    def _handle_new_task(self, result):
        url = result["url"]
        save_to = result["save_to"] or self.dl_path
        if not os.path.isdir(save_to):
            try:
                os.makedirs(save_to, exist_ok=True)
            except Exception:
                save_to = self.dl_path
        self.dl_path = save_to
        quality = result.get("quality", "best")
        rename = result.get("rename", "")
        tag = result.get("tag", "Other")
        splits = result.get("splits", 32)

        task = DownloadTask(url, quality, save_to, Priority.NORMAL)
        task.tag = tag
        task.rename = rename
        task.splits = splits
        task._on_update = lambda t: self.root.after(0, self._update_task, t)
        task._on_done = lambda t: self.root.after(0, self._done_task, t)
        task._on_error = lambda t: self.root.after(0, self._error_task, t)
        self.tasks.append(task)
        self.engine.add(task)
        task._on_update = lambda t: self.root.after(0, self._update_task, t)
        task._on_done = lambda t: self.root.after(0, self._done_task, t)
        task._on_error = lambda t: self.root.after(0, self._error_task, t)
        self.audit_log("DOWNLOAD_START", task.id, url, save_to, "queued")
        self._refresh_view()

    def _update_task(self, task):
        row = self.rows.get(task.id)
        if row:
            row.update_task(task)
        else:
            self._refresh_view()

    def _done_task(self, task):
        row = self.rows.get(task.id)
        if row:
            row.update_task(task)
        self.engine.ui_updater.cleanup(task.id)
        self.history.add(task.title, task.filename, task.filesize)
        self.audit_log("DOWNLOAD_COMPLETE", task.id, task.url, task.folder, "success")
        self._refresh_view()

    def _error_task(self, task):
        row = self.rows.get(task.id)
        if row:
            row.update_task(task)
        self.engine.ui_updater.cleanup(task.id)
        self.audit_log("DOWNLOAD_FAILED", task.id, task.url, task.folder, "error", task.error[:100])
        self._refresh_view()

    def _toggle_pause(self, task):
        if task.state == State.PAUSED:
            task.resume()
        elif task.state in (State.DOWNLOADING, State.CONNECTING):
            task.pause()
        row = self.rows.get(task.id)
        if row:
            row.update_task(task)

    def _cancel_task(self, task):
        if task.state in (State.COMPLETED, State.FAILED, State.CANCELLED):
            return
        if task.state == State.DOWNLOADING and (task.progress > 5 or task.downloaded > 5 * 1048576):
            if not messagebox.askyesno("Cancel Download",
                                        f"Cancel '{task.title[:40]}'?\n\n"
                                        f"Progress: {task.progress:.0f}%\n"
                                        f"Downloaded: {fmt_size(task.downloaded)}"):
                return
        self.audit_log("DOWNLOAD_CANCEL", task.id, task.url, task.folder, "cancelled")
        task.cancel()
        row = self.rows.get(task.id)
        if row:
            row.update_task(task)
        self.engine.ui_updater.cleanup(task.id)

    def _delete_selected(self):
        checked = [tid for tid, row in self.rows.items() if row.checkbox_var.get()]
        if not checked:
            checked = [t.id for t in self.tasks if t.state in (State.COMPLETED, State.FAILED, State.CANCELLED)]
        to_remove = [t for t in self.tasks if t.id in checked and t.state in (State.COMPLETED, State.FAILED, State.CANCELLED)]
        if not to_remove:
            return
        msg = f"Remove {len(to_remove)} completed download(s) from the list?\n\nFiles on disk will NOT be deleted."
        if not messagebox.askyesno("Confirm Delete", msg):
            return
        for task in to_remove:
            self.audit_log("DELETE", task.id, task.url, task.folder, "removed_from_list")
            self.tasks.remove(task)
            self.rows.pop(task.id, None)
        self._refresh_view()
