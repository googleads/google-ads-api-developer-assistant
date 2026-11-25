<#
.SYNOPSIS
    Updates the Google Ads API Developer Assistant plugin and its dependencies on Windows.

.DESCRIPTION
    This script updates the Google Ads API Developer Assistant repository and installed plugin:
    1. Updates the git repository (git pull) while keeping tracked config files clean.
    2. Syncs updated plugin assets to the platform-specific plugin directory (Antigravity or Claude Code).
    3. Clones or updates configured client libraries in the plugin's 'client_libs/' directory.

.PARAMETER Type
    Target platform: 'agy' (Antigravity) or 'claude' (Claude Code).

.PARAMETER Agy
    Shorthand switch for -Type agy.

.PARAMETER Claude
    Shorthand switch for -Type claude.

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
    [switch]$NoGitPull
)

$ErrorActionPreference = "Stop"

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

if ($Status) {
    if (-not [string]::IsNullOrWhiteSpace($Type) -and $Type -notin @("agy", "claude", "all")) {
        Write-Error "ERROR: Invalid Type '$Type'. Must be 'agy', 'claude', or 'all'."
        exit 1
    }
    $ScriptDirTmp = Split-Path -Parent $MyInvocation.MyCommand.Path
    $Target = if ([string]::IsNullOrWhiteSpace($Type)) { "all" } else { $Type }
    & (Join-Path $ScriptDirTmp "plugin.ps1") status $Target
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

function Set-LatestApiVersion {
    param(
        [string]$SearchDir,
        [string]$TargetConfigDir,
        [string]$TempLegacyDir = ""
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
        }
        elseif ($Cid -eq "12345678") {
            $PluginConfigDir = Join-Path (Join-Path $ProjectDirAbs "plugins\google-ads-api-developer-assistant") "config"
            $LegacyCandidates = @(
                (Join-Path $TargetConfigDir "customer_id"),
                (Join-Path $TargetConfigDir "customer_id.txt")
            )
            if ($TempLegacyDir) {
                $LegacyCandidates += @(
                    (Join-Path $TempLegacyDir "legacy_customer_id"),
                    (Join-Path $TempLegacyDir "legacy_customer_id.txt")
                )
            }
            $LegacyCandidates += @(
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

$ErrorActionPreference = "Stop"
$env:GIT_CONFIG_PARAMETERS = "'maintenance.auto=false' 'gc.auto=0' 'gc.autoDetach=false'"

# --- Dependency Check ---
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: git is not installed. Please install it to continue."
    exit 1
}

# --- Project Directory Resolution ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$UserHomeTmp = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$AgyPluginTargetDirTmp = Join-Path $UserHomeTmp ".gemini\config\plugins\google-ads-api-developer-assistant"
$ClaudePluginTargetDirTmp = Join-Path $UserHomeTmp ".claude\plugins\google-ads-assistant-local\plugins\google-ads-api-developer-assistant"
$ProjectDirAbs = $null
try {
    $Candidate = git -C $ScriptDir rev-parse --show-toplevel 2>$null
    if ($Candidate -and (Test-Path -LiteralPath (Join-Path $Candidate "plugins\google-ads-api-developer-assistant"))) {
        $ProjectDirAbs = (Get-Item -LiteralPath $Candidate).FullName
    }
} catch {}
if (-not $ProjectDirAbs) {
    foreach ($RepoRootFile in @(
        (Join-Path (Join-Path $ScriptDir "config") ".repo_root"),
        (Join-Path (Join-Path $AgyPluginTargetDirTmp "config") ".repo_root"),
        (Join-Path (Join-Path $ClaudePluginTargetDirTmp "config") ".repo_root")
    )) {
        if (Test-Path -LiteralPath $RepoRootFile) {
            $SavedRootRaw = Get-Content -LiteralPath $RepoRootFile -Raw -Encoding UTF8
            if ($null -ne $SavedRootRaw) {
                $SavedRoot = $SavedRootRaw.Trim()
                if ($SavedRoot -and (Test-Path -LiteralPath (Join-Path $SavedRoot "plugins\google-ads-api-developer-assistant"))) {
                    $ProjectDirAbs = (Get-Item -LiteralPath $SavedRoot).FullName
                    break
                }
            }
        }
    }
}
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

Write-Host "Detected project root: $ProjectDirAbs"

# --- Update Assistant Repo ---
Write-Host "Updating google-ads-api-developer-assistant repository..."

$ConfigDir = Join-Path (Join-Path $ProjectDirAbs "plugins\google-ads-api-developer-assistant") "config"
$TempConfigDir = Join-Path ([System.IO.Path]::GetTempPath()) ("gads_update_" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TempConfigDir | Out-Null
$UpdateSucceeded = $false
$PullSucceeded = $false
$BackupState = @{ HasData = $false }
$BackedUpTrackedFiles = @()

try {
    # If git-tracked config files in the repository checkout have local modifications,
    # back them up for migrating overrides to installed targets and reset them so git pull
    # never fails with merge conflicts and the repo's tracked config/ stays clean at upstream HEAD.
    foreach ($TrackedRel in @(
        "plugins/google-ads-api-developer-assistant/config/assistant_config",
        "plugins/google-ads-api-developer-assistant/config/financial_limits"
    )) {
        $TrackedBase = Split-Path -Leaf $TrackedRel
        git -C $ProjectDirAbs ls-files --error-unmatch $TrackedRel 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            git -C $ProjectDirAbs diff --quiet -- $TrackedRel 2>$null
            if ($LASTEXITCODE -ne 0) {
                $FullTracked = Join-Path $ProjectDirAbs ($TrackedRel -replace '/', '\')
                $RepoBakDest = Join-Path $TempConfigDir "repo_$TrackedBase"
                if (Test-Path -LiteralPath $FullTracked) {
                    Copy-Item -LiteralPath $FullTracked -Destination $RepoBakDest -Force
                    $BackupState.HasData = $true
                    $BackedUpTrackedFiles += @{ Source = $FullTracked; Backup = $RepoBakDest }
                }
                git -C $ProjectDirAbs checkout -- $TrackedRel 2>$null | Out-Null
            }
        }
    }

    foreach ($LegacyName in @("customer_id", "customer_id.txt")) {
        $LegacyPath = Join-Path $ConfigDir $LegacyName
        if (Test-Path -LiteralPath $LegacyPath) {
            Copy-Item -LiteralPath $LegacyPath -Destination (Join-Path $TempConfigDir "legacy_$LegacyName") -Force
        }
    }

    if ($NoGitPull) {
        Write-Host "Skipping git pull (-NoGitPull)."
        $PullSucceeded = $true
    } else {
        git -C $ProjectDirAbs -c core.longpaths=true -c maintenance.auto=false -c gc.auto=0 -c gc.autoDetach=false pull
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to update google-ads-api-developer-assistant repository."
        }
        $PullSucceeded = $true
        Write-Host "Successfully updated repository."
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
                    throw "Failed to clone $RepoUrl"
                }
                Remove-Item -Force -LiteralPath (Join-Path $SourceLibPath "google-ads.yaml") -ErrorAction SilentlyContinue
            }
        }
    }

    # Locate and update all client libraries in repository
    Write-Host "Locating client libraries to update..."
    $IncludeDirs = @()
    if (-not $NoGitPull -and (Test-Path -LiteralPath $PluginSourceClientLibs)) {
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

    function Sync-InstalledPluginDir {
        param([string]$TargetPluginDir)
        $ParentPluginDir = Split-Path $TargetPluginDir
        $IsSymlink = $false
        $WasDisabled = $false
        $TargetItem = Get-Item -LiteralPath $TargetPluginDir -Force -ErrorAction SilentlyContinue
        if ($TargetItem) {
            if (($TargetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or $TargetItem.LinkType) {
                $IsSymlink = $true
            }
            if ((Test-Path -LiteralPath (Join-Path $TargetPluginDir "plugin.json.disabled")) -and -not (Test-Path -LiteralPath (Join-Path $TargetPluginDir "plugin.json"))) {
                $WasDisabled = $true
            }
            elseif (Test-Path -LiteralPath (Join-Path (Join-Path $TargetPluginDir "config") "assistant_config")) {
                $PriorCfg = Get-Content -LiteralPath (Join-Path (Join-Path $TargetPluginDir "config") "assistant_config") -Raw -Encoding UTF8
                if ($null -ne $PriorCfg -and $PriorCfg -match '(?mi)^\s*(?:enabled|plugin_enabled)\s*=\s*["'']?false["'']?') {
                    $WasDisabled = $true
                }
            }
        }

        if ($IsSymlink) {
            Write-Host "Replacing legacy symlink at $TargetPluginDir with standalone plugin copy..."
            Remove-ReparsePointSafely -Path $TargetPluginDir
        }

        $RepoCfgBak = Join-Path $TempConfigDir "repo_assistant_config"
        $RepoFinBak = Join-Path $TempConfigDir "repo_financial_limits"

        if (-not (Test-Path -LiteralPath $TargetPluginDir)) {
            Write-Host "Plugin not yet installed at $TargetPluginDir. Installing standalone copy..."
            if (-not (Test-Path -LiteralPath $ParentPluginDir)) {
                New-Item -ItemType Directory -Force -Path $ParentPluginDir | Out-Null
            }
            Copy-Item -Recurse -Force -LiteralPath $PluginSourceDir -Destination $TargetPluginDir
            $CopiedSaved = Join-Path $TargetPluginDir "saved"
            if (Test-Path -LiteralPath $CopiedSaved) {
                Remove-Item -Recurse -Force -LiteralPath $CopiedSaved -ErrorAction SilentlyContinue
            }
            $TargetCfgDir = Join-Path $TargetPluginDir "config"
            if (-not (Test-Path -LiteralPath $TargetCfgDir)) {
                New-Item -ItemType Directory -Force -Path $TargetCfgDir | Out-Null
            }
            foreach ($SecretOrLocal in @("google-ads.yaml", ".repo_root", "google_ads_php.ini", "google_ads_config.rb", "ads.properties", "App.config", "appsettings.json")) {
                Remove-Item -Force -LiteralPath (Join-Path $TargetCfgDir $SecretOrLocal) -ErrorAction SilentlyContinue
            }
            if (Test-Path -LiteralPath $RepoCfgBak) {
                Copy-Item -Force -LiteralPath $RepoCfgBak -Destination (Join-Path $TargetCfgDir "assistant_config")
            }
            if (Test-Path -LiteralPath $RepoFinBak) {
                Merge-FinancialLimits -TemplatePath (Join-Path $TargetCfgDir "financial_limits") -BackupPath $RepoFinBak
            }
        }
        else {
            Write-Host "Syncing plugin files to $TargetPluginDir..."
            $TargetCfgDir = Join-Path $TargetPluginDir "config"
            $TargetCfgFile = Join-Path $TargetCfgDir "assistant_config"
            $TargetFinFile = Join-Path $TargetCfgDir "financial_limits"
            $TargetYamlFile = Join-Path $TargetCfgDir "google-ads.yaml"
            $TargetCidFile = Join-Path $TargetCfgDir "customer_id"
            $TargetCidTxtFile = Join-Path $TargetCfgDir "customer_id.txt"
            $TargetCfgBak = Join-Path $TempConfigDir "target_assistant_config"
            $TargetFinBak = Join-Path $TempConfigDir "target_financial_limits"
            $TargetYamlBak = Join-Path $TempConfigDir "target_google_ads_yaml"
            $TargetCidBak = Join-Path $TempConfigDir "target_customer_id"
            $TargetCidTxtBak = Join-Path $TempConfigDir "target_customer_id_txt"
            $TargetSavedBak = Join-Path $TempConfigDir "target_saved"
            Remove-Item -Force -LiteralPath $TargetCfgBak, $TargetFinBak, $TargetYamlBak, $TargetCidBak, $TargetCidTxtBak -ErrorAction SilentlyContinue
            if (Test-Path -LiteralPath $TargetSavedBak) {
                Remove-Item -Recurse -Force -LiteralPath $TargetSavedBak -ErrorAction SilentlyContinue
            }

            if (Test-Path -LiteralPath $TargetCfgFile) {
                Copy-Item -Force -LiteralPath $TargetCfgFile -Destination $TargetCfgBak
                $BackupState.HasData = $true
            }
            if (Test-Path -LiteralPath $TargetFinFile) {
                Copy-Item -Force -LiteralPath $TargetFinFile -Destination $TargetFinBak
                $BackupState.HasData = $true
            }
            if (Test-Path -LiteralPath $TargetYamlFile) {
                Copy-Item -Force -LiteralPath $TargetYamlFile -Destination $TargetYamlBak
                $BackupState.HasData = $true
            }
            if (Test-Path -LiteralPath $TargetCidFile) {
                Copy-Item -Force -LiteralPath $TargetCidFile -Destination $TargetCidBak
                $BackupState.HasData = $true
            }
            if (Test-Path -LiteralPath $TargetCidTxtFile) {
                Copy-Item -Force -LiteralPath $TargetCidTxtFile -Destination $TargetCidTxtBak
                $BackupState.HasData = $true
            }
            $ExistingSaved = Join-Path $TargetPluginDir "saved"
            if (Test-Path -LiteralPath $ExistingSaved) {
                Copy-Item -Recurse -Force -LiteralPath $ExistingSaved -Destination $TargetSavedBak
                $BackupState.HasData = $true
            }

            Get-ChildItem -LiteralPath $PluginSourceDir -Force | ForEach-Object {
                if ($_.Name -ne "client_libs" -and $_.Name -ne "saved" -and $_.Name -ne ".git") {
                    $DestItemPath = Join-Path $TargetPluginDir $_.Name
                    $ExistingDestItem = Get-Item -LiteralPath $DestItemPath -Force -ErrorAction SilentlyContinue
                    if ($ExistingDestItem) {
                        if (($ExistingDestItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or $ExistingDestItem.LinkType) {
                            Remove-ReparsePointSafely -Path $DestItemPath
                        }
                        else {
                            Remove-Item -Recurse -Force -LiteralPath $DestItemPath
                        }
                    }
                    Copy-Item -Recurse -Force -LiteralPath $_.FullName -Destination $DestItemPath
                }
            }

            if (-not (Test-Path -LiteralPath $TargetCfgDir)) {
                New-Item -ItemType Directory -Force -Path $TargetCfgDir | Out-Null
            }
            foreach ($SecretOrLocal in @("google-ads.yaml", ".repo_root", "google_ads_php.ini", "google_ads_config.rb", "ads.properties", "App.config", "appsettings.json")) {
                Remove-Item -Force -LiteralPath (Join-Path $TargetCfgDir $SecretOrLocal) -ErrorAction SilentlyContinue
            }

            if (Test-Path -LiteralPath $TargetCfgBak) {
                Copy-Item -Force -LiteralPath $TargetCfgBak -Destination $TargetCfgFile
            }
            elseif (Test-Path -LiteralPath $RepoCfgBak) {
                Copy-Item -Force -LiteralPath $RepoCfgBak -Destination $TargetCfgFile
            }

            if (Test-Path -LiteralPath $RepoFinBak) {
                Merge-FinancialLimits -TemplatePath $TargetFinFile -BackupPath $RepoFinBak
            }
            if (Test-Path -LiteralPath $TargetFinBak) {
                Merge-FinancialLimits -TemplatePath $TargetFinFile -BackupPath $TargetFinBak
            }

            if (Test-Path -LiteralPath $TargetYamlBak) {
                Copy-Item -Force -LiteralPath $TargetYamlBak -Destination $TargetYamlFile
            }
            if (Test-Path -LiteralPath $TargetCidBak) {
                Copy-Item -Force -LiteralPath $TargetCidBak -Destination $TargetCidFile
            }
            if (Test-Path -LiteralPath $TargetCidTxtBak) {
                Copy-Item -Force -LiteralPath $TargetCidTxtBak -Destination $TargetCidTxtFile
            }
            if ((Test-Path -LiteralPath $TargetSavedBak) -and -not (Test-Path -LiteralPath $ExistingSaved)) {
                Copy-Item -Recurse -Force -LiteralPath $TargetSavedBak -Destination $ExistingSaved
            }
        }

        foreach ($HelperName in @("plugin.ps1", "update.ps1", "set_financial_limits.py")) {
            $HelperPs1 = Join-Path $ProjectDirAbs $HelperName
            if (Test-Path -LiteralPath $HelperPs1) {
                Copy-Item -Force -LiteralPath $HelperPs1 -Destination (Join-Path $TargetPluginDir $HelperName)
            }
        }
        $TargetCfgDir = Join-Path $TargetPluginDir "config"
        if (-not (Test-Path -LiteralPath $TargetCfgDir)) {
            New-Item -ItemType Directory -Force -Path $TargetCfgDir | Out-Null
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

        if (-not $NoGitPull -and (Test-Path -LiteralPath $TargetClientLibs)) {
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

        $TargetPythonDir = Join-Path $TargetPluginDir "client_libs\google-ads-python\google\ads\googleads"
        Set-LatestApiVersion -SearchDir $TargetPythonDir -TargetConfigDir $TargetCfgDir -TempLegacyDir $TempConfigDir

        if ($Disable -or (-not $Enable -and $WasDisabled)) {
            $global:LASTEXITCODE = 0
            & (Join-Path $ProjectDirAbs "plugin.ps1") disable -ConfigDir $TargetCfgDir -Quiet
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to disable plugin via plugin.ps1 (exit code $LASTEXITCODE)."
            }
        }
        elseif ($Enable) {
            $global:LASTEXITCODE = 0
            & (Join-Path $ProjectDirAbs "plugin.ps1") enable -ConfigDir $TargetCfgDir -Quiet
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to enable plugin via plugin.ps1 (exit code $LASTEXITCODE)."
            }
        }
    }

    if ($Type -eq "agy") {
        Sync-InstalledPluginDir -TargetPluginDir $AgyPluginTargetDir
    }
    elseif ($Type -eq "claude") {
        $ClaudeMarketplaceDir = Join-Path $UserHome ".claude\plugins\google-ads-assistant-local"
        $ClaudePluginTargetDir = Join-Path $ClaudeMarketplaceDir "plugins\google-ads-api-developer-assistant"
        $ClaudeManifestDir = Join-Path $ClaudeMarketplaceDir ".claude-plugin"
        if (-not (Test-Path -LiteralPath $ClaudeManifestDir)) {
            New-Item -ItemType Directory -Force -Path $ClaudeManifestDir | Out-Null
        }
        Copy-Item -Force -LiteralPath (Join-Path $ProjectDirAbs ".claude-plugin\marketplace.json") -Destination (Join-Path $ClaudeManifestDir "marketplace.json")
        Sync-InstalledPluginDir -TargetPluginDir $ClaudePluginTargetDir

        if (Get-Command claude -ErrorAction SilentlyContinue) {
            $PrevEAP = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                $global:LASTEXITCODE = 0
                & claude plugin update google-ads-api-developer-assistant@google-ads-assistant-local *> $null
                if ($LASTEXITCODE -ne 0) {
                    $global:LASTEXITCODE = 0
                    & claude plugin install google-ads-api-developer-assistant@google-ads-assistant-local *> $null
                    if ($LASTEXITCODE -ne 0) {
                        Write-Warning "WARN: Failed to refresh plugin registration in Claude Code CLI (exit code $LASTEXITCODE)."
                    }
                }
            } catch {}
            finally {
                $ErrorActionPreference = $PrevEAP
            }
        }
    }
    $UpdateSucceeded = $true
}
catch {
    if (-not $PullSucceeded -and $BackedUpTrackedFiles.Count -gt 0) {
        foreach ($Entry in $BackedUpTrackedFiles) {
            if (Test-Path -LiteralPath $Entry.Backup) {
                Copy-Item -Force -LiteralPath $Entry.Backup -Destination $Entry.Source -ErrorAction SilentlyContinue
            }
        }
    }
    Write-Error "ERROR: $_"
    exit 1
}
finally {
    if ($UpdateSucceeded -or -not $BackupState.HasData) {
        if (Test-Path -LiteralPath $TempConfigDir) {
            Remove-Item -Recurse -Force -LiteralPath $TempConfigDir -ErrorAction SilentlyContinue
        }
    }
    elseif (Test-Path -LiteralPath $TempConfigDir) {
        Write-Warning "Update did not complete. Preserved backed-up configuration and data at: $TempConfigDir"
    }
}

Write-Host "Plugin update for $Type complete."
Write-Host ""
if ($Type -eq "agy") {
    Write-Host "Restart your Antigravity / agy host to apply changes."
} else {
    Write-Host "In your Claude Code session, run /reload-plugins to apply changes."
}
exit 0
