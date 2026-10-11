$ErrorActionPreference = "Stop"

$pythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
& $pythonBin -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,14), 'Zyvarnth requires Python 3.11–3.13'"
if ($LASTEXITCODE -ne 0) { throw "Set PYTHON_BIN to Python 3.11, 3.12, or 3.13." }

& $pythonBin -m venv .venv
$venvPython = Join-Path (Get-Location) ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e '.[desktop,notify]'
& $venvPython -m playwright install chromium
Write-Output "Install complete. Run: .venv\Scripts\python.exe main.py"

