<#
.SYNOPSIS
    Initializes the development environment for the Google Ads API Developer Assistant plugin on Windows.

.DESCRIPTION
    This script installs the Google Ads API Developer Assistant as a plugin for Antigravity (agy)
    or Claude Code (claude).

.PARAMETER Type
    Target platform: 'agy' (Antigravity) or 'claude' (Claude Code).

.PARAMETER Agy
    Shorthand switch for -Type agy.

.PARAMETER Claude
    Shorthand switch for -Type claude.

.PARAMETER Python
    Include google-ads-python client library (included by default).

.PARAMETER Php
    Include google-ads-php client library.

.PARAMETER Ruby
    Include google-ads-ruby client library.

.PARAMETER Java
    Include google-ads-java client library.

.PARAMETER Dotnet
    Include google-ads-dotnet client library.

.PARAMETER All
    Include all client libraries.

.EXAMPLE
    .\install.ps1 -Type agy
    Installs the plugin for Antigravity with the Python client library.

.EXAMPLE
    .\install.ps1 -Type claude
    Installs the plugin for Claude Code using Claude CLI.

.EXAMPLE
    .\install.ps1 -Type agy -Java
    Installs the plugin for Antigravity with Java and Python client libraries.

.EXAMPLE
    .\install.ps1 -Type claude -Php -Ruby -Dotnet
    Installs the plugin for Claude Code with PHP, Ruby, .NET, and Python client libraries.
#>

param(
    [Parameter(Position=0, HelpMessage="Target platform: 'agy' or 'claude'")]
    [string]$Type,

    [switch]$Agy,
    [Alias("ClaudeCode")]
    [switch]$Claude,

    [switch]$Python,
    [switch]$Php,
    [switch]$Ruby,
    [switch]$Java,
    [switch]$Dotnet,
    [switch]$All,

    [Parameter(Mandatory=$false, HelpMessage="Default Google Ads Customer ID (e.g. 1234567890)")]
    [Alias("cid")]
    [string]$CustomerId = "",

    [switch]$Enable,
    [Alias("Disabled")]
    [switch]$Disable,
    [switch]$Status,

    [Parameter(Mandatory=$false, HelpMessage="Legacy option: symlinking is not supported for agy; standalone directory copy is always used.")]
    [switch]$Link
)

$ErrorActionPreference = "Stop"

if ($Link) {
    Write-Error "ERROR: -Link is not supported. Antigravity plugin is always installed as a standalone copy."
    exit 1
}

if ($Agy -and $Claude) {
    Write-Error "ERROR: Cannot specify both -Agy and -Claude."
    exit 1
}

if ([string]::IsNullOrWhiteSpace($Type)) {
    if ($Agy) { $Type = "agy" }
    elseif ($Claude) { $Type = "claude" }
}

if (-not [string]::IsNullOrWhiteSpace($Type)) {
    $Type = $Type.Trim().ToLowerInvariant()
    if ($Type -eq "claudecode") {
        $Type = "claude"
    }
}

# --- Project Directory Resolution ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDirAbs = $null
try {
    $Candidate = git -C $ScriptDir rev-parse --show-toplevel 2>$null
    if ($Candidate -and (Test-Path -LiteralPath (Join-Path $Candidate "plugins\google-ads-api-developer-assistant"))) {
        $ProjectDirAbs = (Get-Item -LiteralPath $Candidate).FullName
    }
} catch {}
if (-not $ProjectDirAbs) {
    try {
        $Candidate = git rev-parse --show-toplevel 2>$null
        if ($Candidate -and (Test-Path -LiteralPath (Join-Path $Candidate "plugins\google-ads-api-developer-assistant"))) {
            $ProjectDirAbs = (Get-Item -LiteralPath $Candidate).FullName
        }
    } catch {}
}
if (-not $ProjectDirAbs) {
    Write-Error "ERROR: Could not locate the google-ads-api-developer-assistant git repository."
    exit 1
}

if ($Status) {
    if (-not [string]::IsNullOrWhiteSpace($Type) -and $Type -notin @("agy", "claude", "all")) {
        Write-Error "ERROR: Invalid Type '$Type'. Must be 'agy', 'claude', or 'all'."
        exit 1
    }
    $Target = if ([string]::IsNullOrWhiteSpace($Type)) { "all" } else { $Type }
    & (Join-Path $ProjectDirAbs "plugin.ps1") status $Target
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($Type)) {
    Write-Error "ERROR: Missing required -Type parameter ('agy' or 'claude')."
    exit 1
}

