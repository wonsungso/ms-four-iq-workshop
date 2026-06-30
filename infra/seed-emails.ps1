<#
.SYNOPSIS
    Seeds sample emails into the lab user's mailbox via Microsoft Graph API.
.DESCRIPTION
    Uses the service principal's app-only token to send emails from the lab user
    to themselves. Requires Mail.Send application permission (admin-consented).
.PARAMETER UserUpn
    The lab user's UPN (email) to send messages to/from.
.PARAMETER TenantId
    The Entra tenant ID for token acquisition.
.PARAMETER ClientId
    The service principal's app/client ID.
.PARAMETER ClientSecret
    The service principal's client secret.
#>
param(
    [Parameter(Mandatory)][string]$UserUpn,
    [Parameter(Mandatory)][string]$TenantId,
    [Parameter(Mandatory)][string]$ClientId,
    [Parameter(Mandatory)][string]$ClientSecret
)

$ErrorActionPreference = "Stop"

function Log {
    param([string]$msg)
    Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
}

# Get an app-only token for Microsoft Graph
function Get-GraphToken {
    $body = @{
        grant_type    = "client_credentials"
        client_id     = $ClientId
        client_secret = $ClientSecret
        scope         = "https://graph.microsoft.com/.default"
    }
    $response = Invoke-RestMethod -Method POST `
        -Uri "https://login.microsoftonline.com/$TenantId/oauth2/v2.0/token" `
        -ContentType "application/x-www-form-urlencoded" `
        -Body $body
    return $response.access_token
}

# Send an email from the user to themselves
function Send-MailMessage {
    param(
        [string]$Token,
        [string]$UserId,
        [hashtable]$Mail
    )
    $headers = @{
        Authorization  = "Bearer $Token"
        "Content-Type" = "application/json; charset=utf-8"
    }
    $url = "https://graph.microsoft.com/v1.0/users/$UserId/sendMail"
    $payload = @{ message = $Mail; saveToSentItems = $false } | ConvertTo-Json -Depth 10
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-RestMethod -Method POST -Uri $url -Headers $headers -Body ([System.Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 60
            return $true
        } catch {
            $errBody = ""
            if ($_.Exception.Response) {
                $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
                $errBody = $reader.ReadToEnd()
                $reader.Close()
            }
            Log "ERROR attempt $attempt ($($_.Exception.Response.StatusCode)): $errBody"
            if ($attempt -lt 3) {
                Start-Sleep -Seconds 5
            }
        }
    }
    return $false
}

# ============================================================
# Email definitions
# ============================================================

$emails = @(
    @{
        subject      = "Urgent: Professional Claw Hammer out of stock at Seattle store"
        from         = @{ emailAddress = @{ name = "Marcus Chen"; address = $UserUpn } }
        toRecipients = @(
            @{ emailAddress = @{ name = "Me"; address = $UserUpn } }
        )
        body         = @{
            contentType = "HTML"
            content     = @"
<p>Hey,</p>
<p>The store manager at <strong>Zava Retail Seattle</strong> says customers keep asking for the <strong>Professional Claw Hammer 16oz</strong> (SKU: HTHM001600) but the shelf has been empty for three days now. We've had at least six customer complaints this week alone.</p>
<p>Can you check stock levels across our other stores and see if we can do a transfer? Seattle is our highest-traffic location and this is one of our best sellers &mdash; we can't afford to be out of stock heading into summer.</p>
<p>If other stores are low too, we may need to escalate to procurement for an emergency reorder.</p>
<p>Thanks,<br/>Marcus Chen<br/>Regional Operations Manager</p>
"@
        }
    },
    @{
        subject      = "RE: Weekly inventory report - Seattle flagged"
        from         = @{ emailAddress = @{ name = "Priya Sharma"; address = $UserUpn } }
        toRecipients = @(
            @{ emailAddress = @{ name = "Me"; address = $UserUpn } }
        )
        body         = @{
            contentType = "HTML"
            content     = @"
<p>Hi,</p>
<p>Just following up on Marcus's note &mdash; I pulled the weekly inventory report and Seattle is showing <strong>zero stock</strong> on several hand tools, not just the claw hammer. The Professional Claw Hammer (HTHM001600) is the most requested one though.</p>
<p>I checked Bellevue and Redmond and they seem to have some units. Could you verify the exact numbers in the system and coordinate a store-to-store transfer if the quantities allow?</p>
<p>Also worth checking if Tacoma or Online have surplus &mdash; their seasonal demand is usually lower this time of year.</p>
<p>Let me know if you need help with the transfer paperwork.</p>
<p>Thanks,<br/>Priya Sharma<br/>Inventory Analyst</p>
"@
        }
    },
    @{
        subject      = "Customer escalation - hammer unavailable again"
        from         = @{ emailAddress = @{ name = "Jordan Lee"; address = $UserUpn } }
        toRecipients = @(
            @{ emailAddress = @{ name = "Me"; address = $UserUpn } }
        )
        body         = @{
            contentType = "HTML"
            content     = @"
<p>Hi team,</p>
<p>Got another customer complaint on the support line &mdash; a contractor needed 5 units of the Professional Claw Hammer 16oz for a job this weekend and was told Seattle is completely out. He's threatening to switch to Home Depot if we can't fulfill by Friday.</p>
<p>This is the third escalation this week on the same SKU (HTHM001600). Can someone please check what's available across all stores and get a transfer or restock in motion ASAP?</p>
<p>Thanks,<br/>Jordan Lee<br/>Customer Support Lead</p>
"@
        }
    }
)

# ============================================================
# Main
# ============================================================

Log "Sending $($emails.Count) emails to mailbox: $UserUpn"

$token = Get-GraphToken
Log "Acquired Graph API token (length: $($token.Length))"

foreach ($email in $emails) {
    $ok = Send-MailMessage -Token $token -UserId $UserUpn -Mail $email
    if ($ok) {
        Log "Sent: $($email.subject)"
    } else {
        Log "FAILED: $($email.subject)"
    }
    Start-Sleep -Seconds 1
}

Log "Email seeding complete!"
