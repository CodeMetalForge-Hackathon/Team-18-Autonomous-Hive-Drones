@echo off
rem Opens the simulator directly. Uses its own port, so it can run alongside start.cmd.
cd /d "%~dp0"
set PORT=8775
echo Starting the simulator in the default WSL distribution.
echo Requirements in WSL: Python 3, Node.js, and authenticated Claude Code.
echo Your browser will open http://127.0.0.1:%PORT%/?mode=simulator
echo Close this window to stop.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 120;$i++){try{Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:%PORT%/api/status' -TimeoutSec 1 | Out-Null; Start-Process 'http://127.0.0.1:%PORT%/?mode=simulator'; break}catch{Start-Sleep -Milliseconds 500}}"
wsl.exe --cd "%CD%" --exec bash -lc "python3 server.py --port %PORT%"
pause
