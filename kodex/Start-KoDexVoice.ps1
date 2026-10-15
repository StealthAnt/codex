param()

$ErrorActionPreference = 'Stop'
$python = Get-Command 'python.exe' -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command 'python' -ErrorAction SilentlyContinue }
$bridge = Join-Path $PSScriptRoot 'assistant_bridge.py'
if (-not $python -or -not (Test-Path -LiteralPath $bridge)) {
    throw 'Install Python 3 and keep assistant_bridge.py beside this script.'
}

try {
    Add-Type -AssemblyName System.Speech
    $recognizer = [System.Speech.Recognition.SpeechRecognitionEngine]::new()
    $recognizer.LoadGrammar([System.Speech.Recognition.DictationGrammar]::new())
    $recognizer.SetInputToDefaultAudioDevice()
    $speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
} catch {
    throw "Windows speech recognition is unavailable. Install an English speech recognition language pack and microphone access. Details: $($_.Exception.Message)"
}

$env:CODEX_HOME = Join-Path $env:LOCALAPPDATA 'KoDex'
New-Item -ItemType Directory -Path $env:CODEX_HOME -Force | Out-Null
$speaker.Speak('KoDex voice task helper is ready. Press Enter to speak a task command, or Q to quit.')
Write-Host 'KoDex voice helper. Press Enter, speak one command, then wait for the result. Press Q to quit.'
Write-Host 'Supported: add task followed by a title; list my tasks; complete task followed by its KDX ID.'

while ($true) {
    $key = Read-Host 'Enter to speak, Q to quit'
    if ($key -match '^(q|quit)$') { break }
    try {
        $result = $recognizer.Recognize([TimeSpan]::FromSeconds(8))
        if (-not $result) { $speaker.Speak('I did not catch that.'); continue }
        $phrase = $result.Text.Trim()
        Write-Host "Heard: $phrase"
        if ($phrase -match '^add task\s+(.+)$') {
            $taskJson = & $python.Source $bridge --task-add $Matches[1]
            $task = $taskJson | ConvertFrom-Json
            $speaker.Speak("Saved task. $($task.id).")
            Write-Host "Saved $($task.id): $($task.title)"
        } elseif ($phrase -match '^(list|read|show)( my)? tasks$') {
            $tasks = @((& $python.Source $bridge --task-list) | ConvertFrom-Json)
            if ($tasks.Count -eq 0) {
                $speaker.Speak('You have no open tasks.')
            } else {
                foreach ($task in $tasks) { Write-Host "$($task.id): $($task.title)" }
                $speaker.Speak("You have $($tasks.Count) open tasks. See the console for their names.")
            }
        } elseif ($phrase -match '^complete task\s+(KDX-[A-F0-9]{8})$') {
            $taskJson = & $python.Source $bridge --task-complete $Matches[1]
            $task = $taskJson | ConvertFrom-Json
            $speaker.Speak('Task completed.')
            Write-Host "Completed $($task.id): $($task.title)"
        } else {
            $speaker.Speak('I can add a task or read your tasks. Use KoDex for other app actions, where you can review and approve each one.')
        }
    } catch {
        Write-Warning $_
        $speaker.Speak('That command did not complete.')
    }
}

$recognizer.Dispose()
$speaker.Dispose()
