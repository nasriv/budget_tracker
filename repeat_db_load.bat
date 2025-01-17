@echo off
REM Path to your virtual environment's activation script
SET VENV_PATH=E:\Personal\Coding_projects\budget_tracker\.venv\Scripts\activate

REM Path to your Python script
SET SCRIPT_PATH=E:\Personal\Coding_projects\budget_tracker\utils.py

REM Path to deactivate script (optional, but good practice)
SET DEACTIVATE_PATH=E:\Personal\Coding_projects\budget_tracker\.venv\Scripts\deactivate

REM Activate the virtual environment and run the Python script 5 times
CALL %VENV_PATH%
FOR /L %%i IN (1,1,10) DO (
    echo Running iteration %%i...
    python %SCRIPT_PATH%
    echo Done with iteration %%i
)

REM Deactivate the virtual environment (optional)
CALL %DEACTIVATE_PATH%

echo Finished all iterations.
pause