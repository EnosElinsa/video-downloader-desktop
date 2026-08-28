import os
import sys
import subprocess
import re
import logging
import time
import json
import html
from urllib.parse import parse_qs, unquote, urljoin, urlparse

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.m4v', '.ts', '.m3u8', '.mpd')
DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36'
)


def normalize_url(raw_url):
    """Normalize URLs copied from Markdown, HTML, or chat applications."""
    if raw_url is None:
        return ''

    value = html.unescape(str(raw_url)).strip()

    # A frequent copy/paste case is a complete Markdown link rather than its
    # destination URL.  Prefer the destination (the second capture group).
    markdown_match = re.fullmatch(r'\[([^\]]+)\]\(([^)]+)\)', value)
    if markdown_match:
        value = markdown_match.group(2).strip()

    # Markdown renderers commonly escape ampersands and JSON commonly escapes
    # slashes.  Both are safe to restore before parsing the URL.
    value = value.replace(r'\&', '&').replace(r'\/', '/')
    value = value.strip('<>')
    value = re.sub(r'[\]\)>;,\.]+$', '', value)

    if value and not re.match(r'^[a-z][a-z0-9+.-]*://', value, re.IGNORECASE):
        value = 'https://' + value
    return value


def _append_unique_url(urls, candidate, base_url):
    """Clean and append a media URL while preserving discovery order."""
    if not candidate:
        return
    candidate = html.unescape(str(candidate)).strip().strip('"\'<>')
    candidate = candidate.replace(r'\/', '/').replace(r'\u0026', '&')
    candidate = unquote(candidate)
    candidate = urljoin(base_url, candidate)
    if candidate.startswith(('http://', 'https://')) and candidate not in urls:
        urls.append(candidate)


def extract_video_urls_from_html(html_content, page_url):
    """Extract direct media URLs from HTML, including relative and JSON URLs."""
    urls = []
    patterns = [
        r'<meta[^>]+property\s*=\s*["\']og:video(?::secure_url)?["\'][^>]+content\s*=\s*["\']([^"\']+)',
        r'<meta[^>]+content\s*=\s*["\']([^"\']+)["\'][^>]+property\s*=\s*["\']og:video(?::secure_url)?["\']',
        r'<(?:video|source)[^>]+src\s*=\s*["\']([^"\']+)',
        r'(?:https?:)?//[^"\'\\\s<>]+\.(?:mp4|m4v|webm|mov|flv|m3u8|mpd)(?:\?[^"\'\\\s<>]*)?',
        r'["\']([^"\']+\.(?:mp4|m4v|webm|mov|flv|m3u8|mpd)(?:\?[^"\']*)?)["\']',
    ]
    for pattern in patterns:
        for match in re.findall(pattern, html_content, flags=re.IGNORECASE):
            _append_unique_url(urls, match, page_url)
    return urls


def get_rockstar_video_urls(url):
    """Return Rockstar's public CDN variants for a /videos/<id> URL.

    The current Rockstar page is a JavaScript shell and does not put the
    playable URL in its HTML.  Its public CDN keeps a stable v4 path.
    """
    parsed = urlparse(normalize_url(url))
    hostname = parsed.hostname.lower() if parsed.hostname else ''
    if hostname not in ('rockstargames.com', 'www.rockstargames.com') \
            and not hostname.endswith('.rockstargames.com'):
        return []

    parts = [unquote(part) for part in parsed.path.split('/') if part]
    try:
        videos_index = next(i for i, part in enumerate(parts) if part.lower() == 'videos')
    except StopIteration:
        return []
    if videos_index + 1 >= len(parts):
        return []
    video_id = parts[videos_index + 1]
    if video_id.lower() == 'video' and videos_index + 2 < len(parts):
        video_id = parts[videos_index + 2]
    if not re.fullmatch(r'[A-Za-z0-9_-]+', video_id):
        return []

    query = parse_qs(parsed.query)
    requested_resolution = query.get('resolution', [''])[0].lower()
    if not re.fullmatch(r'\d{3,4}p', requested_resolution):
        requested_resolution = ''
    resolutions = [requested_resolution] if requested_resolution else []
    resolutions.extend(
        resolution for resolution in ('2160p', '1440p', '1080p', '720p', '480p', '360p')
        if resolution not in resolutions
    )
    locale = query.get('locale', ['en-us'])[0].lower().replace('_', '-')
    if not re.fullmatch(r'[a-z]{2}(?:-[a-z]{2})?', locale):
        locale = 'en-us'

    return [
        f'https://videos-rockstargames-com.akamaized.net/v4/{video_id}/flv/{locale}-{resolution}.mp4'
        for resolution in resolutions
    ]


