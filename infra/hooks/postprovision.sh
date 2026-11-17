#!/bin/sh
set -e

echo "Running postprovision hook..."

# Install workshop dependencies.
python3 -m pip install -r workshop-support/requirements.txt --quiet 2>/dev/null

# Write notebook settings while preserving locally configured Web IQ keys.
python3 infra/setup-env.py

# Create indexes and upload data
echo "Running knowledge setup..."
python3 infra/create-knowledge.py

# Set up Fabric Lakehouse (if capacity was deployed)
if [ -n "$FABRIC_CAPACITY_ID" ]; then
    echo "Setting up Fabric Lakehouse..."
    python3 infra/create-lakehouse.py
fi

# Note: Email seeding (seed-emails.ps1) requires a service principal with
# Mail.Send application permission and is not run as part of self-deploy.
# For self-deploy, Part 4 (Work IQ) will use your own mailbox data.

echo "Postprovision complete! If there were no errors, you can open labs/ to start the lab."