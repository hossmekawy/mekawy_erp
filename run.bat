@echo off
TITLE Run Django Development Server

:: This script finds the local IPv4 address and uses it to run the Django development server.
:: It should be placed in the root directory of your Django project.

SET VENV_DIR=venv
SET MANAGE_PY=manage.py
SET PORT=8000
SET MY_IP=

ECHO.
ECHO ===================================================
ECHO  Django Server Launcher
ECHO ===================================================
ECHO.

:: Check if manage.py exists in the current directory
IF NOT EXIST "%MANAGE_PY%" (
    ECHO [ERROR] 'manage.py' not found.
    ECHO Please run this script from the root directory of your Django project.
    ECHO.
    PAUSE
    EXIT /B 1
)

:: Check if the virtual environment directory exists
IF NOT EXIST "%VENV_DIR%" (
    ECHO [ERROR] Virtual environment folder '%VENV_DIR%' not found.
    ECHO Please run the setup script first to create the environment.
    ECHO.
    PAUSE
    EXIT /B 1
)


ECHO Searching for your local IPv4 address...

:: Find the IPv4 address and store it in the MY_IP variable.
:: This command combination filters the output of ipconfig to get the line with "IPv4 Address",
:: then tokenizes it to extract the IP address itself, trimming any leading spaces.
FOR /F "tokens=2 delims=:" %%a IN ('ipconfig ^| find "IPv4 Address"') DO (
    FOR /F "tokens=*" %%b IN ("%%a") DO SET MY_IP=%%b
)

:: Check if an IP address was found
IF "%MY_IP%"=="" (
    ECHO.
    ECHO [ERROR] Could not automatically determine the IPv4 address.
    ECHO Please check your network connection and try again.
    ECHO.
    PAUSE
    EXIT /B 1
)

ECHO Found IP Address: %MY_IP%
ECHO.

ECHO Activating virtual environment...
CALL "%VENV_DIR%\Scripts\activate.bat"

ECHO.
ECHO Starting the Django development server...
ECHO You will be able to access it at: http://%MY_IP%:%PORT%
ECHO Press CTRL+C in this window to stop the server.
ECHO.

:: Run the Django development server with the found IP and port
python %MANAGE_PY% runserver %MY_IP%:%PORT%

PAUSE