if ($Type -notin @("agy", "claude")) {
    Write-Error "ERROR: Invalid Type '$Type'. Must be 'agy' or 'claude'."
    exit 1
}

Write-Host "Detected project root: $ProjectDirAbs"

# Helper to safely remove a symlink or directory junction without deleting target contents
function Remove-ReparsePointSafely {
    param([string]$Path)
    $Item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $Item) { return }
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        if ($Item.PSIsContainer) {
            [System.IO.Directory]::Delete($Item.FullName)
        } else {
            [System.IO.File]::Delete($Item.FullName)
        }
    } else {
        try {
            [System.IO.File]::Delete($Item.FullName)
        } catch {
            Remove-Item -Force -LiteralPath $Item.FullName
        }
    }
}

# Helper to write UTF-8 without BOM (compatible with Windows PowerShell 5.1 and PowerShell 7+)
function Write-Utf8NoBom {
    param(
        [string]$Path,
        [string]$Content
    )
    $FullPath = if ([System.IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path (Get-Location).ProviderPath $Path }
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($FullPath, $Content, $Utf8NoBom)
}

# Helper to locate a working Python 3.11+ interpreter (rejects Windows Store alias stubs)
function Find-WorkingPython {
    $FoundVersion = $null
    $FoundPath = $null
    foreach ($Candidate in @(
        @{ Name = "python3"; PrefixArgs = @() },
        @{ Name = "python";  PrefixArgs = @() },
        @{ Name = "py";      PrefixArgs = @("-3") },
        @{ Name = "py";      PrefixArgs = @() }
    )) {
        $Cmd = $Candidate.Name
        $PrefixArgs = $Candidate.PrefixArgs
        $CmdInfo = Get-Command $Cmd -ErrorAction SilentlyContinue
        if (-not $CmdInfo) { continue }
        try {
            $ProbeArgs = @($PrefixArgs) + @("-c", 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"); sys.exit(0 if sys.version_info >= (3, 11) else 1)')
            $global:LASTEXITCODE = 0
            $VerOutput = (& $Cmd @ProbeArgs 2>$null | Out-String)
            $ExitCode = $LASTEXITCODE
            $VerTrimmed = if ($null -ne $VerOutput) { $VerOutput.Trim() } else { "" }
            if ($ExitCode -eq 0 -and $VerTrimmed -match '^\d+\.\d+\.\d+$') {
                return @{
                    Found      = $true
                    Name       = $Cmd
                    PrefixArgs = $PrefixArgs
                    Source     = $CmdInfo.Source
                    Version    = $VerTrimmed
                }
            }
            elseif ($VerTrimmed -match '^\d+\.\d+\.\d+$') {
                $FoundVersion = $VerTrimmed
                $FoundPath = $CmdInfo.Source
            }
        }
        catch {}
    }
    return @{
        Found      = $false
        Name       = $null
        PrefixArgs = @()
        Source     = $FoundPath
        Version    = $FoundVersion
    }
}

# Helper to merge non-zero user-configured Service.field overrides onto the newly copied financial_limits template
function Merge-FinancialLimits {
    param(
        [string]$TemplatePath,
        [string]$BackupPath
    )
    if (-not (Test-Path -LiteralPath $BackupPath)) { return }
    if (-not (Test-Path -LiteralPath $TemplatePath)) {
        Copy-Item -Force -LiteralPath $BackupPath -Destination $TemplatePath
        return
    }
    $Overrides = [ordered]@{}
    $CurrentSection = ""
    foreach ($RawLine in (Get-Content -LiteralPath $BackupPath -Encoding UTF8)) {
        $Line = ($RawLine -replace '#.*$', '').Trim()
        if (-not $Line) { continue }
        if ($Line -match '^\[([A-Za-z0-9_.]+)\]$') {
            $CurrentSection = $Matches[1]
            continue
        }
        if ($Line -match '^([A-Za-z0-9_.]+)\s*=\s*(.+)$') {
            $Key = $Matches[1].Trim()
            $ValStr = $Matches[2].Trim().Trim("`"'")
            if ($CurrentSection -and ($Key -notmatch '\.')) {
                $Key = "$CurrentSection.$Key"
            }
            $NumVal = 0.0
            if ([double]::TryParse($ValStr, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$NumVal)) {
                if ($NumVal -ne 0.0) {
                    $Overrides[$Key] = $ValStr
                }
            }
        }
    }
    if ($Overrides.Count -eq 0) { return }

    $Applied = @{}
    $UpdatedLines = @(foreach ($RawLine in (Get-Content -LiteralPath $TemplatePath -Encoding UTF8)) {
        if ($RawLine -match '^(\s*)([A-Za-z0-9_.]+)(\s*=\s*)([^#]+?)(\s*#.*)?$') {
            $Indent = $Matches[1]
            $TKey = $Matches[2]
            $EqSep = $Matches[3]
            $CommentSuffix = $Matches[5]
            if ($Overrides.Contains($TKey)) {
                $Applied[$TKey] = $true
                "${Indent}${TKey}${EqSep}$($Overrides[$TKey])${CommentSuffix}"
                continue
            }
        }
        $RawLine
    })
    $ExtraLines = @()
    foreach ($OKey in $Overrides.Keys) {
        if (-not $Applied.ContainsKey($OKey)) {
            $ExtraLines += "$OKey = $($Overrides[$OKey])"
        }
    }
    $FinalContent = ($UpdatedLines + $ExtraLines) -join "`n"
    if (-not $FinalContent.EndsWith("`n")) {
        $FinalContent += "`n"
    }
    Write-Utf8NoBom -Path $TemplatePath -Content $FinalContent
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
        git -c core.longpaths=true -c maintenance.auto=false -c gc.auto=0 -c gc.autoDetach=false pull
        return ($LASTEXITCODE -eq 0)
    }
    finally {
        Pop-Location
    }
}

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
        "python" { return $true }
        "php"    { return ($Php -or $All) }
        "ruby"   { return ($Ruby -or $All) }
        "java"   { return ($Java -or $All) }
        "dotnet" { return ($Dotnet -or $All) }
        default  { return $false }
    }
}

