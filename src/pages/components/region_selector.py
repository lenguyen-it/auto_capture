import tkinter as tk

from PIL import ImageEnhance, ImageTk

from src.pages.components.annotations import AnnotationLayer
from src.pages.components.toolbar import ActionToolbar

# ---------------------------------------------------------------------------
# Overlay chọn vùng (toàn màn hình)
# ---------------------------------------------------------------------------


class RegionSelector(tk.Toplevel):
    """
    Cửa sổ overlay fullscreen để kéo chọn vùng chụp.
    Trong lúc kéo, khung chọn sẽ hiện trực tiếp.
    Nền overlay là ảnh màn hình "đóng băng" để có thể
    vẽ annotation (text, hình chữ nhật, mũi tên, bút) rõ nét lên vùng chọn.
    """

    def __init__(self, parent, screenshot, on_confirm=None):
        super().__init__(parent)
        self.result = None
        self.on_confirm = on_confirm
        self._screenshot = screenshot

        self._start_x = 0
        self._start_y = 0
        self._selection_item = None
        self._size_text = None
        self._toolbar = None
        self._mask_items = []
        self._hint_bg_id = None
        self._hint_text_id = None
        self._drag_hint_bg_id = None
        self._drag_hint_text_id = None

        # Vùng chọn hiện tại theo toạ độ canvas + trạng thái kéo
        # _drag_mode: None | "select" | "move" | "l"/"r"/"t"/"b"/"tl"/"tr"/"bl"/"br"
        self._sel: list[int] | None = None
        self._drag_mode: str | None = None
        self._drag_origin: tuple[int, int, int, int, int, int] | None = None

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        try:
            self.attributes("-fullscreen", True)
        except tk.TclError:
            self.geometry(f"{screen_w}x{screen_h}+0+0")

        self.overrideredirect(True)
        self.attributes("-alpha", 1.0)
        self.attributes("-topmost", True)
        self.configure(bg="#000000")
        self.geometry(f"{screen_w}x{screen_h}+0+0")

        self.canvas = tk.Canvas(
            self,
            cursor="cross",
            bg="#000000",
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # Nền tối / vùng sáng được vẽ trong _draw_base_mask và _draw_mask
        self._dark_item = None
        self._crop_photo = None
        self._prev_sel: list[int] | None = None

        # Lớp quản lý annotation (pen / text / rect / arrow)
        self._annotations = AnnotationLayer(self.canvas)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_motion)
        self.bind("<Escape>", self._on_cancel)
        self.bind("<Control-z>", lambda _e: self._annotations.undo())

        self._draw_base_mask()
        self._show_drag_hint(self.winfo_pointerx(), self.winfo_pointery())

        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_force()
        # self.after(100, self.focus_force)

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

    def _show_hint(self, text):
        self._hide_hint()

        x_center = self.winfo_screenwidth() // 2
        self._hint_text_id = self.canvas.create_text(
            x_center,
            29,
            text=text,
            fill="white",
            font=("Segoe UI", 12, "bold"),
        )
        bbox = self.canvas.bbox(self._hint_text_id)
        self._hint_bg_id = self.canvas.create_rectangle(
            bbox[0] - 14,
            bbox[1] - 8,
            bbox[2] + 14,
            bbox[3] + 8,
            fill="#111827",
            outline="#ffffff",
            width=1,
        )
        self.canvas.tag_raise(self._hint_text_id)

    def _hide_hint(self):
        if self._hint_bg_id:
            self.canvas.delete(self._hint_bg_id)
            self._hint_bg_id = None
        if self._hint_text_id:
            self.canvas.delete(self._hint_text_id)
            self._hint_text_id = None

    def _show_drag_hint(self, root_x, root_y):
        """Hiển thị chữ 'Chọn vùng kéo' bám theo con trỏ khi chưa có vùng chọn."""
        x = root_x - self.winfo_rootx() + 18
        y = root_y - self.winfo_rooty() + 18

        if self._drag_hint_text_id is None:
            self._drag_hint_text_id = self.canvas.create_text(
                x,
                y,
                text="Chọn vùng kéo",
                fill="white",
                font=("Segoe UI", 10, "bold"),
                anchor="nw",
            )
            bbox = self.canvas.bbox(self._drag_hint_text_id)
            self._drag_hint_bg_id = self.canvas.create_rectangle(
                bbox[0] - 6,
                bbox[1] - 4,
                bbox[2] + 6,
                bbox[3] + 4,
                fill="#111827",
                outline="",
            )
            self.canvas.tag_raise(self._drag_hint_text_id, self._drag_hint_bg_id)
        else:
            self.canvas.coords(self._drag_hint_text_id, x, y)
            bbox = self.canvas.bbox(self._drag_hint_text_id)
            if self._drag_hint_bg_id is not None:
                self.canvas.coords(
                    self._drag_hint_bg_id,
                    bbox[0] - 6,
                    bbox[1] - 4,
                    bbox[2] + 6,
                    bbox[3] + 4,
                )
                self.canvas.tag_raise(self._drag_hint_text_id, self._drag_hint_bg_id)

    def _hide_drag_hint(self):
        if self._drag_hint_bg_id:
            self.canvas.delete(self._drag_hint_bg_id)
            self._drag_hint_bg_id = None
        if self._drag_hint_text_id:
            self.canvas.delete(self._drag_hint_text_id)
            self._drag_hint_text_id = None

    def _draw_base_mask(self):
        # Nền = ảnh màn hình đã làm tối mượt bằng PIL (thay cho stipple bị "nhòe");
        # vùng chọn sẽ được đè ảnh gốc sáng rõ lên trên trong _draw_mask
        dark = ImageEnhance.Brightness(self._screenshot).enhance(0.55)
        self._bg_dark_photo = ImageTk.PhotoImage(dark)
        self._dark_item = self.canvas.create_image(
            0, 0, anchor="nw", image=self._bg_dark_photo
        )

    def _draw_mask(self, x1, y1, x2, y2):
        self._clear_draw()

        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1

        # Vùng chọn = crop ảnh gốc (sáng, sắc nét) đè lên nền đã làm tối
        w, h = x2 - x1, y2 - y1
        if w >= 1 and h >= 1:
            crop = self._screenshot.crop((x1, y1, x2, y2))
            self._crop_photo = ImageTk.PhotoImage(crop)
            crop_item = self.canvas.create_image(
                x1, y1, anchor="nw", image=self._crop_photo
            )
            # Giữ crop ngay trên nền tối để annotation luôn hiển thị phía trên
            self.canvas.tag_raise(crop_item, self._dark_item)
            self._mask_items.append(crop_item)

        self._selection_item = self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            fill="",
            outline="#00d4ff",
            width=2,
            dash=(2, 3),
        )

    def _on_cancel(self, _event=None):
        self.destroy()

    # Con trỏ tương ứng với từng vị trí trên vùng chọn

    _HIT_CURSORS = {  # noqa: RUF012
        "move": "fleur",
        "l": "sb_h_double_arrow",
        "r": "sb_h_double_arrow",
        "t": "sb_v_double_arrow",
        "b": "sb_v_double_arrow",
        "tl": "size_nw_se",
        "br": "size_nw_se",
        "tr": "size_ne_sw",
        "bl": "size_ne_sw",
    }

    def _hit_test(self, x, y):
        """
        Xác định con trỏ đang ở đâu so với vùng chọn hiện có:
        "move" (bên trong), cạnh ("l"/"r"/"t"/"b"), góc ("tl"/"tr"/"bl"/"br")
        hoặc None (bên ngoài / chưa có vùng chọn).
        """
        if not self._sel:
            return None
        x1, y1, x2, y2 = self._sel
        m = 8  # biên bắt cạnh (px)

        near_l = abs(x - x1) <= m and y1 - m <= y <= y2 + m
        near_r = abs(x - x2) <= m and y1 - m <= y <= y2 + m
        near_t = abs(y - y1) <= m and x1 - m <= x <= x2 + m
        near_b = abs(y - y2) <= m and x1 - m <= x <= x2 + m

        if near_l and near_t:
            return "tl"
        if near_r and near_t:
            return "tr"
        if near_l and near_b:
            return "bl"
        if near_r and near_b:
            return "br"
        if near_l:
            return "l"
        if near_r:
            return "r"
        if near_t:
            return "t"
        if near_b:
            return "b"
        if x1 < x < x2 and y1 < y < y2:
            return "move"
        return None

    def _on_motion(self, event):
        # Chữ "Chọn vùng kéo" chỉ hiện khi chưa có vùng chọn nào và chưa vẽ annotation
        if self._sel is None and self._annotations.tool is None:
            self._show_drag_hint(event.x_root, event.y_root)
        else:
            self._hide_drag_hint()

        # Không đổi con trỏ khi đang vẽ annotation hoặc đang kéo
        if self._annotations.tool is not None or self._drag_mode is not None:
            return
        hit = self._hit_test(event.x, event.y)
        cursor = self._HIT_CURSORS.get(hit, "cross") if hit else "cross"
        self.canvas.configure(cursor=cursor)

    def _on_press(self, event):
        # Nếu đang chọn tool annotation thì nhường sự kiện cho lớp annotation
        if self._annotations.on_press(event.x, event.y):
            return

        # Bấm vào vùng chọn có sẵn: kéo để di chuyển hoặc đổi kích thước
        # (toolbar giữ nguyên, sẽ được đặt lại vị trí khi thả chuột)
        hit = self._hit_test(event.x, event.y)
        if hit is not None and self._sel:
            x1, y1, x2, y2 = self._sel
            self._drag_mode = hit
            self._drag_origin = (event.x, event.y, x1, y1, x2, y2)
            return

        self._drag_mode = "select"
        # Nhớ vùng cũ để khôi phục nếu đây chỉ là click nhầm (kéo quá nhỏ)
        self._prev_sel = self._sel
        self._sel = None
        self._start_x = event.x_root
        self._start_y = event.y_root
        self._hide_hint()
        self._hide_drag_hint()
        # Vẽ lại lớp mờ ngay (không chỉ xoá) để overlay không bao giờ
        # rơi về trạng thái trong suốt hoàn toàn / click xuyên qua.
        self._draw_mask(event.x, event.y, event.x, event.y)

    def _drag_move(self, x, y):
        """Kéo di chuyển toàn bộ vùng chọn, giữ nguyên kích thước."""
        if self._drag_origin is None:
            return
        ox, oy, x1, y1, x2, y2 = self._drag_origin
        w, h = x2 - x1, y2 - y1
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()

        nx1 = min(max(x1 + (x - ox), 0), sw - w)
        ny1 = min(max(y1 + (y - oy), 0), sh - h)
        self._sel = [nx1, ny1, nx1 + w, ny1 + h]
        self._draw_mask(*self._sel)
        self._show_size_label()

    def _drag_resize(self, x, y):
        """Kéo cạnh/góc để thay đổi kích thước vùng chọn."""
        if self._drag_origin is None or self._drag_mode is None:
            return
        ox, oy, x1, y1, x2, y2 = self._drag_origin
        dx, dy = x - ox, y - oy
        mode = self._drag_mode

        if "l" in mode:
            x1 += dx
        if "r" in mode:
            x2 += dx
        if "t" in mode:
            y1 += dy
        if "b" in mode:
            y2 += dy

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x1, x2 = min(max(x1, 0), sw), min(max(x2, 0), sw)
        y1, y2 = min(max(y1, 0), sh), min(max(y2, 0), sh)

        # Sắp lại thứ tự để cho phép kéo "lộn ngược" qua cạnh đối diện
        self._sel = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
        self._draw_mask(*self._sel)
        self._show_size_label()

    def _show_size_label(self):
        if not self._sel:
            return
        x1, y1, x2, y2 = self._sel
        if self._size_text:
            self.canvas.delete(self._size_text)
        self._size_text = self.canvas.create_text(
            x1 + 4,
            max(y1 - 6, 16),
            text=f"{x2 - x1} x {y2 - y1}",
            fill="white",
            font=("Segoe UI", 10, "bold"),
            anchor="sw",
        )

    def _on_drag(self, event):
        if self._annotations.on_drag(event.x, event.y):
            return

        if self._drag_mode == "move":
            self._drag_move(event.x, event.y)
            return
        if self._drag_mode in ("l", "r", "t", "b", "tl", "tr", "bl", "br"):
            self._drag_resize(event.x, event.y)
            return
        if self._drag_mode != "select":
            return

        cx1 = self._start_x - self.winfo_rootx()
        cy1 = self._start_y - self.winfo_rooty()
        cx2 = event.x
        cy2 = event.y

        self._draw_mask(cx1, cy1, cx2, cy2)

        w = abs(event.x_root - self._start_x)
        h = abs(event.y_root - self._start_y)
        if self._size_text:
            self.canvas.delete(self._size_text)
        self._size_text = self.canvas.create_text(
            event.x - 55,
            event.y + 15,
            text=f"{w} x {h}",
            fill="white",
            font=("Segoe UI", 10, "bold"),
            anchor="sw",
        )

    def _on_release(self, event):
        if self._annotations.on_release(event.x, event.y):
            return

        mode, self._drag_mode = self._drag_mode, None
        self._drag_origin = None

        # Kết thúc di chuyển / đổi kích thước: chốt vùng mới, hiện lại toolbar
        if mode in ("move", "l", "r", "t", "b", "tl", "tr", "bl", "br"):
            self._finalize_selection()
            return
        if mode != "select":
            return

        x1, y1 = self._start_x, self._start_y
        x2, y2 = event.x_root, event.y_root

        if abs(x2 - x1) < 5 or abs(y2 - y1) < 5:
            # Click nhầm khi đã có vùng chọn: khôi phục vùng cũ,
            # giữ nguyên annotation, không đóng overlay
            if self._prev_sel:
                self._sel = self._prev_sel
                self._prev_sel = None
                self._draw_mask(*self._sel)
                self._finalize_selection()
                return
            self.destroy()
            return

        # Vùng chọn mới hợp lệ -> lúc này mới bỏ annotation cũ
        self._annotations.clear()
        self._prev_sel = None

        # Lưu vùng chọn theo toạ độ canvas rồi chốt
        dx, dy = self.winfo_rootx(), self.winfo_rooty()
        self._sel = [
            min(x1, x2) - dx,
            min(y1, y2) - dy,
            max(x1, x2) - dx,
            max(y1, y2) - dy,
        ]
        self._finalize_selection()

    def _finalize_selection(self):
        """
        Chốt self._sel (toạ độ canvas) thành self.result (toạ độ màn hình),
        giới hạn vùng vẽ annotation và hiển thị toolbar cạnh vùng chọn.
        """
        if not self._sel:
            return

        x1, y1, x2, y2 = self._sel
        dx, dy = self.winfo_rootx(), self.winfo_rooty()
        self.result = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)

        # Giới hạn vùng được vẽ annotation = vùng chọn (toạ độ canvas)
        self._annotations.set_region((x1, y1, x2, y2))
        self._show_action_toolbar()

    def _show_action_toolbar(self):
        if self._toolbar:
            self._toolbar.destroy()
            self._toolbar = None

        if not self.result:
            return

        x1, y1, x2, y2 = self.result

        def handle_action(action):
            if action == "undo":
                self._annotations.undo()
                return
            self._toolbar = None
            if action == "cancel":
                self._on_cancel()
            else:
                self._confirm_action(action)

        def handle_tool(tool):
            self._annotations.set_tool(tool)

        def handle_color(color):
            self._annotations.set_color(color)

        self._toolbar = ActionToolbar(
            self,
            (x1, y1, x2, y2),
            handle_action,
            on_tool=handle_tool,
            initial_color=self._annotations.color,
            on_color=handle_color,
        )

    def _compose_image(self):
        """Crop ảnh màn hình đóng băng theo vùng chọn rồi vẽ annotation lên."""
        if self.result is None:
            return None
        x1, y1, x2, y2 = self.result
        img = self._screenshot.crop((x1, y1, x2, y2))
        # annotation lưu theo toạ độ canvas -> đổi sang toạ độ ảnh crop
        dx, dy = self.winfo_rootx(), self.winfo_rooty()
        return self._annotations.render_to_image(img, offset=(x1 - dx, y1 - dy))

    def _confirm_action(self, action):
        if self.result is None:
            return

        # capture / copy dùng ảnh đóng băng đã ghép annotation
        image = None
        if action in ("capture", "copy"):
            image = self._compose_image()

        self.withdraw()
        self.update_idletasks()

        if self.on_confirm:
            self.on_confirm(self.result, action, image)
        self.destroy()
