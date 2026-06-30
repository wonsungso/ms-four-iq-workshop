# ===========================================
# Download GitHub Repo to Skillable Desktop
# ===========================================

# Set variables
$token = "SECRET"
$targetPath = "C:\Users\LabUser\Desktop\Build26-LAB532-main"
$tempZip = "$env:TEMP\repo.zip"

# Download as ZIP using GitHub API
$headers = @{
    Authorization = "Bearer $token"
    Accept = "application/vnd.github+json"
}

$zipUrl = "https://api.github.com/repos/microsoft/Build26-LAB532-from-data-to-context-agent-ready-knowledge-with-foundry-iq/zipball/main"

Invoke-WebRequest -Uri $zipUrl -Headers $headers -OutFile $tempZip -UseBasicParsing

# Extract to temp location
$tempExtract = "$env:TEMP\extracted"
if (Test-Path $tempExtract) {
    Remove-Item $tempExtract -Recurse -Force
}
Expand-Archive -Path $tempZip -DestinationPath $tempExtract -Force

# Find the extracted folder and move to final location
$extractedFolder = Get-ChildItem $tempExtract -Directory | Select-Object -First 1

if (Test-Path $targetPath) {
    Remove-Item $targetPath -Recurse -Force
}
Move-Item $extractedFolder.FullName $targetPath -Force
