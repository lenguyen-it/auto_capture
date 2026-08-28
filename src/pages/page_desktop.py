import os
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from src.core.capture import capture_desktop
from src.core.scroll_capture import capture_scrolling_window
from src.core.window_utils import get_all_visible_windows

# ---------------------------------------------------------------------------
# Tab chụp toàn bộ desktop
# ---------------------------------------------------------------------------

MODE_FULLSCREEN = "Toàn màn hình"
MODE_SCROLLING = "Scrolling (trang web dài)"


class PageDesktop(tk.Frame):
    """Frame cho tab chụp toàn bộ desktop."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#f5f5f5")

        self.save_folder = os.path.abspath("screenshots")
        self.preview_img = None
        self.windows_data: list[tuple[str, int]] = []

        self.is_running = False
        self.schedule_thread = None

        self._build_ui()

    def _build_ui(self):
        # ===== Phần 0: Chế độ chụp =====
        section0 = tk.LabelFrame(
            self,
            text="Chế độ chụp",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section0.pack(fill="x", padx=15, pady=(10, 4))

        frame_mode = tk.Frame(section0, bg="#f5f5f5")
        frame_mode.pack(fill="x", padx=10, pady=8)

        self.cb_mode = ttk.Combobox(
            frame_mode,
            values=[MODE_FULLSCREEN, MODE_SCROLLING],
            state="readonly",
            font=("Segoe UI", 10),
        )
        self.cb_mode.current(0)
        self.cb_mode.pack(fill="x")
        self.cb_mode.bind("<<ComboboxSelected>>", self._on_mode_changed)

        # --- Chọn cửa sổ (chỉ dùng ở chế độ Scrolling) ---
        self.frame_window_pick = tk.Frame(section0, bg="#f5f5f5")

        tk.Label(
            self.frame_window_pick,
            text="Chọn cửa sổ cần chụp (vd. trình duyệt):",
            font=("Segoe UI", 9),
            bg="#f5f5f5",
            fg="#555",
        ).pack(anchor="w", padx=10)

        frame_cb = tk.Frame(self.frame_window_pick, bg="#f5f5f5")
        frame_cb.pack(fill="x", padx=10, pady=(2, 8))

        self.lb_windows = tk.Listbox(
            frame_cb,
            selectmode="browse",
            exportselection=False,
            height=4,
            font=("Segoe UI", 9),
        )
        self.lb_windows.pack(side="left", fill="x", expand=True)

        tk.Button(
            frame_cb,
            text="Làm mới",
            command=self._refresh_windows,
            font=("Segoe UI", 9),
            relief="flat",
            bg="#e0e0e0",
            cursor="hand2",
        ).pack(side="right", padx=(5, 0))

        # ===== Phần 1: Thư mục lưu =====
        section1 = tk.LabelFrame(
            self,
            text="Thư mục lưu",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section1.pack(fill="x", padx=15, pady=(10, 4))

        frame_folder = tk.Frame(section1, bg="#f5f5f5")
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

        # ===== Phần 2: Hành động =====
        section2 = tk.LabelFrame(
            self,
            text=" Thực hiện  ",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section2.pack(fill="x", padx=15, pady=4)

        self.btn_capture_now = tk.Button(
            section2,
            text="CHỤP NGAY",
            font=("Segoe UI", 11, "bold"),
            bg="#2e7d32",
            fg="white",
            activebackground="#1b5e20",
            relief="flat",
            cursor="hand2",
            command=self._on_click_capture_now,
        )
        self.btn_capture_now.pack(fill="x", padx=10, pady=(8, 4))

        frame_sched = tk.Frame(section2, bg="#f5f5f5")
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

        self.btn_sched = tk.Button(
            frame_sched,
            text="Bắt đầu lịch",
            font=("Segoe UI", 10, "bold"),
            bg="#e65100",
            fg="white",
            activebackground="#bf360c",
            relief="flat",
            cursor="hand2",
            command=self._toggle_schedule,
        )
        self.btn_sched.pack(side="right")

        self.lbl_status = tk.Label(
            section2,
            text="Trạng thái: Sẵn sàng",
            font=("Segoe UI", 9, "italic"),
            fg="#888",
            bg="#f5f5f5",
        )
        self.lbl_status.pack(pady=(4, 8))

        # ===== Phần 3: Preview =====
        section3 = tk.LabelFrame(
            self,
            text="Preview ảnh vừa chụp  ",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section3.pack(fill="both", expand=True, padx=15, pady=(4, 10))

        self.lbl_preview = tk.Label(
            section3,
            text="(Chưa có ảnh)",
            bg="#e8e8e8",
            fg="#aaa",
            font=("Segoe UI", 10, "italic"),
            cursor="hand2",
        )
        self.lbl_preview.pack(fill="both", expand=True, padx=8, pady=8)
        self.lbl_preview.bind("<Button-1>", self._open_last_image)

        self._on_mode_changed()

    def _on_mode_changed(self, _event=None):
        if self.cb_mode.get() == MODE_SCROLLING:
            self.frame_window_pick.pack(fill="x")
            self._refresh_windows()
            self.btn_capture_now.config(text="CHỤP SCROLLING")
        else:
            self.frame_window_pick.pack_forget()
            self.btn_capture_now.config(text="CHỤP NGAY")

    def _refresh_windows(self):
        self.windows_data = get_all_visible_windows()
        self.lb_windows.delete(0, tk.END)
        for title, _ in self.windows_data:
            self.lb_windows.insert(tk.END, title)
        if self.windows_data:
            self.lb_windows.selection_set(0)

    def _on_click_capture_now(self):
        if self.cb_mode.get() == MODE_SCROLLING:
            self._capture_scrolling()
        else:
            self._capture_now()

    def _capture_now(self):
        folder = self.entry_folder.get().strip()
        os.makedirs(folder, exist_ok=True)

        def do_capture():
            path = capture_desktop(folder, "desktop_manual")
            if path:
                self.after(0, lambda: self._show_preview(path))
                self.after(
                    0,
                    lambda: self.lbl_status.config(
                        text=f"Đã chụp: {os.path.basename(path)}", fg="#2e7d32"
                    ),
                )

        threading.Thread(target=do_capture, daemon=True).start()

    def _capture_scrolling(self):
        selection = self.lb_windows.curselection()
        if not selection:
            messagebox.showwarning(
                "Cảnh báo", "Vui lòng chọn một cửa sổ để chụp scrolling!"
            )
            return

        _title, hwnd = self.windows_data[selection[0]]
        folder = self.entry_folder.get().strip()
        os.makedirs(folder, exist_ok=True)

        self.btn_capture_now.config(state="disabled")
        self.lbl_status.config(text="Đang cuộn & chụp...", fg="#e65100")

        def on_progress(count):
            self.after(
                0,
                lambda: self.lbl_status.config(
                    text=f"Đang cuộn & chụp... (đoạn {count})", fg="#e65100"
                ),
            )

        def do_capture():
            path = capture_scrolling_window(
                hwnd, folder, "desktop_scroll", on_progress=on_progress
            )
            self.after(0, lambda: self.btn_capture_now.config(state="normal"))
            if path:
                self.after(0, lambda: self._show_preview(path))
                self.after(
                    0,
                    lambda: self.lbl_status.config(
                        text=f"Đã chụp: {os.path.basename(path)}", fg="#2e7d32"
                    ),
                )
            else:
                self.after(
                    0,
                    lambda: self.lbl_status.config(
                        text="Chụp scrolling thất bại", fg="#e53935"
                    ),
                )
            # Cửa sổ target đã được đưa lên foreground để chụp -> đưa app
            # trở lại lên trước màn hình sau khi chụp & lưu xong.
            self.after(0, self._restore_app_window)

        threading.Thread(target=do_capture, daemon=True).start()

    def _restore_app_window(self):
        top = self.winfo_toplevel()
        top.deiconify()
        top.lift()
        top.focus_force()

    def _toggle_schedule(self):
        if self.is_running:
            self.is_running = False
            self.btn_sched.config(text="Bắt đầu lịch", bg="#e65100")
            self.lbl_status.config(text="Lịch chụp đã dừng", fg="#e53935")
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
        self.btn_sched.config(text="Dừng lịch", bg="#c62828")
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

        path = capture_desktop(folder, "desktop_sched")
        if path:
            self.after(0, lambda p=path: self._show_preview(p))

        next_time = datetime.now() + delta

        while self.is_running:
            if datetime.now() >= next_time:
                path = capture_desktop(folder, "desktop_sched")
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
