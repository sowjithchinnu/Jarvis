"""
Minimal chat-window UI in Tkinter.

Runs the agent in a background thread so API calls and
Playwright actions never freeze the window. Confirmation dialogs are
shown on the main thread (required by Tkinter) while the worker thread
blocks on a threading.Event waiting for the answer.
"""
import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog


class ChatUI:
    def __init__(self, root, agent):
        self.root = root
        self.agent = agent
        self.root.title("Jarvis - Web Agent")
        self.root.geometry("640x560")

        self.chat_log = scrolledtext.ScrolledText(root, state="disabled", wrap="word")
        self.chat_log.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        self.status_var = tk.StringVar(value="Ready.")
        status_label = tk.Label(root, textvariable=self.status_var, anchor="w", fg="gray")
        status_label.pack(fill="x", padx=8)

        input_frame = tk.Frame(root)
        input_frame.pack(fill="x", padx=8, pady=8)

        self.entry = tk.Entry(input_frame)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send())

        send_btn = tk.Button(input_frame, text="Send", command=self.send)
        send_btn.pack(side="left", padx=(6, 0))

        self._ui_queue = queue.Queue()
        self._agent_queue = queue.Queue()
        self._agent_thread = threading.Thread(target=self._agent_worker, daemon=True)
        self._agent_thread.start()
        self.root.after(100, self._drain_ui_queue)

    # ---------- chat log helpers ----------

    def _append(self, who: str, text: str):
        self.chat_log.configure(state="normal")
        self.chat_log.insert("end", f"{who}: {text}\n\n")
        self.chat_log.configure(state="disabled")
        self.chat_log.see("end")

    def _drain_ui_queue(self):
        """Runs on the main thread; applies any pending UI updates from workers."""
        try:
            while True:
                action, payload = self._ui_queue.get_nowait()
                if action == "append":
                    who, text = payload
                    self._append(who, text)
                elif action == "status":
                    self.status_var.set(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_ui_queue)

    # ---------- callbacks passed into Agent (may be called from worker thread) ----------

    def post_status(self, text: str):
        self._ui_queue.put(("status", text))

    def confirm_action(self, description: str, require_phrase: bool = False) -> bool:
        """
        Called from the worker thread. Blocks until the user answers,
        using a threading.Event since Tkinter dialogs must run on main thread.
        """
        result_holder = {}
        event = threading.Event()

        def ask():
            if require_phrase:
                phrase = simpledialog.askstring(
                    "Confirm form submission",
                    f"{description}\n\nType SUBMIT to continue:",
                    parent=self.root,
                )
                result_holder["approved"] = phrase == "SUBMIT"
            else:
                result_holder["approved"] = messagebox.askyesno(
                    "Confirm action", f"{description}\n\nProceed?"
                )
            event.set()

        self.root.after(0, ask)
        event.wait()
        return result_holder.get("approved", False)

    # ---------- sending messages ----------

    def send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._append("You", text)
        self.status_var.set("Thinking...")
        self._agent_queue.put(text)

    def _agent_worker(self):
        while True:
            text = self._agent_queue.get()
            if text is None:
                self.agent.close()
                return
            try:
                reply = self.agent.chat(text)
            except Exception as e:
                reply = f"[Error] {e}"
            self._ui_queue.put(("append", ("Jarvis", reply)))
            self._ui_queue.put(("status", "Ready."))

    def close(self):
        self._agent_queue.put(None)
