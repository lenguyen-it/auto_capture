import tkinter as tk


class ActionToolbar(tk.Toplevel):

    BTN_STYLE = {
        "font": ("Segoe UI Emoji", 10),
        "width": 2,
        "height": 1,
        "bd": 0,
        "relief": "flat",
        "cursor": "hand2",
        "bg": "#ffffff",
        "activebackground": "#e5e7eb",
        "highlightthickness": 0,
    }

    def __init__(self, parent, x, y, on_action):
        super().__init__(parent)

        self.on_action = on_action

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#d1d5db")

        frame = tk.Frame(
            self,
            bg="#ffffff",
            padx=4,
            pady=4,
        )
        frame.pack(padx=1, pady=1)

        buttons = [
            ("📷", "capture"),
            ("🕒", "schedule"),
            ("✕", "cancel"),
        ]

        for icon, action in buttons:
            btn = tk.Button(
                frame,
                text=icon,
                command=lambda a=action: self._fire(a),
                **self.BTN_STYLE,
            )
            btn.pack(fill="x", padx=2)

            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg="#f3f4f6"))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg="#ffffff"))

        self.update_idletasks()

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        tw = self.winfo_reqwidth()
        th = self.winfo_reqheight()

        px = min(x + 12, sw - tw - 8)
        py = min(y, sh - th - 8)
        py = max(py, 8)

        self.geometry(f"+{px}+{py}")

    def _fire(self, action):
        self.destroy()
        self.on_action(action)
