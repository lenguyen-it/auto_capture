import ctypes
import os
import subprocess
import threading
import time
from datetime import datetime

import numpy as np
import win32con
import win32gui
import win32ui
from PIL import Image, ImageDraw

from src.core.app_config import load_config

# ---------------------------------------------------------------------------
# Ghi màn hình: chụp frame liên tục (BitBlt, giống capture.grab_region) và
# pipe từng frame vào ffmpeg (qua imageio-ffmpeg) để encode video.
# ---------------------------------------------------------------------------


def _grab_frame(left: int, top: int, w: int, h: int) -> Image.Image | None:
    """Chụp một frame vùng màn hình (x, y, w, h). Không lưu file."""
    if w <= 0 or h <= 0:
        return None
    try:
        hdesktop = win32gui.GetDesktopWindow()
        desktop_dc = win32gui.GetWindowDC(hdesktop)
        mfc_dc = win32ui.CreateDCFromHandle(desktop_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        save_bmp = win32ui.CreateBitmap()
        save_bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(save_bmp)

        save_dc.BitBlt((0, 0), (w, h), mfc_dc, (left, top), win32con.SRCCOPY)

        bmpinfo = save_bmp.GetInfo()
        bmpstr = save_bmp.GetBitmapBits(True)
        im = Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr,
            "raw",
            "BGRX",
            0,
            1,
        )

        win32gui.DeleteObject(save_bmp.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hdesktop, desktop_dc)

        return im
    except Exception as e:
        print(f"Lỗi khi chụp frame: {e}")
        return None


def _grab_window_frame(hwnd: int, w: int, h: int) -> Image.Image | None:
    """Chụp một frame nội dung cửa sổ bằng PrintWindow (giống capture.capture_window_by_hwnd).

    Không phụ thuộc cửa sổ có bị cửa sổ khác che hay không, chỉ cần cửa sổ
    còn tồn tại (kể cả bị che hoàn toàn hoặc chạy phía sau app khác).
    """
    if w <= 0 or h <= 0:
        return None
    try:
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        save_bmp = win32ui.CreateBitmap()
        save_bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(save_bmp)

        result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)

        bmpinfo = save_bmp.GetInfo()
        bmpstr = save_bmp.GetBitmapBits(True)
        im = Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr,
            "raw",
            "BGRX",
            0,
            1,
        )

        win32gui.DeleteObject(save_bmp.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)

        return im if result == 1 else None
    except Exception as e:
        print(f"Lỗi khi chụp frame cửa sổ: {e}")
        return None


def _draw_cursor(im: Image.Image, origin_x: int, origin_y: int) -> Image.Image:
    """Vẽ highlight con trỏ chuột (và hiệu ứng click) lên frame."""
    try:
        # Stub pywin32 khai báo sai kiểu trả về (tuple[int,int,int,int]); thực tế
        # GetCursorInfo() trả về (flags, hcursor, (x, y)).
        flags, _hcursor, (cx, cy) = win32gui.GetCursorInfo()  # type: ignore[misc]
        if flags != win32con.CURSOR_SHOWING:
            return im

        x, y = cx - origin_x, cy - origin_y
        draw = ImageDraw.Draw(im, "RGBA")

        # Con trỏ: vòng tròn vàng bán trong suốt
        r = 10
        draw.ellipse(
            (x - r, y - r, x + r, y + r),
            fill=(255, 235, 59, 90),
            outline=(255, 193, 7, 220),
            width=2,
        )

        # Click trái/phải: viền đỏ nổi bật thêm quanh con trỏ
        left_down = ctypes.windll.user32.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000
        right_down = ctypes.windll.user32.GetAsyncKeyState(win32con.VK_RBUTTON) & 0x8000
        if left_down or right_down:
            r2 = r + 6
            draw.ellipse(
                (x - r2, y - r2, x + r2, y + r2),
                outline=(255, 23, 68, 230),
                width=3,
            )
    except Exception as e:
        print(f"Lỗi khi vẽ con trỏ: {e}")
    return im


