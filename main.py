import customtkinter as ctk
import os
import sys


def main():
    from ui.main_window import SassiDownloader
    root = ctk.CTk()
    icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "icon.ico")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.exists(icon_path):
        root.iconbitmap(icon_path)
    app = SassiDownloader(root)
    root.mainloop()


if __name__ == "__main__":
    main()
