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
    "instagram": {
        "file": "instagram.txt",
        "domains": ["instagram.com"],
        "recommended": ["sessionid", "csrftoken", "ds_user_id", "mid", "ig_did"],
        "label": "Instagram",
    },
    "youtube": {
        "file": "youtube.txt",
        "domains": ["youtube.com", "google.com", "googlevideo.com", "ytimg.com"],
        "recommended": ["SID", "__Secure-1PSID", "HSID", "SSID", "LOGIN_INFO"],
        "label": "YouTube",
    },
    "tiktok": {
        "file": "tiktok.txt",
        "domains": ["tiktok.com"],
        "recommended": ["sessionid", "ttwid", "passport_auth_status", "sid_guard"],
        "label": "TikTok",
    },
    "facebook": {
        "file": "facebook.txt",
        "domains": ["facebook.com", "fb.com", "messenger.com", "instagram.com"],
        "recommended": ["xs", "c_user", "fr", "datr", "sb", "presence"],
        "label": "Facebook",
    },
    "twitter": {
        "file": "twitter.txt",
        "domains": ["x.com", "twitter.com", "t.co"],
        "recommended": ["auth_token", "ct0", "gt", "dnt"],
        "label": "X (Twitter)",
    },
    "reddit": {
        "file": "reddit.txt",
        "domains": ["reddit.com", "redd.it", "redditstatic.com"],
        "recommended": ["loid", "session", "csrf_token", "edgebucket"],
        "label": "Reddit",
    },
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

        data_lines = [l for l in content.splitlines() if l.strip() and not l.startswith("#")]

        imported = []
        for site, info in PLATFORMS.items():
            site_domains = info["domains"]
            matching = []
            for line in data_lines:
                parts = line.split("\t")
                if len(parts) >= 3:
                    domain = parts[0].lower()
                    bare_domain = domain.lstrip(".")
                    if bare_domain in site_domains or any(bare_domain.endswith("." + d) for d in site_domains):
                        matching.append(line)

            if not matching:
                continue

            dest = self._path(site)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(NETSCAPE_HEADER)
                for line in matching:
                    f.write(line + "\n")

            recommended = info.get("recommended", [])
            found_names = set()
            for line in matching:
                parts = line.split("\t")
                if len(parts) >= 6:
                    found_names.add(parts[5])

            missing = [r for r in recommended if r not in found_names]
            if not missing:
                status = "complete"
            elif len(missing) < len(recommended):
                status = f"partial (missing: {', '.join(missing[:3])})"
            else:
                status = "missing key cookies"

            imported.append((info["label"], status))

        if not imported:
            return False, "No supported platform cookies found in file"

        return True, imported

    def get_status(self):
        result = []
        for site, info in PLATFORMS.items():
            has = self.has(site)
            if not has:
                result.append((info["label"], "Not configured"))
                continue
            try:
                with open(self._path(site), "r", errors="ignore") as f:
                    content = f.read()
                found_names = set()
                for line in content.splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 6:
                        found_names.add(parts[5])
                recommended = info.get("recommended", [])
                missing = [r for r in recommended if r not in found_names]
                if not missing:
                    result.append((info["label"], "Imported"))
                elif len(missing) < len(recommended):
                    result.append((info["label"], f"Partial (missing: {', '.join(missing[:2])})"))
                else:
                    result.append((info["label"], "Missing key cookies"))
            except Exception:
                result.append((info["label"], "Imported"))
        return result

    def get_best_cookie_file(self, url=""):
        url_lower = url.lower()
        for site, info in PLATFORMS.items():
            if any(d in url_lower for d in info["domains"]) and self.has(site):
                return self.get_path(site)
        return None
