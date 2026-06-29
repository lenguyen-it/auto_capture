import win32gui
import win32ui
import win32con
import win32process
from PIL import Image
import time
import os
import ctypes
from ctypes import windll
from datetime import datetime, timedelta
import threading
import psutil


import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import tkinter.filedialog as filedialog

# --- Constant cho DwmGetWindowAttribute ---
DWMWA_CLOAKED = 14


def is_window_cloaked(hwnd):
    """
    Kiểm tra cửa sổ có đang bị 'cloaked' không.
    Cloaked = ẩn bởi hệ thống (UWP apps chạy ngầm, virtual desktop khác, v.v.)
    IsWindowVisible() KHÔNG phát hiện được trường hợp này.
    """
    cloaked_val = ctypes.c_int(0)
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked_val), ctypes.sizeof(cloaked_val)
    )
    # result == 0 là S_OK, cloaked_val != 0 nghĩa là đang bị ẩn
    return result == 0 and cloaked_val.value != 0


# --- HÀM LỌC CỬA SỔ TRÊN TASKBAR ---
def get_all_visible_windows():
    windows_list = []

    def enum_windows_callback(temp_hwnd, extra):
        # 1. Phải có flag visible
        if not win32gui.IsWindowVisible(temp_hwnd):
            return True

        # 2. Phải có tiêu đề
        title = win32gui.GetWindowText(temp_hwnd)
        if not title.strip():
            return True

        # 3. Loại bỏ cửa sổ đang thu nhỏ xuống taskbar (minimized/iconic)
        if win32gui.IsIconic(temp_hwnd):
            return True

        # 4. Loại bỏ cửa sổ bị "cloaked" — ẩn bởi hệ thống
        #    (UWP apps trên virtual desktop khác, Windows Store apps chạy nền, v.v.)
        if is_window_cloaked(temp_hwnd):
            return True

        ex_style = win32gui.GetWindowLong(temp_hwnd, win32con.GWL_EXSTYLE)
        owner = win32gui.GetWindow(temp_hwnd, win32con.GW_OWNER)

        # 5. Điều kiện taskbar: không phải ToolWindow, không có owner
        #    HOẶC có AppWindow style (override cả 2 điều kiện trên)
        is_tool_window = ex_style & win32con.WS_EX_TOOLWINDOW
        is_app_window = ex_style & win32con.WS_EX_APPWINDOW

        if not ((not is_tool_window and owner == 0) or is_app_window):
            return True

        # 6. Kích thước hợp lý — cửa sổ thật phải đủ lớn
        left, top, right, bot = win32gui.GetWindowRect(temp_hwnd)
        if (right - left) <= 100 or (bot - top) <= 100:
            return True

        windows_list.append((title, temp_hwnd))
        return True

    win32gui.EnumWindows(enum_windows_callback, None)
    # Sắp xếp danh sách theo bảng chữ cái
    return sorted(windows_list, key=lambda x: x[0].lower())


# --- HÀM CHỤP MÀN HÌNH THEO HWND ---
def capture_window_by_hwnd(hwnd, title, base_folder, file_prefix="cap"):
    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
        print(f"Cửa sổ '{title}' đã bị đóng hoặc ẩn.")
        return False

    left, top, right, bot = win32gui.GetWindowRect(hwnd)
    w = right - left
    h = bot - top

    if w <= 0 or h <= 0:
        print(f"Cửa sổ '{title}' bị chặn hoặc đang thu nhỏ.")
        return False

    try:
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()

        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(saveBitMap)

        result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)

        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        im = Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr,
            "raw",
            "BGRX",
            0,
            1,
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

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            output_filename = os.path.join(target_dir, f"{file_prefix}_{timestamp}.png")

            im.save(output_filename)
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] Đã chụp: '{title}' -> {output_filename}"
            )
            return True
    except Exception as e:
        print(f"Lỗi khi chụp: {str(e)}")
    return False


# --- HÀM CHẠY VÒNG LẶP THEO LỊCH ---
def start_schedule_loop(hwnd, title, start_time_str, interval_val, unit, base_folder):
    try:
        now = datetime.now()
        target_time = datetime.strptime(
            f"{now.strftime('%Y-%m-%d')} {start_time_str}", "%Y-%m-%d %H:%M:%S"
        )

        # Thiết lập bước nhảy (phút hoặc giây)
        time_delta = (
            timedelta(minutes=interval_val)
            if unit == "Phút"
            else timedelta(seconds=interval_val)
        )

        # Nếu thời gian đặt đã trôi qua, tự động tính mốc tiếp theo trong tương lai
        if now > target_time:
            while now > target_time:
                target_time += time_delta

        print(f"Đã kích hoạt lịch chụp tự động!")
        print(f"Cửa sổ mục tiêu: '{title}'")

        print("[Start] Thực hiện phát chụp đầu tiên ngay lập tức...")
        capture_window_by_hwnd(hwnd, title, base_folder, file_prefix="cap_Start")

        print(
            f"Phát chụp định kỳ tiếp theo sẽ vào lúc: {target_time.strftime('%H:%M:%S')}"
        )

        while is_running:
            current_now = datetime.now()
            if current_now >= target_time:
                capture_window_by_hwnd(hwnd, title, base_folder)
                target_time += time_delta
                print(
                    f"Lịch chụp tiếp theo đặt vào lúc: {target_time.strftime('%H:%M:%S')}"
                )
            time.sleep(0.5)

    except Exception as e:
        messagebox.showerror(
            "Lỗi dữ liệu", "Định dạng thời gian bắt đầu không hợp lệ (Phải là HH:MM:SS)"
        )


def select_folder_save_capture():
    global save_folder
    folder = filedialog.askdirectory(title="Chọn thư mục lưu ảnh chụp")
    if folder:
        save_folder = folder
        entry_folder.delete(0, tk.END)
        entry_folder.insert(0, save_folder)


