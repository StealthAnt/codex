param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Listen', 'Speak')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech

if ($Action -eq 'Listen') {
    $recognizer = [System.Speech.Recognition.SpeechRecognitionEngine]::new()
    try {
        $recognizer.LoadGrammar([System.Speech.Recognition.DictationGrammar]::new())
        $recognizer.SetInputToDefaultAudioDevice()
        $result = $recognizer.Recognize([TimeSpan]::FromSeconds(10))
        if ($result) { [Console]::Out.Write($result.Text.Trim()) }
    } finally {
        $recognizer.Dispose()
    }
    exit 0
}

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
$encodedText = [Console]::In.ReadToEnd().Trim()
if (-not $encodedText) { exit 0 }
$text = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedText))
$speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $speaker.Speak($text)
} finally {
    $speaker.Dispose()
}
