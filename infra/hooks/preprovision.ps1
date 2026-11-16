$ErrorActionPreference = "Stop"

Write-Host "Running preprovision hook..."

# Register the Microsoft.WebIQ resource provider so the Web IQ account in
# main.bicep can be created. Registration is a one-time, subscription-level
# operation and is safe to run on every `azd up`.
Write-Host "Registering Microsoft.WebIQ resource provider..."
az provider register --namespace Microsoft.WebIQ --wait
if ($LASTEXITCODE -ne 0) { throw "Microsoft.WebIQ resource provider registration failed." }

Write-Host "Preprovision complete."
