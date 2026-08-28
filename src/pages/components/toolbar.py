import os
import tkinter as tk
from typing import Any, ClassVar

from PIL import Image, ImageTk

_ICONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "assets",
    "icons",
)


class _Tooltip:
    """Tooltip nhỏ hiện bên cạnh nút khi hover."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event=None):
        if self.tip:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.attributes("-disabled", True)
        tk.Label(
            self.tip,
            text=self.text,
            font=("Segoe UI", 9),
            bg="#111827",
            fg="#ffffff",
            padx=8,
            pady=3,
        ).pack()
        self.tip.update_idletasks()
        tip_w = self.tip.winfo_reqwidth()
        screen_w = self.widget.winfo_screenwidth()

        # Ưu tiên hiện bên phải của thanh công cụ dọc
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
        y = self.widget.winfo_rooty() + (self.widget.winfo_height() - 25) // 2

        # Nếu không đủ chỗ bên phải (thanh sát lề phải màn hình) -> hiện bên trái thay vì đè lên nút
        if x + tip_w > screen_w - 4:
            x = self.widget.winfo_rootx() - tip_w - 8

        self.tip.geometry(f"+{x}+{y}")

    def _hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class ActionToolbar(tk.Toplevel):

    ICON_SIZE: ClassVar[int] = 15

    BTN_STYLE: ClassVar[dict[str, Any]] = {
        "width": 28,
        "height": 28,
        "bd": 0,
        "relief": "flat",
        "cursor": "hand2",
        "bg": "#ffffff",
        "activebackground": "#e5e7eb",
        "highlightthickness": 0,
    }

    # Màu nền của nút tool đang được chọn
    ACTIVE_BG: ClassVar[str] = "#bfdbfe"
    HOVER_BG: ClassVar[str] = "#eef2f7"

    # (file icon trong assets/icons, tên tool, tooltip) — nút chọn công cụ annotation
    TOOL_BUTTONS: ClassVar[list[tuple[str, str, str]]] = [
        ("pen.png", "pen", "Bút vẽ tự do"),
        ("text.png", "text", "Thêm chữ (Arial 12)"),
        ("rect.png", "rect", "Khung chữ nhật"),
        ("arrow.png", "arrow", "Mũi tên"),
    ]

    # (file icon trong assets/icons, action, tooltip) — nút hành động
    ACTION_BUTTONS: ClassVar[list[tuple[str, str, str]]] = [
        ("undo.png", "undo", "Hoàn tác (Ctrl+Z)"),
        ("copy.png", "copy", "Copy vào clipboard"),
        ("camera.png", "capture", "Lưu ảnh vùng chọn"),
        ("schedule.png", "schedule", "Chụp tự động theo lịch"),
        ("cancel.png", "cancel", "Hủy (Esc)"),
    ]

    def __init__(self, parent, rect, on_action, on_tool=None):
        """rect = (x1, y1, x2, y2) của vùng chọn theo toạ độ màn hình."""
        super().__init__(parent)

        self.on_action = on_action
        self.on_tool = on_tool
        self._active_tool = None
        self._tool_btns: dict[str, tk.Button] = {}
        # Giữ tham chiếu PhotoImage để tránh bị garbage-collected
        self._icon_cache: dict[str, ImageTk.PhotoImage] = {}

        # Ẩn cửa sổ trong lúc dựng nút để tránh nháy ở góc (0,0) trước khi
        # geometry() được đặt đúng vị trí cạnh vùng chọn.
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.transient(parent)
        self.configure(bg="#9ca3af")

        frame = tk.Frame(
            self,
            bg="#ffffff",
            padx=4,
            pady=4,
        )
        frame.pack(padx=1, pady=1)

        # --- Nhóm nút tool annotation (XẾP DỌC, nằm bên phải vùng chọn) ---
        for icon_file, tool, tip in self.TOOL_BUTTONS:
            btn = tk.Button(
                frame,
                image=self._load_icon(icon_file),
                command=lambda t=tool: self._toggle_tool(t),
                **self.BTN_STYLE,
            )
            btn.pack(side="top", pady=1)  # Xếp dọc, cách nhau bằng pady

            btn.bind("<Enter>", lambda e, t=tool: self._paint_tool(t, hover=True))
            btn.bind("<Leave>", lambda e, t=tool: self._paint_tool(t, hover=False))
            _Tooltip(btn, tip)
            self._tool_btns[tool] = btn

        # Vạch ngăn cách nằm ngang giữa nhóm tool và nhóm hành động (fill="x", height=1)
        tk.Frame(frame, bg="#d1d5db", height=1).pack(
            side="top", fill="x", padx=2, pady=4
        )

        # --- Nhóm nút hành động (XẾP DỌC, nằm bên phải vùng chọn) ---
        for icon_file, action, tip in self.ACTION_BUTTONS:
            btn = tk.Button(
                frame,
                image=self._load_icon(icon_file),
                command=lambda a=action: self._fire(a),
                **self.BTN_STYLE,
            )
            btn.pack(side="top", pady=1)  # Xếp dọc, cách nhau bằng pady

            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=self.HOVER_BG))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg="#ffffff"))
            _Tooltip(btn, tip)

        self.update_idletasks()

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        tw = self.winfo_reqwidth()
        th = self.winfo_reqheight()

        x1, y1, x2, y2 = rect

        # --- TÍNH TOÁN TỌA ĐỘ: NẰM DỌC BÊN PHẢI VÙNG CHỌN ---
        # Mặc định đặt bên phải vùng chọn, cách mép phải 8px. Canh lề trên bằng với y1 của vùng chọn.
        px = x2 + 8
        py = y1

        # Nếu không đủ chỗ bên phải -> Đẩy toolbar sang bên trái vùng chọn
        if px + tw > sw - 8:
            px = x1 - tw - 8

        # Đảm bảo trục X không bị tràn khỏi màn hình
        px = min(max(px, 8), sw - tw - 8)

        # Kiểm tra trục Y: Nếu toolbar dài hơn chiều cao màn hình tính từ y1
        if py + th > sh - 8:
            # Đẩy ngược toolbar lên sao cho mép dưới sát đáy màn hình (cách 8px)
            py = sh - th - 8

        # Đảm bảo trục Y không bị đẩy lên quá mép trên màn hình
        py = max(py, 8)

        self.geometry(f"+{px}+{py}")
        self.deiconify()
        self.lift()

    def _load_icon(self, filename: str) -> ImageTk.PhotoImage:
        """Nạp icon PNG từ assets/icons, resize về ICON_SIZE và cache lại."""
        if filename not in self._icon_cache:
            path = os.path.join(_ICONS_DIR, filename)
            img = Image.open(path).resize(
                (self.ICON_SIZE, self.ICON_SIZE), Image.Resampling.LANCZOS
            )
            self._icon_cache[filename] = ImageTk.PhotoImage(img)
        return self._icon_cache[filename]

    def _paint_tool(self, tool, hover):
        btn = self._tool_btns[tool]
        if tool == self._active_tool:
            btn.configure(bg=self.ACTIVE_BG)
        else:
            btn.configure(bg=self.HOVER_BG if hover else "#ffffff")

    def _toggle_tool(self, tool):
        self._active_tool = None if self._active_tool == tool else tool
        for t in self._tool_btns:
            self._paint_tool(t, hover=False)
        if self.on_tool:
            self.on_tool(self._active_tool)
        self.lift()

    def _fire(self, action):
        if action == "undo":
            self.on_action(action)
            self.lift()
            return
        self.destroy()
        self.on_action(action)
