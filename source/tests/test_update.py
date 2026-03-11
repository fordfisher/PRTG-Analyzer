from __future__ import annotations

import json
import sys
import tempfile
import time
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import app as app_module
from analyzer.version import ANALYZER_VERSION

client = TestClient(app_module.app)

FAKE_RELEASE = {
    "tag_name": "v99.0",
    "html_url": "https://github.com/test/repo/releases/tag/v99.0",
    "assets": [
        {
            "name": "PyPRTG_CLA_v99.0.zip",
            "browser_download_url": "https://github.com/test/repo/releases/download/v99.0/PyPRTG_CLA_v99.0.zip",
        }
    ],
}

FAKE_RELEASE_SAME = {
    "tag_name": f"v{ANALYZER_VERSION}",
    "html_url": "https://github.com/test/repo/releases/tag/v1.3",
    "assets": [],
}


def _mock_urlopen(data: dict):
    """Return a context-manager mock that reads *data* as JSON."""
    body = json.dumps(data).encode()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=BytesIO(body))
    cm.__exit__ = MagicMock(return_value=False)
    return cm


class TestUpdateCheck:
    """Tests for GET /api/update-check."""

    def setup_method(self):
        app_module._UPDATE_CACHE.clear()

    @patch("app.urllib.request.urlopen")
    def test_newer_version_available(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(FAKE_RELEASE)
        resp = client.get("/api/update-check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["current"] == ANALYZER_VERSION
        assert body["latest"] == "99.0"
        assert body["up_to_date"] is False
        assert "PyPRTG_CLA_v99.0.zip" in body["download_url"]

    @patch("app.urllib.request.urlopen")
    def test_already_up_to_date(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(FAKE_RELEASE_SAME)
        resp = client.get("/api/update-check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["up_to_date"] is True

    @patch("app.urllib.request.urlopen")
    def test_cache_is_used(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(FAKE_RELEASE)
        client.get("/api/update-check")
        mock_urlopen.return_value = _mock_urlopen(FAKE_RELEASE_SAME)
        resp = client.get("/api/update-check")
        body = resp.json()
        assert body["latest"] == "99.0", "Should still return cached result"
        assert mock_urlopen.call_count == 1

    @patch("app.urllib.request.urlopen")
    def test_cache_expires(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(FAKE_RELEASE)
        client.get("/api/update-check")
        app_module._UPDATE_CACHE["checked_at"] = time.time() - 7200
        mock_urlopen.return_value = _mock_urlopen(FAKE_RELEASE_SAME)
        resp = client.get("/api/update-check")
        body = resp.json()
        assert body["up_to_date"] is True, "Cache expired, should re-fetch"
        assert mock_urlopen.call_count == 2

    @patch("app.urllib.request.urlopen", side_effect=Exception("network down"))
    def test_network_error_returns_up_to_date(self, mock_urlopen):
        resp = client.get("/api/update-check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["up_to_date"] is True
        assert "error" in body


class TestApplyUpdate:
    """Tests for POST /api/apply-update."""

    def test_rejects_when_not_frozen(self):
        resp = client.post("/api/apply-update")
        assert resp.status_code == 400
        assert "packaged EXE" in resp.json()["detail"]

    @patch("app.urllib.request.urlopen")
    def test_rejects_when_already_up_to_date(self, mock_urlopen):
        app_module._UPDATE_CACHE.clear()
        mock_urlopen.return_value = _mock_urlopen(FAKE_RELEASE_SAME)
        with patch("app.getattr", return_value=True):
            with patch.object(app_module.sys, "frozen", True, create=True):
                resp = client.post("/api/apply-update")
                assert resp.status_code == 400

    @patch("app.subprocess.Popen")
    @patch("app.os._exit")
    @patch("threading.Timer")
    @patch("app.urllib.request.urlretrieve")
    @patch("app._install_dir")
    @patch("app.urllib.request.urlopen")
    def test_apply_update_downloads_extracts_and_launches(
        self,
        mock_urlopen,
        mock_install_dir,
        mock_urlretrieve,
        mock_timer,
        mock_exit,
        mock_popen,
    ):
        """With a real zip, apply-update extracts and runs batch + launch (Timer runs immediately)."""
        app_module._UPDATE_CACHE.clear()
        mock_urlopen.return_value = _mock_urlopen(FAKE_RELEASE)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            current_dir = tmp_path / "PyPRTG_CLA_current"
            current_dir.mkdir()
            mock_install_dir.return_value = current_dir

            # Zip: PyPRTG_CLA_v99.0/apply-update.bat and PyPRTG_CLA_v99.0/PyPRTG_CLA.exe
            zip_buf = BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("PyPRTG_CLA_v99.0/apply-update.bat", "@echo off\n")
                zf.writestr("PyPRTG_CLA_v99.0/PyPRTG_CLA.exe", b"")
            zip_buf.seek(0)
            zip_bytes = zip_buf.read()

            def copy_zip(url, path):
                Path(path).write_bytes(zip_bytes)

            mock_urlretrieve.side_effect = copy_zip

            # Run scheduled callbacks immediately so launch runs during request
            def run_now(interval, func):
                func()
                return MagicMock()  # .start() is called on this

            mock_timer.side_effect = run_now
            mock_exit.side_effect = lambda _: None

            with patch.object(app_module.sys, "frozen", True, create=True):
                resp = client.post("/api/apply-update")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "updating"
        assert body["new_version"] == "99.0"

        # Batch was started
        popen_calls = [c[0][0] for c in mock_popen.call_args_list]
        assert any("apply-update.bat" in str(c) for c in popen_calls)

        # On Windows, launch uses cmd /C start ... exe
        if sys.platform == "win32":
            start_calls = [
                args
                for args in popen_calls
                if isinstance(args, (list, tuple)) and len(args) >= 5 and args[2] == "start"
            ]
            assert start_calls, "Expected Popen(cmd /C start ... exe)"
            assert any("PyPRTG_CLA.exe" in str(args) for args in start_calls)


class TestVersionTuple:
    """Tests for _version_tuple helper."""

    def test_basic(self):
        assert app_module._version_tuple("1.3") == (1, 3)

    def test_strips_v(self):
        assert app_module._version_tuple("v2.0") == (2, 0)

    def test_three_part(self):
        assert app_module._version_tuple("1.3.7") == (1, 3, 7)

    def test_comparison(self):
        assert app_module._version_tuple("1.4") > app_module._version_tuple("1.3")
        assert app_module._version_tuple("2.0") > app_module._version_tuple("1.99")
        assert app_module._version_tuple("1.3") >= app_module._version_tuple("1.3")
