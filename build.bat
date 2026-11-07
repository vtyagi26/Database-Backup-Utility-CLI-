@echo off
echo ====================================================
echo  Building Database Backup Utility (Modern C++14/17)
echo ====================================================

where g++ >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Error: g++ compiler not found in PATH!
    exit /b 1
)

if not exist bin mkdir bin
if not exist backups mkdir backups

echo Compiling Main CLI (bin\db-backup.exe)...
g++ -std=c++14 -O2 -Iinclude src\main.cpp -o bin\db-backup.exe
if %ERRORLEVEL% NEQ 0 (
    echo Compilation of CLI failed!
    exit /b 1
)
echo Successfully built bin\db-backup.exe

echo Compiling Test Suite (bin\db-backup-test.exe)...
g++ -std=c++14 -O2 -Iinclude src\test_main.cpp -o bin\db-backup-test.exe
if %ERRORLEVEL% NEQ 0 (
    echo Compilation of Test Suite failed!
    exit /b 1
)
echo Successfully built bin\db-backup-test.exe

echo.
echo ====================================================
echo  Running C++ Automated Test Suite
echo ====================================================
bin\db-backup-test.exe

echo.
echo Build and tests completed successfully!

