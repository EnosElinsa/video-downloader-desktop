import os
import sys
import subprocess
import shutil
from setuptools import setup, find_packages
from desktop_app.security import sanitize_message

# Check if pip is available and install dependencies
def install_dependencies():
    print("Checking and installing dependencies...")
    
    try:
        # Install required packages
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "PySide6==6.8.2.1",
            "yt-dlp>=2023.3.4", "requests>=2.25.0",
        ])
        print("Dependencies installed successfully.")
        
        return True
        
    except Exception as e:
        print(f"Error installing dependencies: {sanitize_message(e)}")
        return False

# Create desktop shortcut (Windows only)
def create_desktop_shortcut():
    if sys.platform.startswith('win'):
        try:
            # Get desktop path
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            
            # Create command file for CLI
            cli_path = os.path.join(desktop, "Video Downloader (CLI).bat")
            with open(cli_path, "w") as f:
                f.write(f'@echo off\n"{sys.executable}" -m desktop_app.cli\npause')
            
            # Create command file for GUI
            gui_path = os.path.join(desktop, "Video Downloader (GUI).bat")
            with open(gui_path, "w") as f:
                f.write(f'@echo off\n"{sys.executable}" -m desktop_app\npause')
            
            print(f"Desktop shortcuts created at: {desktop}")
            return True
            
        except Exception as e:
            print(f"Error creating desktop shortcuts: {sanitize_message(e)}")
    
    return False

# Main setup
if __name__ == "__main__":
    # Standard setuptools commands (including ``--version``) must be
    # side-effect free; the dependency/bootstrap prompt is only for a
    # deliberate no-argument legacy invocation.
    if len(sys.argv) > 1:
        setup(
            name="video_downloader",
            version="0.1.1",
            description="Universal Video Downloader",
            author="Video Downloader Team",
            packages=find_packages(),
            install_requires=[
                "PySide6==6.8.2.1",
                "yt-dlp>=2023.3.4",
                "requests>=2.25.0",
            ],
            entry_points={
                'console_scripts': [
                    'video-downloader=desktop_app.cli:main',
                    'video-downloader-gui=desktop_app.main:main',
                    'video-downloader-batch=desktop_app.batch:main',
                ],
            },
        )
    else:
        # This is being run as a standalone script
        print("=== Universal Video Downloader Setup ===")
        
        # Install dependencies
        if install_dependencies():
            print("\nAll dependencies installed successfully!")
        else:
            print("\nFailed to install some dependencies. Please try to install them manually.")
            print("Required packages: yt-dlp>=2023.3.4, requests>=2.25.0")
        
        # Ask to create desktop shortcuts (Windows only)
        if sys.platform.startswith('win'):
            create_shortcuts = input("\nCreate desktop shortcuts? (y/n): ").strip().lower() == 'y'
            if create_shortcuts:
                create_desktop_shortcut()
        
        print("\nSetup completed!")
        print("\nTo use the downloader:")
        print("1. Command line: python -m desktop_app.cli")
        print("2. GUI version: python -m desktop_app")
        print("3. Markdown batch: python -m desktop_app.batch --source FILE.md")
        
        input("\nPress Enter to exit...") 
