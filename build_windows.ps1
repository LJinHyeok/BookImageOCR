$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$tesseractHome = "C:\Program Files\Tesseract-OCR"
$distApp = Join-Path $root "dist\BookImageOCR"
$bundleRoot = Join-Path $distApp "_internal"

if (-not (Test-Path (Join-Path $tesseractHome "tesseract.exe"))) {
    throw "Tesseract was not found at $tesseractHome. Install it before building."
}

Push-Location $root
try {
    python -m pip install -r requirements.txt
    python -m pip install pyinstaller
    python -m PyInstaller --noconfirm --clean --windowed --name BookImageOCR `
        --add-data "tessdata;tessdata" `
        app.py

    $runtimeDir = Join-Path $bundleRoot "tesseract"
    New-Item -ItemType Directory -Force $runtimeDir | Out-Null
    Copy-Item (Join-Path $tesseractHome "tesseract.exe") $runtimeDir -Force
    Copy-Item (Join-Path $tesseractHome "*.dll") $runtimeDir -Force
}
finally {
    Pop-Location
}

Write-Host "Portable app created at: $distApp"

