import os
import sys
import subprocess
import shutil
from setuptools import setup, find_packages

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
        
        # If tkinter is not available, inform the user
        try:
            import tkinter
        except ImportError:
            print("\nWARNING: tkinter is not installed. The GUI version will not work.")
            print("To install tkinter:")
            if sys.platform.startswith('win'):
                print("1. Download and install Python with tkinter from python.org")
            elif sys.platform.startswith('linux'):
                print("1. Use your package manager to install tkinter")
                print("   For Ubuntu/Debian: sudo apt-get install python3-tk")
                print("   For Fedora: sudo dnf install python3-tkinter")
                print("   For Arch: sudo pacman -S tk")
            elif sys.platform.startswith('darwin'):
                print("1. Install tkinter via Homebrew: brew install python-tk")
            
        return True
        
    except Exception as e:
        print(f"Error installing dependencies: {e}")
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
                f.write(f'@echo off\n"{sys.executable}" "{os.path.join(os.path.dirname(os.path.abspath(__file__)), "universal_video_downloader.py")}"\npause')
            
            # Create command file for GUI
            gui_path = os.path.join(desktop, "Video Downloader (GUI).bat")
            with open(gui_path, "w") as f:
                f.write(f'@echo off\n"{sys.executable}" "{os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_downloader_gui.py")}"\npause')
            
            print(f"Desktop shortcuts created at: {desktop}")
            return True
            
        except Exception as e:
            print(f"Error creating desktop shortcuts: {e}")
    
    return False

# Main setup
if __name__ == "__main__":
    # Check if this is being run as a script or as a setup.py install
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        # This is a regular setup.py install
        setup(
            name="video_downloader",
            version="1.0.0",
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
                    'video-downloader=universal_video_downloader:main',
                    'video-downloader-gui=desktop_app.main:main',
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
        print("1. Command line: python universal_video_downloader.py")
        print("2. GUI version: python video_downloader_gui.py")
        
        input("\nPress Enter to exit...") 
