import unittest
from unittest.mock import patch

import universal_video_downloader as downloader


class DownloaderUrlTests(unittest.TestCase):
    def test_normalizes_markdown_url_and_escaped_ampersand(self):
        raw = r"[https://www.rockstargames.com/videos/rk721912?resolution=2160p&embed](https://www.rockstargames.com/videos/rk721912?resolution=2160p\&embed)"

        self.assertEqual(
            downloader.normalize_url(raw),
            "https://www.rockstargames.com/videos/rk721912?resolution=2160p&embed",
        )

    def test_builds_rockstar_cdn_candidates_from_video_page(self):
        url = "https://www.rockstargames.com/videos/rk721912?resolution=2160p&embed"

        candidates = downloader.get_rockstar_video_urls(url)

        self.assertEqual(
            candidates[0],
            "https://videos-rockstargames-com.akamaized.net/v4/rk721912/flv/en-us-2160p.mp4",
        )
        self.assertIn(
            "https://videos-rockstargames-com.akamaized.net/v4/rk721912/flv/en-us-1080p.mp4",
            candidates,
        )

    def test_extracts_absolute_and_relative_media_urls_from_html(self):
        html = """
        <meta property="og:video" content="/media/trailer.mp4">
        <video><source src="https://cdn.example.test/stream.m3u8?token=1&amp;x=2"></video>
        <script>const fallback = "\\/media\\/fallback.mp4";</script>
        """

        self.assertEqual(
            downloader.extract_video_urls_from_html(
                html, "https://example.test/watch/page"
            ),
            [
                "https://example.test/media/trailer.mp4",
                "https://cdn.example.test/stream.m3u8?token=1&x=2",
                "https://example.test/media/fallback.mp4",
            ],
        )

    @patch.object(downloader, "download_with_ytdlp", return_value=True)
    def test_download_video_uses_normalized_rockstar_cdn_url(self, download_mock):
        raw = r"[Rockstar](https://www.rockstargames.com/videos/rk721912?resolution=2160p\&embed)"

        self.assertTrue(downloader.download_video(raw, output_dir="downloads"))
        self.assertEqual(
            download_mock.call_args.args[0],
            "https://videos-rockstargames-com.akamaized.net/v4/rk721912/flv/en-us-2160p.mp4",
        )

    @patch.object(downloader, "download_with_ytdlp", return_value=True)
    def test_rockstar_download_preserves_interactive_format_selection(self, download_mock):
        downloader.download_video(
            "https://www.rockstargames.com/videos/rk721912", select_format=True
        )

        self.assertTrue(download_mock.call_args.args[4])


class DownloaderOptionsTests(unittest.TestCase):
    def test_uses_modern_fallback_format_and_browser_cookies(self):
        options = downloader.build_ytdlp_options(
            "https://www.youtube.com/watch?v=demo",
            ".",
            cookie_browser="chrome",
        )

        self.assertEqual(options["format"], "bv*+ba/b")
        self.assertEqual(options["cookiesfrombrowser"], ("chrome",))
        self.assertEqual(options["noplaylist"], True)

    def test_non_interactive_format_selection_does_not_read_stdin(self):
        with patch.object(downloader.sys.stdin, "isatty", return_value=False):
            self.assertIsNone(
                downloader.choose_format_for_context(
                    [{"format_id": "1", "vcodec": "h264", "acodec": "aac"}],
                    requested=True,
                )
            )

    def test_retries_when_first_format_selector_is_unavailable(self):
        import yt_dlp

        class FakeYDL:
            instances = []

            def __init__(self, options):
                self.options = options
                self.downloaded = False
                self.__class__.instances.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                if self.options["format"] == "bv*+ba/b":
                    raise yt_dlp.utils.DownloadError("Requested format is not available")
                return {"title": "fallback", "duration": 1, "formats": []}

            def download(self, urls):
                self.downloaded = True
                return 0

        with patch.object(yt_dlp, "YoutubeDL", FakeYDL):
            self.assertTrue(
                downloader.download_with_ytdlp(
                    "https://example.test/video.mp4", output_dir="downloads"
                )
            )

        self.assertEqual(
            [instance.options["format"] for instance in FakeYDL.instances],
            ["bv*+ba/b", "best", "best"],
        )

    def test_download_video_preserves_selected_interactive_format(self):
        import yt_dlp

        class FakeYDL:
            instances = []

            def __init__(self, options):
                self.options = options
                self.__class__.instances.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                return {"title": "demo", "duration": 1, "formats": [{"format_id": "22"}]}

            def download(self, urls):
                return 0

        with patch.object(yt_dlp, "YoutubeDL", FakeYDL), \
                patch.object(downloader, "choose_format_for_context", return_value="22"):
            result = downloader.download_video("https://example.test/video", select_format=True)

        self.assertTrue(result)
        self.assertIn("22", [instance.options["format"] for instance in FakeYDL.instances])


class DownloaderFallbackTests(unittest.TestCase):
    def test_page_fallback_extracts_media_from_successful_html(self):
        import requests

        response = requests.Response()
        response.status_code = 200
        response._content = b'<video><source src="/assets/clip.m3u8"></video>'
        response.headers["content-type"] = "text/html; charset=utf-8"
        response.encoding = "utf-8"

        with patch("requests.get", return_value=response), \
                patch.object(downloader, "download_video", return_value=True) as download_mock:
            self.assertTrue(downloader.try_fallback_methods("https://example.test/watch", output_dir="downloads"))

        self.assertEqual(download_mock.call_args.args[0], "https://example.test/assets/clip.m3u8")

    def test_page_fallback_resolves_relative_media_and_passes_proxy(self):
        import requests

        response = requests.Response()
        response.status_code = 200
        response._content = b'<video><source src="/assets/clip.m3u8"></video>'
        response.encoding = "utf-8"

        with patch("requests.get", return_value=response) as requests_get, \
                patch.object(downloader, "download_video", return_value=True) as download_mock:
            self.assertTrue(
                downloader.try_fallback_methods(
                    "https://example.test/watch",
                    output_dir="downloads",
                    use_proxy=True,
                    proxy_url="http://127.0.0.1:8080",
                )
            )

        self.assertEqual(
            download_mock.call_args.args[0],
            "https://example.test/assets/clip.m3u8",
        )
        self.assertEqual(
            requests_get.call_args.kwargs["proxies"],
            {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"},
        )


if __name__ == "__main__":
    unittest.main()
