@echo off
chcp 65001 > nul
title برنامج طباعة ملصقات الأرفف - شركة العصلي
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo حدث خطأ أثناء تشغيل البرنامج.
    pause
)
