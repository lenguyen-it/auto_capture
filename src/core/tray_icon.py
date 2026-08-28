import threading

import pystray
from PIL import Image


class TrayIcon:
    """Icon khay hệ thống với menu Mở app / Thoát."""

    def __init__(self, icon_path: str, app_name: str, on_open, on_quit):
        image = Image.open(icon_path)
        menu = pystray.Menu(
            pystray.MenuItem("Mở ứng dụng", lambda: on_open(), default=True),
            pystray.MenuItem("Thoát", lambda: on_quit()),
        )
        self._icon = pystray.Icon(app_name, image, app_name, menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._icon.stop()
