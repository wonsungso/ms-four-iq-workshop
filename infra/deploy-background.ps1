[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$logFile = "C:\Users\LabUser\Desktop\lifecycle-log.txt"
function Log {
    param([string]$msg)
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

Log "=== Background deploy script started ==="

$subscriptionId = $env:BG_SUBSCRIPTION_ID
$resourceGroupName = $env:BG_RESOURCE_GROUP
$labUserObjectId = $env:BG_LAB_USER_OID
$labUserUpn = $env:BG_LAB_USER_UPN
$bicepFilePath = $env:BG_BICEP_PATH
$clientId = $env:BG_CLIENT_ID
$clientSecret = $env:BG_CLIENT_SECRET
$tenantId = $env:BG_TENANT_ID

# Reuse the az CLI session from the foreground script (token cache in ~/.azure/)
az config set core.only_show_errors=yes --only-show-errors
az config set bicep.use_binary_from_path=false --only-show-errors

# Resolve SP object ID so Bicep can add it as a Fabric capacity admin
$spObjectId = az ad sp show --id $clientId --query id -o tsv
Log "SP Object ID: $spObjectId"

$deploymentName = "deployment"

# Purge soft-deleted Cognitive Services accounts to prevent custom subdomain conflicts
Log "Checking for soft-deleted Cognitive Services accounts..."
$deletedJson = az cognitiveservices account list-deleted -o json 2>$null
if ($deletedJson -and $deletedJson -ne "[]") {
    $deletedAccounts = $deletedJson | ConvertFrom-Json
    foreach ($account in $deletedAccounts) {
        if ($account.name -like "lab532-foundry-*") {
            Log "Purging soft-deleted Cognitive Services account: $($account.name) (location: $($account.location))"
            az cognitiveservices account purge --location $account.location --resource-group $resourceGroupName --name $account.name 2>&1 | Out-Null
            Log "Purged: $($account.name)"
        }
    }
}

Log "Starting Bicep deployment..."
$deploymentOutput = az deployment group create `
  --name $deploymentName `
  --resource-group $resourceGroupName `
  --template-file $bicepFilePath `
  --parameters principalId="$labUserObjectId" `
  --parameters fabricAdminUpn="$labUserUpn" `
  --parameters spPrincipalId="$spObjectId" `
  --parameters location="eastus2" `
  --query properties.outputs -o json 2>&1
$deployExitCode = $LASTEXITCODE

if ($deployExitCode -ne 0) {
    Log "Deployment failed (exit code $deployExitCode):"
    Add-Content -Path $logFile -Value $deploymentOutput
    $opErrors = az deployment operation group list `
      --resource-group $resourceGroupName `
      --name $deploymentName `
      --query "[?properties.provisioningState=='Failed'].{Resource:properties.targetResource.resourceName, Type:properties.targetResource.resourceType, Error:properties.statusMessage.error}" `
      -o json 2>&1
    Log "Operation errors:"
    Add-Content -Path $logFile -Value $opErrors
    Log "=== Background deploy script FAILED ==="
    exit 1
}

Log "Deployment succeeded."

Add-Content -Path $logFile -Value $deploymentOutput
$outs = $deploymentOutput | ConvertFrom-Json

$searchName          = $outs.AZURE_SEARCH_SERVICE_NAME.value
$searchEndpoint      = $outs.AZURE_SEARCH_SERVICE_ENDPOINT.value
$openaiName          = $outs.AZURE_OPENAI_SERVICE_NAME.value
$openaiEndpoint      = $outs.AZURE_OPENAI_ENDPOINT.value
$projectEndpoint     = $outs.MICROSOFT_FOUNDRY_PROJECT_ENDPOINT.value
$projectResourceId   = $outs.MICROSOFT_FOUNDRY_PROJECT_ID.value
$fabricCapacityId    = $outs.FABRIC_CAPACITY_ID.value

$searchAdminKey = az rest --method POST `
  --url "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroupName/providers/Microsoft.Search/searchServices/$searchName/listAdminKeys?api-version=2023-11-01" `
  --query primaryKey -o tsv

$openaiKey = az cognitiveservices account keys list -g $resourceGroupName -n $openaiName --query key1 -o tsv

# Validate all required values before calling setup-knowledge.ps1
# (empty mandatory params cause PowerShell to hang waiting for interactive input)
Log "searchEndpoint=$searchEndpoint"
Log "searchAdminKey length=$($searchAdminKey.Length)"
Log "openaiEndpoint=$openaiEndpoint"
Log "openaiKey length=$($openaiKey.Length)"
Log "projectEndpoint=$projectEndpoint"
Log "projectResourceId=$projectResourceId"

$missingParams = @()
if ([string]::IsNullOrWhiteSpace($searchEndpoint))      { $missingParams += "SearchEndpoint" }
if ([string]::IsNullOrWhiteSpace($searchAdminKey))       { $missingParams += "SearchAdminKey" }
if ([string]::IsNullOrWhiteSpace($openaiEndpoint))       { $missingParams += "OpenAIEndpoint" }
if ([string]::IsNullOrWhiteSpace($openaiKey))            { $missingParams += "OpenAIKey" }
if ($missingParams.Count -gt 0) {
    Log "ERROR: Missing required values: $($missingParams -join ', ')"
    exit 1
}

$localInfraPath = "C:\Users\LabUser\Desktop\Build26-LAB532-main\infra"
$setupLocal = Join-Path $localInfraPath "setup-knowledge.ps1"

if (-not (Test-Path $setupLocal)) {
    Log "ERROR: Setup file not found at: $setupLocal"
    exit 1
}

$docsPath = "C:\Users\LabUser\Desktop\Build26-LAB532-main\data\ai-search-data"
[Environment]::SetEnvironmentVariable("LOCAL_DOCS_PATH", $docsPath, "Process")

Log "Running setup-knowledge.ps1..."
powershell -ExecutionPolicy Bypass -File $setupLocal `
  -SearchEndpoint $searchEndpoint `
  -SearchAdminKey $searchAdminKey `
  -OpenAIEndpoint $openaiEndpoint `
  -OpenAIKey $openaiKey `
  -TenantId $tenantId `
  -ProjectEndpoint $projectEndpoint `
  -ProjectResourceId $projectResourceId 2>&1 | Tee-Object -FilePath $logFile -Append

# Set up Fabric Lakehouse
if ($fabricCapacityId) {
    Log "Setting up Fabric Lakehouse..."
    $setupLakehouse = Join-Path $localInfraPath "setup-lakehouse.ps1"
    if (Test-Path $setupLakehouse) {
        powershell -ExecutionPolicy Bypass -File $setupLakehouse `
          -CapacityId $fabricCapacityId `
          -TenantId $tenantId `
          -ClientId $clientId `
          -ClientSecret $clientSecret `
          -LabUserUpn $labUserUpn `
          -LabUserObjectId $labUserObjectId 2>&1 | Tee-Object -FilePath $logFile -Append
        # Append the Python-level log for debugging
        $fabricLog = Join-Path $localInfraPath "create-lakehouse.log"
        if (Test-Path $fabricLog) {
            Log "--- Fabric Python log ---"
            Get-Content $fabricLog | Add-Content -Path $logFile
        }
        Log "Fabric Lakehouse setup complete"
    } else {
        Log "WARNING: setup-lakehouse.ps1 not found, skipping lakehouse"
    }
}

# Seed sample emails
$seedEmails = Join-Path $localInfraPath "seed-emails.ps1"
if (Test-Path $seedEmails) {
    Log "Seeding sample emails..."
    powershell -ExecutionPolicy Bypass -File $seedEmails `
      -UserUpn $labUserUpn `
      -TenantId $tenantId `
      -ClientId $clientId `
      -ClientSecret $clientSecret 2>&1 | Tee-Object -FilePath $logFile -Append
    Log "Email seeding complete"
}

Log "=== Background deploy script completed ==="
