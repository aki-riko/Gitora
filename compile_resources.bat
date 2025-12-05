@echo off
chcp 65001 >nul
echo ========================================
echo 编译Qt资源文件
echo ========================================
echo.

cd app\resource

echo 正在编译resource.qrc...
pyside6-rcc resource.qrc -o resource_rc.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ 编译成功！
    echo.
) else (
    echo.
    echo ❌ 编译失败！
    echo.
)

cd ..\..

pause
