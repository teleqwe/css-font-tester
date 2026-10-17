# Builds FontTester.exe here: checks first, then PyInstaller, then the exe's own check.
# Run: powershell -ExecutionPolicy Bypass -File build.ps1            (add -Desktop for a copy on the desktop too)
param([switch]$Desktop)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python cssfont.py
if ($LASTEXITCODE -ne 0) { throw 'cssfont self-check failed, not building.' }
python test_fonttester.py
if ($LASTEXITCODE -ne 0) { throw 'Tests failed, not building.' }
if (Get-Process -Name FontTester -ErrorAction SilentlyContinue) { throw 'Close FontTester first (a running copy can''t be replaced).' }
python -m PyInstaller --noconfirm --onefile --windowed --name FontTester --icon icon.ico --add-data 'icon.ico;.' --collect-all customtkinter `
    --distpath . fonttester.pyw
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
function Check($exe) {
    $check = Join-Path $env:TEMP 'fonttester_selftest.txt'
    Remove-Item $check -ErrorAction SilentlyContinue
    Start-Process -Wait $exe -ArgumentList '--selftest', "`"$check`""
    if (!(Test-Path $check)) { throw "$exe wrote no check (it crashed?)" }
    $r = Get-Content $check -Raw
    Remove-Item $check -ErrorAction SilentlyContinue
    if ($r -ne 'ok') { throw "$exe's check failed: $r" }
}
Check '.\FontTester.exe'
if ($Desktop) {
    $desk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'FontTester.exe'
    Copy-Item '.\FontTester.exe' $desk -Force
    Check $desk
    Write-Output "Built $PSScriptRoot\FontTester.exe (its check: ok), copied to $desk"
} else { Write-Output "Built $PSScriptRoot\FontTester.exe (its check: ok)" }
