[CmdletBinding()]
param([switch]$ValidateOnly)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repositoryUrl = 'https://github.com/thanhheo7749-ui/translation-multimodal.git'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$includeDirectories = @('backend', 'frontend', 'tests', 'scripts', 'docs', 'research', 'experiments')
$includeRootFiles = @('.gitignore', 'publish_project.cmd', 'diagnose_network.cmd',
    'diagnose_network.py', 'launch_studio.py', 'run_local_comparison.cmd',
    'run_studio.cmd', 'start_studio.ps1', 'Project_Plan_Adaptive_Multimodal_Translation.md')
$excludedDirectories = @('.git', '.agents', '.codex', '.aws', '.venv', 'venv',
    '__pycache__', '.pytest_cache', 'node_modules', '.cache', '.publish-staging',
    'models', 'checkpoints', 'downloads', 'artifacts', 'runtime_logs', 'logs', 'runs',
    'local_comparison', 'nature-skills', 'reference_ui', 'tailieuthamkhao', 'researchwrite')
$textExtensions = @('.py', '.js', '.cjs', '.mjs', '.html', '.css', '.md', '.txt',
    '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.csv', '.cmd', '.ps1', '.svg')
$manifest = [Collections.Generic.List[string]]::new()
$skipped = 0

function Assert-PublishableFile([IO.FileInfo]$File) {
    if ($File.Name -match '^(\.env($|\.)|id_(rsa|ed25519|dsa|ecdsa)($|\.)|credentials.*\.json$|service[-_]account.*\.json$)' -or
        $File.Extension -in @('.pem', '.key', '.p12', '.pfx')) {
        throw "Credential-like filename rejected: $($File.Name). Keep credentials outside the publish scope."
    }
    if ($File.Length -gt 20MB) { throw "File exceeds the 20 MB publish limit: $($File.Name)" }
    $content = [IO.File]::ReadAllText($File.FullName)
    $secretPatterns = @(
        '-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
        'AIza[0-9A-Za-z_-]{35}',
        'gh[pousr]_[0-9A-Za-z]{30,}',
        'github_pat_[0-9A-Za-z_]{30,}',
        'sk-(?:proj-)?[0-9A-Za-z_-]{32,}',
        'AKIA[0-9A-Z]{16}',
        '(?i)https?://[^\s/:]+:[^\s/@]+@',
        '(?i)["'']?(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)["'']?\s*[:=]\s*["''][A-Za-z0-9_+/=-]{24,}["'']'
    )
    foreach ($pattern in $secretPatterns) {
        if ($content -match $pattern) {
            throw "Potential credential rejected in $($File.Name). Review locally; matched text is not printed."
        }
    }
}

function Add-PublishFile([IO.FileInfo]$File) {
    if (($File.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Symbolic link/reparse point rejected: $($File.Name)"
    }
    # Reject credential filenames before filtering extensions.
    if ($File.Name -match '^\.env($|\.)' -or $File.Extension -in @('.pem', '.key', '.p12', '.pfx') -or
        $File.Name -match '^(id_(rsa|ed25519|dsa|ecdsa)|credentials.*\.json$|service[-_]account.*\.json$)') {
        throw "Credential-like filename rejected: $($File.Name)"
    }
    if ($File.Extension -notin $textExtensions -and $File.Name -ne '.gitignore') {
        $script:skipped++
        return
    }
    Assert-PublishableFile $File
    $relative = $File.FullName.Substring($projectRoot.Length + 1)
    $manifest.Add($relative)
}

function Add-PublishDirectory([string]$Directory) {
    $item = Get-Item -LiteralPath $Directory -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Symbolic link/reparse directory rejected: $($item.Name)"
    }
    foreach ($entry in Get-ChildItem -LiteralPath $Directory -Force) {
        if ($entry.PSIsContainer) {
            if ($entry.Name -notin $excludedDirectories) { Add-PublishDirectory $entry.FullName }
        } else { Add-PublishFile $entry }
    }
}

function Invoke-PublishGit([string[]]$GitArguments) {
    & git @GitArguments
    if ($LASTEXITCODE -ne 0) { throw "Git failed (exit $LASTEXITCODE): $($GitArguments[0]). No force push or cleanup was attempted." }
}

