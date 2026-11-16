#!/bin/sh
set -e

echo "Running preprovision hook..."

# Register the Microsoft.WebIQ resource provider so the Web IQ account in
# main.bicep can be created. Registration is a one-time, subscription-level
# operation and is safe to run on every `azd up`.
echo "Registering Microsoft.WebIQ resource provider..."
az provider register --namespace Microsoft.WebIQ --wait

echo "Preprovision complete."
