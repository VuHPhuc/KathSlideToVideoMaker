@echo off
chcp 65001 > nul
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [CẢNH BÁO] Chưa tìm thấy .venv - chạy install.bat trước!
    echo Đang thử chạy với Python hệ thống...
)

python main.py
