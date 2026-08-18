# SessionStart hook: inject the "Resume here" block of docs/STATUS.md.
#
# After an auto-compaction the summary decides what survives, and the handoff is exactly the thing
# that must not be paraphrased. Re-injecting it makes recovery deterministic instead of hopeful.
# Runs on every session source (startup, resume, clear, compact, fork): the block is short and it
# is the right first thing to know in all of them.
#
# Silent no-op when there is no STATUS.md. This hook must never be the reason a session fails to
# start, so every failure path exits 0 with no output.
#
# Keep this file ASCII-only. Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI, and a UTF-8 em
# dash decodes to a curly quote that PowerShell honours as a string delimiter - the script then
# fails to parse.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Hook input arrives as JSON on stdin. We only want `source`; missing or unreadable stdin is fine.
$source = 'unknown'
try {
    $raw = [Console]::In.ReadToEnd()
    if ($raw) { $source = (ConvertFrom-Json $raw).source }
} catch {}

try {
    $projectDir = $env:CLAUDE_PROJECT_DIR
    if (-not $projectDir) { $projectDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }

    $status = Join-Path $projectDir 'docs/STATUS.md'
    if (-not (Test-Path -LiteralPath $status)) { exit 0 }

    $lines = @(Get-Content -LiteralPath $status -Encoding UTF8)

    # '^##\s' deliberately does not match '### Next three actions' - that subsection is part of the
    # block and must come through with it.
    $start = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^##\s+Resume here\s*$') { $start = $i; break }
    }
    if ($start -lt 0) { exit 0 }

    $block = New-Object System.Collections.Generic.List[string]
    for ($i = $start; $i -lt $lines.Count; $i++) {
        if ($i -gt $start -and $lines[$i] -match '^##\s+') { break }
        $block.Add($lines[$i])
        if ($block.Count -ge 60) { $block.Add('<truncated - read docs/STATUS.md for the rest>'); break }
    }

    $header = @(
        "Handoff from docs/STATUS.md (session source: $source).",
        "This is the project's resume point. The tree is the authority: where the two disagree,",
        "believe the tree and correct the file. Do not re-read STATUS.md unless you need a section",
        "below this block."
    ) -join ' '

    $payload = [ordered]@{
        hookSpecificOutput = [ordered]@{
            hookEventName     = 'SessionStart'
            additionalContext = ($header + "`n`n" + ($block -join "`n"))
        }
    }

    $payload | ConvertTo-Json -Depth 5 -Compress
} catch {
    exit 0
}