def build_ytdlp_options(url, output_dir='.', use_proxy=False, proxy_url=None,
                        format_selector='bv*+ba/b', cookie_browser=None,
                        output_template=None):
    """Build resilient yt-dlp options shared by CLI, GUI, and fallbacks."""
    if output_template is None:
        output_template = os.path.join(output_dir, f'video_{int(time.time())}.%(ext)s')

    options = {
        'format': format_selector,
        'outtmpl': output_template,
        'noplaylist': True,
        'progress_hooks': [lambda d: print_progress(d)],
        'verbose': False,
        'no_warnings': False,
        'ignoreerrors': False,
        'geo_bypass': True,
        'retries': 3,
        'fragment_retries': 3,
        'file_access_retries': 3,
        'continuedl': True,
        'http_headers': {
            'User-Agent': DEFAULT_USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': url,
        },
        # When separate streams are selected, yt-dlp will merge them if
        # ffmpeg is available; otherwise its /best branch remains usable.
        'merge_output_format': 'mp4',
    }
    if use_proxy and proxy_url:
        options['proxy'] = proxy_url
    if cookie_browser:
        browser = str(cookie_browser).strip().lower()
        if browser:
            options['cookiesfrombrowser'] = (browser,)
    return options


def choose_format_for_context(formats, requested=False):
    """Choose a format only when an interactive terminal is available."""
    if not requested or not formats:
        return None
    stdin = getattr(sys, 'stdin', None)
    if stdin is None or not stdin.isatty():
        logger.warning('Format selection is unavailable in this window; using automatic best quality.')
        return None
    return get_user_format_choice(formats)


def _is_format_error(error):
    message = str(error).lower()
    return any(
        phrase in message
        for phrase in ('requested format is not available', 'format is not available',
                       'requested format not available', 'no video formats found')
    )


def _log_download_error(error):
    # yt-dlp may include terminal colour escapes; they make GUI logs hard to
    # read and can obscure the actionable part of the error.
    message = re.sub(r'\x1b\[[0-9;]*m', '', str(error))
    lower_message = message.lower()
    if 'sign in to confirm your age' in lower_message or 'age-restricted' in lower_message:
        logger.error(
            'YouTube requires authentication for this video. Select a browser in '
            'Cookies from browser (Chrome/Edge/Firefox) and retry while signed in.'
        )
    elif _is_format_error(error):
        logger.warning('The requested format is unavailable; retrying with an automatic fallback format.')
    logger.error(f'yt-dlp could not download this video: {message}')

