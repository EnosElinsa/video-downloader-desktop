from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_legacy_root_modules_are_replaced_by_desktop_modules():
    assert not (ROOT / "universal_video_downloader.py").exists()
    assert not (ROOT / "video_downloader_gui.py").exists()
    assert not (ROOT / "video_extractor.py").exists()
    assert (ROOT / "desktop_app" / "cli.py").is_file()
    assert (ROOT / "desktop_app" / "batch.py").is_file()
    assert (ROOT / "desktop_app" / "yt_dlp_adapter.py").is_file()


def test_download_helpers_are_importable_from_desktop_package():
    from desktop_app.cli import download_video
    from desktop_app.filenames import sanitize_filename
    from desktop_app.urls import (
        extract_video_urls_from_html,
        get_rockstar_video_urls,
        normalize_url,
    )
    from desktop_app.yt_dlp_adapter import build_ytdlp_options

    assert callable(download_video)
    assert sanitize_filename("a:b") == "a_b"
    assert normalize_url("example.test/video").startswith("https://")
    assert get_rockstar_video_urls("https://www.rockstargames.com/videos/rk721912")
    assert extract_video_urls_from_html("<video src='/clip.mp4'>", "https://example.test")
    assert callable(build_ytdlp_options)


def test_new_batch_module_exposes_markdown_workflow():
    from desktop_app.batch import create_folder_structure, parse_markdown_file

    assert callable(parse_markdown_file)
    assert callable(create_folder_structure)
