@echo off
chcp 65001 > NUL
setlocal
rem Собирает dist\dns_resolver.exe. Запускать двойным щелчком из этой папки.
rem Нужен .venv с PyInstaller:  python -m venv .venv
rem                            .venv\Scripts\python.exe -m pip install pyinstaller

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo Не найден %PY%
    echo Создайте окружение:
    echo    python -m venv .venv
    echo    .venv\Scripts\python.exe -m pip install pyinstaller
    pause
    exit /b 1
)

"%PY%" -m PyInstaller --noconfirm --clean --onefile --console ^
    --name dns_resolver ^
    --icon "%~dp0assets\icon.ico" ^
    --paths "%~dp0src" ^
    --distpath "%~dp0dist" --workpath "%~dp0build" --specpath "%~dp0build" ^
    "%~dp0src\dns_resolver.py"
if errorlevel 1 (
    echo Сборка не удалась.
    pause
    exit /b 1
)

echo.
echo Готово: %~dp0dist\dns_resolver.exe
"%~dp0dist\dns_resolver.exe" --version
pause
