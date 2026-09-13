@echo off
chcp 65001 >nul
title استعادة النسخة الاحتياطية المستقرة - OdooDB v1.08
echo =====================================================================
echo       استعادة النسخة الاحتياطية المستقرة (v1.08 - قبل تعديلات Opus)
echo =====================================================================
echo.
echo تحذير: هذا السكربت سيقوم باسترجاع كافة ملفات الكود والبرامج التنفيذية (.exe)
echo وقواعد البيانات إلى حالتها المستقرة المؤكدة والمحفوظة في 13-09-2026.
echo.
set /p confirm="هل أنت متأكد من استرجاع النسخة الاحتياطية المستقرة؟ (y/n): "
if /i "%confirm%" NEQ "y" (
    echo تم إلغاء الاستعادة.
    pause
    exit /b
)

echo.
echo جاري استعادة الملفات من C:\OdooDB_Backups...

set BACKUP_DIR=C:\OdooDB_Backups\Backup_OdooDB_v1.08_Stable_20260913
set TARGET_DIR=%~dp0

xcopy "%BACKUP_DIR%\*" "%TARGET_DIR%\" /E /I /Y /H

echo.
echo =====================================================================
echo   تم استرجاع النسخة المستقرة v1.08 بنجاح!
echo   يمكنك تشغيل البرامج الآن:
echo   1. OdooReportExporter.exe
echo   2. ShowroomChecker.exe
echo   3. Keygen_Admin.exe
echo =====================================================================
echo.
pause