def check_dependencies():
    """Check if required dependencies are installed, install if necessary."""
    try:
        import yt_dlp
        logger.info("yt-dlp is already installed.")
    except ImportError:
        logger.info("Installing yt-dlp...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
        logger.info("yt-dlp installed successfully.")
    
    try:
        import requests
        logger.info("requests is already installed.")
    except ImportError:
        logger.info("Installing requests...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
        logger.info("requests installed successfully.")

def sanitize_filename(filename):
    """Remove characters that are not allowed in filenames."""
    return re.sub(r'[\\/*?:"<>|]', '_', filename)

def get_user_format_choice(formats):
    """Let the user choose a format from available options."""
    print("\nAvailable formats:")
    
    # Group formats by resolution for video formats
    video_formats = {}
    audio_formats = []
    resolution_options = {}
    
    for i, fmt in enumerate(formats):
        format_id = fmt.get('format_id', 'N/A')
        ext = fmt.get('ext', 'N/A')
        
        if fmt.get('vcodec') != 'none':
            # Include video-only formats too; modern sites commonly expose
            # video and audio as separate streams.
            resolution = fmt.get('height', 0)
            filesize = fmt.get('filesize', fmt.get('filesize_approx', 0))
            
            if resolution not in video_formats:
                video_formats[resolution] = []
            
            video_formats[resolution].append({
                'index': i,
                'format_id': format_id,
                'ext': ext,
                'filesize': filesize,
                'tbr': fmt.get('tbr', 0),  # Total bit rate
                'has_audio': fmt.get('acodec') != 'none',
            })
        
        elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
            # This is an audio-only format
            filesize = fmt.get('filesize', fmt.get('filesize_approx', 0))
            audio_formats.append({
                'index': i,
                'format_id': format_id,
                'ext': ext,
                'filesize': filesize,
                'abr': fmt.get('abr', 0)  # Audio bit rate
            })
    
    # Display video formats sorted by resolution
    if video_formats:
        print("\n== Video Formats ==")
        option_index = 1
        
        for resolution in sorted(video_formats.keys(), reverse=True):
            formats_for_resolution = video_formats[resolution]
            
            # Sort by bit rate (quality) within the same resolution
            formats_for_resolution.sort(key=lambda x: x['tbr'], reverse=True)
            
            for fmt in formats_for_resolution:
                filesize_str = format_size(fmt['filesize']) if fmt['filesize'] else "Unknown size"
                audio_label = 'with audio' if fmt['has_audio'] else 'video only'
                print(f"{option_index}. {resolution}p ({fmt['ext']}, {audio_label}) - {filesize_str}")
                resolution_options[option_index] = formats[fmt['index']]
                option_index += 1
    
    # Display audio formats
    if audio_formats:
        print("\n== Audio Only Formats ==")
        audio_formats.sort(key=lambda x: x['abr'], reverse=True)
        
        for fmt in audio_formats:
            filesize_str = format_size(fmt['filesize']) if fmt['filesize'] else "Unknown size"
            abr_str = f"{fmt['abr']} kbps" if fmt['abr'] else "Unknown bitrate"
            print(f"{option_index}. Audio {abr_str} ({fmt['ext']}) - {filesize_str}")
            resolution_options[option_index] = formats[fmt['index']]
            option_index += 1
    
    # Add some standard combined options
    print("\n== Common Options ==")
    print(f"{option_index}. Best video quality (might be separate audio/video)")
    best_option = option_index
    option_index += 1
    
    print(f"{option_index}. Best video with audio (single file)")
    best_audio_video_option = option_index
    option_index += 1
    
    print(f"{option_index}. Best audio only")
    best_audio_option = option_index
    
    # Get user choice
    while True:
        try:
            choice = input("\nSelect format number (or press Enter for best quality): ").strip()
            
            if not choice:
                return "best"
            
            choice = int(choice)
            
            if choice in resolution_options:
                return resolution_options[choice]['format_id']
            elif choice == best_option:
                return "best"
            elif choice == best_audio_video_option:
                return "bestvideo+bestaudio/best"
            elif choice == best_audio_option:
                return "bestaudio"
            else:
                print("Invalid choice, please try again.")
        
        except ValueError:
            print("Please enter a valid number.")

def download_with_ytdlp(url, output_dir='.', use_proxy=False, proxy_url=None,
                         select_format=False, cookie_browser=None,
                         output_template=None):
    """Download with yt-dlp, retrying a format failure with a safe fallback."""
    import yt_dlp

    url = normalize_url(url)
    if not url:
        logger.error('The URL is empty or invalid.')
        return False

    # `bv*+ba/b` handles sites that expose separate video/audio streams while
    # retaining the single-file `best` branch for direct files and older sites.
    format_candidates = ['bv*+ba/b', 'best']
    interactive_selection_pending = select_format

    for attempt, format_selector in enumerate(format_candidates):
        ydl_opts = build_ytdlp_options(
            url,
            output_dir,
            use_proxy,
            proxy_url,
            format_selector=format_selector,
            cookie_browser=cookie_browser,
            output_template=output_template,
        )
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise yt_dlp.utils.DownloadError('No video information was returned.')

                logger.info(f"Video found: {info.get('title', 'Unknown title')}")
                logger.info(f"Duration: {format_duration(info.get('duration', 0))}")
                selected_format = choose_format_for_context(
                    info.get('formats', []), requested=interactive_selection_pending
                )
                interactive_selection_pending = False

            if selected_format:
                logger.info(f"Selected format: {selected_format}")
                ydl_opts = build_ytdlp_options(
                    url,
                    output_dir,
                    use_proxy,
                    proxy_url,
                    format_selector=selected_format,
                    cookie_browser=cookie_browser,
                    output_template=output_template,
                )

            logger.info('Starting download...')
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return True

        except yt_dlp.utils.DownloadError as error:
            _log_download_error(error)
            if attempt == 0 and _is_format_error(error):
                continue
            break
        except Exception as error:
            logger.error(f"An error occurred: {error}")
            break

    return False

def print_progress(d):
    """Print download progress."""
    if d['status'] == 'downloading':
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
        
        if total > 0:
            percent = downloaded / total * 100
            progress = f"{percent:.1f}% ({format_size(downloaded)}/{format_size(total)})"
        else:
            progress = f"{format_size(downloaded)} downloaded"
            
        speed = d.get('speed', 0)
        if speed:
            progress += f" at {format_size(speed)}/s"
            
        eta = d.get('eta', 0)
        if eta:
            progress += f", ETA: {format_duration(eta)}"
            
        # Use carriage return to update the same line
        print(f"\r{progress}", end='', flush=True)
    
    elif d['status'] == 'finished':
        # Move to next line after download finishes
        print("")
        logger.info(f"Download complete: {d['filename']}")

def format_size(bytes_size):
    """Format size in bytes to human-readable format."""
    if not bytes_size:
        return "Unknown"
    
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size/1024:.1f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size/(1024*1024):.1f} MB"
    else:
        return f"{bytes_size/(1024*1024*1024):.1f} GB"

def format_duration(seconds):
    """Format duration in seconds to HH:MM:SS format."""
    if not seconds:
        return "Unknown"
    
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

def try_fallback_methods(url, output_dir='.', use_proxy=False, proxy_url=None,
                         cookie_browser=None):
    """Try direct files and media URLs embedded in unsupported pages."""
    logger.info("Attempting fallback methods for unsupported URL...")
    
    # Method 1: Direct download for specific types
    import requests
    
    try:
        url = normalize_url(url)
        headers = {
            'User-Agent': DEFAULT_USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': url,
        }
        request_kwargs = {'headers': headers, 'timeout': 30}
        if use_proxy and proxy_url:
            request_kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}
        
        # Check if this is a direct video URL
        parsed_url = urlparse(url)
        path = parsed_url.path.lower()
        
        if path.endswith(('.m3u8', '.mpd')):
            logger.info("Direct streaming manifest detected. Passing it to yt-dlp...")
            return download_with_ytdlp(
                url, output_dir, use_proxy, proxy_url, False, cookie_browser
            )

        if path.endswith(VIDEO_EXTENSIONS[:-2]):
            logger.info("Direct video link detected. Attempting direct download...")
            response = requests.get(url, stream=True, **request_kwargs)
            
            if response.status_code == 200:
                # Extract filename from URL or use the timestamp
                filename = os.path.basename(parsed_url.path)
                if not filename:
                    filename = f"video_{int(time.time())}{os.path.splitext(path)[1]}"
                
                filename = sanitize_filename(filename)
                file_path = os.path.join(output_dir, filename)
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 1024 * 1024  # 1 MB chunks
                
                logger.info(f"Starting direct download of {filename}")
                
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total_size > 0:
                                percent = downloaded / total_size * 100
                                print(f"\r{percent:.1f}% ({format_size(downloaded)}/{format_size(total_size)})", end='', flush=True)
                
                print("")  # New line after progress
                logger.info(f"Download complete: {file_path}")
                return True
            else:
                logger.error(f"HTTP error: {response.status_code}")
        else:
            logger.info("Not a direct video link. Attempting to extract video from page...")
            
            # Try to get the page and extract video links
            response = requests.get(url, **request_kwargs)
            content_type = response.headers.get('content-type', '').lower()
            # Some servers omit Content-Type for otherwise ordinary HTML pages;
            # keep that legacy-compatible case parseable as HTML.
            if response.status_code == 200 and (not content_type or content_type.startswith('text/html')):
                html_content = response.text

                video_urls = extract_video_urls_from_html(html_content, url)
                if video_urls:
                    logger.info(f"Found {len(video_urls)} video links in the page.")
                    for i, match in enumerate(video_urls):
                        logger.info(f"Trying video link {i + 1}: {match}")
                        if download_video(
                            match, output_dir, use_proxy, proxy_url,
                            False, cookie_browser
                        ):
                            return True
                else:
                    logger.error("Could not find any video links on the page.")
            elif response.status_code == 200:
                logger.error(
                    'The URL returned unexpected non-HTML content; no embedded media links can be extracted.'
                )
            else:
                logger.error(f"HTTP error: {response.status_code}")
    
    except Exception as e:
        logger.error(f"Fallback method failed: {e}")
    
    logger.error("All download methods failed. This URL may not be supported.")
    return False

