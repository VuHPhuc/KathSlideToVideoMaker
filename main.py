"""
KathTTS Studio — Entry Point
Slide To Video Project: Text → MP3 with Word Timestamps
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon
from app.ui.main_window import MainWindow


def main():
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
