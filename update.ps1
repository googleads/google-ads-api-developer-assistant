<#
.SYNOPSIS
    Updates the Google Ads API Developer Assistant and its dependencies on Windows.

.DESCRIPTION
    This script performs the following steps:
    1. Updates the 'google-ads-api-developer-assistant' repository (git pull).
    2. Reads '.gemini/settings.json' to locate configured client library repositories.
    3. Updates each found client library repository (git pull).

.EXAMPLE
    .\update.ps1
#>

$ErrorActionPreference = "Stop"

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
Write-Host "Updating google-ads-api-developer-assistant..."

$SettingsFile = Join-Path $ProjectDirAbs ".gemini\settings.json"
$TempSettingsFile = [System.IO.Path]::GetTempFileName()

$CustomerIdFile = Join-Path $ProjectDirAbs "customer_id.txt"
$TempCustomerIdFile = [System.IO.Path]::GetTempFileName()

try {
    # 1. Backup existing settings if they exist
    if (Test-Path -LiteralPath $SettingsFile) {
        Write-Host "Backing up $SettingsFile..."
        Copy-Item -LiteralPath $SettingsFile -Destination $TempSettingsFile -Force

        # 2. Reset local changes to settings.json to allow git pull
        # Check if file is tracked by git
        $GitStatus = git ls-files --error-unmatch $SettingsFile 2>$null
        if ($LASTEXITCODE -eq 0) {
             Write-Host "Resetting $SettingsFile to avoid merge conflicts..."
             git checkout $SettingsFile
        }
    }

    # 1b. Backup customer_id.txt if it exists
    if (Test-Path -LiteralPath $CustomerIdFile) {
        Write-Host "Backing up $CustomerIdFile..."
        Copy-Item -LiteralPath $CustomerIdFile -Destination $TempCustomerIdFile -Force

        # Reset local changes
        $GitStatus = git ls-files --error-unmatch $CustomerIdFile 2>$null
        if ($LASTEXITCODE -eq 0) {
             Write-Host "Resetting $CustomerIdFile to avoid merge conflicts..."
             git checkout $CustomerIdFile
        }
    }

    # 3. Update Repo
    git pull
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to update google-ads-api-developer-assistant."
    }
    Write-Host "Successfully updated google-ads-api-developer-assistant."

    # 4. Restore/Merge settings
    if ((Test-Path -LiteralPath $TempSettingsFile) -and (Get-Item $TempSettingsFile).Length -gt 0) {
        Write-Host "Merging preserved settings with new defaults..."
        
        # Read contents
        $UserContent = Get-Content -LiteralPath $TempSettingsFile -Raw | ConvertFrom-Json
        $RepoContent = Get-Content -LiteralPath $SettingsFile -Raw | ConvertFrom-Json
        
        # Merge Logic: User overrides Repo
        # Helper function for recursive merge could go here, but for now we do specific top-level merge
        # replicating jq * behavior for simple objects.
        # Actually, let's just use strict property copy from User to Repo for top-level keys
        # If deeply nested merge is needed, valid for context.includeDirectories?
        # Usually settings.json is flat or 1-level deep.
        
        # Simple Merge: Add/Overwrite properties from User to Repo object
        foreach ($Prop in $UserContent.PSObject.Properties) {
             if ($Prop.Name -eq "context") {
                 # Special handling for context if needed, or just overwrite?
                 # jq * merges recursively.
                 # Let's try to merge context if both have it.
                 if ($RepoContent.PSObject.Properties["context"]) {
                     foreach ($CtxProp in $Prop.Value.PSObject.Properties) {
                         # e.g. includeDirectories
                         if (-not $RepoContent.context.PSObject.Properties[$CtxProp.Name]) {
                             $RepoContent.context | Add-Member -MemberType NoteProperty -Name $CtxProp.Name -Value $CtxProp.Value
                         } else {
                             $RepoContent.context.$($CtxProp.Name) = $CtxProp.Value
                         }
                     }
                 } else {
                     $RepoContent | Add-Member -MemberType NoteProperty -Name "context" -Value $Prop.Value
                 }
             } else {
                 if (-not $RepoContent.PSObject.Properties[$Prop.Name]) {
                     $RepoContent | Add-Member -MemberType NoteProperty -Name $Prop.Name -Value $Prop.Value
                 } else {
                     $RepoContent.$($Prop.Name) = $Prop.Value
                 }
             }
        }
        
        # Save merged
        $RepoContent | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $SettingsFile -Encoding UTF8
        Write-Host "Settings restored and merged successfully."
        Write-Host "Settings restored and merged successfully."
    }

    # 4b. Restore customer_id.txt
    if ((Test-Path -LiteralPath $TempCustomerIdFile) -and (Get-Item $TempCustomerIdFile).Length -gt 0) {
        Write-Host "Restoring preserved $CustomerIdFile..."
        # Always overwrite with user's backup
        Move-Item -LiteralPath $TempCustomerIdFile -Destination $CustomerIdFile -Force
        Write-Host "Restored $CustomerIdFile successfully."
    }

}
catch {
    Write-Error "ERROR: $_"
    # Restore backup if pull failed or something went wrong involving the file
    if ((Test-Path -LiteralPath $TempSettingsFile) -and (Get-Item $TempSettingsFile).Length -gt 0) {
         if (-not (Test-Path -LiteralPath $SettingsFile) -or (Get-Item $SettingsFile).Length -eq 0) {
             Write-Host "Restoring original settings after failure..."
             Copy-Item -LiteralPath $TempSettingsFile -Destination $SettingsFile -Force
         }
    }
    if ((Test-Path -LiteralPath $TempCustomerIdFile) -and (Get-Item $TempCustomerIdFile).Length -gt 0) {
         if (-not (Test-Path -LiteralPath $CustomerIdFile) -or (Get-Item $CustomerIdFile).Length -eq 0) {
             Write-Host "Restoring original customer_id.txt after failure..."
             Copy-Item -LiteralPath $TempCustomerIdFile -Destination $CustomerIdFile -Force
         }
    }
    exit 1
}
finally {
    if (Test-Path -LiteralPath $TempSettingsFile) {
        Remove-Item -LiteralPath $TempSettingsFile -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $TempCustomerIdFile) {
        Remove-Item -LiteralPath $TempCustomerIdFile -Force -ErrorAction SilentlyContinue
    }
}


