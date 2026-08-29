import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import weekly_check as weekly


class AtmoviesFetchTests(unittest.TestCase):
    @patch("weekly_check.time.sleep")
    @patch("weekly_check.requests.get")
    def test_retries_temporary_server_error_then_succeeds(self, get, sleep):
        failed = Mock()
        failed.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "502 Bad Gateway", response=Mock(status_code=502)
        )
        succeeded = Mock(
            content=b'<meta charset=utf-8>ok',
            headers={"Content-Type": "text/html"},
        )
        succeeded.raise_for_status.return_value = None
        get.side_effect = [failed, succeeded]

        result = weekly.fetch_atmovies("https://example.test/movie/next/w38/")

        self.assertIn("ok", result)
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(weekly.ATMOVIES_RETRY_DELAY)

    @patch("weekly_check.time.sleep")
    @patch("weekly_check.requests.get")
    def test_raises_after_temporary_error_retries_are_exhausted(self, get, sleep):
        error = requests.exceptions.HTTPError(
            "502 Bad Gateway", response=Mock(status_code=502)
        )
        failed = Mock()
        failed.raise_for_status.side_effect = error
        get.return_value = failed

        with self.assertRaises(requests.exceptions.HTTPError):
            weekly.fetch_atmovies("https://example.test/movie/next/w38/")

        self.assertEqual(get.call_count, weekly.ATMOVIES_RETRY_ATTEMPTS)
        self.assertEqual(sleep.call_count, weekly.ATMOVIES_RETRY_ATTEMPTS - 1)

    @patch("weekly_check.time.sleep")
    @patch("weekly_check.requests.get")
    def test_does_not_retry_non_temporary_client_error(self, get, sleep):
        error = requests.exceptions.HTTPError(
            "404 Not Found", response=Mock(status_code=404)
        )
        failed = Mock()
        failed.raise_for_status.side_effect = error
        get.return_value = failed

        with self.assertRaises(requests.exceptions.HTTPError):
            weekly.fetch_atmovies("https://example.test/missing/")

        get.assert_called_once()
        sleep.assert_not_called()

    @patch("weekly_check.requests.get")
    def test_honors_quoted_utf8_meta_instead_of_wrong_apparent_encoding(self, get):
        response = Mock(
            content='<meta charset="UTF-8" /><h1>現正上映</h1>'.encode("utf-8"),
            headers={"Content-Type": "text/html"},
            apparent_encoding="ptcp154",
        )
        response.raise_for_status.return_value = None
        get.return_value = response

        result = weekly.fetch_atmovies("https://example.test/movie/now/1/")

        self.assertIn("現正上映", result)

    @patch("weekly_check.requests.get")
    def test_honors_utf8_http_content_type(self, get):
        response = Mock(
            content="幕末太陽傳".encode("utf-8"),
            headers={"Content-Type": "text/html;charset=UTF-8"},
            apparent_encoding="ptcp154",
        )
        response.raise_for_status.return_value = None
        get.return_value = response

        self.assertEqual(
            weekly.fetch_atmovies("https://example.test/movie/now/1/"),
            "幕末太陽傳",
        )

    def test_rejects_replacement_character_in_movie_title(self):
        with self.assertRaises(UnicodeError):
            weekly.validate_atmovies_title("錯誤片�")


if __name__ == "__main__":
    unittest.main()
