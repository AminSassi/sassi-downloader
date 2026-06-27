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
    "instagram": {"file": "instagram.txt", "domains": ["instagram.com"], "required": ["sessionid"], "label": "Instagram"},
    "youtube": {"file": "youtube.txt", "domains": ["youtube.com", "google.com"], "required": ["SID"], "label": "YouTube"},
    "tiktok": {"file": "tiktok.txt", "domains": ["tiktok.com"], "required": ["sessionid", "ttwid"], "label": "TikTok"},
    "facebook": {"file": "facebook.txt", "domains": ["facebook.com", "fb.com"], "required": ["xs", "c_user"], "label": "Facebook"},
    "twitter": {"file": "twitter.txt", "domains": ["x.com", "twitter.com", "t.co"], "required": ["auth_token", "ct0"], "label": "X (Twitter)"},
    "reddit": {"file": "reddit.txt", "domains": ["reddit.com"], "required": ["loid"], "label": "Reddit"},
}

NETSCAPE_HEADER = "# Netscape HTTP Cookie File\n# https://curl.haxx.se/rfc/cookie_spec.html\n\n"


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

        all_lines = content.splitlines()
        header_lines = [l for l in all_lines if l.startswith("#") or not l.strip()]
        data_lines = [l for l in all_lines if l.strip() and not l.startswith("#")]

        imported = []
        for site, info in PLATFORMS.items():
            site_domains = info["domains"]
            matching = []
            for line in data_lines:
                parts = line.split("\t")
                if len(parts) >= 3:
                    domain = parts[0].lstrip(".").lower()
                    if any(domain == d or domain.endswith("." + d) for d in site_domains):
                        matching.append(line)

            if not matching:
                continue

            required = info["required"]
            has_required = self._check_required(matching, required)
            status = "complete" if has_required else "partial"

            dest = self._path(site)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(NETSCAPE_HEADER)
                for line in matching:
                    f.write(line + "\n")

            imported.append((info["label"], status))

        if not imported:
            return False, "No supported platform cookies found in file"

        return True, imported

    def _check_required(self, lines, required):
        for line in lines:
            parts = line.split("\t")
            if len(parts) >= 6 and parts[5] in required:
                return True
        return False

    def get_status(self):
        result = []
        for site, info in PLATFORMS.items():
            has = self.has(site)
            result.append((info["label"], "Imported" if has else "Not configured"))
        return result

    def get_best_cookie_file(self, url=""):
        url_lower = url.lower()
        for site, info in PLATFORMS.items():
            if any(d in url_lower for d in info["domains"]) and self.has(site):
                return self.get_path(site)
        return None
