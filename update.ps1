<#
.SYNOPSIS
    Updates the Google Ads API Developer Assistant plugin and its dependencies on Windows.

.DESCRIPTION
    This script updates the Google Ads API Developer Assistant repository and installed plugin:
    1. Updates the git repository (git pull).
    2. Syncs updated plugin assets to the platform-specific plugin directory (Antigravity or Claude Code).
    3. Clones or updates configured client libraries in the plugin's 'client_libs/' directory.

.PARAMETER Type
    Required. Target platform: 'agy' (Antigravity) or 'claude' (Claude Code).

.PARAMETER Python
    Ensure google-ads-python is present and updated.

.PARAMETER Php
    Ensure google-ads-php is present and updated.

.PARAMETER Ruby
    Ensure google-ads-ruby is present and updated.

.PARAMETER Java
    Ensure google-ads-java is present and updated.

.PARAMETER Dotnet
    Ensure google-ads-dotnet is present and updated.

.PARAMETER All
    Ensure all client libraries are present and updated.

.EXAMPLE
    .\update.ps1 -Type agy
    Updates repository, Antigravity plugin, and all configured client libraries.

.EXAMPLE
    .\update.ps1 -Type claude
    Updates repository, Claude Code plugin, and all configured client libraries.

.EXAMPLE
    .\update.ps1 -Type agy -Java
    Ensures Java library is present and updated in Antigravity plugin.
#>

param(
    [Parameter(Position=0, HelpMessage="Target platform: 'agy' or 'claude'")]
    [string]$Type,

    [switch]$Python,
    [switch]$Php,
    [switch]$Ruby,
    [switch]$Java,
    [switch]$Dotnet,
    [switch]$All
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Type)) {
    Write-Error "ERROR: Missing required -Type parameter ('agy' or 'claude')."
    exit 1
}

$TypeLower = $Type.ToLower()
if ($TypeLower -notin @("agy", "claude", "claudecode")) {
    Write-Error "ERROR: Invalid Type '$Type'. Must be 'agy' or 'claude'."
    exit 1
}

function Get-RepoUrl {
    param($Lang)
    switch ($Lang) {
        "python" { return "https://github.com/googleads/google-ads-python.git" }
        "php"    { return "https://github.com/googleads/google-ads-php.git" }
        "ruby"   { return "https://github.com/googleads/google-ads-ruby.git" }
        "java"   { return "https://github.com/googleads/google-ads-java.git" }
        "dotnet" { return "https://github.com/googleads/google-ads-dotnet.git" }
    }
}

function Get-RepoName {
    param($Lang)
    switch ($Lang) {
        "python" { return "google-ads-python" }
        "php"    { return "google-ads-php" }
        "ruby"   { return "google-ads-ruby" }
        "java"   { return "google-ads-java" }
        "dotnet" { return "google-ads-dotnet" }
    }
}


function Update-GitRepo {
    param([string]$RepoDir)
    Push-Location $RepoDir
    try {
        $CurrentBranch = git symbolic-ref -q --short HEAD 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($CurrentBranch)) {
            $DefaultBranch = $null
            $OriginHead = git symbolic-ref -q --short refs/remotes/origin/HEAD 2>$null
            if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($OriginHead)) {
                $DefaultBranch = $OriginHead -replace '^origin/', ''
            }
            if ([string]::IsNullOrWhiteSpace($DefaultBranch)) {
                foreach ($Candidate in @("main", "master")) {
                    git show-ref --verify --quiet "refs/heads/$Candidate" 2>$null
                    if ($LASTEXITCODE -eq 0) {
                        $DefaultBranch = $Candidate
                        break
                    }
                    git show-ref --verify --quiet "refs/remotes/origin/$Candidate" 2>$null
                    if ($LASTEXITCODE -eq 0) {
                        $DefaultBranch = $Candidate
                        break
                    }
                }
            }
            if (-not [string]::IsNullOrWhiteSpace($DefaultBranch)) {
                git show-ref --verify --quiet "refs/heads/$DefaultBranch" 2>$null
                if ($LASTEXITCODE -eq 0) {
                    git checkout $DefaultBranch 2>$null | Out-Null
                } else {
                    git checkout -B $DefaultBranch "origin/$DefaultBranch" 2>$null | Out-Null
                }
                git branch --set-upstream-to="origin/$DefaultBranch" $DefaultBranch 2>$null | Out-Null
            }
        }
        git -c maintenance.auto=false -c gc.auto=0 -c gc.autoDetach=false pull
        return ($LASTEXITCODE -eq 0)
    }
    finally {
        Pop-Location
    }
}

