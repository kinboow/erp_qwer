$ErrorActionPreference = "Stop"

Write-Host "========================================"
Write-Host "  ERP Print Client - Build Installer"
Write-Host "========================================"
Write-Host ""

# Step 1: Check dependencies
Write-Host "[1/4] Checking dependencies ..."

$pyinstaller = pip show pyinstaller 2>$null
if (-not $pyinstaller) {
    Write-Host "       Installing PyInstaller ..."
    pip install pyinstaller
}

$pystray = pip show pystray 2>$null
if (-not $pystray) {
    Write-Host "       Installing pystray ..."
    pip install pystray Pillow
}

# Find Inno Setup
$ISCC = $null
$candidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
foreach ($c in $candidates) {
    if (Test-Path $c) { $ISCC = $c; break }
}
if (-not $ISCC) {
    Write-Host ""
    Write-Host "[ERROR] Inno Setup 6 not found. Install from:"
    Write-Host "        https://jrsoftware.org/isdl.php"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "       Inno Setup: $ISCC"

# Check SumatraPDF
if (-not (Test-Path "deps")) { New-Item -ItemType Directory -Path "deps" | Out-Null }
$sumatraFiles = Get-ChildItem -Path "deps" -Filter "SumatraPDF-*.exe" -ErrorAction SilentlyContinue
if (-not $sumatraFiles) {
    Write-Host ""
    Write-Host "[INFO] Please download SumatraPDF installer to deps\ folder:"
    Write-Host "       https://www.sumatrapdfreader.org/download-free-pdf-viewer"
    Write-Host "       Example: SumatraPDF-3.5.2-64-install.exe"
    Read-Host "Press Enter to exit"
    exit 1
}
$sumatraExe = $sumatraFiles[0].Name
Write-Host "       SumatraPDF: deps\$sumatraExe"

# Step 2: Build EXE
Write-Host ""
Write-Host "[2/4] Building EXE with PyInstaller ..."
$exeName = "ERP" + [char]0x6253 + [char]0x5370 + [char]0x5BA2 + [char]0x6237 + [char]0x7AEF  # ERP打印客户端
$scriptPath = Join-Path $PSScriptRoot "print_client.py"
$iconPath = Join-Path $PSScriptRoot "logo.ico"
$addDataArg = "$iconPath;."
$pyArgs = "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed", "--name", $exeName, "--icon", $iconPath, "--add-data", $addDataArg, "--hidden-import", "win32print", "--hidden-import", "win32api", "--hidden-import", "pystray", "--hidden-import", "PIL", $scriptPath
$pyProc = Start-Process -FilePath "python" -ArgumentList $pyArgs -NoNewWindow -Wait -PassThru
if ($pyProc.ExitCode -ne 0) {
    Write-Host "[ERROR] PyInstaller failed!"
    Read-Host "Press Enter to exit"
    exit 1
}

$exePath = "dist\$exeName.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "[ERROR] EXE build failed!"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "       EXE build OK: $exePath"

# Step 3: Update setup.iss with actual SumatraPDF filename and build
Write-Host ""
Write-Host "[3/4] Building installer with Inno Setup ..."
& $ISCC "/DSumatraInstaller=$sumatraExe" "setup.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Installer build failed!"
    Read-Host "Press Enter to exit"
    exit 1
}

# Step 4: Done
Write-Host ""
Write-Host "[4/4] ========================================"
Write-Host "  Build complete!"
Write-Host "  Output: installer_output\"
Write-Host "========================================"
Write-Host ""
Read-Host "Press Enter to exit"
