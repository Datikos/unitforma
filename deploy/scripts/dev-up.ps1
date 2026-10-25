# Windows twin of dev-up.sh: runs the same bash script through Git Bash with the same arguments.
# Usage: .\dev-up.ps1 [service ...]
$bash = "C:\Program Files\Git\bin\bash.exe"
if (-not (Test-Path $bash)) {
  $found = Get-Command bash.exe -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch 'System32' } | Select-Object -First 1
  if ($found) { $bash = $found.Source } else { Write-Error "Git Bash not found (install Git for Windows)."; exit 1 }
}
$env:MSYS_NO_PATHCONV = "1"
& $bash "$PSScriptRoot/dev-up.sh" @args
exit $LASTEXITCODE
