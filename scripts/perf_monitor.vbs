Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\Users\hasin\jarvis\scripts\run_perf_monitor.ps1""", 0, false
