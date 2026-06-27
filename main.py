import customtkinter as ctk
import os
import sys


def main():
    from ui.main_window import SassiDownloader
    root = ctk.CTk()

    icon_paths = []
    if sys.executable:
        icon_paths.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "icon.ico"))
        icon_paths.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "_internal", "icon.ico"))
    icon_paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico"))
    for icon_path in icon_paths:
        if os.path.exists(icon_path):
            try:
                root.iconbitmap(icon_path)
            except Exception:
                pass
            break

    app = SassiDownloader(root)
    root.mainloop()


if __name__ == "__main__":
    main()
