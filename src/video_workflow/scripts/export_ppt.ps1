param([string]$InputDeck=$env:WORKFLOW_INPUT_DECK, [string]$OutputDir=$env:WORKFLOW_OUTPUT_DIR)
$ErrorActionPreference = 'Stop'
$workflowOffice = $null
$workflowDeck = $null
$workflowHadOffice = [bool](Get-Process -Name POWERPNT -ErrorAction SilentlyContinue)
try {
    $workflowOffice = New-Object -ComObject PowerPoint.Application
    $workflowDeck = $workflowOffice.Presentations.Open($InputDeck, $true, $false, $false)
    for ($workflowIndex = 1; $workflowIndex -le $workflowDeck.Slides.Count; $workflowIndex++) {
        $workflowPath = Join-Path $OutputDir ('page-{0:D3}.png' -f $workflowIndex)
        $workflowPage = $workflowDeck.Slides.Item($workflowIndex)
        $workflowPage.Export($workflowPath, 'PNG', 1920)
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($workflowPage)
    }
} finally {
    if ($workflowDeck) {
        $workflowDeck.Close()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($workflowDeck)
    }
    if ($workflowOffice) {
        # Never close an Office session that was already running for the user.
        if (-not $workflowHadOffice -and $workflowOffice.Presentations.Count -eq 0) {
            $workflowOffice.Quit()
        }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($workflowOffice)
    }
}
