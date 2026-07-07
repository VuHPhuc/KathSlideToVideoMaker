"""
KathTTS Studio — Entry Point
Slide To Video Project: Text → MP3 with Word Timestamps
"""

import sys
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
    app.setApplicationName("KathTTS Studio")
    app.setOrganizationName("KathSlideToVideo")

    # Apply base font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
