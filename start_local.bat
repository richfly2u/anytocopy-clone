@echo off
:: ============================================
:: 啟動 VideoText AI 本機後端 + CDP Proxy
:: ============================================
cd /d "D:\我的知識庫\anytocopy-clone\backend"

:: 啟動小紅書 CDP Proxy（新視窗）
start "CDP Proxy" powershell.exe -ExecutionPolicy Bypass -File "..\run_xhs_proxy.ps1"

:: 等 CDP Proxy 就緒
timeout /t 8 /nobreak >nul

:: 啟動 Flask 後端
echo Starting Flask backend...
wsl.exe -d Ubuntu -- bash -c "cd /mnt/d/我的知識庫/anytocopy-clone/backend && source .venv/bin/activate && CDP_HOST=172.22.192.1 CDP_PORT=5001 python app.py"

pause
