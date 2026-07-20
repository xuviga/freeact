$ErrorActionPreference = 'Stop'

$packageName = 'freeact'
$version = '0.4.0'

Write-Host "Installing freeact v$version — The Browser Tamer"

pip install freeact-cli==$version

Write-Host "Installing Playwright browsers..."
playwright install chromium

Write-Host ""
Write-Host "freeact v$version installed!"
Write-Host "Quick start:"
Write-Host "  freeact daemon start"
Write-Host "  freeact --session demo browser open DSYandex https://example.com"
Write-Host "  freeact --session demo state"
Write-Host ""
Write-Host "Docs: https://github.com/xuviga/freeact"
