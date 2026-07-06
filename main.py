import tkinter as tk
from tkinter import ttk

from pages.page_auto_cap_window import PageAuto
from pages.page_region import PageRegion


def build_app():
    root = tk.Tk()
    root.title("Tự Động Chụp Màn Hình")
    root.geometry("580x560")
    root.minsize(520, 500)
    root.configure(bg="#f0f0f0")

    # ---- Tiêu đề app ----
    header = tk.Frame(root, bg="#1565c0", height=40, takefocus=False)
    header.pack(fill="x")
    header.pack_propagate(False)

    tk.Label(
        header,
        text="Tự Động Chụp Màn Hình",
        font=("Segoe UI", 13, "bold"),
        fg="white",
        bg="#1565c0",
    ).pack(side="left", padx=15, pady=10)

    # ---- Taps ----
    style = ttk.Style()
    style.theme_use("clam")
    style.layout("TNotebook", [])
    style.configure("TNotebook", background="#f0f0f0", borderwidth=0, takefocus=False)

    style.configure(
        "TNotebook.Tab",
        font=("Segoe UI", 10, "bold"),
        background="#dce3f0",
        foreground="#333",
        borderwidth=0,
        takefocus=False,
    )

    style.map(
        "TNotebook.Tab",
        background=[("selected", "#1565c0")],
        foreground=[("selected", "white")],
    )

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=0, pady=0)

    # Tab 1: Chụp tự động
    tab_auto = PageAuto(notebook, bg="#f5f5f5")
    notebook.add(tab_auto, text="Chụp Tự Động")

    # Tab 2: Chụp theo vùng
    tab_region = PageRegion(notebook, bg="#f5f5f5")
    notebook.add(tab_region, text="Chụp Theo Vùng")

    root.mainloop()


if __name__ == "__main__":
    build_app()
