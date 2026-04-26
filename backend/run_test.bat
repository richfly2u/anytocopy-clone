@echo off
REM 先把測試腳本複製到 Windows 端
copy "D:\我的知識庫\anytocopy-clone\backend\test_xhs_direct.py" "D:\test_xhs_direct.py"

REM 用 Python 跑
cd /d D:\我的知識庫\anytocopy-clone\backend
python test_xhs_direct.py

echo.
echo 完成
pause
