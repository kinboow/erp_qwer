@echo off
chcp 65001 >nul
echo ========================================
echo   ERP 打印客户端 - 构建安装包
echo ========================================
echo.

:: ---- 步骤 1: 检查依赖 ----
echo [1/4] 检查依赖 ...

pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo       安装 PyInstaller ...
    pip install pyinstaller
)

pip show pystray >nul 2>&1
if errorlevel 1 (
    echo       安装 pystray ...
    pip install pystray Pillow
)

:: 检查 Inno Setup
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if "%ISCC%"=="" (
    echo.
    echo [错误] 未找到 Inno Setup 6，请先安装:
    echo        https://jrsoftware.org/isdl.php
    echo.
    pause
    exit /b 1
)
echo       Inno Setup: %ISCC%

:: 检查 SumatraPDF 安装包
if not exist "deps" mkdir deps
if not exist "deps\SumatraPDF-3.5.2-64-install.exe" (
    echo.
    echo [提示] 请将 SumatraPDF 安装包下载到 deps 目录:
    echo        https://www.sumatrapdfreader.org/download-free-pdf-viewer
    echo        文件名: SumatraPDF-3.5.2-64-install.exe
    echo.
    echo        下载完成后重新运行本脚本。
    echo.
    pause
    exit /b 1
)

:: ---- 步骤 2: PyInstaller 打包 EXE ----
echo.
echo [2/4] PyInstaller 打包 EXE ...
pyinstaller --noconfirm --onefile --windowed ^
    --name "ERP打印客户端" ^
    --icon "logo.ico" ^
    --add-data "logo.ico;." ^
    --hidden-import win32print ^
    --hidden-import win32api ^
    --hidden-import pystray ^
    --hidden-import PIL ^
    print_client.py

if not exist "dist\ERP打印客户端.exe" (
    echo.
    echo [错误] EXE 打包失败!
    pause
    exit /b 1
)
echo       EXE 打包成功: dist\ERP打印客户端.exe

:: ---- 步骤 3: Inno Setup 编译安装包 ----
echo.
echo [3/4] Inno Setup 编译安装包 ...
"%ISCC%" setup.iss

if errorlevel 1 (
    echo.
    echo [错误] 安装包编译失败!
    pause
    exit /b 1
)

:: ---- 步骤 4: 完成 ----
echo.
echo [4/4] ========================================
echo   构建完成!
echo   安装包: installer_output\ERP打印客户端_Setup_1.0.0.exe
echo ========================================
echo.
pause
