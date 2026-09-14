@echo off
title Odoo 17 to DuckDB Product Sync
color 0A
echo ==================================================
echo   Starting Odoo 17 -> DuckDB Product Sync
echo ==================================================
python "%~dp0odoo_duckdb_sync.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Synchronization failed! Check error messages above.
    pause
    exit /b %ERRORLEVEL%
)
echo.
echo Sync finished successfully.
pause