# Helper to detect latest API version from client_libs and pre-seed config/assistant_config
function Set-LatestApiVersion {
    param(
        [string]$SearchDir,
        [string]$TargetConfigDir
    )
    $Latest = $null
    if (Test-Path -LiteralPath $SearchDir) {
        $VersionDirs = Get-ChildItem -Directory -LiteralPath $SearchDir -Filter "v*" |
            Where-Object { $_.Name -match "^v\d+$" } |
            Sort-Object { [int]($_.Name.Substring(1)) }
        if ($VersionDirs) {
            $Latest = $VersionDirs[-1].Name
        }
    }
    if (-not $Latest) {
        $Py = Find-WorkingPython
        if ($Py.Found) {
            try {
                $DetectArgs = @($Py.PrefixArgs) + @("-c", 'import importlib.util, os, re; s = importlib.util.find_spec("google.ads.googleads"); locs = list(s.submodule_search_locations or ()) if s else []; vs = sorted([d for p in locs if os.path.isdir(p) for d in os.listdir(p) if re.fullmatch(r"v\d+", d)], key=lambda d: int(d[1:])); print(vs[-1] if vs else "")')
                $global:LASTEXITCODE = 0
                $DetectedPy = (& $Py.Name @DetectArgs 2>$null | Out-String)
                if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($DetectedPy)) {
                    $Latest = $DetectedPy.Trim()
                }
            } catch {}
        }
    }
    if ($Latest -or $CustomerId) {
        if (-not (Test-Path -LiteralPath $TargetConfigDir)) {
            New-Item -ItemType Directory -Force -Path $TargetConfigDir | Out-Null
        }
        $CfgFile = Join-Path $TargetConfigDir "assistant_config"
        $ApiVer = if ($Latest) { $Latest } else { "" }
        $Cid = "12345678"
        $ExecMutates = "false"
        $Tier1Mutates = "false"
        $PluginEnabled = "true"
        $ExtraLines = @()
        if (Test-Path -LiteralPath $CfgFile) {
            $Existing = Get-Content -LiteralPath $CfgFile -Raw -Encoding UTF8
            if ($null -ne $Existing) {
                if (-not $Latest -and ($Existing -match '(?m)^\s*api_version\s*=\s*["'']?([^"''\s#]+)["'']?')) {
                    $ExistingVer = $Matches[1].Trim()
                    if ($ExistingVer -match '^v?(\d+)$') {
                        $ApiVer = "v$($Matches[1])"
                    }
                    else {
                        Write-Warning "Ignoring invalid api_version '$ExistingVer' in $CfgFile (expected vNN)."
                    }
                }
                if ($Existing -match '(?m)^\s*customer_id\s*=\s*["'']?([^"''\s#]+)["'']?') {
                    $Cid = $Matches[1].Trim()
                }
                if ($Existing -match '(?mi)^\s*execute_mutates\s*=\s*["'']?(true|false)["'']?') {
                    $ExecMutates = $Matches[1].ToLower()
                }
                if ($Existing -match '(?mi)^\s*allow_tier1_financial_mutates\s*=\s*["'']?(true|false)["'']?') {
                    $Tier1Mutates = $Matches[1].ToLower()
                }
                if ($Existing -match '(?mi)^\s*(?:enabled|plugin_enabled)\s*=\s*["'']?(true|false)["'']?') {
                    $PluginEnabled = $Matches[1].ToLower()
                }
                foreach ($RawLine in ($Existing -split "`r?`n")) {
                    if ([string]::IsNullOrWhiteSpace($RawLine)) { continue }
                    if ($RawLine -notmatch '^\s*(?:api_version|customer_id|execute_mutates|allow_tier1_financial_mutates|enabled|plugin_enabled)\s*=') {
                        $ExtraLines += $RawLine
                    }
                }
            }
        }
        if ($Disable) { $PluginEnabled = "false" }
        elseif ($Enable) { $PluginEnabled = "true" }
        if ($CustomerId) {
            $Cid = $CustomerId.Trim().Trim("`"'").Replace("-", "")
        } elseif ($Cid -eq "12345678") {
            $PluginConfigDir = Join-Path (Join-Path $ProjectDirAbs "plugins\google-ads-api-developer-assistant") "config"
            $LegacyCandidates = @(
                (Join-Path $TargetConfigDir "customer_id"),
                (Join-Path $TargetConfigDir "customer_id.txt"),
                (Join-Path $PluginConfigDir "customer_id"),
                (Join-Path $PluginConfigDir "customer_id.txt")
            )
            foreach ($LegacyFile in $LegacyCandidates) {
                if ($LegacyFile -and (Test-Path -LiteralPath $LegacyFile)) {
                    $LegacyRaw = Get-Content -LiteralPath $LegacyFile -Raw -Encoding UTF8
                    if ($null -ne $LegacyRaw) {
                        $LegacyCid = $LegacyRaw.Trim().Trim("`"'")
                        if ($LegacyCid -and $LegacyCid -ne "12345678") {
                            $Cid = $LegacyCid
                            break
                        }
                    }
                }
            }
        }
        $TomlContent = "api_version = `"$ApiVer`"`ncustomer_id = `"$Cid`"`nexecute_mutates = $ExecMutates`nallow_tier1_financial_mutates = $Tier1Mutates`nenabled = $PluginEnabled`n"
        if ($ExtraLines.Count -gt 0) {
            $TomlContent += ($ExtraLines -join "`n") + "`n"
        }
        Write-Utf8NoBom -Path $CfgFile -Content $TomlContent
        if ($ApiVer) {
            Write-Host "Configured API version $ApiVer in $CfgFile"
        }
        else {
            Write-NoApiVersionWarning -CfgPath $CfgFile
        }
    }
    else {
        Write-NoApiVersionWarning -CfgPath (Join-Path $TargetConfigDir "assistant_config")
    }
}

# Warn when no Google Ads API version could be detected for config/assistant_config
function Write-NoApiVersionWarning {
    param([string]$CfgPath)
    Write-Warning "No Google Ads API version was detected (no client_libs/google-ads-python and no installed google-ads package)."
    Write-Warning "api_version is not set in $CfgPath. Install the google-ads Python package, or set api_version = `"vNN`" in that file, or pass --api_version vNN to the skill scripts."
}

# --- Environment Verification ---
function Test-PythonEnvironment {
    $Py = Find-WorkingPython
    if ($Py.Found) {
        Write-Host "Found Python $($Py.Version) ($($Py.Source))"
        return $true
    }

    Write-Error "ERROR: Python 3.11 or higher is required."
    if ($Py.Version) {
        Write-Error "Incompatible Python version detected: $($Py.Version) ($($Py.Source))."
    }
    else {
        Write-Error "No Python interpreter was found on PATH."
    }
    Write-Error "Please install Python 3.11 or later and ensure it is available in your PATH."
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
    if (-not [string]::IsNullOrWhiteSpace($UserHome)) {
        $GeminiDir = Join-Path $UserHome ".gemini"
        $AntigravityDir = Join-Path $UserHome ".antigravity"
        if ((Test-Path -LiteralPath $GeminiDir) -or (Test-Path -LiteralPath $AntigravityDir)) {
            Write-Host "Antigravity configuration/installation found in home directory ($GeminiDir or $AntigravityDir)"
            return $true
        }
    }

    $ProgramDirs = @()
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $ProgramDirs += (Join-Path $env:LOCALAPPDATA "Programs\Antigravity")
    }
    if (-not [string]::IsNullOrWhiteSpace($env:PROGRAMFILES)) {
        $ProgramDirs += (Join-Path $env:PROGRAMFILES "Antigravity")
    }
    if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
        $ProgramDirs += (Join-Path ${env:ProgramFiles(x86)} "Antigravity")
    }
    foreach ($Dir in $ProgramDirs) {
        if ($Dir -and (Test-Path -LiteralPath $Dir)) {
            Write-Host "Antigravity CLI installation found at $Dir"
            return $true
        }
    }

    Write-Error "ERROR: Antigravity CLI ('agy' or 'antigravity') is not installed."
    Write-Error "The Google Ads API Developer Assistant requires an active Antigravity CLI environment."
    Write-Error "Please install Antigravity CLI ('agy' or 'antigravity') to continue."
    return $false
}

function Test-ClaudeCodeEnvironment {
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        Write-Host "Found Claude Code CLI (claude)"
        return $true
    }
    Write-Error "ERROR: Claude Code CLI ('claude') is not installed or not in PATH."
    Write-Error "Please install Claude Code CLI to continue."
    return $false
}

function check_environment {
    Write-Host "Checking environment for $Type..."
    $EnvOk = $true

    if (-not (Test-PythonEnvironment)) {
        $EnvOk = $false
    }

    if ($Type -eq "agy") {
        if (-not (Test-AntigravityEnvironment)) {
            $EnvOk = $false
        }
    }
    elseif ($Type -eq "claude") {
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

$PluginSource = Join-Path $ProjectDirAbs "plugins\google-ads-api-developer-assistant"
if (-not (Test-Path -LiteralPath $PluginSource)) {
    Write-Error "ERROR: Plugin directory not found at $PluginSource"
    exit 1
}

function Install-PluginCopy {
    param([string]$TargetPluginDir)
    $ParentPluginDir = Split-Path $TargetPluginDir
    if (-not (Test-Path -LiteralPath $ParentPluginDir)) {
        New-Item -ItemType Directory -Force -Path $ParentPluginDir | Out-Null
    }

    $TempBackupDir = Join-Path ([System.IO.Path]::GetTempPath()) ("gads_install_bak_" + [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $TempBackupDir | Out-Null
    $BackupCfgDir = Join-Path $TempBackupDir "config"
    $BackupLibsDir = Join-Path $TempBackupDir "client_libs"
    $BackupSavedDir = Join-Path $TempBackupDir "saved"
    $WasDisabled = $false
    $InstallSucceeded = $false
    $HasBackupData = $false

    try {
        $TargetItem = Get-Item -LiteralPath $TargetPluginDir -Force -ErrorAction SilentlyContinue
        if ($TargetItem) {
            $IsSymlink = [bool](($TargetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or $TargetItem.LinkType)

            if ((Test-Path -LiteralPath (Join-Path $TargetPluginDir "plugin.json.disabled")) -and -not (Test-Path -LiteralPath (Join-Path $TargetPluginDir "plugin.json"))) {
                $WasDisabled = $true
            }
            elseif (Test-Path -LiteralPath (Join-Path (Join-Path $TargetPluginDir "config") "assistant_config")) {
                $PriorCfg = Get-Content -LiteralPath (Join-Path (Join-Path $TargetPluginDir "config") "assistant_config") -Raw -Encoding UTF8
                if ($null -ne $PriorCfg -and $PriorCfg -match '(?mi)^\s*(?:enabled|plugin_enabled)\s*=\s*["'']?false["'']?') {
                    $WasDisabled = $true
                }
            }

            if ($IsSymlink) {
                Remove-ReparsePointSafely -Path $TargetPluginDir
            }
            else {
                New-Item -ItemType Directory -Force -Path $BackupCfgDir | Out-Null
                foreach ($CfgName in @("assistant_config", "financial_limits", "google-ads.yaml", "customer_id", "customer_id.txt")) {
                    $ExistingCfgFile = Join-Path (Join-Path $TargetPluginDir "config") $CfgName
                    if (Test-Path -LiteralPath $ExistingCfgFile) {
                        Copy-Item -Force -LiteralPath $ExistingCfgFile -Destination (Join-Path $BackupCfgDir $CfgName)
                        $HasBackupData = $true
                    }
                }
                $ExistingSaved = Join-Path $TargetPluginDir "saved"
                if (Test-Path -LiteralPath $ExistingSaved) {
                    $HasBackupData = $true
                    try {
                        Move-Item -Force -LiteralPath $ExistingSaved -Destination $BackupSavedDir
                    } catch {
                        Copy-Item -Recurse -Force -LiteralPath $ExistingSaved -Destination $BackupSavedDir
                    }
                }
                $ExistingClientLibs = Join-Path $TargetPluginDir "client_libs"
                if (Test-Path -LiteralPath $ExistingClientLibs) {
                    New-Item -ItemType Directory -Force -Path $BackupLibsDir | Out-Null
                    foreach ($ExistingLib in Get-ChildItem -LiteralPath $ExistingClientLibs -Directory -Filter "google-ads-*" -ErrorAction SilentlyContinue) {
                        $HasBackupData = $true
                        $DestBakLib = Join-Path $BackupLibsDir $ExistingLib.Name
                        try {
                            Move-Item -Force -LiteralPath $ExistingLib.FullName -Destination $DestBakLib
                        } catch {
                            Copy-Item -Recurse -Force -LiteralPath $ExistingLib.FullName -Destination $DestBakLib
                        }
                    }
                }
                Remove-Item -Recurse -Force -LiteralPath $TargetPluginDir
            }
        }

        Copy-Item -Recurse -Force -LiteralPath $PluginSource -Destination $TargetPluginDir

        # Exclude gitignored repo credentials and saved artifacts from copied plugin source
        $TargetCfgDir = Join-Path $TargetPluginDir "config"
        if (-not (Test-Path -LiteralPath $TargetCfgDir)) {
            New-Item -ItemType Directory -Force -Path $TargetCfgDir | Out-Null
        }
        foreach ($SecretOrLocal in @("google-ads.yaml", ".repo_root", "google_ads_php.ini", "google_ads_config.rb", "ads.properties", "App.config", "appsettings.json")) {
            Remove-Item -Force -LiteralPath (Join-Path $TargetCfgDir $SecretOrLocal) -ErrorAction SilentlyContinue
        }
        $CopiedSaved = Join-Path $TargetPluginDir "saved"
        if (Test-Path -LiteralPath $CopiedSaved) {
            Remove-Item -Recurse -Force -LiteralPath $CopiedSaved -ErrorAction SilentlyContinue
        }

        # Restore backed-up config files, saved directory, and previously cloned client_libs
        foreach ($RestoreCfgName in @("assistant_config", "google-ads.yaml", "customer_id", "customer_id.txt")) {
            $BakCfg = Join-Path $BackupCfgDir $RestoreCfgName
            if (Test-Path -LiteralPath $BakCfg) {
                Copy-Item -Force -LiteralPath $BakCfg -Destination (Join-Path $TargetCfgDir $RestoreCfgName)
            }
        }
        Merge-FinancialLimits -TemplatePath (Join-Path $TargetCfgDir "financial_limits") -BackupPath (Join-Path $BackupCfgDir "financial_limits")

        if (Test-Path -LiteralPath $BackupSavedDir) {
            try {
                Move-Item -Force -LiteralPath $BackupSavedDir -Destination $CopiedSaved
            } catch {
                Copy-Item -Recurse -Force -LiteralPath $BackupSavedDir -Destination $CopiedSaved
            }
        }

        foreach ($HelperName in @("plugin.ps1", "update.ps1", "set_financial_limits.py")) {
            $HelperPs1 = Join-Path $ProjectDirAbs $HelperName
            if (Test-Path -LiteralPath $HelperPs1) {
                Copy-Item -Force -LiteralPath $HelperPs1 -Destination (Join-Path $TargetPluginDir $HelperName)
            }
        }
        Write-Utf8NoBom -Path (Join-Path $TargetCfgDir ".repo_root") -Content "$ProjectDirAbs`n"

        # Strip Claude-Code-only files from the installed agy copy before manifest normalization
        # and plugin disable/enable so `jetski plugin validate` emits 0 warnings and no orphaned `.mcp.json.disabled` remains
        if ($Type -eq "agy") {
            foreach ($ClaudeOnly in @(".claude-plugin", ".mcp.json", ".mcp.json.disabled", "hooks", "commands")) {
                $ClaudeOnlyPath = Join-Path $TargetPluginDir $ClaudeOnly
                $ClaudeOnlyItem = Get-Item -LiteralPath $ClaudeOnlyPath -Force -ErrorAction SilentlyContinue
                if ($ClaudeOnlyItem) {
                    if (($ClaudeOnlyItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or $ClaudeOnlyItem.LinkType) {
                        Remove-ReparsePointSafely -Path $ClaudeOnlyPath
                    } else {
                        Remove-Item -Recurse -Force -LiteralPath $ClaudeOnlyPath -ErrorAction SilentlyContinue
                    }
                }
            }
        }

        # On Windows hosts where python3 is missing or a Windows Store alias stub, normalize installed JSON manifests
        $WorkingPy = Find-WorkingPython
        if ($WorkingPy.Found -and $WorkingPy.Name -ne "python3") {
            foreach ($RelJson in @("hooks.json", "mcp_config.json", ".mcp.json", "sidecars\google-ads-a2a-service\sidecar.json")) {
                $ManifestPath = Join-Path $TargetPluginDir $RelJson
                if (Test-Path -LiteralPath $ManifestPath) {
                    $RawJson = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8
                    if ($null -eq $RawJson) { continue }
                    if ($WorkingPy.Name -eq "python") {
                        $UpdatedJson = $RawJson -replace '"command"\s*:\s*"python3(?=\s|")', '"command": "python'
                    }
                    else {
                        $PyPrefix = if ($WorkingPy.PrefixArgs -contains "-3") { "py -3" } else { "py" }
                        $UpdatedJson = $RawJson -replace '"command"\s*:\s*"python3(?=\s)', ('"command": "' + $PyPrefix)
                        if ($UpdatedJson -match '"command"\s*:\s*"python3"') {
                            $UpdatedJson = $UpdatedJson -replace '"command"\s*:\s*"python3"', '"command": "py"'
                            if ($WorkingPy.PrefixArgs -contains "-3") {
                                if ($UpdatedJson -match '"args"\s*:\s*\[\s*\]') {
                                    $UpdatedJson = $UpdatedJson -replace '"args"\s*:\s*\[\s*\]', '"args": ["-3"]'
                                }
                                else {
                                    $UpdatedJson = $UpdatedJson -replace '("args"\s*:\s*\[)(\s*)(?=[^\]\s])', '$1$2"-3", '
                                }
                            }
                        }
                    }
                    if ($UpdatedJson -ne $RawJson) {
                        Write-Utf8NoBom -Path $ManifestPath -Content $UpdatedJson
                    }
                }
            }
        }

        $PluginClientLibsDir = Join-Path $TargetPluginDir "client_libs"
        if (-not (Test-Path -LiteralPath $PluginClientLibsDir)) {
            New-Item -ItemType Directory -Force -Path $PluginClientLibsDir | Out-Null
        }

        if (Test-Path -LiteralPath $BackupLibsDir) {
            foreach ($BakLib in Get-ChildItem -LiteralPath $BackupLibsDir -Directory -Filter "google-ads-*" -ErrorAction SilentlyContinue) {
                $RestoredLibPath = Join-Path $PluginClientLibsDir $BakLib.Name
                if (-not (Test-Path -LiteralPath $RestoredLibPath)) {
                    try {
                        Move-Item -Force -LiteralPath $BakLib.FullName -Destination $RestoredLibPath
                    } catch {
                        Copy-Item -Recurse -Force -LiteralPath $BakLib.FullName -Destination $RestoredLibPath
                    }
                    Remove-Item -Force -LiteralPath (Join-Path $RestoredLibPath "google-ads.yaml") -ErrorAction SilentlyContinue
                }
            }
        }

        $AllLangs = @("python", "php", "ruby", "java", "dotnet")
        foreach ($Lang in $AllLangs) {
            if (Test-Enabled -Lang $Lang) {
                $Config = Get-RepoConfig -Lang $Lang
                $TargetRepoPath = Join-Path $PluginClientLibsDir $Config.Name
                $SourceRepoPath = Join-Path $PluginSource (Join-Path "client_libs" $Config.Name)
                $RepoUrl = $Config.Url

                if (Test-Path -LiteralPath $SourceRepoPath) {
                    Write-Host "Adding $($Config.Name) to plugin client_libs from $SourceRepoPath..."
                    if (Test-Path -LiteralPath $TargetRepoPath) {
                        Remove-Item -Recurse -Force -LiteralPath $TargetRepoPath
                    }
                    Copy-Item -Recurse -Force -LiteralPath $SourceRepoPath -Destination $TargetRepoPath
                    Remove-Item -Force -LiteralPath (Join-Path $TargetRepoPath "google-ads.yaml") -ErrorAction SilentlyContinue
                }
                elseif (Test-Path -LiteralPath (Join-Path $TargetRepoPath ".git")) {
                    Write-Host "Directory $TargetRepoPath already exists. Updating..."
                    if (Update-GitRepo -RepoDir $TargetRepoPath) {
                        Write-Host "Successfully updated $($Config.Name)."
                    } else {
                        Write-Warning "WARN: Failed to update $($Config.Name). Continuing..."
                    }
                    Remove-Item -Force -LiteralPath (Join-Path $TargetRepoPath "google-ads.yaml") -ErrorAction SilentlyContinue
                }
                else {
                    Write-Host "Cloning $RepoUrl into $TargetRepoPath..."
                    git -c core.longpaths=true -c maintenance.auto=false -c gc.auto=0 -c gc.autoDetach=false clone --depth 1 $RepoUrl $TargetRepoPath
                    if ($LASTEXITCODE -ne 0) {
                        Write-Error "ERROR: Failed to clone $RepoUrl"
                        exit 1
                    }
                    Write-Host "Successfully cloned $($Config.Name)."
                    Remove-Item -Force -LiteralPath (Join-Path $TargetRepoPath "google-ads.yaml") -ErrorAction SilentlyContinue
                }
            }
        }

        $PluginPythonDir = Join-Path $TargetPluginDir "client_libs\google-ads-python\google\ads\googleads"
        Set-LatestApiVersion -SearchDir $PluginPythonDir -TargetConfigDir $TargetCfgDir
        $global:LASTEXITCODE = 0
        if ($Disable -or (-not $Enable -and $WasDisabled)) {
            & (Join-Path $ProjectDirAbs "plugin.ps1") disable -ConfigDir $TargetCfgDir -Quiet
            if ($LASTEXITCODE -ne 0) {
                Write-Error "ERROR: Failed to disable plugin via plugin.ps1 (exit code $LASTEXITCODE)."
                exit $LASTEXITCODE
            }
        }
        else {
            & (Join-Path $ProjectDirAbs "plugin.ps1") enable -ConfigDir $TargetCfgDir -Quiet
            if ($LASTEXITCODE -ne 0) {
                Write-Error "ERROR: Failed to enable plugin via plugin.ps1 (exit code $LASTEXITCODE)."
                exit $LASTEXITCODE
            }
        }
        $InstallSucceeded = $true
    }
    finally {
        if ($InstallSucceeded -or -not $HasBackupData) {
            if (Test-Path -LiteralPath $TempBackupDir) {
                Remove-Item -Recurse -Force -LiteralPath $TempBackupDir -ErrorAction SilentlyContinue
            }
        }
        elseif (Test-Path -LiteralPath $TempBackupDir) {
            Write-Warning "Installation did not complete. Preserved backed-up configuration and data at: $TempBackupDir"
        }
    }
}

$UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }

