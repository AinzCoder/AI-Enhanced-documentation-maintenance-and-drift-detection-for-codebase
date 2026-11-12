param(
    [string]$Python = "python",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

if ($env:DOCGUARD_MODE -and $env:DOCGUARD_MODE -ne "local") {
    throw "DOCGUARD_MODE is already set to a non-local value; refusing to start a local backend."
}

$pythonExecutable = (Get-Command $Python -CommandType Application -ErrorAction Stop).Source
$previousMode = $env:DOCGUARD_MODE
try {
    $env:DOCGUARD_MODE = "local"
    Push-Location $PSScriptRoot
    try {
        & $pythonExecutable -m uvicorn app.main:app --host 127.0.0.1 --port $Port
        $result = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    $env:DOCGUARD_MODE = $previousMode
}
exit $result