# --- Locate and Update Client Libraries ---
$SettingsFile = Join-Path $ProjectDirAbs ".gemini\settings.json"

if (-not (Test-Path -LiteralPath $SettingsFile)) {
    Write-Error "ERROR: Settings file not found: $SettingsFile"
    Write-Error "Please run setup.ps1 first."
    exit 1
}

Write-Host "Reading $SettingsFile to find client libraries..."

try {
    $SettingsJson = Get-Content -LiteralPath $SettingsFile -Raw | ConvertFrom-Json
    
    if (-not $SettingsJson.context -or -not $SettingsJson.context.includeDirectories) {
        Write-Warning "No directories found in settings."
        exit 0
    }

    $IncludeDirs = $SettingsJson.context.includeDirectories
    Write-Host "Found $($IncludeDirs.Count) directories in settings."

    foreach ($LibPath in $IncludeDirs) {
        if ([string]::IsNullOrWhiteSpace($LibPath)) { continue }
        
        # Check if path exists
        if (-not (Test-Path -LiteralPath $LibPath)) {
            Write-Warning "Directory not found: $LibPath. Skipping."
            continue
        }

        $AbsLibPath = (Get-Item -LiteralPath $LibPath).FullName

        # Skip if it is the project directory itself or a subdirectory of it
        if ($AbsLibPath.StartsWith($ProjectDirAbs)) {
            Write-Host "Skipping internal directory: $AbsLibPath"
            continue
        }

        # Check if it is a git repository
        if (-not (Test-Path -LiteralPath (Join-Path $AbsLibPath ".git"))) {
            Write-Warning "Skipping non-git directory: $AbsLibPath"
            continue
        }

        Write-Host "Updating repository at: $AbsLibPath..."
        Push-Location $AbsLibPath
        try {
            git pull
            if ($LASTEXITCODE -eq 0) {
                 Write-Host "Successfully updated $AbsLibPath."
            } else {
                 Write-Error "ERROR: Failed to update $AbsLibPath"
                 # We exit on error to match update.sh behavior of failing fast-ish? 
                 # Actually update.sh likely fails fast due to set -e.
                 exit 1 
            }
        }
        finally {
            Pop-Location
        }
    }
}
catch {
    Write-Error "ERROR: An error occurred while processing settings or updating libraries: $_"
    exit 1
}

Write-Host "Update complete."
