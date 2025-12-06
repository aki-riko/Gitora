@echo off
echo 正在清理Python缓存...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
del /s /q *.pyc 2>nul
echo 缓存清理完成！
echo.
echo 请重新运行程序：
echo python Gitess.py
pause
