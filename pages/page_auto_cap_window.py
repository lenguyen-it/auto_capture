import os
import ctypes
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta

from core.window_utils import get_all_visible_windows
from core.capture import capture_window_by_hwnd


class PageAuto(tk.Frame):
    """Frame cho tab chụp tự động theo lịch."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#f5f5f5")

        self.windows_data: list[tuple[str, int]] = []
        self.is_running = False
        self.schedule_thread: threading.Thread | None = None
        self.save_folder = os.path.abspath("screenshots")

        self._build_ui()
        self.refresh_windows()

    # ------------------------------------------------------------------
    # Xây dựng giao diện
    # ------------------------------------------------------------------

    def _build_ui(self):
        # --- Chọn cửa sổ ---
        tk.Label(
            self,
            text="Chọn cửa sổ muốn chụp:",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
        ).pack(anchor="w", padx=15, pady=4)

        frame_cb = tk.Frame(self, bg="#f5f5f5")
        frame_cb.pack(fill="x", padx=15)

        self.cb_windows = ttk.Combobox(frame_cb, state="readonly", font=("Segoe UI", 9))
        self.cb_windows.pack(side="left", fill="x", expand=True)

        tk.Button(
            frame_cb,
            text="Làm mới",
            command=self.refresh_windows,
            font=("Segoe UI", 9),
            relief="flat",
            bg="#e0e0e0",
            cursor="hand2",
        ).pack(side="right", padx=5)

        # --- Chọn folder ---
        tk.Label(
            self,
            text="Thư mục lưu ảnh:",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
        ).pack(anchor="w", padx=15, pady=4)

        frame_folder = tk.Frame(self, bg="#f5f5f5")
        frame_folder.pack(fill="x", padx=15)

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

        # --- Thời gian bắt đầu ---
        tk.Label(
            self,
            text="Thời gian bắt đầu (HH:MM:SS):",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
        ).pack(anchor="w", padx=15, pady=4)

        default_start = (datetime.now() + timedelta(minutes=1)).strftime("%H:%M:%S")
        self.entry_start_time = tk.Entry(self, font=("Segoe UI", 10))
        self.entry_start_time.insert(0, default_start)
        self.entry_start_time.pack(fill="x", padx=15)

        # --- Khoảng cách chụp ---
        tk.Label(
            self,
            text="Khoảng cách giữa các lần chụp:",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
        ).pack(anchor="w", padx=15, pady=4)

        frame_time = tk.Frame(self, bg="#f5f5f5")
        frame_time.pack(fill="x", padx=15)

        self.entry_interval = tk.Entry(frame_time, font=("Segoe UI", 10))
        self.entry_interval.insert(0, "30")
        self.entry_interval.pack(side="left", fill="x", expand=True)

        self.cb_unit = ttk.Combobox(
            frame_time,
            values=["Phút", "Giây"],
            state="readonly",
            width=8,
            font=("Segoe UI", 10),
        )
        self.cb_unit.current(0)
        self.cb_unit.pack(side="right", padx=5)

        # --- Trạng thái ---
        self.lbl_status = tk.Label(
            self,
            text="Trạng thái: Đang dừng",
            font=("Segoe UI", 10, "italic"),
            fg="#e53935",
            bg="#f5f5f5",
        )
        self.lbl_status.pack(pady=8)

        # --- Các nút ---
        frame_btns = tk.Frame(self, bg="#f5f5f5")
        frame_btns.pack(fill="x", padx=15, pady=4)

        self.btn_start = tk.Button(
            frame_btns,
            text="BẮT ĐẦU",
            font=("Segoe UI", 11, "bold"),
            bg="#2e7d32",
            fg="white",
            activebackground="#1b5e20",
            relief="flat",
            cursor="hand2",
            command=self._on_click_start,
        )
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 5))

        tk.Button(
            frame_btns,
            text="TẮT MÀN HÌNH",
            font=("Segoe UI", 11, "bold"),
            bg="#546e7a",
            fg="white",
            activebackground="#37474f",
            relief="flat",
            cursor="hand2",
            command=self._turn_off_monitor,
        ).pack(side="right", fill="x", expand=True, padx=(5, 0))

        tk.Button(
            self,
            text="CHỤP NGAY",
            font=("Segoe UI", 11, "bold"),
            bg="#1565c0",
            fg="white",
            activebackground="#0d47a1",
            relief="flat",
            cursor="hand2",
            command=self._on_click_capture,
        ).pack(fill="x", padx=15, pady=6)

    # ------------------------------------------------------------------
    # Logic
    # ------------------------------------------------------------------

    def refresh_windows(self):
        self.windows_data = get_all_visible_windows()
        titles = [w[0] for w in self.windows_data]
        self.cb_windows["values"] = titles
        if titles:
            self.cb_windows.current(0)
        else:
            self.cb_windows.set("Không tìm thấy cửa sổ nào phù hợp")

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục lưu ảnh")
        if folder:
            self.save_folder = folder
            self.entry_folder.config(state="normal")
            self.entry_folder.delete(0, tk.END)
            self.entry_folder.insert(0, folder)
            self.entry_folder.config(state="readonly")

    def _on_click_start(self):
        self.save_folder = self.entry_folder.get().strip()
        os.makedirs(self.save_folder, exist_ok=True)

        if self.is_running:
            self.is_running = False
            self.btn_start.config(text="BẮT ĐẦU", bg="#2e7d32")
            self.lbl_status.config(text="Trạng thái: Đang dừng", fg="#e53935")
            return

        idx = self.cb_windows.current()
        if idx == -1:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một cửa sổ để chụp!")
            return

        hwnd = self.windows_data[idx][1]
        title = self.windows_data[idx][0]
        start_time = self.entry_start_time.get().strip()
        unit = self.cb_unit.get()

        try:
            interval = int(self.entry_interval.get().strip())
            if interval <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning(
                "Cảnh báo", "Khoảng thời gian phải là số nguyên dương!"
            )
            return

        self.is_running = True
        self.btn_start.config(text="DỪNG LẠI", bg="#c62828")
        self.lbl_status.config(text=f"Đang chạy: {title[:35]}...", fg="#2e7d32")

        self.schedule_thread = threading.Thread(
            target=self._schedule_loop,
            args=(hwnd, title, start_time, interval, unit),
            daemon=True,
        )
        self.schedule_thread.start()

    def _schedule_loop(self, hwnd, title, start_time_str, interval_val, unit):
        from datetime import datetime, timedelta
        import time

        try:
            now = datetime.now()
            target = datetime.strptime(
                f"{now.strftime('%Y-%m-%d')} {start_time_str}", "%Y-%m-%d %H:%M:%S"
            )
            delta = (
                timedelta(minutes=interval_val)
                if unit == "Phút"
                else timedelta(seconds=interval_val)
            )

            if now > target:
                while now > target:
                    target += delta

            print(f"[Auto] Bắt đầu lịch chụp cho '{title}'")
            capture_window_by_hwnd(hwnd, title, self.save_folder, "cap_Start")
            print(f"[Auto] Lần chụp tiếp theo: {target.strftime('%H:%M:%S')}")

            while self.is_running:
                now = datetime.now()
                if now >= target:
                    capture_window_by_hwnd(hwnd, title, self.save_folder)
                    target += delta
                    print(f"[Auto] Lịch tiếp theo: {target.strftime('%H:%M:%S')}")
                time.sleep(0.5)

        except Exception:
            messagebox.showerror(
                "Lỗi",
                "Định dạng thời gian bắt đầu không hợp lệ (phải là HH:MM:SS)",
            )

    def _on_click_capture(self):
        idx = self.cb_windows.current()
        if idx == -1:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một cửa sổ để chụp!")
            return

        hwnd = self.windows_data[idx][1]
        title = self.windows_data[idx][0]
        folder = self.entry_folder.get().strip()
        os.makedirs(folder, exist_ok=True)

        threading.Thread(
            target=capture_window_by_hwnd,
            args=(hwnd, title, folder, "cap_manual"),
            daemon=True,
        ).start()

    def _turn_off_monitor(self):
        try:
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể tắt màn hình: {e}")
