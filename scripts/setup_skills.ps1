# setup_skills.ps1 — clone/update the vendored claude-skills roster (Phase 37).
#
# The 345+ engineering skills from alirezarezvani/claude-skills are NOT committed into this repo
# (skills/external/ is gitignored). Run this once to fetch them; re-run to update.
#
# SkillsEngine auto-discovers every canonical SKILL.md under skills/ (it skips the .gemini/.claude/
# tool-converted duplicate copies), so cloned skills become available immediately — and any skill
# is callable as a full agent via run_skill_agent / run_engineering_agent.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $repoRoot "skills\external"

if (Test-Path (Join-Path $dest ".git")) {
    Write-Host "Updating existing skills/external ..."
    git -C $dest pull --ff-only
} else {
    Write-Host "Cloning claude-skills into skills/external ..."
    git clone --depth 1 https://github.com/alirezarezvani/claude-skills.git $dest
}

$count = (Get-ChildItem -Path $dest -Recurse -Filter "SKILL.md" -ErrorAction SilentlyContinue |
          Where-Object { $_.FullName -notmatch "\\\.[^\\]+\\" }).Count
Write-Host "Done. Canonical SKILL.md files available: $count"
