try {
    Set-Location frontend
    Start-Process powershell {npm run dev}

    Set-Location ../backend
    venv\Scripts\python.exe -m uvicorn app.main:app --reload
} finally {
    Set-Location ..
}