if ($Type -eq "claude") {
    $ClaudeMarketplaceDir = Join-Path $UserHome ".claude\plugins\google-ads-assistant-local"
    $ClaudePluginTargetDir = Join-Path $ClaudeMarketplaceDir "plugins\google-ads-api-developer-assistant"
    $ClaudeManifestDir = Join-Path $ClaudeMarketplaceDir ".claude-plugin"

    Write-Host "Installing standalone Claude Code plugin into: $ClaudePluginTargetDir"
    if (-not (Test-Path -LiteralPath $ClaudeManifestDir)) {
        New-Item -ItemType Directory -Force -Path $ClaudeManifestDir | Out-Null
    }
    Copy-Item -Force -LiteralPath (Join-Path $ProjectDirAbs ".claude-plugin\marketplace.json") -Destination (Join-Path $ClaudeManifestDir "marketplace.json")

    Install-PluginCopy -TargetPluginDir $ClaudePluginTargetDir

    Write-Host "Registering marketplace in Claude Code..."
    Push-Location -LiteralPath $ClaudePluginTargetDir
    try {
        $global:LASTEXITCODE = 0
        & claude plugin marketplace add $ClaudeMarketplaceDir
        if ($LASTEXITCODE -ne 0) {
            Write-Error "ERROR: Failed to register marketplace in Claude Code (exit code $LASTEXITCODE)."
            exit $LASTEXITCODE
        }

        Write-Host "Installing plugin in Claude Code..."
        $global:LASTEXITCODE = 0
        & claude plugin install google-ads-api-developer-assistant@google-ads-assistant-local
        if ($LASTEXITCODE -ne 0) {
            Write-Error "ERROR: Failed to install plugin in Claude Code (exit code $LASTEXITCODE)."
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }

    Write-Host "Plugin installation for claude complete."
    Write-Host ""
    Write-Host "In your Claude Code session, run /reload-plugins to activate the plugin."
    exit 0
}

# Antigravity installation
$TargetPluginDir = Join-Path $UserHome ".gemini\config\plugins\google-ads-api-developer-assistant"

Write-Host "Installing plugin for agy into: $TargetPluginDir"
Install-PluginCopy -TargetPluginDir $TargetPluginDir

Write-Host "Plugin installation for agy complete."
Write-Host ""
Write-Host "Restart your Antigravity / agy host to activate the plugin."
exit 0
