@echo off
:: Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ==========================================================
    echo ERROR: This script must be run as Administrator!
    echo Please right-click this file and select "Run as administrator".
    echo ==========================================================
    echo.
    pause
    exit /b 1
)

echo ==========================================================
echo Configuring Static IP 10.10.10.99 for Colorlight Art-Net
echo ==========================================================
echo.

:: Try to configure Ethernet first
echo Checking interface "Ethernet"...
netsh interface ipv4 show addresses "Ethernet" >nul 2>&1
if %errorLevel% equ 0 (
    echo Adding IP 10.10.10.99 to "Ethernet"...
    netsh interface ipv4 add address "Ethernet" 10.10.10.99 255.255.255.0
    if %errorLevel% equ 0 (
        echo Success! Added IP 10.10.10.99 to interface "Ethernet".
        goto done
    )
)

:: Try to configure Wi-Fi 3 if Ethernet failed or wasn't available
echo Checking interface "Wi-Fi 3"...
netsh interface ipv4 show addresses "Wi-Fi 3" >nul 2>&1
if %errorLevel% equ 0 (
    echo Adding IP 10.10.10.99 to "Wi-Fi 3"...
    netsh interface ipv4 add address "Wi-Fi 3" 10.10.10.99 255.255.255.0
    if %errorLevel% equ 0 (
        echo Success! Added IP 10.10.10.99 to interface "Wi-Fi 3".
        goto done
    )
)

echo.
echo Could not find or configure "Ethernet" or "Wi-Fi 3" automatically.
echo Listing available interfaces:
netsh interface show interface
echo.
echo Please run:
echo netsh interface ipv4 add address "YOUR_INTERFACE_NAME" 10.10.10.99 255.255.255.0
echo manually in an Administrator Command Prompt.

:done
echo.
pause
