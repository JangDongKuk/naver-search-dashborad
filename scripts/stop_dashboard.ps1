# 8501 포트로 떠 있는 streamlit 프로세스를 종료한다.
Get-CimInstance Win32_Process -Filter "name='python.exe' or name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like '*streamlit*' -and $_.CommandLine -like '*8501*' } |
    ForEach-Object {
        Write-Output "종료: PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force
    }