class ScreenRecorder:
    """Ghi màn hình thành file video, chạy trên thread riêng.

    Có 2 nguồn frame:
    - region (x, y, w, h): BitBlt vùng màn hình cố định (desktop / vùng chọn tự do).
      Bị cửa sổ khác che lên là sẽ dính vào video.
    - hwnd: PrintWindow lấy đúng nội dung một cửa sổ, giống capture.capture_window_by_hwnd
      dùng cho chụp ảnh. Không phụ thuộc cửa sổ có bị che hay không, chỉ cần cửa sổ
      còn tồn tại (không cần ở foreground, không cần app này ẩn đi).

    Dùng ffmpeg (qua imageio-ffmpeg) nhận frame RGB thô qua stdin và encode
    thành MP4 (H.264), WebM (VP9) hoặc GIF, theo cấu hình trong Cài Đặt.
    """

    def __init__(
        self,
        region: tuple[int, int, int, int] | None = None,
        out_path: str = "",
        fps: int = 15,
        highlight_cursor: bool = True,
        video_format: str = "MP4",
        video_quality: int = 23,
        on_status=None,
        hwnd: int | None = None,
    ):
        self.hwnd = hwnd
        if hwnd is not None:
            left, top, right, bot = win32gui.GetWindowRect(hwnd)
        else:
            if region is None:
                raise ValueError("Phải truyền region hoặc hwnd")
            x1, y1, x2, y2 = region
            left, top = min(x1, x2), min(y1, y2)
            right, bot = max(x1, x2), max(y1, y2)

        self.left, self.top = left, top
        self.width = right - left
        self.height = bot - top
        # ffmpeg yêu cầu kích thước chẵn cho H.264/VP9
        self.width -= self.width % 2
        self.height -= self.height % 2

        self.out_path = out_path
        self.fps = max(1, fps)
        self.highlight_cursor = highlight_cursor
        self.video_format = video_format
        self.video_quality = video_quality
        self.on_status = on_status

        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None
        self._running = False
        self._paused = False
        self._frame_count = 0

    def start(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Vùng ghi không hợp lệ")
        self._proc = self._spawn_ffmpeg()
        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _spawn_ffmpeg(self) -> subprocess.Popen:
        import imageio_ffmpeg

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

        os.makedirs(os.path.dirname(self.out_path), exist_ok=True)

        cmd = [
            ffmpeg_exe,
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "-",
        ]

        fmt = self.video_format.upper()
        if fmt == "MP4":
            cmd += [
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "veryfast",
                "-crf", str(self.video_quality),
            ]
        elif fmt == "WEBM":
            cmd += [
                "-c:v", "libvpx-vp9",
                "-pix_fmt", "yuv420p",
                "-crf", str(self.video_quality),
                "-b:v", "0",
            ]
        elif fmt == "GIF":
            cmd += [
                "-vf", "split[a][b];[a]palettegen[p];[b][p]paletteuse",
            ]
        else:
            raise ValueError(f"Định dạng video không hỗ trợ: {self.video_format}")

        cmd.append(self.out_path)

        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def _run(self):
        frame_interval = 1.0 / self.fps
        next_time = time.perf_counter()

        try:
            while self._running:
                if self._paused:
                    time.sleep(0.1)
                    next_time = time.perf_counter()
                    continue

                if self.hwnd is not None:
                    if not win32gui.IsWindow(self.hwnd):
                        print("Cửa sổ đang ghi đã bị đóng, dừng ghi hình.")
                        break
                    im = _grab_window_frame(self.hwnd, self.width, self.height)
                else:
                    im = _grab_frame(self.left, self.top, self.width, self.height)

                if im is not None:
                    if self.highlight_cursor:
                        im = _draw_cursor(im, self.left, self.top)
                    if self._proc and self._proc.stdin:
                        try:
                            self._proc.stdin.write(np.array(im).tobytes())
                        except (BrokenPipeError, OSError):
                            break
                    self._frame_count += 1
                    if self.on_status:
                        self.on_status(self._frame_count)

                next_time += frame_interval
                sleep_time = next_time - time.perf_counter()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    next_time = time.perf_counter()
        finally:
            self._running = False
            if self._proc and self._proc.stdin:
                try:
                    self._proc.stdin.close()
                except OSError:
                    pass
            if self._proc:
                self._proc.wait(timeout=30)


def default_output_path(base_folder: str, video_format: str, prefix: str = "record") -> str:
    """Tạo đường dẫn file output theo pattern base_folder/YYYY-MM-DD/{prefix}_{timestamp}.{ext}."""
    current_date = datetime.now().strftime("%Y-%m-%d")
    target_dir = os.path.join(base_folder, current_date)
    os.makedirs(target_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    ext = video_format.lower()
    return os.path.join(target_dir, f"{prefix}_{timestamp}.{ext}")


def is_ffmpeg_available() -> bool:
    try:
        import imageio_ffmpeg

        return bool(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return False


def get_record_config() -> dict:
    config = load_config()
    return {
        "video_format": config.get("video_format", "MP4"),
        "video_fps": config.get("video_fps", 15),
        "video_quality": config.get("video_quality", 23),
        "highlight_cursor": config.get("highlight_cursor", True),
    }