function Set-LatestApiVersion {
    param(
        [string]$SearchDir,
        [string]$TargetConfigDir
    )
    if (Test-Path -LiteralPath $SearchDir) {
        $VersionDirs = Get-ChildItem -Directory -Path $SearchDir -Filter "v*" |
            Where-Object { $_.Name -match "^v\d+$" } |
            Sort-Object { [int]($_.Name.Substring(1)) }
        if ($VersionDirs) {
            $Latest = $VersionDirs[-1].Name
            if (-not (Test-Path -LiteralPath $TargetConfigDir)) {
                New-Item -ItemType Directory -Force -Path $TargetConfigDir | Out-Null
            }
            $CfgFile = Join-Path $TargetConfigDir "assistant_config"
            $Cid = "12345678"
            $ExecMutates = "false"
            if (Test-Path -LiteralPath $CfgFile) {
                $Existing = Get-Content -LiteralPath $CfgFile -Raw
                if ($Existing -match '(?m)^\s*customer_id\s*=\s*["'']?([^"''\s#]+)["'']?') {
                    $Cid = $Matches[1].Trim()
                }
                if ($Existing -match '(?mi)^\s*execute_mutates\s*=\s*["'']?(true|false)["'']?') {
                    $ExecMutates = $Matches[1].ToLower()
                }
            }
            if ($Cid -eq "12345678") {
                $PluginConfigDir = Join-Path (Join-Path $ProjectDirAbs "plugins\google-ads-api-developer-assistant") "config"
                $LegacyCandidates = @(
                    (Join-Path $TargetConfigDir "customer_id"),
                    (Join-Path $TargetConfigDir "customer_id.txt"),
                    (Join-Path $PluginConfigDir "customer_id"),
                    (Join-Path $PluginConfigDir "customer_id.txt")
                )
                foreach ($LegacyFile in $LegacyCandidates) {
                    if ($LegacyFile -and (Test-Path -LiteralPath $LegacyFile)) {
                        $LegacyCid = (Get-Content -LiteralPath $LegacyFile -Raw).Trim().Trim("`"'")
                        if ($LegacyCid -and $LegacyCid -ne "12345678") {
                            $Cid = $LegacyCid
                            break
                        }
                    }
                }
            }
            $TomlContent = "api_version = `"$Latest`"`ncustomer_id = `"$Cid`"`nexecute_mutates = $ExecMutates`n"
            Set-Content -Path $CfgFile -Value $TomlContent -NoNewline
            Write-Host "Configured API version $Latest in $CfgFile"
        }
    }
}

$ErrorActionPreference = "Stop"
$env:GIT_CONFIG_PARAMETERS = "'maintenance.auto=false' 'gc.auto=0' 'gc.autoDetach=false'"

# --- Dependency Check ---
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: git is not installed. Please install it to continue."
    exit 1
}

# --- Project Directory Resolution ---
try {
    $ProjectDirAbs = git rev-parse --show-toplevel 2>$null
    if (-not $ProjectDirAbs) { throw "Not in a git repo" }
    $ProjectDirAbs = (Get-Item -LiteralPath $ProjectDirAbs).FullName
}
catch {
    Write-Error "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
    exit 1
}

Write-Host "Detected project root: $ProjectDirAbs"

# --- Update Assistant Repo ---
Write-Host "Updating google-ads-api-developer-assistant repository..."

$ConfigDir = Join-Path (Join-Path $ProjectDirAbs "plugins\google-ads-api-developer-assistant") "config"
$TempConfigDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Force -Path $TempConfigDir | Out-Null

try {
    $CfgFiles = @("assistant_config", "customer_id", "customer_id.txt")
    foreach ($CfgFile in $CfgFiles) {
        $SrcCfg = Join-Path $ConfigDir $CfgFile
        if (Test-Path -LiteralPath $SrcCfg) {
            Copy-Item -LiteralPath $SrcCfg -Destination (Join-Path $TempConfigDir $CfgFile) -Force
        }
    }

    git -c maintenance.auto=false -c gc.auto=0 -c gc.autoDetach=false pull
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to update google-ads-api-developer-assistant repository."
    }
    Write-Host "Successfully updated repository."

    foreach ($CfgFile in $CfgFiles) {
        $BackupCfg = Join-Path $TempConfigDir $CfgFile
        if (Test-Path -LiteralPath $BackupCfg) {
            Copy-Item -LiteralPath $BackupCfg -Destination (Join-Path $ConfigDir $CfgFile) -Force
        }
    }
}
catch {
    Write-Error "ERROR: $_"
    foreach ($CfgFile in $CfgFiles) {
        $BackupCfg = Join-Path $TempConfigDir $CfgFile
        if (Test-Path -LiteralPath $BackupCfg) {
            Copy-Item -LiteralPath $BackupCfg -Destination (Join-Path $ConfigDir $CfgFile) -Force
        }
    }
    exit 1
}
finally {
    if (Test-Path -LiteralPath $TempConfigDir) {
        Remove-Item -Recurse -Force -LiteralPath $TempConfigDir -ErrorAction SilentlyContinue
    }
}

