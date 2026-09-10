param(
  [string]$Message = "Update resumes"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

& "$Root\build.cmd"

$insideWorkTree = git rev-parse --is-inside-work-tree 2>$null
if ($LASTEXITCODE -ne 0 -or $insideWorkTree.Trim() -ne "true") {
  Write-Host ""
  Write-Host "Git-репозиторий ещё не настроен. Выполни один раз:"
  Write-Host "git init"
  Write-Host "git branch -M main"
  Write-Host "git add resume_data.json build.py build.cmd requirements.txt README.md assets public .github publish.ps1 .gitignore"
  Write-Host "git commit -m `"Initial resume site`""
  Write-Host "git remote add origin https://github.com/<github-user>/<repo>.git"
  Write-Host "git push -u origin main"
  exit 1
}

git remote get-url origin *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "Remote origin не настроен. Создай GitHub-репозиторий и добавь его:"
  Write-Host "git remote add origin https://github.com/<github-user>/<repo>.git"
  Write-Host "git push -u origin main"
  exit 1
}

git status --short
git add resume_data.json build.py build.cmd requirements.txt README.md assets public .github publish.ps1 .gitignore

git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
  Write-Host "Нет изменений для публикации."
  exit 0
}

git commit -m $Message
git push

$remoteUrl = git remote get-url origin
$pagesPath = $null
if ($remoteUrl -match "github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+)(\.git)?$") {
  $owner = $Matches.owner.ToLowerInvariant()
  $repo = $Matches.repo
  $pagesPath = "https://$owner.github.io/$repo"
}

Write-Host ""
Write-Host "После завершения GitHub Actions ссылки останутся теми же:"
if ($pagesPath) {
  Write-Host "$pagesPath/resume-1c-junior.pdf"
  Write-Host "$pagesPath/resume-1c-senior.pdf"
} else {
  Write-Host "https://<github-user>.github.io/<repo>/resume-1c-junior.pdf"
  Write-Host "https://<github-user>.github.io/<repo>/resume-1c-senior.pdf"
}
