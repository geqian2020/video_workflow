param([string]$TextFile=$env:WORKFLOW_TEXT_FILE, [string]$OutputWave=$env:WORKFLOW_OUTPUT_WAVE)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$workflowVoice = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $workflowChinese = $workflowVoice.GetInstalledVoices() |
        Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'zh-CN' } |
        Select-Object -First 1
    if (-not $workflowChinese) { throw 'No zh-CN voice installed' }
    $workflowVoice.SelectVoice($workflowChinese.VoiceInfo.Name)
    $workflowFormat = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
        16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono)
    $workflowVoice.SetOutputToWaveFile($OutputWave, $workflowFormat)
    $workflowVoice.Speak([IO.File]::ReadAllText($TextFile, [Text.Encoding]::UTF8))
} finally {
    $workflowVoice.Dispose()
}
