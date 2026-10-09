param(
    [ValidateSet('google-demo', 'gemini')]
    [string]$Provider = 'google-demo',
    [string]$GeminiModel = 'gemini-3.5-flash-lite',
    [ValidateRange(1024,65535)]
    [int]$Port = 8003
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExecutable = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Missing .venv Python executable.' }
$env:TRANSLATION_PROVIDER = $Provider
$env:STUDIO_PORT = [string]$Port
if ($Provider -eq 'gemini') {
    $env:GEMINI_MODEL = $GeminiModel
    if (-not $env:GEMINI_API_KEY) {
        $secureApiKey = Read-Host 'Gemini API key (hidden; kept in this process environment only)' -AsSecureString
        $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureApiKey)
        try { $env:GEMINI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer) }
    }
}
$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($listener) {
    throw "Port $Port is occupied. Close its server or pass a different -Port."
}
Write-Host "Studio: http://localhost:$Port"
Write-Host "Translation smoke test: http://localhost:$Port/translation-test"
Write-Host 'Keep this terminal open. Press Ctrl+C to stop.'
& $pythonExecutable -u -m backend.server
