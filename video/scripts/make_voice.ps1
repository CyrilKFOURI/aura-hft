# Generate the v2 voiceover offline with Windows SAPI (System.Speech).
# Reads the table in video/VOICEOVER_v2.md and writes one WAV per line to video/render/voice/.
# Usage: powershell -ExecutionPolicy Bypass -File video/scripts/make_voice.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root "render\voice"
New-Item -ItemType Directory -Force $out | Out-Null
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice("Microsoft Zira Desktop")
$synth.Rate = 1
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$lines = Get-Content (Join-Path $root "VOICEOVER_v2.md") -Encoding UTF8 | Where-Object { $_ -match '^\| \d\d \|' }
$cues = @()
foreach ($l in $lines) {
    $c = $l.Split('|') | ForEach-Object { $_.Trim() }
    $id, $start, $text = $c[1], $c[2], $c[4]
    $wav = Join-Path $out "vo_$id.wav"
    $synth.SetOutputToWaveFile($wav, $fmt)
    $synth.Speak($text)
    $synth.SetOutputToNull()
    $secs = ((Get-Item $wav).Length - 44) / 96000
    $cues += "$id;$start;$([math]::Round($secs, 2))"
    Write-Output ("{0} start {1,5}s  dur {2,5:N2}s  end {3,5:N2}s" -f $id, $start, $secs, ([double]$start + $secs))
}
$cues | Set-Content (Join-Path $out "cues.txt") -Encoding ascii
