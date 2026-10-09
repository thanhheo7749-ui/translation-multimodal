param([string]$Server = 'http://127.0.0.1:8003')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$basePython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$testPython = Join-Path $projectRoot '.venv-mt-benchmark\Scripts\python.exe'
Write-Host 'NLLB local vs Gemini. Keep the existing Gemini studio server running.'
Write-Host 'First run downloads PyTorch CUDA and official NLLB weights (several GB).'
Write-Host 'Uses a separate Python environment; does not change the running studio.'
if (-not (Test-Path -LiteralPath $testPython)) {
    & $basePython -m venv (Join-Path $projectRoot '.venv-mt-benchmark')
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create benchmark environment.' }
}
& $testPython -m pip install 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed. Check network and retry this script.' }
& $testPython -m pip install 'transformers>=4.50,<5' sentencepiece safetensors
if ($LASTEXITCODE -ne 0) { throw 'Tokenizer installation failed. Check network and retry this script.' }
& $testPython -X utf8 experiments/compare_local_translation.py --providers both --device cuda --download --repeats 3 --server $Server
if ($LASTEXITCODE -ne 0) { throw 'Comparison incomplete. See the printed report/error above.' }
