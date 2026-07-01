import os
import sys
import shutil
import urllib.request
import zipfile
import tempfile
from pathlib import Path

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

def download_progress(block_num, block_size, total_size):
    read_so_far = block_num * block_size
    if total_size > 0:
        percent = min(100, int(read_so_far * 100 / total_size))
        sys.stdout.write(f"\rDownloading FFmpeg: {percent}% ({read_so_far / (1024*1024):.1f} MB of {total_size / (1024*1024):.1f} MB)")
        sys.stdout.flush()
    else:
        sys.stdout.write(f"\rDownloading FFmpeg: {read_so_far / (1024*1024):.1f} MB")
        sys.stdout.flush()

def main():
    # Find .venv/Scripts
    dest_dir = Path(__file__).parent.parent / ".venv" / "Scripts"
    if not dest_dir.exists():
        print(f"Error: Virtual environment directory '{dest_dir}' does not exist.")
        print("Please run install.bat first.")
        sys.exit(1)

    print(f"Target directory: {dest_dir}")
    
    # Check if already installed
    ffmpeg_exe = dest_dir / "ffmpeg.exe"
    ffprobe_exe = dest_dir / "ffprobe.exe"
    if ffmpeg_exe.exists() and ffprobe_exe.exists():
        print("FFmpeg and FFprobe already exist in .venv/Scripts. Skipping.")
        sys.exit(0)

    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = Path(tmp_dir) / "ffmpeg.zip"
        print(f"Downloading from {FFMPEG_URL}...")
        try:
            urllib.request.urlretrieve(FFMPEG_URL, zip_path, download_progress)
            print("\nDownload finished. Extracting...")
        except Exception as e:
            print(f"\nFailed to download FFmpeg: {e}")
            sys.exit(1)

        # Extract files
        extract_dir = Path(tmp_dir) / "extracted"
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            print("Extraction finished.")
        except Exception as e:
            print(f"Failed to extract zip: {e}")
            sys.exit(1)

        # Find ffmpeg.exe and ffprobe.exe
        found_ffmpeg = None
        found_ffprobe = None
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.lower() == "ffmpeg.exe":
                    found_ffmpeg = Path(root) / file
                elif file.lower() == "ffprobe.exe":
                    found_ffprobe = Path(root) / file

        if not found_ffmpeg or not found_ffprobe:
            print("Could not find ffmpeg.exe or ffprobe.exe in the downloaded archive.")
            sys.exit(1)

        # Copy to dest
        print(f"Copying {found_ffmpeg.name} to {dest_dir}...")
        shutil.copy2(found_ffmpeg, ffmpeg_exe)
        print(f"Copying {found_ffprobe.name} to {dest_dir}...")
        shutil.copy2(found_ffprobe, ffprobe_exe)
        
        print("\nFFmpeg setup completed successfully!")

if __name__ == "__main__":
    main()
