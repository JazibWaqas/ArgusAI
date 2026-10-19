param(
    [string]$FrontendUrl = "https://argusai-frontend.onrender.com",
    [string]$BackendUrl = "https://argusai-backend-qvrp.onrender.com"
)

$ErrorActionPreference = "Stop"
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

$checks = @(
    Test-PublicUrl "frontend" "$FrontendUrl/"
    Test-PublicUrl "backend-health" "$BackendUrl/health"
)
$checks | Format-Table -AutoSize

if ($checks.ok -contains $false) {
    Write-Error "One or more ArgusAI production checks failed."
    exit 3
}

$health = Invoke-RestMethod -Uri "$BackendUrl/health" -TimeoutSec 120
if ($health.status -ne "ok" -or $health.llm_provider_ready -ne "gemini") {
    Write-Error "Backend responded but is not ready for Gemini investigations."
    exit 4
}
$health.llm | Select-Object gemini_model, gemini_vision_model, gemini_grounding_model, gemini_fallback_model, explanation_model, model_update_policy | Format-List

Write-Host "ArgusAI Render production maintenance check passed."
