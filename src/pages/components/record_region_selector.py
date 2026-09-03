import tkinter as tk

from PIL import ImageEnhance, ImageTk

# ---------------------------------------------------------------------------
# Overlay chọn vùng (dùng riêng cho ghi màn hình): chỉ kéo chọn vùng, không có
# annotation/toolbar chụp ảnh như RegionSelector. Enter để xác nhận, Esc để huỷ.
# ---------------------------------------------------------------------------


class RecordRegionSelector(tk.Toplevel):
    def __init__(self, parent, screenshot, on_confirm=None):
        super().__init__(parent)
        self.result = None
        self.on_confirm = on_confirm
        self._screenshot = screenshot

        self._start_x = 0
        self._start_y = 0
        self._sel: list[int] | None = None
        self._selection_item = None
        self._size_text = None
        self._crop_photo = None
        self._mask_items: list[int] = []
        self._dragging = False

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        try:
            self.attributes("-fullscreen", True)
        except tk.TclError:
            self.geometry(f"{screen_w}x{screen_h}+0+0")

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#000000")
        self.geometry(f"{screen_w}x{screen_h}+0+0")

        self.canvas = tk.Canvas(self, cursor="cross", bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        dark = ImageEnhance.Brightness(self._screenshot).enhance(0.55)
        self._bg_dark_photo = ImageTk.PhotoImage(dark)
        self._dark_item = self.canvas.create_image(0, 0, anchor="nw", image=self._bg_dark_photo)

        self._show_hint("Kéo chọn vùng ghi hình  |  Enter: xác nhận   Esc: huỷ")

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._on_cancel)
        self.bind("<Return>", self._on_confirm_key)

        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_force()

    def _show_hint(self, text):
        x_center = self.winfo_screenwidth() // 2
        text_id = self.canvas.create_text(
            x_center, 29, text=text, fill="white", font=("Segoe UI", 12, "bold")
        )
        bbox = self.canvas.bbox(text_id)
        bg_id = self.canvas.create_rectangle(
            bbox[0] - 14, bbox[1] - 8, bbox[2] + 14, bbox[3] + 8,
            fill="#111827", outline="#ffffff", width=1,
        )
        self.canvas.tag_raise(text_id, bg_id)

    def _clear_draw(self):
        for item in self._mask_items:
            self.canvas.delete(item)
        self._mask_items.clear()
        if self._selection_item:
            self.canvas.delete(self._selection_item)
            self._selection_item = None
        if self._size_text:
            self.canvas.delete(self._size_text)
            self._size_text = None

    def _draw_mask(self, x1, y1, x2, y2):
        self._clear_draw()
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1

        w, h = x2 - x1, y2 - y1
        if w >= 1 and h >= 1:
            crop = self._screenshot.crop((x1, y1, x2, y2))
            self._crop_photo = ImageTk.PhotoImage(crop)
            crop_item = self.canvas.create_image(x1, y1, anchor="nw", image=self._crop_photo)
            self.canvas.tag_raise(crop_item, self._dark_item)
            self._mask_items.append(crop_item)

        self._selection_item = self.canvas.create_rectangle(
            x1, y1, x2, y2, fill="", outline="#e53935", width=2, dash=(2, 3)
        )

        self._size_text = self.canvas.create_text(
            x1 + 4, max(y1 - 6, 16), text=f"{w} x {h}",
            fill="white", font=("Segoe UI", 10, "bold"), anchor="sw",
        )

    def _on_press(self, event):
        self._dragging = True
        self._start_x = event.x_root
        self._start_y = event.y_root
        self._draw_mask(event.x, event.y, event.x, event.y)

    def _on_drag(self, event):
        if not self._dragging:
            return
        cx1 = self._start_x - self.winfo_rootx()
        cy1 = self._start_y - self.winfo_rooty()
        self._draw_mask(cx1, cy1, event.x, event.y)

    def _on_release(self, event):
        self._dragging = False
        x1, y1 = self._start_x, self._start_y
        x2, y2 = event.x_root, event.y_root

        if abs(x2 - x1) < 10 or abs(y2 - y1) < 10:
            return

        dx, dy = self.winfo_rootx(), self.winfo_rooty()
        self._sel = [
            min(x1, x2) - dx, min(y1, y2) - dy,
            max(x1, x2) - dx, max(y1, y2) - dy,
        ]

    def _on_confirm_key(self, _event=None):
        if not self._sel:
            return
        x1, y1, x2, y2 = self._sel
        dx, dy = self.winfo_rootx(), self.winfo_rooty()
        self.result = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        self.withdraw()
        self.update_idletasks()
        if self.on_confirm:
            self.on_confirm(self.result)
        self.destroy()

    def _on_cancel(self, _event=None):
        self.destroy()
