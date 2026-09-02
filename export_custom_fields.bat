@echo off
title Export 26 Odoo Product Fields to Excel
color 0B
echo ==================================================
echo   Exporting 26 Custom Fields from Odoo to Excel
echo ==================================================
python "%~dp0export_custom_26_fields.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Export failed!
    pause
    exit /b %ERRORLEVEL%
)
echo.
echo Export completed successfully.
pause
