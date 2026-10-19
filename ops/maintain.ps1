param(
    [string]$Project = "argusai-497719",
    [string]$Region = "us-central1"
)

$ErrorActionPreference = "Stop"
$gcloud = "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"

if (-not (Test-Path -LiteralPath $gcloud)) {
    throw "Google Cloud CLI was not found at $gcloud"
}

function Invoke-GcloudJson {
    param([string[]]$Arguments)
    $raw = & $gcloud @Arguments --project $Project --format=json 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($raw -join [Environment]::NewLine) }
    return ($raw | ConvertFrom-Json)
}

function Test-PublicUrl {
    param([string]$Name, [string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 90
        [pscustomobject]@{ service = $Name; url = $Url; status = $response.StatusCode; ok = $true }
    } catch {
        $status = 0
        if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
        [pscustomobject]@{ service = $Name; url = $Url; status = $status; ok = $false }
    }
}

$billing = Invoke-GcloudJson @("billing", "projects", "describe", $Project)
if (-not $billing.billingEnabled) {
    Write-Error "Billing is disabled for $Project. Cloud Run and Secret Manager cannot serve even free-tier traffic. Enable it at https://console.developers.google.com/billing/enable?project=$Project"
    exit 2
}

$services = foreach ($name in @("argusai-frontend", "argusai-backend", "argusai-phoenix")) {
    $service = Invoke-GcloudJson @("run", "services", "describe", $name, "--region", $Region)
    $ready = @($service.status.conditions | Where-Object { $_.type -eq "Ready" })[0]
    [pscustomobject]@{
        service = $name
        ready = $ready.status -eq "True"
        revision = $service.status.latestReadyRevisionName
        url = $service.status.url
    }
}

$services | Format-Table -AutoSize

$projectNumber = "1007754127412"
$checks = @(
    Test-PublicUrl "frontend" "https://argusai-frontend-$projectNumber.$Region.run.app"
    Test-PublicUrl "frontend-canonical" "https://argusai-frontend-ddmxiumrdq-uc.a.run.app"
    Test-PublicUrl "backend-health" "https://argusai-backend-$projectNumber.$Region.run.app/health"
)
$checks | Format-Table -AutoSize

if ($services.ready -contains $false -or $checks.ok -contains $false) {
    Write-Error "One or more production checks failed. No deployment was attempted."
    exit 3
}

$health = Invoke-RestMethod -Uri "https://argusai-backend-$projectNumber.$Region.run.app/health" -TimeoutSec 90
$health.llm | Select-Object gemini_model, gemini_vision_model, gemini_grounding_model, gemini_fallback_model, explanation_model, model_update_policy | Format-List

Write-Host "ArgusAI production maintenance check passed."
