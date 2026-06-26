import tkinter as tk
from ui.main_window import SassiDownloader


def main():
    root = tk.Tk()
    app = SassiDownloader(root)
    root.mainloop()


if __name__ == "__main__":
    main()