$SpecifiedLangs = @()
if ($All) {
    $SpecifiedLangs = @("python", "php", "ruby", "java", "dotnet")
} else {
    if ($Python) { $SpecifiedLangs += "python" }
    if ($Php)    { $SpecifiedLangs += "php" }
    if ($Ruby)   { $SpecifiedLangs += "ruby" }
    if ($Java)   { $SpecifiedLangs += "java" }
    if ($Dotnet) { $SpecifiedLangs += "dotnet" }
}

# --- Plugin Update & Client Libraries ---
$UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$AgyPluginTargetDir = Join-Path $UserHome ".gemini\config\plugins\google-ads-api-developer-assistant"
$PluginSourceDir = Join-Path $ProjectDirAbs "plugins\google-ads-api-developer-assistant"
$PluginSourceClientLibs = Join-Path $PluginSourceDir "client_libs"

if (-not (Test-Path -LiteralPath $PluginSourceClientLibs)) {
    New-Item -ItemType Directory -Force -Path $PluginSourceClientLibs | Out-Null
}

# Handle specific library additions in repository plugin source
if ($SpecifiedLangs.Count -gt 0) {
    foreach ($Lang in $SpecifiedLangs) {
        $RepoUrl = Get-RepoUrl $Lang
        $RepoName = Get-RepoName $Lang
        $SourceLibPath = Join-Path $PluginSourceClientLibs $RepoName

        if (-not (Test-Path -LiteralPath $SourceLibPath)) {
            Write-Host "Library $RepoName not found in repository client_libs. Cloning into $SourceLibPath..."
            git -c core.longpaths=true -c maintenance.auto=false -c gc.auto=0 -c gc.autoDetach=false clone --depth 1 $RepoUrl $SourceLibPath
            if ($LASTEXITCODE -ne 0) {
                Write-Error "ERROR: Failed to clone $RepoUrl"
                exit 1
            }
            Remove-Item -Force -LiteralPath (Join-Path $SourceLibPath "google-ads.yaml") -ErrorAction SilentlyContinue
        }
    }
}

# Locate and update all client libraries in repository
Write-Host "Locating client libraries to update..."
$IncludeDirs = @()
if (Test-Path -LiteralPath $PluginSourceClientLibs) {
    foreach ($Dir in Get-ChildItem -LiteralPath $PluginSourceClientLibs -Directory) {
        if (Test-Path -LiteralPath (Join-Path $Dir.FullName ".git")) {
            $IncludeDirs += $Dir.FullName
        }
    }
}

if ($IncludeDirs.Count -eq 0) {
    Write-Host "No client libraries found in repository to update."
} else {
    Write-Host "Found $($IncludeDirs.Count) client libraries to update."
    foreach ($LibPath in $IncludeDirs) {
        if ([string]::IsNullOrWhiteSpace($LibPath)) { continue }
        if (-not (Test-Path -LiteralPath $LibPath)) { continue }
        $AbsLibPath = (Get-Item -LiteralPath $LibPath).FullName
        if (-not (Test-Path -LiteralPath (Join-Path $AbsLibPath ".git"))) { continue }

        Write-Host "Updating repository at: $AbsLibPath..."
        try {
            if (Update-GitRepo -RepoDir $AbsLibPath) {
                Write-Host "Successfully updated $(Split-Path $AbsLibPath -Leaf)."
            } else {
                Write-Warning "WARN: Failed to update $(Split-Path $AbsLibPath -Leaf). Continuing..."
            }
        }
        catch {
            Write-Warning "WARN: Failed to update $(Split-Path $AbsLibPath -Leaf). Continuing..."
        }
        Remove-Item -Force -LiteralPath (Join-Path $AbsLibPath "google-ads.yaml") -ErrorAction SilentlyContinue
    }
}

$PluginPythonDir = Join-Path $PluginSourceDir "client_libs\google-ads-python\google\ads\googleads"
Set-LatestApiVersion -SearchDir $PluginPythonDir -TargetConfigDir (Join-Path $PluginSourceDir "config")

