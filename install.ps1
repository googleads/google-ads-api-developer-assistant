<#
.SYNOPSIS
    Initializes the development environment for the Google Ads API Developer Assistant plugin on Windows.

.DESCRIPTION
    This script installs the Google Ads API Developer Assistant as a plugin for Antigravity (agy)
    or Claude Code (claudecode).

.PARAMETER Target
    Required. Target platform: 'agy' (Antigravity) or 'claudecode' (Claude Code).

.PARAMETER Php
    Include google-ads-php client library.

.PARAMETER Ruby
    Include google-ads-ruby client library.

.PARAMETER Java
    Include google-ads-java client library.

.PARAMETER Dotnet
    Include google-ads-dotnet client library.

.EXAMPLE
    .\install.ps1 -Target agy
    Installs the plugin for Antigravity with the Python client library.

.EXAMPLE
    .\install.ps1 -Target claudecode
    Installs the plugin for Claude Code into the OS-specific directory (%APPDATA%\Claude\plugins).

.EXAMPLE
    .\install.ps1 -Target agy -Java
    Installs the plugin for Antigravity with Java and Python client libraries.

.EXAMPLE
    .\install.ps1 -Target claudecode -Php -Ruby -Dotnet
    Installs the plugin for Claude Code with PHP, Ruby, .NET, and Python client libraries.
#>

param(
    [Parameter(Mandatory=$true, Position=0, HelpMessage="Target platform: 'agy' or 'claudecode'")]
    [ValidateSet("agy", "claudecode", IgnoreCase=$true)]
    [string]$Target,

    [switch]$Php,
    [switch]$Ruby,
    [switch]$Java,
    [switch]$Dotnet
)

$ErrorActionPreference = "Stop"

# --- Project Directory Resolution ---
# Determine the root directory of the current git repository.
try {
    $ProjectDirAbs = git rev-parse --show-toplevel 2>$null
    if (-not $ProjectDirAbs) { throw "Not in a git repo" }
    # Normalize path separator
    $ProjectDirAbs = (Get-Item -LiteralPath $ProjectDirAbs).FullName
}
catch {
    Write-Error "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
    exit 1
}

Write-Host "Detected project root: $ProjectDirAbs"

# Helper to get repo config
function Get-RepoConfig {
    param([string]$Lang)
    switch ($Lang) {
        "python" { return @{ Name = "google-ads-python"; Url = "https://github.com/googleads/google-ads-python.git" } }
        "php"    { return @{ Name = "google-ads-php";    Url = "https://github.com/googleads/google-ads-php.git" } }
        "ruby"   { return @{ Name = "google-ads-ruby";   Url = "https://github.com/googleads/google-ads-ruby.git" } }
        "java"   { return @{ Name = "google-ads-java";   Url = "https://github.com/googleads/google-ads-java.git" } }
        "dotnet" { return @{ Name = "google-ads-dotnet"; Url = "https://github.com/googleads/google-ads-dotnet.git" } }
    }
}

# Helper to check if enabled
function Test-Enabled {
    param([string]$Lang)
    switch ($Lang) {
        "python" { return $Python }
        "php"    { return $Php }
        "ruby"   { return $Ruby }
        "java"   { return $Java }
        "dotnet" { return $Dotnet }
        default  { return $false }
    }
}

# Helper to resolve OS-specific target plugin directory
function Get-PluginTargetDir {
    param([string]$TargetPlatform)

    $UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }

    switch ($TargetPlatform.ToLower()) {
        "agy" {
            return (Join-Path $UserHome ".gemini\config\plugins\google-ads-api-developer-assistant")
        }
        "claudecode" {
            if ($env:APPDATA) {
                return (Join-Path $env:APPDATA "Claude\plugins\google-ads-api-developer-assistant")
            }
            elseif ($IsMacOS -or ($PSVersionTable.OS -and $PSVersionTable.OS -match "Darwin")) {
                return (Join-Path $UserHome "Library/Application Support/Claude/plugins/google-ads-api-developer-assistant")
            }
            elseif ($IsLinux -or ($PSVersionTable.OS -and $PSVersionTable.OS -match "Linux")) {
                $ConfigBase = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $UserHome ".config" }
                return (Join-Path $ConfigBase "claude/plugins/google-ads-api-developer-assistant")
            }
            else {
                return (Join-Path $UserHome ".claude\plugins\google-ads-api-developer-assistant")
            }
        }
        default {
            throw "Invalid target '$TargetPlatform'. Must be 'agy' or 'claudecode'."
        }
    }
}

