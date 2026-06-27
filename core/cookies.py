import os
import sys
import shutil


def _appdata_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.path.expanduser("~")
    return os.path.join(base, "Sassi Downloader")


PLATFORMS = {
    "instagram": {"file": "instagram.txt", "required": ["sessionid"], "label": "Instagram"},
    "youtube": {"file": "youtube.txt", "required": ["SID", "__Secure-1PSID"], "label": "YouTube"},
    "tiktok": {"file": "tiktok.txt", "required": ["sessionid", "ttwid"], "label": "TikTok"},
    "facebook": {"file": "facebook.txt", "required": ["xs", "c_user"], "label": "Facebook"},
    "twitter": {"file": "twitter.txt", "required": ["auth_token", "ct0"], "label": "X (Twitter)"},
    "reddit": {"file": "reddit.txt", "required": ["loid"], "label": "Reddit"},
}


class CookieManager:
    def __init__(self):
        self._dir = os.path.join(_appdata_dir(), "cookies")
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, site):
        info = PLATFORMS.get(site)
        if info:
            return os.path.join(self._dir, info["file"])
        return os.path.join(self._dir, f"{site}.txt")

    def has(self, site):
        p = self._path(site)
        return os.path.exists(p) and os.path.getsize(p) > 50

    def get_path(self, site):
        p = self._path(site)
        return p if self.has(site) else None

    def import_file(self, source_path):
        if not os.path.exists(source_path):
            return False, "File not found"
        if os.path.getsize(source_path) < 50:
            return False, "File is empty or too small"

        try:
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return False, "Could not read file"

        if "Netscape" not in content and "# HttpOnly" not in content and "version" not in content.lower():
            return False, "Not a valid Netscape cookies file"

        domains_found = self._extract_domains(content)
        imported = []
        for site, info in PLATFORMS.items():
            if any(d.endswith(site) or site in d for d in domains_found):
                required = info["required"]
                has_required = self._check_required(content, required)
                dest = self._path(site)
                shutil.copy2(source_path, dest)
                status = "complete" if has_required else "partial"
                imported.append((info["label"], status))

        if not imported:
            return False, "No supported platform cookies found in file"

        return True, imported

    def _extract_domains(self, content):
        domains = set()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                domains.add(parts[0].lstrip(".").lower())
        return domains

    def _check_required(self, content, required):
        found = 0
        for line in content.splitlines():
            if line.startswith("#") or not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 6:
                cookie_name = parts[5]
                if cookie_name in required:
                    found += 1
        return found >= 1

    def get_status(self):
        result = []
        for site, info in PLATFORMS.items():
            has = self.has(site)
            result.append((info["label"], "Imported" if has else "Not configured"))
        return result

    def get_best_cookie_file(self, url=""):
        url_lower = url.lower()
        for site in PLATFORMS:
            if site in url_lower and self.has(site):
                return self.get_path(site)
        for site in PLATFORMS:
            if self.has(site):
                return self.get_path(site)
        return None