# --- XỬ LÝ SỰ KIỆN NÚT TRÊN GUI ---
is_running = False
schedule_thread = None


def on_click_start():
    global is_running, schedule_thread, save_folder

    save_folder = entry_folder.get().strip()
    if not os.path.exists(save_folder):
        os.makedirs(save_folder)

    if is_running:
        is_running = False
        btn_start.config(text="BẮT ĐẦU CHẠY", bg="green", fg="white")
        lbl_status.config(text="Trạng thái: Đang dừng", fg="red")
        return

    selected_idx = cb_windows.current()
    if selected_idx == -1:
        messagebox.showwarning("Cảnh báo", "Vui lòng chọn một cửa sổ để chụp!")
        return

    hwnd = windows_data[selected_idx][1]
    title = windows_data[selected_idx][0]
    start_time = entry_start_time.get().strip()
    unit = cb_unit.get()

    try:
        interval = int(entry_interval.get().strip())
        if interval <= 0:
            raise ValueError
    except ValueError:
        messagebox.showwarning(
            "Cảnh báo", f"Khoảng thời gian lặp lại phải là một số nguyên dương!"
        )
        return

    is_running = True
    btn_start.config(text="DỪNG LẠI", bg="red", fg="white")
    lbl_status.config(text=f"Đang chạy tự động: {title[:30]}...", fg="green")

    schedule_thread = threading.Thread(
        target=start_schedule_loop,
        args=(hwnd, title, start_time, interval, unit, save_folder),
        daemon=True,
    )
    schedule_thread.start()


def refresh_windows():
    global windows_data
    windows_data = get_all_visible_windows()
    titles = [win[0] for win in windows_data]
    cb_windows["values"] = titles
    if titles:
        cb_windows.current(0)
    else:
        cb_windows.set("Không tìm thấy cửa sổ nào phù hợp")


# --- THIẾT KẾ GIAO DIỆN ---
root = tk.Tk()
root.title("Tự Động Chụp Màn Hình Cửa Sổ")
root.geometry("520x340")
root.resizable(True, True)

# Chọn cửa sổ cần chụp
lbl1 = tk.Label(
    root,
    text="Chọn cửa sổ muốn chụp (chỉ cửa sổ hiển thị không bị ẩn) :",
    font=("Arial", 10, "bold"),
)
lbl1.pack(anchor="w", padx=15, pady=5)

frame_cb = tk.Frame(root)
frame_cb.pack(fill="x", padx=15)

windows_data = []
cb_windows = ttk.Combobox(frame_cb, state="readonly", font=("Arial", 9))
cb_windows.pack(side="left", fill="x", expand=True)

btn_refresh = tk.Button(
    frame_cb, text="Làm mới", command=refresh_windows, font=("Arial", 9)
)
btn_refresh.pack(side="right", padx=5)

# Chọn folder
# save_folder = "screenshots"
save_folder = os.path.abspath("screenshots")
lbl_folder_title = tk.Label(
    root, text="Chọn folder muốn lưu ảnh:", font=("Arial", 10, "bold")
)
lbl_folder_title.pack(anchor="w", padx=15, pady=5)

frame_folder = tk.Frame(root)
frame_folder.pack(fill="x", padx=15)

entry_folder = tk.Entry(frame_folder, font=("Arial", 10))
# entry_folder.insert(0, save_folder)
entry_folder.pack(side="left", fill="x", expand=True)

entry_folder.config(state="normal")
entry_folder.insert(0, save_folder)
entry_folder.config(state="readonly")

btn_folder = tk.Button(
    frame_folder,
    text="Chọn thư mục",
    command=select_folder_save_capture,
    font=("Arial", 9),
)
btn_folder.pack(side="right")

# Thời gian bắt đầu
lbl2 = tk.Label(
    root,
    text="Thời gian bắt đầu (Định dạng Giờ:Phút:Giây):",
    font=("Arial", 10, "bold"),
)
lbl2.pack(anchor="w", padx=15, pady=5)

default_start = (datetime.now() + timedelta(minutes=1)).strftime("%H:%M:%S")
entry_start_time = tk.Entry(root, font=("Arial", 10))
entry_start_time.insert(0, default_start)
entry_start_time.pack(fill="x", padx=15)

# Thời gian chụp mỗi lần + Đơn vị lựa chọn
lbl3 = tk.Label(root, text="Khoảng cách giữa các lần chụp:", font=("Arial", 10, "bold"))
lbl3.pack(anchor="w", padx=15, pady=5)

frame_time = tk.Frame(root)
frame_time.pack(fill="x", padx=15)

entry_interval = tk.Entry(frame_time, font=("Arial", 10))
entry_interval.insert(0, "30")
entry_interval.pack(side="left", fill="x", expand=True)

cb_unit = ttk.Combobox(
    frame_time, values=["Phút", "Giây"], state="readonly", width=8, font=("Arial", 10)
)
cb_unit.current(0)
cb_unit.pack(side="right", padx=5)

# --- TRẠNG THÁI HIỂN THỊ ---
lbl_status = tk.Label(
    root, text="Trạng thái: Đang dừng", font=("Arial", 10, "italic"), fg="red"
)
lbl_status.pack(pady=10)

# --- NÚT KÍCH HOẠT ---
btn_start = tk.Button(
    root,
    text="BẮT ĐẦU CHẠY",
    font=("Arial", 12, "bold"),
    bg="green",
    fg="white",
    command=on_click_start,
)
btn_start.pack(fill="x", padx=40, pady=5)

# Tạo dữ liệu ban đầu cho menu thả xuống
refresh_windows()

# Chạy giao diện
root.mainloop()
