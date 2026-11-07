@echo off
cd /d "%~dp0"
echo Starting Rover Lab in the default WSL distribution.
echo Requirements in WSL: Python 3, Node.js, and authenticated Claude Code.
echo Open http://localhost:8765 in your browser. Close this window to stop.
wsl.exe --cd "%CD%" --exec python3 server.py
pause