function Assert-NoReparsePath([string]$Path, [string]$Boundary) {
    $resolvedBoundary = [IO.Path]::GetFullPath($Boundary).TrimEnd('\', '/')
    $candidate = [IO.Path]::GetFullPath($Path)
    if ($candidate -ne $resolvedBoundary -and
        -not $candidate.StartsWith($resolvedBoundary + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Publish destination escaped the intended staging directory.'
    }
    while ($candidate.Length -ge $resolvedBoundary.Length) {
        if (Test-Path -LiteralPath $candidate) {
            $item = Get-Item -LiteralPath $candidate -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Symbolic link/reparse point encountered in publish destination.'
            }
        }
        if ($candidate -eq $resolvedBoundary) { break }
        $candidate = Split-Path -Parent $candidate
    }
}

try {
    foreach ($directory in $includeDirectories) {
        $path = Join-Path $projectRoot $directory
        if (Test-Path -LiteralPath $path -PathType Container) { Add-PublishDirectory $path }
    }
    foreach ($name in $includeRootFiles) {
        $path = Join-Path $projectRoot $name
        if (Test-Path -LiteralPath $path -PathType Leaf) { Add-PublishFile (Get-Item -LiteralPath $path -Force) }
    }
    Write-Host "Validated $($manifest.Count) source files; skipped $skipped unsupported/binary files."
    Write-Host 'Runtime artifacts, models, data, agent installations, and downloaded papers are excluded.'
    if ($ValidateOnly) {
        Write-Host 'Validation only: no clone, commit, or push performed.'
        exit 0
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git for Windows is required. Install it and rerun in your terminal.' }
    $suffix = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $branch = "import/translation-project-$suffix"
    $stagingRoot = Join-Path $projectRoot '.publish-staging'
    $checkout = Join-Path $stagingRoot $suffix
    Assert-NoReparsePath $checkout $projectRoot
    New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null
    Write-Host "Cloning $repositoryUrl into $checkout"
    # Authentication is handled normally by Git/Git Credential Manager in the user's terminal.
    Invoke-PublishGit @('clone', '--', $repositoryUrl, $checkout)
    & git -C $checkout rev-parse --verify --quiet HEAD | Out-Null
    $hasHead = $LASTEXITCODE -eq 0
    if (-not $hasHead) {
        $remoteBranches = @(& git -C $checkout branch -r)
        if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect cloned remote branches.' }
        if ($remoteBranches.Count -gt 0) {
            throw 'Remote contains branches but has no usable default HEAD. Set its default branch on GitHub, then rerun.'
        }
    }
    Invoke-PublishGit @('-C', $checkout, 'checkout', '-b', $branch)
    foreach ($relative in $manifest) {
        $source = Join-Path $projectRoot $relative
        $destination = Join-Path $checkout $relative
        Assert-NoReparsePath $destination $checkout
        $sourceFile = Get-Item -LiteralPath $source -Force
        if (($sourceFile.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Source changed to a symbolic link during publishing.' }
        Assert-PublishableFile $sourceFile
        $destinationParent = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
        if ($relative -eq '.gitignore' -and (Test-Path -LiteralPath $destination -PathType Leaf)) {
            [IO.File]::AppendAllText($destination, "`n# Imported project exclusions`n" + [IO.File]::ReadAllText($source))
        } else {
            Copy-Item -LiteralPath $source -Destination $destination
        }
        Assert-PublishableFile (Get-Item -LiteralPath $destination -Force)
        # Only imported paths are staged; existing remote files are not removed.
        Invoke-PublishGit @('-C', $checkout, 'add', '--', $relative)
    }
    & git -C $checkout diff --cached --quiet
    $difference = $LASTEXITCODE
    if ($difference -eq 0) { throw 'No project changes to commit. Nothing was pushed.' }
    if ($difference -ne 1) { throw 'Cannot inspect the staged changes. Nothing was pushed.' }
    Invoke-PublishGit @('-C', $checkout, 'commit', '-m', 'Import translation multimodal project')
    $commit = (& git -C $checkout rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read the created commit.' }
    Invoke-PublishGit @('-C', $checkout, 'push', '--set-upstream', 'origin', "HEAD:refs/heads/$branch")
    Write-Host "Published repository: $repositoryUrl"
    Write-Host "Branch: $branch"
    Write-Host "Commit: $commit"
    Write-Host "Review: https://github.com/thanhheo7749-ui/translation-multimodal/tree/$branch"
    Write-Host "Import checkout retained at: $checkout"
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
