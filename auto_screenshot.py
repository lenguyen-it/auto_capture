import win32gui
import win32ui
import win32con
from PIL import Image
import time
import os
import ctypes
from datetime import datetime, timedelta


def capture_hidden_window(window_title_keyword, base_folder, file_prefix="cap"):
    hwnd = None
    matched_title = ""

    def enum_windows_callback(temp_hwnd, extra):
        nonlocal hwnd, matched_title  # Thêm matched_title vào nonlocal
        if win32gui.IsWindowVisible(temp_hwnd):
            title = win32gui.GetWindowText(temp_hwnd)
            # KIỂM TRA: Chứa từ khóa UltraViewer VÀ KHÔNG chứa chữ "Chat" hoặc "Bảng điều khiển"
            if (
                window_title_keyword.lower() in title.lower()
                and "chat" not in title.lower()
            ):
                # Kiểm tra thêm kích thước để chắc chắn đó là cửa sổ lớn (màn hình kết nối)
                left, top, right, bot = win32gui.GetWindowRect(temp_hwnd)
                w = right - left
                h = bot - top
                # Ước lượng kích thước tối thiểu để xác định cửa sổ kết nối UltraViewer (ví dụ: 600x600)
                if w > 600 and h > 600:
                    hwnd = temp_hwnd
                    # Lưu lại tiêu đề của cửa sổ khớp điều kiện
                    matched_title = title
                    # Tìm thấy rồi thì dừng quét
                    return False
        return True

    win32gui.EnumWindows(enum_windows_callback, None)

    if not hwnd:
        print(f"Không tìm thấy cửa sổ kết nối UltraViewer nào phù hợp!")
        return False

    left, top, right, bot = win32gui.GetWindowRect(hwnd)
    w = right - left
    h = bot - top

    if w <= 0 or h <= 0:
        print(
            f"Cửa sổ '{matched_title}' bị chặn hoặc đang thu nhỏ (Kích thước bằng 0)."
        )
        return False

    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()

    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(saveBitMap)

    # Sử dụng flag 3 (hoặc thử thay bằng 2 nếu màn hình bị đen)
    result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)

    bmpinfo = saveBitMap.GetInfo()
    bmpstr = saveBitMap.GetBitmapBits(True)
    im = Image.frombuffer(
        "RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1
    )

    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

    if result == 1:
        current_date = datetime.now().strftime("%Y-%m-%d")
        target_dir = os.path.join(base_folder, current_date)

        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
            print(f"Đã tạo thư mục ngày mới: {target_dir}")

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_filename = os.path.join(target_dir, f"{file_prefix}_{timestamp}.png")

        im.save(output_filename)
        # Hiện rõ tên cửa sổ được chụp trong log thành công
        print(
            f"📸 [{datetime.now().strftime('%H:%M:%S')}] Đã chụp thành công cửa sổ: '{matched_title}'"
        )
        print(f" Lưu tại: {output_filename}")
        return True
    else:
        print(f"❌ Lỗi không thể render hình ảnh cửa sổ: '{matched_title}'")
        return False


# --- CẤU HÌNH CHẠY TỰ ĐỘNG THEO LỊCH ---
if __name__ == "__main__":
    WINDOW_NAME = "UltraViewer"
    BASE_FOLDER = "screenshots"

    print("[BẮT ĐẦU] Tiến hành chụp ngay phát đầu tiên làm mẫu...")
    capture_hidden_window(WINDOW_NAME, BASE_FOLDER, file_prefix="cap_START")

    # Nhập time định kỳ chụp (ví dụ: 00:00:00), đổi time trực tiếp trong code nếu muốn thay đổi
    # Đặt thời gian chụp định kỳ đầu tiên là 00:00:00, sau đó cứ 30 phút sẽ chụp một lần
    target_time_str = "00:00:00"
    now = datetime.now()

    target_time = datetime.strptime(
        f"{now.strftime('%Y-%m-%d')} {target_time_str}", "%Y-%m-%d %H:%M:%S"
    )

    if now > target_time:
        while now > target_time:
            target_time += timedelta(minutes=30)

    print(f"Chụp định kỳ tiếp theo sẽ vào lúc: {target_time.strftime('%H:%M:%S')}")

    while True:
        current_now = datetime.now()

        if current_now >= target_time:
            capture_hidden_window(WINDOW_NAME, BASE_FOLDER, file_prefix="cap")
            target_time += timedelta(minutes=30)
            print(
                f"⏭️ Lịch chụp tiếp theo đặt vào lúc: {target_time.strftime('%H:%M:%S')}"
            )

        time.sleep(0.5)
