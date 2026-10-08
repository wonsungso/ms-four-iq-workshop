$ErrorActionPreference = "Stop"

Write-Host "Running postprovision hook..."

# Install Python dependencies first (needed for key fetching below)
python -m pip install -r notebooks\requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

# Write .env and fetch API keys using azure-identity (no az CLI needed)
python infra\setup-env.py
if ($LASTEXITCODE -ne 0) { throw "Environment setup failed." }

# Create indexes and upload data
Write-Host "Running knowledge setup..."
python infra\create-knowledge.py
if ($LASTEXITCODE -ne 0) { throw "Knowledge setup failed." }

# Set up Fabric Lakehouse (if capacity was deployed)
if ($env:FABRIC_CAPACITY_ID) {
    Write-Host "Setting up Fabric Lakehouse..."
    python infra\create-lakehouse.py
    if ($LASTEXITCODE -ne 0) { throw "Fabric Lakehouse or Ontology setup failed." }
}

Write-Host "Postprovision complete! If there were no errors, you can open notebooks/ to start the lab."
