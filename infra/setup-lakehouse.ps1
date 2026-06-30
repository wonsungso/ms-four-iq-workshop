<#
.SYNOPSIS
    Sets up and runs the Fabric Lakehouse creation script for Zava DIY dataset.
.DESCRIPTION
    Creates a Python virtual environment, installs dependencies, and runs
    create-lakehouse.py to provision a Fabric Lakehouse with Zava DIY data.
    
    This script follows the same pattern as setup-knowledge.ps1 in the
    Build26-LAB532 infra folder and can be called from a postprovision hook.
.PARAMETER WorkspaceId
    The Microsoft Fabric workspace GUID where the lakehouse will be created.
    If not provided, a workspace will be auto-created using CapacityId.
.PARAMETER CapacityId
    The Fabric capacity resource ID (from Bicep output). Used to auto-create a workspace.
.PARAMETER LakehouseName
    Name for the lakehouse (default: zava-diy-lakehouse).
.PARAMETER OntologyName
    Name for the Fabric IQ ontology (default: ZavaDIYOntology).
.PARAMETER IncludeEmbeddings
    If specified, includes vector embedding columns in the products table.
.PARAMETER SkipOntology
    If specified, skips Fabric IQ ontology creation.
.PARAMETER TenantId
    Microsoft Entra tenant ID to use for Fabric and OneLake authentication.
#>
param(
    [string]$WorkspaceId = "",
    [string]$CapacityId = "",
    [string]$LakehouseName = "ZavaDIYLakehouse",
    [string]$WorkspaceName = "ZavaDIYWorkspace",
    [string]$OntologyName = "ZavaDIYOntology",
    [string]$TenantId = "",
    [string]$ClientId = "",
    [string]$ClientSecret = "",
    [string]$LabUserUpn = "",
    [string]$LabUserObjectId = "",
    [switch]$IncludeEmbeddings,
    [switch]$SkipOntology
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

if (-not $WorkspaceId -and -not $CapacityId) {
    throw "Either -WorkspaceId or -CapacityId must be provided."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = $scriptDir

Write-Output "==============================================" 
Write-Output " Fabric Lakehouse Setup - Zava DIY Dataset"
Write-Output "=============================================="
Write-Output ""

# Create .env file
$envContent = @"
FABRIC_WORKSPACE_ID=$WorkspaceId
FABRIC_CAPACITY_ID=$CapacityId
FABRIC_WORKSPACE_NAME=$WorkspaceName
LAKEHOUSE_NAME=$LakehouseName
FABRIC_ONTOLOGY_NAME=$OntologyName
FABRIC_TENANT_ID=$TenantId
FABRIC_LAB_USER_UPN=$LabUserUpn
FABRIC_LAB_USER_OID=$LabUserObjectId
CREATE_ONTOLOGY=$(if ($SkipOntology) { "false" } else { "true" })
INCLUDE_EMBEDDINGS=$(if ($IncludeEmbeddings) { "true" } else { "false" })
"@

$envPath = Join-Path $repoRoot ".env"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($envPath, $envContent, $utf8NoBom)
Write-Output "Created .env file"

# Find Python
$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $pythonCmd) { $pythonCmd = (Get-Command py -ErrorAction SilentlyContinue) }
if (-not $pythonCmd) { throw "Python 3.10+ is required. Please install Python." }

# Create venv
$venvPath = Join-Path $repoRoot ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Output "Creating Python virtual environment..."
    python -m venv $venvPath
}

$venvPy = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPy)) { 
    # Linux/Mac fallback
    $venvPy = Join-Path $venvPath "bin/python"
}
if (-not (Test-Path $venvPy)) { throw "Venv python not found at $venvPy" }

# Install dependencies (reuse notebooks/requirements.txt which has all needed packages)
$repoParent = Split-Path $repoRoot -Parent
$reqFile = Join-Path (Join-Path $repoParent "notebooks") "requirements.txt"
if (-not (Test-Path $reqFile)) {
    $reqFile = Join-Path $repoRoot "requirements.txt"
}
if (-not (Test-Path $reqFile)) { throw "No requirements file found" }

Write-Output "Installing Python dependencies..."
& $venvPy -m pip install --upgrade pip --quiet 2>$null
& $venvPy -m pip install -r $reqFile --quiet 2>$null

# Run the lakehouse creation script
$createScript = Join-Path $repoRoot "create-lakehouse.py"
if (-not (Test-Path $createScript)) { throw "create-lakehouse.py not found at $createScript" }

Write-Output "Running create-lakehouse.py..."
Write-Output ""

# Set env vars for DefaultAzureCredential (EnvironmentCredential)
if ($ClientId) { [Environment]::SetEnvironmentVariable("AZURE_CLIENT_ID", $ClientId, "Process") }
if ($ClientSecret) { [Environment]::SetEnvironmentVariable("AZURE_CLIENT_SECRET", $ClientSecret, "Process") }
if ($TenantId) { [Environment]::SetEnvironmentVariable("AZURE_TENANT_ID", $TenantId, "Process") }

Push-Location $repoRoot
& $venvPy $createScript
$exitCode = $LASTEXITCODE
Pop-Location

if ($exitCode -eq 0) {
    Write-Output ""
    Write-Output "Lakehouse and ontology setup completed successfully!"
} else {
    Write-Output ""
    Write-Output "ERROR: Lakehouse setup failed. Check create-lakehouse.log for details."
    exit $exitCode
}
