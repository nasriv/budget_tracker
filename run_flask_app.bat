@echo off
echo Changing to project directory...
cd /d E:\Personal\Coding_projects\budget_tracker\

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Starting Flask application...
start python app.py

echo Opening Chrome...
timeout /t 7
start chrome http://localhost:5000

echo.
echo Flask application is running. Close this window to stop the application.
pause >nul

echo Deactivating virtual environment...
deactivate

