import os
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageEnhance, ImageTk

from scr.core.capture import capture_region, grab_region, save_image
from scr.core.clipboard_utils import copy_image_to_clipboard
from scr.pages.components.annotations import AnnotationLayer
from scr.pages.components.toolbar import ActionToolbar

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

        self._toolbar = ActionToolbar(
            self, (x1, y1, x2, y2), handle_action, on_tool=handle_tool
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


# ---------------------------------------------------------------------------
# Tab chụp theo vùng
# ---------------------------------------------------------------------------


class PageRegion(tk.Frame):
    """Frame cho tab chụp theo vùng."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#f5f5f5")

        self.save_folder = os.path.abspath("screenshots")
        self.region = None
        self.preview_img = None

        self.is_running = False
        self.schedule_thread = None

        self._build_ui()

    def _build_ui(self):
        # ===== Phần 1: Chọn vùng =====
        section1 = tk.LabelFrame(
            self,
            text="Chọn vùng chụp  ",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section1.pack(fill="x", padx=15, pady=(10, 4))

        tk.Button(
            section1,
            text="KÉO CHỌN VÙNG",
            font=("Segoe UI", 11, "bold"),
            bg="#1565c0",
            fg="white",
            activebackground="#0d47a1",
            relief="flat",
            cursor="hand2",
            command=self._start_region_select,
        ).pack(fill="x", padx=10, pady=8)

        # self.lbl_region = tk.Label(
        #     section1,
        #     text="Chưa có vùng nào được chọn",
        #     font=("Segoe UI", 9, "italic"),
        #     fg="#888",
        #     bg="#f5f5f5",
        # )
        # self.lbl_region.pack(pady=(2, 8))

        # ===== Phần 2: Thư mục lưu =====
        section2 = tk.LabelFrame(
            self,
            text="Thư mục lưu",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section2.pack(fill="x", padx=15, pady=4)

        frame_folder = tk.Frame(section2, bg="#f5f5f5")
        frame_folder.pack(fill="x", padx=10, pady=8)

        self.entry_folder = tk.Entry(frame_folder, font=("Segoe UI", 10))
        self.entry_folder.insert(0, self.save_folder)
        self.entry_folder.config(state="readonly")
        self.entry_folder.pack(side="left", fill="x", expand=True)

        tk.Button(
            frame_folder,
            text="Chọn",
            command=self._select_folder,
            font=("Segoe UI", 9),
            relief="flat",
            bg="#e0e0e0",
            cursor="hand2",
        ).pack(side="right", padx=5)

        # ===== Phần 3: Hành động =====
        section3 = tk.LabelFrame(
            self,
            text=" Thực hiện  ",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section3.pack(fill="x", padx=15, pady=4)

        # tk.Button(
        #     section3,
        #     text="CHỤP NGAY",
        #     font=("Segoe UI", 11, "bold"),
        #     bg="#2e7d32",
        #     fg="white",
        #     activebackground="#1b5e20",
        #     relief="flat",
        #     cursor="hand2",
        #     command=self._capture_now,
        # ).pack(fill="x", padx=10, pady=(8, 4))

        frame_sched = tk.Frame(section3, bg="#f5f5f5")
        frame_sched.pack(fill="x", padx=10, pady=4)

        tk.Label(
            frame_sched,
            text="Chụp mỗi:",
            font=("Segoe UI", 10),
            bg="#f5f5f5",
        ).pack(side="left")

        self.entry_interval = tk.Entry(frame_sched, width=6, font=("Segoe UI", 10))
        self.entry_interval.insert(0, "30")
        self.entry_interval.pack(side="left", padx=5)

        self.cb_unit = ttk.Combobox(
            frame_sched,
            values=["Giây", "Phút"],
            state="readonly",
            width=6,
            font=("Segoe UI", 10),
        )
        self.cb_unit.current(0)
        self.cb_unit.pack(side="left")

        # self.btn_sched = tk.Button(
        #     frame_sched,
        #     text="Bắt đầu lịch",
        #     font=("Segoe UI", 10, "bold"),
        #     bg="#e65100",
        #     fg="white",
        #     activebackground="#bf360c",
        #     relief="flat",
        #     cursor="hand2",
        #     command=self._toggle_schedule,
        # )
        # self.btn_sched.pack(side="right")

        self.lbl_status = tk.Label(
            section3,
            text="Trạng thái: Sẵn sàng",
            font=("Segoe UI", 9, "italic"),
            fg="#888",
            bg="#f5f5f5",
        )
        self.lbl_status.pack(pady=(4, 8))

        # ===== Phần 4: Preview =====
        section4 = tk.LabelFrame(
            self,
            text="Preview ảnh vừa chụp  ",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section4.pack(fill="both", expand=True, padx=15, pady=(4, 10))

        self.lbl_preview = tk.Label(
            section4,
            text="(Chưa có ảnh)",
            bg="#e8e8e8",
            fg="#aaa",
            font=("Segoe UI", 10, "italic"),
            cursor="hand2",
        )
        self.lbl_preview.pack(fill="both", expand=True, padx=8, pady=8)
        self.lbl_preview.bind("<Button-1>", self._open_last_image)

    def _start_region_select(self):
        root = self.winfo_toplevel()
        root.withdraw()
        # Chờ cửa sổ app ẩn hẳn rồi mới đóng băng màn hình,
        # để giao diện app không lọt vào ảnh nền chụp
        self.after(300, lambda: self._open_overlay(root))

    def _open_overlay(self, root):
        selector = None
        try:
            # Đóng băng ảnh màn hình trước khi mở overlay
            screenshot = grab_region(
                0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
            )
            if screenshot is None:
                raise RuntimeError("Không chụp được ảnh nền màn hình")

            selector = RegionSelector(
                root, screenshot, on_confirm=self._handle_region_selection
            )
            root.wait_window(selector)
        except Exception as e:
            print(f"Lỗi khi mở overlay chọn vùng: {e}")
        finally:
            if selector is not None and selector.winfo_exists():
                try:
                    selector.grab_release()
                    selector.destroy()
                except Exception:
                    pass
            root.deiconify()

    def _handle_region_selection(self, region, action, image=None):
        self.region = region
        # self._update_region_label()

        if action == "capture":
            self._save_annotated(image)
        elif action == "copy":
            self._copy_annotated(image)
        elif action == "schedule":
            self._toggle_schedule()

    def _save_annotated(self, image):
        """Lưu ảnh vùng chọn đã ghép annotation. Không có ảnh thì chụp live."""
        if image is None:
            self._capture_now()
            return

        folder = self.entry_folder.get().strip()
        os.makedirs(folder, exist_ok=True)

        path = save_image(image, folder, "region_manual", label=f"{image.size}")
        if path:
            self._show_preview(path)
            self.lbl_status.config(
                text=f"Đã chụp: {os.path.basename(path)}", fg="#2e7d32"
            )

    def _copy_annotated(self, image):
        if image is None:
            return
        try:
            copy_image_to_clipboard(image)
            self.lbl_status.config(
                text="Đã copy ảnh vào clipboard (Ctrl+V để dán)", fg="#2e7d32"
            )
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể copy vào clipboard: {e}")

    # def _update_region_label(self):
    #     if self.region:
    #         x1, y1, x2, y2 = self.region
    #         w = x2 - x1
    #         h = y2 - y1
    #         self.lbl_region.config(
    #             text=f"Vùng: ({x1}, {y1}) → ({x2}, {y2})   |   Kích thước: {w} x {h} px",
    #             fg="#1565c0",
    #             font=("Segoe UI", 9, "bold"),
    #         )

    def _capture_now(self):
        if not self.region:
            messagebox.showwarning(
                "Chưa chọn vùng", "Vui lòng chọn vùng trước khi chụp!"
            )
            return

        folder = self.entry_folder.get().strip()
        os.makedirs(folder, exist_ok=True)

        def do_capture():
            if not self.region:
                return
            x1, y1, x2, y2 = self.region
            path = capture_region(x1, y1, x2, y2, folder, "region_manual")
            if path:
                self.after(0, lambda: self._show_preview(path))
                self.after(
                    0,
                    lambda: self.lbl_status.config(
                        text=f"Đã chụp: {os.path.basename(path)}", fg="#2e7d32"
                    ),
                )

        threading.Thread(target=do_capture, daemon=True).start()

    def _toggle_schedule(self):
        if self.is_running:
            self.is_running = False
            # self.btn_sched.config(text="Bắt đầu lịch", bg="#e65100")
            self.lbl_status.config(text="Lịch chụp đã dừng", fg="#e53935")
            return

        if not self.region:
            messagebox.showwarning("Chưa chọn vùng", "Vui lòng chọn vùng trước!")
            return

        try:
            interval = int(self.entry_interval.get().strip())
            if interval <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning(
                "Cảnh báo", "Khoảng thời gian phải là số nguyên dương!"
            )
            return

        unit = self.cb_unit.get()
        folder = self.entry_folder.get().strip()
        os.makedirs(folder, exist_ok=True)

        self.is_running = True
        # self.btn_sched.config(text="Dừng lịch", bg="#c62828")
        self.lbl_status.config(
            text=f"Đang chụp mỗi {interval} {unit.lower()}...", fg="#2e7d32"
        )

        self.schedule_thread = threading.Thread(
            target=self._schedule_loop,
            args=(interval, unit, folder),
            daemon=True,
        )
        self.schedule_thread.start()

    def _schedule_loop(self, interval_val, unit, folder):
        delta = (
            timedelta(minutes=interval_val)
            if unit == "Phút"
            else timedelta(seconds=interval_val)
        )

        if not self.region:
            return
        x1, y1, x2, y2 = self.region
        path = capture_region(x1, y1, x2, y2, folder, "region_sched")
        if path:
            self.after(0, lambda p=path: self._show_preview(p))

        next_time = datetime.now() + delta

        while self.is_running:
            if datetime.now() >= next_time:
                x1, y1, x2, y2 = self.region
                path = capture_region(x1, y1, x2, y2, folder, "region_sched")
                if path:
                    self.after(0, lambda p=path: self._show_preview(p))
                    self.after(
                        0,
                        lambda p=path: self.lbl_status.config(
                            text=f"Chụp: {os.path.basename(p)}", fg="#2e7d32"
                        ),
                    )
                next_time = datetime.now() + delta
            time.sleep(0.3)

    def _show_preview(self, image_path):
        try:
            self._last_image_path = image_path
            img = Image.open(image_path)

            pw = self.lbl_preview.winfo_width() or 400
            ph = self.lbl_preview.winfo_height() or 150
            img.thumbnail((pw, ph), Image.Resampling.LANCZOS)

            self.preview_img = ImageTk.PhotoImage(img)
            self.lbl_preview.config(image=self.preview_img, text="")
        except Exception as e:
            print(f"Lỗi hiển thị preview: {e}")

    def _open_last_image(self, _event=None):
        if hasattr(self, "_last_image_path") and self._last_image_path:
            os.startfile(self._last_image_path)

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục lưu ảnh")
        if folder:
            self.save_folder = folder
            self.entry_folder.config(state="normal")
            self.entry_folder.delete(0, tk.END)
            self.entry_folder.insert(0, folder)
            self.entry_folder.config(state="readonly")
