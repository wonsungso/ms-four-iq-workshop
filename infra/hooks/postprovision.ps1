$ErrorActionPreference = "Stop"

Write-Host "Running postprovision hook..."

# Install workshop dependencies.
python -m pip install -r workshop-support\requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

# Write notebook settings while preserving locally configured Web IQ keys.
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

Write-Host "Postprovision complete! If there were no errors, you can open labs/ to start the lab."
