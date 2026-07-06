import os
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
from PIL import Image, ImageTk

from core.capture import capture_region
from pages.components.toolbar import ActionToolbar

# ---------------------------------------------------------------------------
# Overlay chọn vùng (toàn màn hình)
# ---------------------------------------------------------------------------


class RegionSelector(tk.Toplevel):
    """
    Cửa sổ overlay fullscreen để kéo chọn vùng chụp.
    Trong lúc kéo, khung chọn sẽ hiện trực tiếp.
    """

    def __init__(self, parent, on_confirm=None):
        super().__init__(parent)
        self.result = None
        self.on_confirm = on_confirm

        self._start_x = 0
        self._start_y = 0
        self._selection_item = None
        self._size_text = None
        self._toolbar = None
        self._mask_items = []
        self._hint_bg_id = None
        self._hint_text_id = None

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        try:
            self.attributes("-fullscreen", True)
        except tk.TclError:
            self.geometry(f"{screen_w}x{screen_h}+0+0")

        self.overrideredirect(True)
        self.attributes("-alpha", 0.30)
        self.attributes("-transparentcolor", "#000001")
        self.attributes("-topmost", True)
        self.configure(bg="#000001")
        self.geometry(f"{screen_w}x{screen_h}+0+0")

        self.canvas = tk.Canvas(
            self,
            cursor="cross",
            bg="#000001",
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._on_cancel)

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
        self._mask_items.append(
            self.canvas.create_rectangle(
                0,
                0,
                self.winfo_screenwidth(),
                self.winfo_screenheight(),
                fill="#000000",
                outline="",
            )
        )

    def _draw_mask(self, x1, y1, x2, y2):
        self._clear_draw()

        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1

        self._draw_base_mask()

        self._selection_item = self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            fill="#000001",
            outline="#00d4ff",
            width=2,
            dash=(2, 3),
        )

    def _on_cancel(self, _event=None):
        self.destroy()

    def _on_press(self, event):
        self._start_x = event.x_root
        self._start_y = event.y_root
        self._hide_hint()
        # Vẽ lại lớp mờ ngay (không chỉ xoá) để overlay không bao giờ
        # rơi về trạng thái trong suốt hoàn toàn / click xuyên qua.
        self._draw_mask(event.x, event.y, event.x, event.y)
        if self._toolbar:
            self._toolbar.destroy()
            self._toolbar = None

    def _on_drag(self, event):
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
        x1, y1 = self._start_x, self._start_y
        x2, y2 = event.x_root, event.y_root

        if abs(x2 - x1) < 5 or abs(y2 - y1) < 5:
            self.destroy()
            return

        self.result = (
            min(x1, x2),
            min(y1, y2),
            max(x1, x2),
            max(y1, y2),
        )
        self._show_action_toolbar()

    def _show_action_toolbar(self):
        if self._toolbar:
            self._toolbar.destroy()
            self._toolbar = None

        if not self.result:
            return

        x1, y1, x2, y2 = self.result

        def handle_action(action):
            self._toolbar = None
            if action == "cancel":
                self._on_cancel()
            else:
                self._confirm_action(action)

        self._toolbar = ActionToolbar(self, x2, y1, handle_action)

    def _confirm_action(self, action):
        if self.result is None:
            return

        self.withdraw()
        self.update_idletasks()

        if self.on_confirm:
            self.on_confirm(self.result, action)
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
        self.after(150, lambda: self._open_overlay(root))

    def _open_overlay(self, root):
        selector = None
        try:
            selector = RegionSelector(root, on_confirm=self._handle_region_selection)
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

    def _handle_region_selection(self, region, action):
        self.region = region
        # self._update_region_label()

        if action == "capture":
            self._capture_now()
        elif action == "schedule":
            self._toggle_schedule()

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
