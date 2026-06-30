param(
  [Parameter(Mandatory=$true)][string]$SearchEndpoint,
  [Parameter(Mandatory=$true)][string]$SearchAdminKey,
  [Parameter(Mandatory=$true)][string]$OpenAIEndpoint,
  [Parameter(Mandatory=$true)][string]$OpenAIKey,
  [string]$EmbeddingDeployment = "text-embedding-3-large",
  [string]$TenantId = "",
  [string]$ProjectEndpoint = "",
  [string]$ProjectResourceId = "",
  [string]$ProjectConnectionName = "kb-mcp-connection",
  [string]$CapacityId = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$repoRoot = "C:\Users\LabUser\Desktop\Build26-LAB532-main"
$knowledgeFolder = Join-Path $repoRoot "notebooks"
$infraFolder = Join-Path $repoRoot "infra"

# Create .env content
$envContent = @"
# Azure AI Search Configuration
AZURE_SEARCH_SERVICE_ENDPOINT=$SearchEndpoint
AZURE_SEARCH_ADMIN_KEY=$SearchAdminKey

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=$OpenAIEndpoint
AZURE_OPENAI_KEY=$OpenAIKey
AZURE_OPENAI_CHATGPT_DEPLOYMENT=gpt-5.4
AZURE_OPENAI_CHATGPT_MODEL_NAME=gpt-5.4
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=$EmbeddingDeployment

# Tenant and project configuration
AZURE_TENANT_ID=$TenantId

# Fabric configuration (populated by lakehouse setup if capacity was deployed)
FABRIC_CAPACITY_ID=$CapacityId
"@

# Write .env to repo root WITHOUT BOM
$envPathRoot = Join-Path $repoRoot ".env"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($envPathRoot, $envContent, $utf8NoBom)
Write-Output "Created .env in repo root"

# # Write .env to notebook folder WITHOUT BOM
# $envPathNotebook = Join-Path $knowledgeFolder ".env"
# [System.IO.File]::WriteAllText($envPathNotebook, $envContent, $utf8NoBom)
# Write-Output "Created .env in notebook folder"

$docsPath = Join-Path $repoRoot "data\ai-search-data"
if (-not (Test-Path $docsPath)) {
    throw "Documents folder not found at $docsPath"
}
Write-Output "Using existing documents at: $docsPath"

[System.Environment]::SetEnvironmentVariable("LOCAL_DOCS_PATH", $docsPath, "Process")

$reqLocal = Join-Path $knowledgeFolder "requirements.txt"
if (-not (Test-Path $reqLocal)) { 
    throw "requirements.txt not found at $reqLocal" 
}

$pyLocal = Join-Path $infraFolder "create-knowledge.py"
if (-not (Test-Path $pyLocal)) { 
    throw "create-knowledge.py not found at $pyLocal" 
}

# Change to repo root (where .env and .venv will be)
Push-Location $repoRoot

$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $pythonCmd) { $pythonCmd = (Get-Command py -ErrorAction SilentlyContinue) }
if (-not $pythonCmd) { throw "Python 3.10+ is required." }

# Create venv in repo root
if (-not (Test-Path ".venv")) {
    Write-Output "Creating Python virtual environment in repo root..."
    python -m venv .venv
}

$venvPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "Venv python not found at $venvPy" }

Write-Output "Installing Python dependencies..."
& $venvPy -m pip install --upgrade pip --no-python-version-warning
& $venvPy -m pip install -r $reqLocal --no-cache-dir --disable-pip-version-check

Write-Output "Uploading documents to blob storage..."
& $venvPy $pyLocal

Pop-Location

Write-Output ""
Write-Output "Setup completed successfully!"
Write-Output "Next: Open the notebook to create Knowledge Sources from existing indexes and a Knowledge Base with multi knowledge source setup."
