# Install this complete skill and archive the previous installation outside skills.
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$skillRoot = [IO.Path]::GetFullPath((Join-Path $codexRoot 'skills'))
$destination = [IO.Path]::GetFullPath((Join-Path $skillRoot 'simple-reviewer-v1'))
$oldInstallation = [IO.Path]::GetFullPath((Join-Path $skillRoot 'simple-checker-v1'))
foreach ($target in @($destination, $oldInstallation)) {
    if (-not $target.StartsWith($skillRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Installation path is outside the configured skills directory.'
    }
}
if ([IO.Path]::GetFullPath($repoPath) -eq $destination) { throw 'Run this installer from the repository checkout, not from the installed skill.' }
Write-Host 'Installing Simple Reviewer in the configured Codex skills directory...'
$required = @('SKILL.md', 'agents', 'assets', 'references', 'scripts', 'docs', 'README.md', ([string][char]0x4f7f + [char]0x7528 + [char]0x8bf4 + [char]0x660e + '.md'))
foreach ($entry in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoPath $entry))) { throw "Missing installation resource: $entry" }
}
$null = New-Item -ItemType Directory -Path $skillRoot -Force
$backupRoot = Join-Path $codexRoot ('skill-backups\simple-reviewer-v1-' + [DateTime]::Now.ToString('yyyyMMdd-HHmmss-fff'))
$previousDestination = $null
if (Test-Path -LiteralPath $destination) {
    if ((Get-Item -LiteralPath $destination).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing to move an installed skill symlink.' }
    $null = New-Item -ItemType Directory -Path $backupRoot -Force
    $previousDestination = Join-Path $backupRoot 'previous-reviewer'
    Move-Item -LiteralPath $destination -Destination $previousDestination
}
try {
    $null = New-Item -ItemType Directory -Path $destination
    $sourceFiles = @(Get-ChildItem -LiteralPath $repoPath -File -Recurse | Where-Object {
        $relative = $_.FullName.Substring($repoPath.Length + 1)
        $relative -notmatch '(^|[\\/])__pycache__([\\/]|$)|\.py[co]$' -and
        ($required | Where-Object { $relative -eq $_ -or $relative.StartsWith($_ + [IO.Path]::DirectorySeparatorChar) }).Count -gt 0
    })
    foreach ($source in $sourceFiles) {
        $relative = $source.FullName.Substring($repoPath.Length + 1)
        $copy = Join-Path $destination $relative
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $copy) -Force
        Copy-Item -LiteralPath $source.FullName -Destination $copy
    }
    foreach ($source in $sourceFiles) {
        $relative = $source.FullName.Substring($repoPath.Length + 1)
        $copy = Join-Path $destination $relative
        if ((Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash) {
            throw "Installed file differs from source: $relative"
        }
    }
} catch {
    if (Test-Path -LiteralPath $destination) {
        $null = New-Item -ItemType Directory -Path $backupRoot -Force
        Move-Item -LiteralPath $destination -Destination (Join-Path $backupRoot 'incomplete-installation')
    }
    if ($previousDestination) { Move-Item -LiteralPath $previousDestination -Destination $destination }
    throw
}
if (Test-Path -LiteralPath $oldInstallation) {
    if ((Get-Item -LiteralPath $oldInstallation).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing to move the old skill symlink.' }
    $null = New-Item -ItemType Directory -Path $backupRoot -Force
    Move-Item -LiteralPath $oldInstallation -Destination (Join-Path $backupRoot 'previous-skill')
}
Write-Host "Installed and hash-verified: $destination"
if (Test-Path -LiteralPath $backupRoot) { Write-Host "Previous installation saved outside active skills: $backupRoot" }
Write-Host 'Open a new Codex conversation to load $simple-reviewer-v1.'
