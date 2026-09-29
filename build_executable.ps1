[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildEnvironment = Join-Path $ProjectRoot ".build-venv"
$Python = Join-Path $BuildEnvironment "Scripts\python.exe"
$OutputDirectory = Join-Path $ProjectRoot "dist"
$Executable = Join-Path $OutputDirectory "MoneyManager.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    $UserPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
    if (Test-Path -LiteralPath $UserPython) {
        & $UserPython -m venv $BuildEnvironment
    }
    else {
        py -3.13 -m venv $BuildEnvironment
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Python)) {
        throw "Python 3.13 is required to build Money Manager."
    }
}

& $Python -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Installing build dependencies failed."
}
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name MoneyManager `
    --distpath $OutputDirectory `
    --workpath (Join-Path $ProjectRoot "build") `
    --specpath $ProjectRoot `
    --add-data "$(Join-Path $ProjectRoot 'templates');templates" `
    --add-data "$(Join-Path $ProjectRoot 'static');static" `
    (Join-Path $ProjectRoot "run.py")
if ($LASTEXITCODE -ne 0) {
    throw "Building MoneyManager.exe failed."
}

$SourceDatabase = Join-Path $ProjectRoot "data\money_manager.sqlite3"
$ReleaseDataDirectory = Join-Path $OutputDirectory "data"
$ReleaseDatabase = Join-Path $ReleaseDataDirectory "money_manager.sqlite3"
if ((Test-Path -LiteralPath $SourceDatabase) -and -not (Test-Path -LiteralPath $ReleaseDatabase)) {
    New-Item -ItemType Directory -Path $ReleaseDataDirectory -Force | Out-Null
    Copy-Item -LiteralPath $SourceDatabase -Destination $ReleaseDatabase
}

Write-Host ""
Write-Host "Built: $Executable"
Write-Host "The data folder beside the executable stores your database and uploaded merchant logos."
