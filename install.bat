@echo off
chcp 65001 > nul
echo ============================================================
echo   KathTTS Studio — Cài đặt môi trường
echo ============================================================
echo.

:: Kiểm tra Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LỖI] Không tìm thấy Python!
    echo Tải tại: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] Tạo virtual environment...
if not exist ".venv" (
    python -m venv .venv
) else (
    echo   .venv đã tồn tại, bỏ qua.
)

echo [2/4] Kích hoạt venv và cài thư viện...
call .venv\Scripts\activate.bat

echo [3/4] Cài đặt dependencies...
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt

echo.
echo [4/4] Kiểm tra ffmpeg...
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [CẢNH BÁO] ffmpeg chưa được cài hoặc chưa trong PATH!
    echo   ffmpeg cần thiết để xuất file MP3.
    echo.
    echo   Cách cài ffmpeg:
    echo     1. Tải tại: https://www.gyan.dev/ffmpeg/builds/
    echo        - chọn ffmpeg-release-essentials.zip
    echo     2. Giải nén, copy thư mục vào C:\ffmpeg
    echo     3. Thêm C:\ffmpeg\bin vào biến môi trường PATH
    echo     4. Mở lại terminal và chạy lại install.bat
    echo.
) else (
    echo   ffmpeg OK.
)

echo.
echo ============================================================
echo   Cài đặt xong! Chạy run.bat để khởi động ứng dụng.
echo ============================================================
echo.
pause
