import os
import re
import requests
from urllib.parse import urlparse
import subprocess
import sys
import argparse
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_environment():
    """Check if yt-dlp is installed, install if necessary."""
    try:
        import yt_dlp
        logger.info("yt-dlp is already installed.")
    except ImportError:
        logger.info("Installing yt-dlp...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
        logger.info("yt-dlp has been installed.")

def parse_markdown_file(file_path):
    """Parse the markdown file to extract chapters, sections, and video links."""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Define patterns to identify chapters and sections
    chapter_pattern = r'(序\s*章|第[一二三四五六七八九十]+篇章)\s*([^（\n]+)'
    section_pattern = r'^(\d+)[\.、]([^\n]+)'
    url_pattern = r'https?://[^\s)"<]+'
    
    # Initialize the structure to store chapter information
    chapter_data = []
    current_chapter = None
    current_section = None
    
    # Split content by lines
    lines = content.split('\n')
    
    for i, line in enumerate(lines):
        # Check if this line defines a chapter
        chapter_match = re.search(chapter_pattern, line)
        if chapter_match:
            chapter_num = chapter_match.group(1)
            chapter_title = chapter_match.group(2).strip()
            current_chapter = {'number': chapter_num, 'title': chapter_title, 'sections': []}
            logger.info(f"Found chapter: {chapter_num} - {chapter_title}")
            chapter_data.append(current_chapter)
            continue
        
        # Check if this line defines a section
        section_match = re.search(section_pattern, line)
        if section_match and current_chapter is not None:
            section_num = section_match.group(1)
            section_title = section_match.group(2).strip()
            current_section = {'number': section_num, 'title': section_title, 'videos': []}
            logger.info(f"Found section in {current_chapter['number']}: {section_num} - {section_title}")
            current_chapter['sections'].append(current_section)
            continue
        
        # Check if this line contains a URL
        urls = re.findall(url_pattern, line)
        if urls and current_section is not None:
            for url in urls:
                logger.info(f"Found video URL in section {current_section['number']}: {url}")
                description = line.split(url)[0].strip() if url in line else ""
                current_section['videos'].append({
                    'url': url,
                    'description': description
                })
    
    # Log summary of what was found
    total_videos = sum(len(section['videos']) for chapter in chapter_data for section in chapter['sections'])
    logger.info(f"Found {len(chapter_data)} chapters, with a total of {total_videos} videos")
    
    # Print detailed debug info about the structure
    if logger.level <= logging.DEBUG:
        for chapter in chapter_data:
            logger.debug(f"Chapter: {chapter['number']} - {chapter['title']}")
            for section in chapter['sections']:
                logger.debug(f"  Section: {section['number']} - {section['title']}")
                for i, video in enumerate(section['videos'], 1):
                    logger.debug(f"    Video {i}: {video['url']}")
    
    return chapter_data

def create_folder_structure(chapter_data, base_dir='videos'):
    """Create folder structure based on chapter data."""
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    
    for chapter in chapter_data:
        chapter_folder = sanitize_filename(f"{chapter['number']}_{chapter['title']}")
        chapter_path = os.path.join(base_dir, chapter_folder)
        
        if not os.path.exists(chapter_path):
            os.makedirs(chapter_path)
            logger.info(f"Created chapter directory: {chapter_path}")
        
        for section in chapter['sections']:
            section_folder = sanitize_filename(f"{section['number']}_{section['title']}")
            section_path = os.path.join(chapter_path, section_folder)
            
            if not os.path.exists(section_path):
                os.makedirs(section_path)
                logger.info(f"Created section directory: {section_path}")

def sanitize_filename(filename):
    """Remove characters that are not allowed in filenames."""
    # Replace characters not allowed in filenames with underscores
    return re.sub(r'[\\/*?:"<>|]', '_', filename)

def download_videos(chapter_data, base_dir='videos'):
    """Download videos from URLs in chapter data."""
    # Reuse the GUI/CLI downloader so URL normalization, site-specific
    # handling, retries, and truthful failure reporting stay consistent.
    from universal_video_downloader import download_video
    
    total_videos = sum(len(section['videos']) for chapter in chapter_data for section in chapter['sections'])
    if total_videos == 0:
        logger.warning("No videos found to download!")
        return
    
    # Create a file to save unsupported URLs
    unsupported_urls_file = os.path.join(base_dir, "unsupported_urls.txt")
    with open(unsupported_urls_file, "w", encoding="utf-8") as f:
        f.write("# Unsupported URLs for manual download\n\n")
    
    for chapter in chapter_data:
        chapter_folder = sanitize_filename(f"{chapter['number']}_{chapter['title']}")
        
        for section in chapter['sections']:
            section_folder = sanitize_filename(f"{section['number']}_{section['title']}")
            download_path = os.path.join(base_dir, chapter_folder, section_folder)
            
            for i, video in enumerate(section['videos'], start=1):
                url = video['url']
                desc = video['description']
                
                # Create a short descriptive name for the video
                video_name = f"{i}_{sanitize_filename(desc[:30] if desc else 'video')}"
                
                logger.info(f"\nDownloading video {i} in section {section['number']} of {chapter['number']}:")
                logger.info(f"URL: {url}")
                logger.info(f"Saving to: {download_path}/{video_name}")
                
                try:
                    success = download_video(
                        url,
                        download_path,
                        select_format=False,
                        output_template=os.path.join(download_path, f'{video_name}.%(ext)s'),
                    )
                    if not success:
                        raise RuntimeError("all downloader methods failed")
                    logger.info(f"Successfully downloaded: {video_name}")
                    
                except Exception as e:
                    logger.error(f"Error downloading {url}: {e}")
                    # Save unsupported URL to the file for manual download
                    with open(unsupported_urls_file, "a", encoding="utf-8") as f:
                        f.write(f"Chapter: {chapter['number']} - {chapter['title']}\n")
                        f.write(f"Section: {section['number']} - {section['title']}\n")
                        f.write(f"Video {i}: {desc}\n")
                        f.write(f"URL: {url}\n\n")
                    
                    # Create a .url file in the appropriate folder
                    url_file_path = os.path.join(download_path, f"{video_name}.url")
                    with open(url_file_path, "w", encoding="utf-8") as f:
                        f.write(f"[InternetShortcut]\nURL={url}\n")
                    logger.info(f"Created URL shortcut file at {url_file_path}")

def main():
    parser = argparse.ArgumentParser(description='Extract and download videos from markdown file.')
    parser.add_argument('--source', default='source.md', help='Path to the source markdown file')
    parser.add_argument('--output', default='videos', help='Base directory for downloaded videos')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    args = parser.parse_args()
    
    # Set debug level if requested
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    
    # Check if source file exists
    if not os.path.exists(args.source):
        logger.error(f"Source file {args.source} not found!")
        sys.exit(1)
    
    # Ensure yt-dlp is installed
    setup_environment()
    
    # Parse the markdown file
    logger.info(f"Parsing {args.source}...")
    chapter_data = parse_markdown_file(args.source)
    
    # Verify we got chapter data
    if not chapter_data:
        logger.error("No chapters found in the markdown file. Exiting.")
        sys.exit(1)
    
    # Create folder structure
    logger.info(f"Creating folder structure in {args.output}...")
    create_folder_structure(chapter_data, args.output)
    
    # Download videos
    logger.info("Starting video downloads...")
    download_videos(chapter_data, args.output)
    
    logger.info("Video extraction complete!")

if __name__ == "__main__":
    main() 
