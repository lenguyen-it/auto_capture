import ctypes
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.core.app_config import load_config
from src.core.screen_record import (
    ScreenRecorder,
    default_output_path,
    get_record_config,
    is_ffmpeg_available,
)
from src.core.window_utils import get_all_visible_windows
from src.pages.components.record_region_selector import RecordRegionSelector

# ---------------------------------------------------------------------------
# Tab ghi màn hình (record)
# ---------------------------------------------------------------------------

_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79


class PageRecord(tk.Frame):
    """Frame cho tab ghi màn hình."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#f5f5f5")

        self.save_folder = os.path.abspath("screenshots")
        self.windows_data: list[tuple[str, int]] = []
        self.region: tuple[int, int, int, int] | None = None
        self._record_hwnd: int | None = None

        self.recorder: ScreenRecorder | None = None
        self.is_recording = False
        self._elapsed_start = 0.0
        self._elapsed_paused_at = 0.0
        self._timer_job = None
        self._last_output_path: str | None = None

        self._build_ui()
        self.refresh_windows()

    # ------------------------------------------------------------------
    # Giao diện
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ===== Phần 1: Chọn nguồn quay =====
        section1 = tk.LabelFrame(
            self,
            text="Nguồn quay",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section1.pack(fill="x", padx=15, pady=(10, 4))

        self.var_mode = tk.StringVar(value="desktop")
        frame_mode = tk.Frame(section1, bg="#f5f5f5")
        frame_mode.pack(fill="x", padx=10, pady=(8, 4))

        for value, text in (
            ("desktop", "Toàn màn hình"),
            ("window", "Cửa sổ"),
            ("region", "Vùng chọn"),
        ):
            tk.Radiobutton(
                frame_mode,
                text=text,
                variable=self.var_mode,
                value=value,
                font=("Segoe UI", 10),
                bg="#f5f5f5",
                command=self._on_mode_changed,
            ).pack(side="left", padx=(0, 12))

        # --- Chọn cửa sổ (chỉ hiện khi mode = window) ---
        self.frame_window = tk.Frame(section1, bg="#f5f5f5")
        frame_cb = tk.Frame(self.frame_window, bg="#f5f5f5")
        frame_cb.pack(fill="x", padx=10, pady=4)

        self.cb_window = ttk.Combobox(
            frame_cb,
            state="readonly",
            font=("Segoe UI", 9),
        )
        self.cb_window.pack(side="left", fill="x", expand=True)
        # Danh sách cửa sổ đổi liên tục (mở/đóng/thu nhỏ) nên làm mới lại
        # ngay trước khi người dùng mở dropdown, thay vì chỉ load 1 lần.
        self.cb_window.bind("<Button-1>", self._on_window_dropdown_open)

        tk.Button(
            frame_cb,
            text="Làm mới",
            command=self.refresh_windows,
            font=("Segoe UI", 9),
            relief="flat",
            bg="#e0e0e0",
            cursor="hand2",
        ).pack(side="right", padx=(5, 0))

        # --- Chọn vùng tự do (chỉ hiện khi mode = region) ---
        self.frame_region = tk.Frame(section1, bg="#f5f5f5")
        self.lbl_region = tk.Label(
            self.frame_region,
            text="Chưa có vùng nào được chọn",
            font=("Segoe UI", 9, "italic"),
            fg="#888",
            bg="#f5f5f5",
        )
        self.lbl_region.pack(side="left", padx=10, pady=4)

        tk.Button(
            self.frame_region,
            text="Kéo chọn vùng",
            command=self._start_region_select,
            font=("Segoe UI", 9),
            relief="flat",
            bg="#e0e0e0",
            cursor="hand2",
        ).pack(side="right", padx=10, pady=4)

        self._on_mode_changed()

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

        # ===== Phần 3: Điều khiển =====
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

        frame_btns = tk.Frame(section3, bg="#f5f5f5")
        frame_btns.pack(fill="x", padx=10, pady=(8, 4))

        self.btn_record = tk.Button(
            frame_btns,
            text="BẮT ĐẦU GHI",
            font=("Segoe UI", 11, "bold"),
            bg="#c62828",
            fg="white",
            activebackground="#8e0000",
            relief="flat",
            cursor="hand2",
            command=self._toggle_record,
        )
        self.btn_record.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_pause = tk.Button(
            frame_btns,
            text="TẠM DỪNG",
            font=("Segoe UI", 11, "bold"),
            bg="#e65100",
            fg="white",
            activebackground="#bf360c",
            relief="flat",
            cursor="hand2",
            state="disabled",
            command=self._toggle_pause,
        )
        self.btn_pause.pack(side="right", fill="x", expand=True, padx=(5, 0))

        self.lbl_status = tk.Label(
            section3,
            text="Trạng thái: Sẵn sàng  |  00:00:00",
            font=("Segoe UI", 9, "italic"),
            fg="#888",
            bg="#f5f5f5",
        )
        self.lbl_status.pack(pady=(4, 8))

        self.lbl_last_file = tk.Label(
            section3,
            text="(Chưa có video nào)",
            font=("Segoe UI", 9),
            fg="#1565c0",
            bg="#f5f5f5",
            cursor="hand2",
        )
        self.lbl_last_file.pack(pady=(0, 8))
        self.lbl_last_file.bind("<Button-1>", self._open_last_video)

    def _on_mode_changed(self):
        self.frame_window.pack_forget()
        self.frame_region.pack_forget()
        mode = self.var_mode.get()
        if mode == "window":
            self.frame_window.pack(fill="x")
        elif mode == "region":
            self.frame_region.pack(fill="x")

    # ------------------------------------------------------------------
    # Chọn cửa sổ
    # ------------------------------------------------------------------

    def refresh_windows(self):
        # Ghi nhớ cửa sổ đang chọn theo hwnd để giữ nguyên lựa chọn sau khi
        # làm mới danh sách (nếu cửa sổ đó vẫn còn hợp lệ).
        idx = self.cb_window.current()
        selected_hwnd = (
            self.windows_data[idx][1]
            if 0 <= idx < len(self.windows_data)
            else None
        )

        self.windows_data = get_all_visible_windows()
        self.cb_window["values"] = [title for title, _ in self.windows_data]

        if selected_hwnd is not None:
            for i, (_title, hwnd) in enumerate(self.windows_data):
                if hwnd == selected_hwnd:
                    self.cb_window.current(i)
                    return

        if self.windows_data:
            self.cb_window.current(0)
        else:
            self.cb_window.set("")

    def _on_window_dropdown_open(self, _event=None):
        self.refresh_windows()

    # ------------------------------------------------------------------
    # Chọn vùng tự do
    # ------------------------------------------------------------------

    def _start_region_select(self):
        root = self.winfo_toplevel()
        was_visible = root.state() != "withdrawn"
        root.withdraw()
        self.after(300, lambda: self._open_overlay(root, was_visible))

    def _open_overlay(self, root, was_visible=True):
        from src.core.capture import grab_region

        selector = None
        try:
            screenshot = grab_region(
                0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
            )
            if screenshot is None:
                raise RuntimeError("Không chụp được ảnh nền màn hình")

            selector = RecordRegionSelector(
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
            if was_visible:
                root.deiconify()

    def _handle_region_selection(self, region):
        self.region = region
        x1, y1, x2, y2 = region
        self.lbl_region.config(
            text=f"Vùng: {x2 - x1} x {y2 - y1} px", fg="#1565c0", font=("Segoe UI", 9, "bold")
        )

    # ------------------------------------------------------------------
    # Lấy vùng ghi hiện tại theo mode
    # ------------------------------------------------------------------

    def _get_region_for_mode(self) -> tuple[int, int, int, int] | None:
        """Trả về vùng ghi (x1, y1, x2, y2) cho mode desktop/region.
        Với mode "window", self._record_hwnd được đặt và hàm trả về None
        vì ghi theo cửa sổ dùng PrintWindow (ScreenRecorder(hwnd=...)),
        không cần toạ độ vùng cố định."""
        self._record_hwnd = None
        mode = self.var_mode.get()

        if mode == "desktop":
            left = ctypes.windll.user32.GetSystemMetrics(_SM_XVIRTUALSCREEN)
            top = ctypes.windll.user32.GetSystemMetrics(_SM_YVIRTUALSCREEN)
            width = ctypes.windll.user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN)
            height = ctypes.windll.user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN)
            return (left, top, left + width, top + height)

        if mode == "window":
            # Làm mới + đối chiếu lại với danh sách cửa sổ đang thực sự hiển thị
            # (đã lọc: mở, không thu nhỏ, không bị cloaked) ngay trước khi ghi,
            # để không quay nhầm cửa sổ đã đóng/thu nhỏ. Không cần cửa sổ ở
            # foreground hay không bị che: PrintWindow đọc trực tiếp nội dung
            # cửa sổ, giống hệt cách chụp ảnh cửa sổ (capture_window_by_hwnd).
            title = self.cb_window.get()
            self.refresh_windows()
            current_windows = dict(
                (t, h) for t, h in self.windows_data
            )
            hwnd = current_windows.get(title)
            if hwnd is None:
                messagebox.showwarning(
                    "Chưa chọn cửa sổ",
                    "Cửa sổ đã chọn không còn mở hoặc đang bị thu nhỏ. "
                    "Vui lòng mở cửa sổ và chọn lại.",
                )
                return None

            self._record_hwnd = hwnd
            return None

        # mode == "region"
        if not self.region:
            messagebox.showwarning("Chưa chọn vùng", "Vui lòng kéo chọn vùng trước!")
            return None
        return self.region

    # ------------------------------------------------------------------
    # Ghi hình
    # ------------------------------------------------------------------

    def _toggle_record(self):
        if self.is_recording:
            self._stop_record()
        else:
            self._start_record()

    def _start_record(self):
        if not is_ffmpeg_available():
            messagebox.showerror(
                "Thiếu ffmpeg",
                "Không tìm thấy ffmpeg (thư viện imageio-ffmpeg). "
                "Vui lòng cài đặt: pip install imageio-ffmpeg",
            )
            return

        mode = self.var_mode.get()
        region = self._get_region_for_mode()
        if mode != "window" and region is None:
            return
        if mode == "window" and self._record_hwnd is None:
            return

        folder = self.entry_folder.get().strip()
        os.makedirs(folder, exist_ok=True)

        rec_config = get_record_config()
        out_path = default_output_path(folder, rec_config["video_format"])

        try:
            self.recorder = ScreenRecorder(
                region=region,
                hwnd=self._record_hwnd,
                out_path=out_path,
                fps=rec_config["video_fps"],
                highlight_cursor=rec_config["highlight_cursor"],
                video_format=rec_config["video_format"],
                video_quality=rec_config["video_quality"],
            )
            self.recorder.start()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể bắt đầu ghi hình: {e}")
            self.recorder = None
            return

        self._last_output_path = out_path
        self.is_recording = True
        self._elapsed_start = time.monotonic()
        self._elapsed_paused_at = 0.0

        self.btn_record.config(text="DỪNG GHI", bg="#546e7a")
        self.btn_pause.config(state="normal", text="TẠM DỪNG", bg="#e65100")
        self._tick_timer()

    def _toggle_pause(self):
        if not self.recorder:
            return
        if self.recorder.is_paused():
            self.recorder.resume()
            self._elapsed_start += time.monotonic() - self._elapsed_paused_at
            self.btn_pause.config(text="TẠM DỪNG", bg="#e65100")
            self.lbl_status.config(fg="#2e7d32")
        else:
            self.recorder.pause()
            self._elapsed_paused_at = time.monotonic()
            self.btn_pause.config(text="TIẾP TỤC", bg="#2e7d32")
            self.lbl_status.config(fg="#e65100")

    def _stop_record(self):
        if self._timer_job:
            self.after_cancel(self._timer_job)
            self._timer_job = None

        self.btn_record.config(text="Đang lưu video...", state="disabled")
        self.btn_pause.config(state="disabled")
        self.update_idletasks()

        recorder = self.recorder
        self.recorder = None
        self.is_recording = False

        def do_stop():
            if recorder:
                recorder.stop()
            self.after(0, self._on_record_finished)

        import threading

        threading.Thread(target=do_stop, daemon=True).start()

    def _on_record_finished(self):
        self.btn_record.config(text="BẮT ĐẦU GHI", bg="#c62828", state="normal")
        self.btn_pause.config(state="disabled", text="TẠM DỪNG", bg="#e65100")
        self._record_hwnd = None

        path = self._last_output_path
        if path and os.path.exists(path):
            self.lbl_status.config(
                text=f"Đã lưu video  |  {self._format_elapsed()}", fg="#2e7d32"
            )
            self.lbl_last_file.config(text=os.path.basename(path))
        else:
            self.lbl_status.config(text="Ghi hình thất bại", fg="#e53935")

    def _tick_timer(self):
        if not self.is_recording:
            return
        self.lbl_status.config(text=f"Đang ghi...  |  {self._format_elapsed()}")
        self._timer_job = self.after(500, self._tick_timer)

    def _format_elapsed(self) -> str:
        if self.recorder and self.recorder.is_paused():
            elapsed = self._elapsed_paused_at - self._elapsed_start
        else:
            elapsed = time.monotonic() - self._elapsed_start
        elapsed = max(0, int(elapsed))
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _open_last_video(self, _event=None):
        if self._last_output_path and os.path.exists(self._last_output_path):
            os.startfile(self._last_output_path)

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục lưu video")
        if folder:
            self.save_folder = folder
            self.entry_folder.config(state="normal")
            self.entry_folder.delete(0, tk.END)
            self.entry_folder.insert(0, folder)
            self.entry_folder.config(state="readonly")
