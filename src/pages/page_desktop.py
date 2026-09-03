import os
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from src.core.capture import capture_desktop

# ---------------------------------------------------------------------------
# Tab chụp toàn bộ desktop
# ---------------------------------------------------------------------------


class PageDesktop(tk.Frame):
    """Frame cho tab chụp toàn bộ desktop."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#f5f5f5")

        self.save_folder = os.path.abspath("screenshots")
        self.preview_img = None

        self.is_running = False
        self.schedule_thread = None

        self._build_ui()

    def _build_ui(self):
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
            command=self._capture_now,
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
