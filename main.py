import customtkinter as ctk
import os
import sys
import hashlib


def get_build_info():
    info = {"version": "v1.1", "commit": "unknown"}
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode == 0:
            info["commit"] = result.stdout.strip()
    except Exception:
        pass
    return info


def log_build_checksum():
    try:
        exe_path = os.path.abspath(sys.executable)
        if os.path.exists(exe_path):
            h = hashlib.sha256()
            with open(exe_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            log_path = os.path.join(os.path.expanduser("~"), ".sassi_build.log")
            build = get_build_info()
            with open(log_path, 'w') as f:
                f.write(f"Sassi Downloader {build['version']}\n")
                f.write(f"Commit: {build['commit']}\n")
                f.write(f"SHA-256: {h.hexdigest()}\n")
    except Exception:
        pass


def main():
    log_build_checksum()
    build = get_build_info()
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

    root.title(f"Sassi Downloader {build['version']} ({build['commit']})")
    app = SassiDownloader(root)
    root.mainloop()


if __name__ == "__main__":
    main()
