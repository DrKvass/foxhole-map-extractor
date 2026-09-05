@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ============================================================
echo Foxhole Dynamic Vanilla + Complete Map Mod Builder
echo ============================================================
echo.
echo Reading settings.txt and building all outputs...
echo.

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3.14 "%~dp0build_maps.py"
) else (
    python "%~dp0build_maps.py"
)

set "EXITCODE=%ERRORLEVEL%"
echo.
if "%EXITCODE%"=="0" (
    echo Finished successfully.
    echo Output: %~dp0output
) else (
    echo Build failed with error code %EXITCODE%.
)
echo.
pause
exit /b %EXITCODE%
