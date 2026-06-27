import os
import inspect
import pytest


CORE_DIR = os.path.join(os.path.dirname(__file__), '..', 'core')
UI_DIR = os.path.join(os.path.dirname(__file__), '..', 'ui')
ROOT_DIR = os.path.join(os.path.dirname(__file__), '..')

ALL_PY = []
for d in [CORE_DIR, UI_DIR, ROOT_DIR]:
    for f in os.listdir(d):
        if f.endswith('.py'):
            ALL_PY.append(os.path.join(d, f))


class TestNoDangerousCalls:
    DANGEROUS = ['os.system', 'shell=True', 'eval(', 'exec(', 'pickle.loads', 'marshal.loads']

    @pytest.mark.parametrize("filepath", ALL_PY)
    def test_no_dangerous_calls(self, filepath):
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        for pattern in self.DANGEROUS:
            assert pattern not in content, f"{os.path.basename(filepath)} contains '{pattern}'"


class TestNoBareExcept:

    @pytest.mark.parametrize("filepath", ALL_PY)
    def test_no_bare_except(self, filepath):
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f, 1):
                stripped = line.strip()
                if stripped == 'except:' or (stripped.startswith('except:') and 'Exception' not in stripped):
                    pytest.fail(f"{os.path.basename(filepath)}:{i} has bare except: {stripped}")


class TestURLValidation:
    def _validate(self, url):
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https', 'ftp') and bool(parsed.netloc)

    @pytest.mark.parametrize("url", [
        'https://youtube.com/watch?v=abc',
        'http://tiktok.com/@user/video/123',
        'https://www.instagram.com/reel/ABC123/',
        'ftp://example.com/file.zip',
    ])
    def test_valid_urls(self, url):
        assert self._validate(url), f"Should be valid: {url}"

    @pytest.mark.parametrize("url", [
        'javascript:alert(1)',
        'https://',
        'not-a-url',
        '',
        'file:///etc/passwd',
        'data:text/html,<script>',
        '//evil.com/path',
    ])
    def test_invalid_urls(self, url):
        assert not self._validate(url), f"Should be invalid: {url}"


class TestPathTraversal:
    def _sanitize(self, name):
        return ''.join(c for c in os.path.basename(name) if c.isalnum() or c in ' ._-=+()[]')

    @pytest.mark.parametrize("input_name,expected", [
        ('../../etc/passwd', 'passwd'),
        ('..\\\\..\\\\Windows\\\\cmd.exe', 'cmd.exe'),
        ('a/b/c/d.txt', 'd.txt'),
        ('normal_file.mp4', 'normal_file.mp4'),
        ('', ''),
    ])
    def test_sanitization(self, input_name, expected):
        assert self._sanitize(input_name) == expected

    def test_no_path_traversal_in_result(self):
        result = self._sanitize('../../etc/shadow')
        assert '..' not in result
        assert '/' not in result
        assert '\\' not in result
