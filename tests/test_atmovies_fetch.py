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
        succeeded = Mock(content=b'<meta charset=utf-8>ok', apparent_encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
