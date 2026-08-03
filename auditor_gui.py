"""
JSON-PDF COMPARE TOOL — desktop GUI

A lightweight wrapper around auditor.py's PDF/JSON audit engine, built with
customtkinter so the whole thing can be packaged into a standalone macOS
.app (see setup.py / BUILD.md) that runs without a separate Python install.

The GUI never re-implements the matching/reporting logic — it only drives
auditor.audit_directory_recursively() on a background thread and surfaces
its print() output and results in the window.
"""

import os
import queue
import subprocess
import sys
import threading
import traceback

from tkinter import filedialog
import customtkinter as ctk

import auditor


class _QueueWriter:
    """
    A minimal file-like object that pushes writes onto a thread-safe
    queue instead of stdout. auditor.py's functions run on a background
    thread (so the GUI doesn't freeze during a long audit); Tkinter widgets
    may only be touched from the main thread, so we can't have that
    background thread write directly into the log box. Redirecting
    sys.stdout to this queue during the run lets us reuse auditor.py's
    existing print() calls unmodified — the main thread then drains the
    queue and appends to the log box.
    """

    def __init__(self, q):
        self._queue = q

    def write(self, text):
        if text:
            self._queue.put(text)

    def flush(self):
        pass


class AuditorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title("JSON-PDF COMPARE TOOL")
        self.geometry("760x620")
        self.minsize(640, 480)

        self.data_dir = None
        self.reports_dir = None
        self.log_queue = queue.Queue()
        self.last_results = None
        self.last_report_path = None

        self._build_layout()
        self._poll_log_queue()

    # --- Layout ------------------------------------------------------------

    def _build_layout(self):
        header = ctk.CTkLabel(
            self, text="📊 JSON-PDF COMPARE TOOL", font=ctk.CTkFont(size=22, weight="bold")
        )
        header.pack(pady=(20, 4))

        subtitle = ctk.CTkLabel(
            self,
            text="Compare PDF/JSON document pairs and generate an audit report.",
            text_color="gray60",
        )
        subtitle.pack(pady=(0, 16))

        folder_frame = ctk.CTkFrame(self, fg_color="transparent")
        folder_frame.pack(fill="x", padx=24, pady=(0, 8))

        self.folder_label = ctk.CTkLabel(
            folder_frame, text="No folder selected", anchor="w", text_color="gray60"
        )
        self.folder_label.pack(side="left", fill="x", expand=True)

        select_btn = ctk.CTkButton(
            folder_frame, text="Select Data Folder…", width=170, command=self._select_folder
        )
        select_btn.pack(side="right")

        self.run_btn = ctk.CTkButton(
            self, text="▶  Run Audit", height=40, state="disabled", command=self._start_audit
        )
        self.run_btn.pack(fill="x", padx=24, pady=(4, 16))

        self.log_box = ctk.CTkTextbox(
            self, wrap="word", font=ctk.CTkFont(family="Menlo", size=12)
        )
        self.log_box.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        self.log_box.configure(state="disabled")

        result_frame = ctk.CTkFrame(self, fg_color="transparent")
        result_frame.pack(fill="x", padx=24, pady=(0, 20))

        self.open_report_btn = ctk.CTkButton(
            result_frame, text="Open Report", state="disabled", command=self._open_report
        )
        self.open_report_btn.pack(side="left", padx=(0, 8))

        self.reveal_btn = ctk.CTkButton(
            result_frame,
            text="Reveal Reports Folder",
            state="disabled",
            command=self._reveal_reports_folder,
        )
        self.reveal_btn.pack(side="left")

        self.status_label = ctk.CTkLabel(result_frame, text="", text_color="gray60")
        self.status_label.pack(side="right")

    # --- Folder selection ----------------------------------------------------

    def _select_folder(self):
        chosen = filedialog.askdirectory(title="Select the folder containing PDF/JSON pairs")
        if not chosen:
            return

        self.data_dir = chosen
        # Reports go to a sibling folder named "<FolderName>_reports", so
        # output never gets mixed into whatever the user selected and the
        # location stays predictable regardless of what that folder is called.
        self.reports_dir = f"{chosen.rstrip('/')}_reports"

        self.folder_label.configure(text=chosen, text_color=("black", "white"))
        self.run_btn.configure(state="normal")
        self._clear_log()
        self._log(f"Selected data folder: {chosen}\n")
        self._log(f"Reports will be saved to: {self.reports_dir}\n\n")

    # --- Running the audit ---------------------------------------------------

    def _start_audit(self):
        if not self.data_dir:
            return

        self.run_btn.configure(state="disabled", text="Running…")
        self.open_report_btn.configure(state="disabled")
        self.reveal_btn.configure(state="disabled")
        self.status_label.configure(text="")
        self._clear_log()

        thread = threading.Thread(target=self._run_audit_thread, daemon=True)
        thread.start()

    def _run_audit_thread(self):
        os.makedirs(self.reports_dir, exist_ok=True)

        writer = _QueueWriter(self.log_queue)
        original_stdout = sys.stdout
        sys.stdout = writer
        try:
            results, report_path = auditor.audit_directory_recursively(
                self.data_dir, self.reports_dir
            )
        except Exception:
            traceback.print_exc()
            results, report_path = [], None
        finally:
            sys.stdout = original_stdout

        self.log_queue.put(("__DONE__", results, report_path))

    def _poll_log_queue(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__DONE__":
                    _, results, report_path = item
                    self._on_audit_finished(results, report_path)
                else:
                    self._log(item)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_log_queue)

    def _on_audit_finished(self, results, report_path):
        self.run_btn.configure(state="normal", text="▶  Run Audit")
        self.last_results = results
        self.last_report_path = report_path

        if report_path:
            total_matches = sum(len(r["matches"]) for r in results)
            total_unverifiable = sum(len(r["unverifiable"]) for r in results)
            total_mismatches = sum(len(r["mismatches"]) for r in results)
            self.status_label.configure(
                text=(
                    f"{len(results)} doc(s)  ·  ✅ {total_matches}  ·  "
                    f"🟡 {total_unverifiable}  ·  ❌ {total_mismatches}"
                )
            )
            self.open_report_btn.configure(state="normal")
            self.reveal_btn.configure(state="normal")
        else:
            self.status_label.configure(text="No report generated — see log above.")

    # --- Log helpers -----------------------------------------------------

    def _log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    # --- Report actions ----------------------------------------------------

    def _open_report(self):
        if self.last_report_path and os.path.exists(self.last_report_path):
            subprocess.run(["open", self.last_report_path])

    def _reveal_reports_folder(self):
        if self.reports_dir and os.path.exists(self.reports_dir):
            subprocess.run(["open", self.reports_dir])


def main():
    app = AuditorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