function Sync-InstalledPluginDir {
    param([string]$TargetPluginDir)
    $ParentPluginDir = Split-Path $TargetPluginDir
    $IsSymlink = $false
    if (Test-Path -LiteralPath $TargetPluginDir) {
        $TargetItem = Get-Item -LiteralPath $TargetPluginDir -Force
        if (($TargetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or $TargetItem.LinkType) {
            $IsSymlink = $true
        }
    }

    if ($IsSymlink) {
        Write-Host "Replacing legacy symlink at $TargetPluginDir with standalone plugin copy..."
        Remove-Item -Force -LiteralPath $TargetPluginDir
    }

    if (-not (Test-Path -LiteralPath $TargetPluginDir)) {
        Write-Host "Plugin not yet installed at $TargetPluginDir. Installing standalone copy..."
        if (-not (Test-Path -LiteralPath $ParentPluginDir)) {
            New-Item -ItemType Directory -Force -Path $ParentPluginDir | Out-Null
        }
        Copy-Item -Recurse -Force -LiteralPath $PluginSourceDir -Destination $TargetPluginDir
    }
    else {
        Write-Host "Syncing plugin files to $TargetPluginDir..."
        $TargetCfgFile = Join-Path (Join-Path $TargetPluginDir "config") "assistant_config"
        $BackupCfgContent = $null
        if (Test-Path -LiteralPath $TargetCfgFile) {
            $BackupCfgContent = Get-Content -LiteralPath $TargetCfgFile -Raw
        }
        Get-ChildItem -LiteralPath $PluginSourceDir -Force | ForEach-Object {
            if ($_.Name -ne "client_libs") {
                Copy-Item -Recurse -Force -LiteralPath $_.FullName -Destination (Join-Path $TargetPluginDir $_.Name)
            }
        }
        if ($BackupCfgContent) {
            Set-Content -Path $TargetCfgFile -Value $BackupCfgContent -NoNewline
        }
    }

    $TargetClientLibs = Join-Path $TargetPluginDir "client_libs"
    if (-not (Test-Path -LiteralPath $TargetClientLibs)) {
        New-Item -ItemType Directory -Force -Path $TargetClientLibs | Out-Null
    }

    if (Test-Path -LiteralPath $PluginSourceClientLibs) {
        foreach ($LibDir in Get-ChildItem -LiteralPath $PluginSourceClientLibs -Directory) {
            $TargetLibPath = Join-Path $TargetClientLibs $LibDir.Name
            if (-not (Test-Path -LiteralPath $TargetLibPath)) {
                Write-Host "Copying $($LibDir.Name) to $TargetLibPath..."
                Copy-Item -Recurse -Force -LiteralPath $LibDir.FullName -Destination $TargetLibPath
            }
            Remove-Item -Force -LiteralPath (Join-Path $TargetLibPath "google-ads.yaml") -ErrorAction SilentlyContinue
        }
    }

    if (Test-Path -LiteralPath $TargetClientLibs) {
        foreach ($Dir in Get-ChildItem -LiteralPath $TargetClientLibs -Directory) {
            if (Test-Path -LiteralPath (Join-Path $Dir.FullName ".git")) {
                Write-Host "Updating repository at: $($Dir.FullName)..."
                try {
                    if (Update-GitRepo -RepoDir $Dir.FullName) {
                        Write-Host "Successfully updated $($Dir.Name)."
                    } else {
                        Write-Warning "WARN: Failed to update $($Dir.Name) in target directory. Continuing..."
                    }
                }
                catch {
                    Write-Warning "WARN: Failed to update $($Dir.Name) in target directory. Continuing..."
                }
                Remove-Item -Force -LiteralPath (Join-Path $Dir.FullName "google-ads.yaml") -ErrorAction SilentlyContinue
            }
        }
    }

    $TargetPythonDir = Join-Path $TargetPluginDir "client_libs\google-ads-python\google\ads\googleads"
    Set-LatestApiVersion -SearchDir $TargetPythonDir -TargetConfigDir (Join-Path $TargetPluginDir "config")
}

if ($Type.ToLower() -eq "agy") {
    Sync-InstalledPluginDir -TargetPluginDir $AgyPluginTargetDir
}
elseif ($Type.ToLower() -eq "claude" -or $Type.ToLower() -eq "claudecode") {
    $ClaudeMarketplaceDir = Join-Path $UserHome ".claude\plugins\google-ads-assistant-local"
    $ClaudePluginTargetDir = Join-Path $ClaudeMarketplaceDir "plugins\google-ads-api-developer-assistant"
    $ClaudeManifestDir = Join-Path $ClaudeMarketplaceDir ".claude-plugin"
    if (-not (Test-Path -LiteralPath $ClaudeManifestDir)) {
        New-Item -ItemType Directory -Force -Path $ClaudeManifestDir | Out-Null
    }
    Copy-Item -Force -LiteralPath (Join-Path $ProjectDirAbs ".claude-plugin\marketplace.json") -Destination (Join-Path $ClaudeManifestDir "marketplace.json")
    Sync-InstalledPluginDir -TargetPluginDir $ClaudePluginTargetDir
}

Write-Host "Plugin update for $Type complete."
Write-Host ""
if ($Type.ToLower() -eq "agy") {
    Write-Host "Restart your Antigravity / agy host to apply changes."
} else {
    Write-Host "In your Claude Code session, run /reload-plugins to apply changes."
}
