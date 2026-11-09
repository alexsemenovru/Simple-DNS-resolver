# Собирает dist\dns_resolver.exe из src\dns_resolver.py
# Запуск:  .\build.ps1
# Нужен venv с PyInstaller:  python -m venv .venv; .venv\Scripts\python.exe -m pip install pyinstaller

[CmdletBinding()]
param(
    [string]$Python = (Join-Path $PSScriptRoot '.venv\Scripts\python.exe')
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$src = Join-Path $root 'src\dns_resolver.py'

if (-not (Test-Path $Python)) {
    throw "Не найден Python: $Python`nСоздайте venv: python -m venv .venv"
}
if (-not (Test-Path $src)) {
    throw "Не найден исходник: $src"
}

Push-Location $root
try {
    & $Python -m PyInstaller `
        --noconfirm --clean --onefile --console `
        --name dns_resolver `
        --paths (Join-Path $root 'src') `
        --distpath dist --workpath build --specpath build `
        $src
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller завершился с кодом $LASTEXITCODE" }

    $exe = Join-Path $root 'dist\dns_resolver.exe'
    if (-not (Test-Path $exe)) { throw "exe не появился: $exe" }

    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "`nГотово: $exe ($size МБ)" -ForegroundColor Green
    Write-Host 'Проверка:' -ForegroundColor Cyan
    & $exe --version
}
finally {
    Pop-Location
}
