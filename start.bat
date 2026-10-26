@echo off
REM Constitutional Analysis Engine: one-click start for Windows.
REM First run installs everything (several minutes); later runs start in seconds.
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python 3.10+ is required. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
where npm >nul 2>nul || (echo Node.js is required. Install the LTS version from https://nodejs.org/ & pause & exit /b 1)

if not exist .env (
  echo.
  echo One-time setup: your Claude API key ^(from https://console.anthropic.com/settings/keys^)
  set /p KEY="Paste ANTHROPIC_API_KEY: "
  call echo ANTHROPIC_API_KEY=%%KEY%%> .env
)
for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"

if not exist .venv\Scripts\python.exe (
  echo.
  echo ==^> Installing Python packages ^(first run only, can take 5-10 minutes^)
  python -m venv .venv || (pause & exit /b 1)
  .venv\Scripts\python -m pip install --upgrade pip -q
  .venv\Scripts\python -m pip install -r backend\requirements.txt || (pause & exit /b 1)
)

if not exist backend\data\constitutional_db (
  echo.
  echo ==^> Building the knowledge base ^(first run only^)
  pushd backend
  ..\.venv\Scripts\python -m ingest seed
  ..\.venv\Scripts\python -m ingest constitution || echo   Warning: couldn't load the Constitution text; continuing with demo data.
  set /p ANS="Also download the full Constitution Annotated now? This takes a long time. [y/N] "
  call :maybe_conan
  popd
)

if not exist frontend\node_modules (
  echo.
  echo ==^> Installing web app packages ^(first run only^)
  pushd frontend
  call npm install --no-audit --no-fund
  popd
)

echo.
echo ==^> Starting. The app opens at http://localhost:5173. Close both windows to stop.
start "Constitution API" cmd /k "cd /d %~dp0backend && ..\.venv\Scripts\python -m uvicorn app.main:app --port 8000"
start "" cmd /c "timeout /t 5 >nul && start http://localhost:5173"
cd frontend
call npm run dev
exit /b 0

:maybe_conan
if /i "%ANS%"=="y" ..\.venv\Scripts\python -m ingest conan
exit /b 0
