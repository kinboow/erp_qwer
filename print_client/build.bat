@echo off
echo ========================================
echo   ERP 打印客户端 - 打包为 EXE
echo ========================================
echo.

:: 检查 pyinstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [1/3] 安装 PyInstaller ...
    pip install pyinstaller
) else (
    echo [1/3] PyInstaller 已安装
)

echo [2/3] 开始打包 ...
pyinstaller --noconfirm --onefile --windowed ^
    --name "ERP打印客户端" ^
    --icon NUL ^
    --add-data "README.md;." ^
    --hidden-import win32print ^
    --hidden-import win32api ^
    print_client.py

echo.
echo [3/3] 打包完成!
echo.
echo 输出文件: dist\ERP打印客户端.exe
echo.
pause