def download_video(url, output_dir='.', use_proxy=False, proxy_url=None,
                   select_format=False, cookie_browser=None, output_template=None):
    """Main function to download video from URL.

    The typed Qt-free service owns generic yt-dlp orchestration while this
    compatibility entry point retains Rockstar CDN and HTML fallback handling.
    ``DownloadResult`` implements truthiness for existing callers.
    """
    from pathlib import Path
    from desktop_app.download_core import DownloadService
    from desktop_app.models import DownloadRequest, DownloadResult

    normalized_url = normalize_url(url)
    if not normalized_url or not urlparse(normalized_url).scheme:
        logger.error(f"Invalid URL: {url}")
        return DownloadResult(False, None, None, "invalid_url", f"Invalid URL: {url}")
    logger.info(f"Attempting to download video from: {normalized_url}")

    # Rockstar's current page is a JavaScript shell; use its documented public
    # CDN path before asking yt-dlp's generic extractor to parse the shell.
    rockstar_urls = get_rockstar_video_urls(normalized_url)
    if rockstar_urls:
        logger.info('Detected Rockstar Games video page; trying direct CDN variants.')
        for direct_url in rockstar_urls:
            logger.info(f'Trying Rockstar media URL: {direct_url}')
            if download_with_ytdlp(
                direct_url, output_dir, use_proxy, proxy_url, False,
                cookie_browser, output_template
            ):
                return DownloadResult(True, None, None, None, None)

    # The CLI's optional interactive format picker needs yt-dlp's format list,
    # so retain the established legacy path only when the user requested it.
    # Normal GUI/programmatic downloads continue through the typed service.
    if select_format:
        selected_success = download_with_ytdlp(
            normalized_url, output_dir, use_proxy, proxy_url, True,
            cookie_browser, output_template,
        )
        if selected_success:
            return DownloadResult(True, None, None, None, None)

    request = DownloadRequest(
        normalized_url, Path(output_dir),
        format_selector='bv*+ba/b', use_proxy=use_proxy, proxy_url=proxy_url,
        cookie_browser=cookie_browser, output_template=output_template,
    )

    def emit(event):
        if event.message:
            logger.info(event.message)
        if event.kind == 'finished' and event.filename:
            logger.info(f"Download complete: {event.filename}")

    result = DownloadService().download(request, emit)
    if result:
        return result

    # If yt-dlp fails, try fallback methods
    fallback_ok = try_fallback_methods(
        normalized_url, output_dir, use_proxy, proxy_url, cookie_browser)
    if fallback_ok:
        return DownloadResult(True, None, None, None, None)
    return result