# Helper to detect latest API version from client_libs and pre-seed config/api_version.txt
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
                New-Item -ItemType Directory -Force -LiteralPath $TargetConfigDir | Out-Null
            }
            Set-Content -Path (Join-Path $TargetConfigDir "api_version.txt") -Value $Latest
            Write-Host "Configured API version $Latest in $(Join-Path $TargetConfigDir 'api_version.txt')"
        }
    }
}

# --- Defaults ---
$Python = $true
$AnySelected = $false

if ($Php -or $Ruby -or $Java -or $Dotnet) {
    $AnySelected = $true
}

# --- Environment Verification ---
function Test-PythonEnvironment {
    $Candidates = @("python3", "python", "py")
    $FoundVersion = $null
    $FoundPath = $null

    foreach ($Cmd in $Candidates) {
        $CmdInfo = Get-Command $Cmd -ErrorAction SilentlyContinue
        if ($CmdInfo) {
            try {
                $VerOutput = & $Cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Found Python $VerOutput ($($CmdInfo.Source))"
                    return $true
                }
                elseif ($VerOutput) {
                    $FoundVersion = $VerOutput
                    $FoundPath = $CmdInfo.Source
                }
            }
            catch {}
        }
    }

    Write-Error "ERROR: Python 3.10 or higher is required."
    if ($FoundVersion) {
        Write-Error "Incompatible Python version detected: $FoundVersion ($FoundPath)."
    }
    else {
        Write-Error "No Python interpreter was found on PATH."
    }
    Write-Error "Please install Python 3.10 or later and ensure it is available in your PATH."
    Write-Error "Visit https://www.python.org/downloads/ for installation instructions."
    return $false
}

function Test-AntigravityEnvironment {
    if (Get-Command agy -ErrorAction SilentlyContinue) {
        Write-Host "Found Antigravity CLI (agy)"
        return $true
    }
    if (Get-Command antigravity -ErrorAction SilentlyContinue) {
        Write-Host "Found Antigravity CLI (antigravity)"
        return $true
    }

    if ($env:ANTIGRAVITY_APP_DIR -or $env:ANTIGRAVITY_LS_ADDRESS -or $env:ANTIGRAVITY_PORT -or $env:JETSKI_HOME -or $env:GEMINI_HOME) {
        Write-Host "Antigravity environment detected via environment variables"
        return $true
    }

    $UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
    $GeminiDir = Join-Path $UserHome ".gemini"
    $AntigravityDir = Join-Path $UserHome ".antigravity"
    if ((Test-Path -LiteralPath $GeminiDir) -or (Test-Path -LiteralPath $AntigravityDir)) {
        Write-Host "Antigravity configuration/installation found in home directory ($GeminiDir or $AntigravityDir)"
        return $true
    }

    $ProgramDirs = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Antigravity"),
        (Join-Path $env:PROGRAMFILES "Antigravity"),
        (Join-Path ${env:ProgramFiles(x86)} "Antigravity")
    )
    foreach ($Dir in $ProgramDirs) {
        if ($Dir -and (Test-Path -LiteralPath $Dir)) {
            Write-Host "Antigravity Desktop installation found at $Dir"
            return $true
        }
    }

    Write-Error "ERROR: Antigravity CLI or Antigravity Desktop/Web is not installed."
    Write-Error "The Google Ads API Developer Assistant requires an active Antigravity environment."
    Write-Error "Please install Antigravity CLI ('agy' or 'antigravity') or Antigravity Desktop/Web to continue."
    return $false
}

function Test-ClaudeCodeEnvironment {
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        Write-Host "Found Claude Code CLI (claude)"
        return $true
    }
    if (Get-Command claude-code -ErrorAction SilentlyContinue) {
        Write-Host "Found Claude Code CLI (claude-code)"
        return $true
    }

    $UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
    $ClaudeConfigDir = if ($env:APPDATA) { Join-Path $env:APPDATA "Claude" } else { Join-Path $UserHome ".claude" }
    if (Test-Path -LiteralPath $ClaudeConfigDir) {
        Write-Host "Claude configuration found at $ClaudeConfigDir"
        return $true
    }

    Write-Host "Note: Claude Code CLI ('claude') not found on PATH. Proceeding with installation to target plugin directory."
    return $true
}

