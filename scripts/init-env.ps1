# Creates .env from .env.example with fresh random secrets (Windows, no extra tools needed).
# Each placeholder gets one value, so passwords and the connection URLs that contain them match.
param([string]$Path = ".env")

if (Test-Path $Path) { Write-Host "$Path already exists - leaving it unchanged."; exit 0 }

$text = Get-Content ".env.example" -Raw
$placeholders = [regex]::Matches($text, "change-me[-A-Za-z0-9]*") | ForEach-Object { $_.Value } | Sort-Object -Unique
foreach ($p in $placeholders) {
    $secret = -join ((1..48) | ForEach-Object { "0123456789abcdef"[(Get-Random -Maximum 16)] })
    $text = $text.Replace($p, $secret)
}
[System.IO.File]::WriteAllText((Join-Path (Get-Location) $Path), $text)
Write-Host "Wrote $Path with $($placeholders.Count) random secrets."
