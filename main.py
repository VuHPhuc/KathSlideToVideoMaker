"""
KathFlow Studio — Entry Point
Slide To Video Project: Text → MP3 with Word Timestamps
"""

import os
import sys
import warnings

# Suppress Hugging Face symlink warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Suppress Hugging Face unauthenticated request warnings and user warnings
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", message=".*unauthenticated requests.*")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon
from app.ui.main_window import MainWindow


def main():
    # Suppress harmless FFmpeg/MP3 and QFont console warnings
    from PyQt6.QtCore import qInstallMessageHandler
    def message_handler(msg_type, context, msg_string):
        if any(term in msg_string for term in ["mp3float", "timestamps for skipped samples", "setFontSize", "Point size <= 0"]):
            return
        sys.stderr.write(f"Qt Msg: {msg_string}\n")
    qInstallMessageHandler(message_handler)

    app = QApplication(sys.argv)
    app.setApplicationName("KathFlow Studio")
    app.setOrganizationName("KathSlideToVideo")

    # Apply base font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Set application window icon
    icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "app", "resources", "icon.png"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