function check_environment {
    Write-Host "Checking environment for $Target..."
    $EnvOk = $true

    if (-not (Test-PythonEnvironment)) {
        $EnvOk = $false
    }

    if ($Target.ToLower() -eq "agy") {
        if (-not (Test-AntigravityEnvironment)) {
            $EnvOk = $false
        }
    }
    elseif ($Target.ToLower() -eq "claudecode") {
        if (-not (Test-ClaudeCodeEnvironment)) {
            $EnvOk = $false
        }
    }

    if (-not $EnvOk) {
        Write-Error "ERROR: Environment check failed. Aborting installation."
        exit 1
    }
    Write-Host "Environment check passed."
}

# Run environment verification before proceeding with installation
check_environment

# --- Plugin Installation ---
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: git is not installed. Please install it to continue."
    exit 1
}

$PluginSource = Join-Path $ProjectDirAbs "plugins\agy"
if (-not (Test-Path -LiteralPath $PluginSource)) {
    Write-Error "ERROR: Plugin directory not found at $PluginSource"
    exit 1
}

$TargetPluginDir = Get-PluginTargetDir -TargetPlatform $Target
$ParentPluginDir = Split-Path $TargetPluginDir

Write-Host "Installing plugin for $Target into: $TargetPluginDir"
if (-not (Test-Path -LiteralPath $ParentPluginDir)) {
    New-Item -ItemType Directory -Force -LiteralPath $ParentPluginDir | Out-Null
}

if (Test-Path -LiteralPath $TargetPluginDir) {
    Remove-Item -Recurse -Force -LiteralPath $TargetPluginDir
}

Copy-Item -Recurse -Force -LiteralPath $PluginSource -Destination $TargetPluginDir

# Add any additional selected client libraries to plugin structure
$PluginClientLibsDir = Join-Path $TargetPluginDir "client_libs"
if (-not (Test-Path -LiteralPath $PluginClientLibsDir)) {
    New-Item -ItemType Directory -Force -LiteralPath $PluginClientLibsDir | Out-Null
}

$OtherLangs = @("php", "ruby", "java", "dotnet")
foreach ($Lang in $OtherLangs) {
    if (Test-Enabled -Lang $Lang) {
        $Config = Get-RepoConfig -Lang $Lang
        $TargetRepoPath = Join-Path $PluginClientLibsDir $Config.Name
        $SourceRepoPath = Join-Path $ProjectDirAbs (Join-Path "client_libs" $Config.Name)
        $RepoUrl = $Config.Url

        if (Test-Path -LiteralPath $SourceRepoPath) {
            Write-Host "Adding $($Config.Name) to plugin client_libs from $SourceRepoPath..."
            if (Test-Path -LiteralPath $TargetRepoPath) {
                Remove-Item -Recurse -Force -LiteralPath $TargetRepoPath
            }
            Copy-Item -Recurse -Force -LiteralPath $SourceRepoPath -Destination $TargetRepoPath
        }
        else {
            Write-Host "Cloning $RepoUrl into $TargetRepoPath..."
            git clone $RepoUrl $TargetRepoPath
            if ($LASTEXITCODE -ne 0) {
                Write-Error "ERROR: Failed to clone $RepoUrl"
                exit 1
            }
            Write-Host "Successfully cloned $($Config.Name)."
        }
    }
}

# Pre-seed latest API version in plugin and project config
$PluginPythonDir = Join-Path $TargetPluginDir "client_libs\google-ads-python\google\ads\googleads"
Set-LatestApiVersion -SearchDir $PluginPythonDir -TargetConfigDir (Join-Path $TargetPluginDir "config")
Set-LatestApiVersion -SearchDir $PluginPythonDir -TargetConfigDir (Join-Path $ProjectDirAbs "config")

Write-Host "Plugin installation for $Target complete."
Write-Host ""
if ($Target.ToLower() -eq "agy") {
    Write-Host "Restart your Antigravity / agy host to activate the plugin."
} else {
    Write-Host "Restart your Claude Code environment to activate the plugin."
}

