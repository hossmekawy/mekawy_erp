@echo off
TITLE Python Environment Setup

:: This script checks for a Python virtual environment, creates one if it doesn't exist,
:: and then installs dependencies from a requirements.txt file.

SET VENV_DIR=venv
SET REQUIREMENTS_FILE=requirements.txt

:: Check if the requirements.txt file exists
IF NOT EXIST "%REQUIREMENTS_FILE%" (
    ECHO.
    ECHO [ERROR] '%REQUIREMENTS_FILE%' not found in this directory.
    ECHO Please make sure the requirements file is present before running this script.
    ECHO.
    PAUSE
    EXIT /B 1
)

:: Check if the virtual environment directory already exists
ECHO Checking for virtual environment directory: '%VENV_DIR%'
IF NOT EXIST "%VENV_DIR%" (
    ECHO.
    ECHO Virtual environment not found. Creating a new one...
    
    :: Create the virtual environment.
    :: Assumes 'python' is in your system's PATH. You might need to change this to 'py' or a specific python.exe path.
    python -m venv %VENV_DIR%
    
    :: Check if the venv creation was successful
    IF %ERRORLEVEL% NEQ 0 (
        ECHO.
        ECHO [ERROR] Failed to create the virtual environment.
        ECHO Please ensure Python is installed and accessible from your PATH.
        ECHO.
        PAUSE
        EXIT /B 1
    )
    
    ECHO Virtual environment created successfully.
) ELSE (
    ECHO Virtual environment already exists.
)

ECHO.
ECHO Activating the virtual environment and installing dependencies...
ECHO This may take a few moments.
ECHO.

:: Activate the virtual environment and install requirements
CALL "%VENV_DIR%\Scripts\activate.bat" && python -m pip install -r %REQUIREMENTS_FILE%

:: Check if the installation was successful
IF %ERRORLEVEL% NEQ 0 (
    ECHO.
    ECHO [ERROR] Failed to install requirements from '%REQUIREMENTS_FILE%'.
    ECHO Please check the file for errors and ensure you have an internet connection.
    ECHO.
    PAUSE
    EXIT /B 1
)

ECHO.
ECHO =================================================================
ECHO  Setup Complete!
ECHO.
ECHO  To activate the virtual environment in your terminal, run:
ECHO  %VENV_DIR%\Scripts\activate
ECHO =================================================================
ECHO.

PAUSE