def save_config(config):
    """Save configuration to a file."""
    config_dir = os.path.expanduser("~")
    config_file = os.path.join(config_dir, ".video_downloader_config.json")
    
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f)
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")

def load_config():
    """Load configuration from a file."""
    config_dir = os.path.expanduser("~")
    config_file = os.path.join(config_dir, ".video_downloader_config.json")
    
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
    
    # Default configuration
    return {
        "output_dir": ".",
        "use_proxy": False,
        "proxy_url": "",
        "select_format": False,
        "cookie_browser": ""
    }

def main():
    """Main entry point for the script."""
    check_dependencies()
    
    # Load configuration
    config = load_config()
    
    print("\n===== Universal Video Downloader =====")
    print("This program will download videos from almost any website")
    print("Enter 'q' to quit, 'c' for configuration\n")
    
    while True:
        url = input("Enter video URL to download (or 'q' to quit, 'c' for config): ").strip()
        
        if url.lower() == 'q':
            break
        
        if url.lower() == 'c':
            # Configuration menu
            print("\n== Configuration ==")
            print(f"1. Output directory: {config['output_dir']}")
            print(f"2. Use proxy: {config['use_proxy']}")
            if config['use_proxy']:
                print(f"3. Proxy URL: {config['proxy_url']}")
            print(f"4. Select video format: {config['select_format']}")
            print(f"5. Cookies from browser: {config.get('cookie_browser', '') or 'none'}")
            print("6. Back to main menu")
            
            choice = input("\nSelect option to change: ").strip()
            
            if choice == '1':
                new_dir = input("Enter new output directory: ").strip()
                if os.path.exists(new_dir):
                    config['output_dir'] = new_dir
                    logger.info(f"Output directory set to: {new_dir}")
                else:
                    create = input(f"Directory {new_dir} doesn't exist. Create it? (y/n): ").strip().lower()
                    if create == 'y':
                        try:
                            os.makedirs(new_dir, exist_ok=True)
                            config['output_dir'] = new_dir
                            logger.info(f"Created directory: {new_dir}")
                        except Exception as e:
                            logger.error(f"Failed to create directory: {e}")
            
            elif choice == '2':
                use_proxy = input("Use proxy? (y/n): ").strip().lower()
                config['use_proxy'] = (use_proxy == 'y')
                if config['use_proxy'] and not config['proxy_url']:
                    config['proxy_url'] = input("Enter proxy URL (e.g., socks5://127.0.0.1:1080): ").strip()
            
            elif choice == '3' and config['use_proxy']:
                config['proxy_url'] = input("Enter proxy URL (e.g., socks5://127.0.0.1:1080): ").strip()
            
            elif choice == '4':
                select_format = input("Select video format before downloading? (y/n): ").strip().lower()
                config['select_format'] = (select_format == 'y')
            elif choice == '5':
                config['cookie_browser'] = input(
                    "Browser name for cookies (chrome/edge/firefox/brave, blank to disable): "
                ).strip().lower()
            
            # Save configuration
            save_config(config)
            continue
        
        if not url:
            logger.error("Please enter a valid URL")
            continue
        
        # Normalize Markdown/chat formatting and add https:// when omitted.
        normalized_url = normalize_url(url)
        if normalized_url != url:
            logger.info(f"Normalized URL: {normalized_url}")
        url = normalized_url
        
        # Download the video with current configuration
        success = download_video(
            url, 
            config['output_dir'], 
            config['use_proxy'], 
            config['proxy_url'], 
            config['select_format'],
            config.get('cookie_browser')
        )
        
        if success:
            logger.info("Video downloaded successfully!")
        else:
            logger.error("Failed to download video.")
        
        print("\n" + "-" * 40 + "\n")

if __name__ == "__main__":
    main() 
