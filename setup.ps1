#Requires -Version 5.1
<#
.SYNOPSIS
Prepare a Windows Python 3.11 checkout without running inference or benchmarks.
.EXAMPLE
.\setup.ps1
.EXAMPLE
.\setup.ps1 -WithDatabase -WithFrontend
.EXAMPLE
.\setup.ps1 -VenvPath .venv311 -VerifyOnly
#>
[CmdletBinding()]
param(
    [string]$VenvPath = '.venv',
    [string]$AI1ArtifactZip,
    [switch]$WithDatabase,
    [switch]$WithFrontend,
    [switch]$SkipFrontend,
    [switch]$VerifyOnly,
    [switch]$SkipSlm
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
# Validated Windows/Python 3.11 build; the wheel bundles its CUDA runtime.
$cudaTorchBuild = 'torch==2.14.1+cu130'
$cudaTorchIndex = 'https://download.pytorch.org/whl/cu130'
$capabilities = [ordered]@{
    'Core Python environment' = 'FAILED'
    'AI1 artifacts' = 'MISSING'
    'AI3 CatBoost model' = 'MISSING'
    'Local SLM' = 'UNAVAILABLE'
    'Gemini fallback' = 'NEEDS API KEY'
    'Frontend' = 'SKIPPED'
    'PostgreSQL' = 'SKIPPED'
}

function Test-Nvidia {
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        try {
            $devices = @(& nvidia-smi --query-gpu=name --format=csv,noheader)
            if ($LASTEXITCODE -eq 0 -and ($devices -join '').Trim()) {
                Write-Host "NVIDIA detected: $($devices -join ', '). CUDA will be checked separately."
                return $true
            }
        } catch { Write-Warning "NVIDIA query failed: $_" }
    }
    Write-Host 'No usable NVIDIA detected: Local SLM unavailable; skipping SLM installation. Gemini fallback is available/configurable.'
    return $false
}

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE). Review the output above." }
}

function Test-Torch {
    param([string]$Python)
    $statusText = & $Python 'scripts/preflight.py' '--torch-json'
    if ($LASTEXITCODE -ne 0) { throw 'Torch inspection failed. Review the output above.' }
    $status = ($statusText -join "`n") | ConvertFrom-Json
    Write-Host "PyTorch: $($status.detail)"
    return $status
}

function Initialize-CudaTorch {
    param([string]$Python)
    if (-not $hasNvidia) { return }
    $status = Test-Torch $Python
    if ($status.state -eq 'ready') { return }
    Write-Host 'Local SLM: UNAVAILABLE'
    if ($status.state -in @('cpu', 'missing')) {
        Write-Host 'Action: install CUDA-enabled PyTorch'
        if ($VerifyOnly) { return }
        # Explicit local version replaces even an equal-version CPU wheel. No
        # force-reinstall: working CUDA builds never reach this installation.
        Invoke-Checked $Python @('-m', 'pip', 'install', $cudaTorchBuild, '--index-url', $cudaTorchIndex)
        $status = Test-Torch $Python
        if ($status.state -ne 'ready') { throw "CUDA Torch validation failed: $($status.detail)" }
    } else {
        # Reinstalling a CUDA build is not a driver/runtime repair.
        Write-Warning "CUDA Torch is unusable: $($status.detail)"
    }
}

function Install-Frontend {
    $frontend = Join-Path $PSScriptRoot 'src/frontend'
    if (-not (Test-Path -LiteralPath (Join-Path $frontend 'package.json'))) {
        if ($WithFrontend) {
            $capabilities['Frontend'] = 'UNAVAILABLE'
            throw 'Frontend requested, but src/frontend/package.json is absent.'
        }
        Write-Host 'Frontend absent; skipped.'
        return
    }
    if ($SkipFrontend) { Write-Host 'Frontend skipped by request.'; return }
    $capabilities['Frontend'] = 'UNAVAILABLE'
    if (-not (Get-Command node -ErrorAction SilentlyContinue) -or
        -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        if ($WithFrontend) { throw 'Frontend requested: install Node.js/npm, then rerun setup.' }
        Write-Warning 'Node.js/npm unavailable; AI-only setup continues. Install Node.js/npm and rerun for frontend.'
        return
    }
    Push-Location $frontend
    try {
        if (Test-Path -LiteralPath 'package-lock.json') {
            Invoke-Checked 'npm.cmd' @('ci')
            $capabilities['Frontend'] = 'READY'
        } else {
            # Do not invent a lockfile or substitute another package manager.
            throw 'No npm lockfile found. Ask the frontend owner for its supported install command/lockfile.'
        }
    } catch {
        if ($WithFrontend) { throw }
        Write-Warning "Optional frontend setup failed: $_"
    } finally { Pop-Location }
}

function Start-Database {
    param([string]$Python)
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'WithDatabase requires Docker Desktop with the Compose plugin. Start Docker and rerun.'
    }
    Invoke-Checked 'docker' @('info', '--format', '{{.ServerVersion}}')
    Invoke-Checked 'docker' @('compose', 'version')
    $composeArgs = @('compose', '-f', (Join-Path $PSScriptRoot 'compose.yaml'))
    # Resolve the same .env/process settings Compose uses; never print credentials.
    $configText = & docker @composeArgs config --format json
    if ($LASTEXITCODE -ne 0) { throw 'Could not resolve compose.yaml configuration.' }
    $config = ($configText -join "`n") | ConvertFrom-Json
    $databaseEnv = $config.services.postgres.environment
    Invoke-Checked 'docker' ($composeArgs + @('up', '-d', '--wait', '--wait-timeout', '90', 'postgres'))
    foreach ($file in @('schema.sql', 'indexes.sql', 'procedures.sql')) {
        Invoke-Checked 'docker' ($composeArgs + @('cp', "database/$file", "postgres:/tmp/$file"))
        Invoke-Checked 'docker' ($composeArgs + @('exec', '-T', 'postgres', 'psql', '-v', 'ON_ERROR_STOP=1',
            '-U', [string]$databaseEnv.POSTGRES_USER, '-d', [string]$databaseEnv.POSTGRES_DB, '-f', "/tmp/$file"))
    }
    $processed = @('restaurants', 'dishes', 'menu_items')
    $missing = @($processed | Where-Object { -not (Test-Path -LiteralPath "data/processed/$_.parquet") })
    if ($missing.Count -gt 0) {
        Write-Warning "Database schema ready; seed skipped. Missing processed Parquets: $($missing -join ', '). Request V3 data from AI1 owner."
        return
    }
    $binding = & docker @composeArgs port postgres 5432
    if ($LASTEXITCODE -ne 0 -or -not $binding) { throw 'Cannot find the local PostgreSQL port.' }
    $port = ($binding | Select-Object -First 1).Split(':')[-1]
    $savedDatabaseUrl = [Environment]::GetEnvironmentVariable('DATABASE_URL', 'Process')
    try {
        $dbUser = [Uri]::EscapeDataString([string]$databaseEnv.POSTGRES_USER)
        $dbPassword = [Uri]::EscapeDataString([string]$databaseEnv.POSTGRES_PASSWORD)
        $dbName = [Uri]::EscapeDataString([string]$databaseEnv.POSTGRES_DB)
        # Seed only this local Compose instance, never an unrelated DATABASE_URL.
        $env:DATABASE_URL = "postgresql://${dbUser}:${dbPassword}@127.0.0.1:${port}/${dbName}"
        Invoke-Checked $Python @('scripts/seed_database.py', '--if-empty')
    } finally {
        [Environment]::SetEnvironmentVariable('DATABASE_URL', $savedDatabaseUrl, 'Process')
    }
}

Push-Location $PSScriptRoot
try {
    if ($WithFrontend -and $SkipFrontend) { throw 'Choose either WithFrontend or SkipFrontend.' }
    if ($VerifyOnly -and ($WithDatabase -or $WithFrontend)) { throw 'VerifyOnly cannot start database/frontend setup.' }
    $environmentPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $VenvPath))
    $rootPrefix = $PSScriptRoot.TrimEnd('\') + '\'
    if (-not $environmentPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'VenvPath must name a virtual environment inside this checkout.'
    }
    $python = Join-Path $environmentPath 'Scripts/python.exe'
    $marker = Join-Path $environmentPath '.mlai-setup'
    $hasNvidia = (-not $SkipSlm) -and (Test-Nvidia)
    $slmInstallFailed = $false
    if ($VerifyOnly) {
        if (-not (Test-Path -LiteralPath $python)) { throw "No environment at $VenvPath. Run setup without VerifyOnly." }
        Initialize-CudaTorch $python
    } else {
        $launcher = $null
        $launcherArgs = @()
        foreach ($candidate in @('py', 'python3.11', 'python')) {
            if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
            $candidateArgs = @()
            if ($candidate -eq 'py') { $candidateArgs = @('-3.11') }
            try { & $candidate @candidateArgs -c 'import sys; sys.exit(sys.version_info[:2] != (3, 11))' 2>$null }
            catch { continue }
            if ($LASTEXITCODE -eq 0) { $launcher = $candidate; $launcherArgs = $candidateArgs; break }
        }
        if (-not $launcher) { throw 'Python 3.11 not found. Install Python 3.11 and its Windows py launcher, then rerun.' }
        if (Test-Path -LiteralPath $environmentPath) {
            if (-not (Test-Path -LiteralPath (Join-Path $environmentPath 'pyvenv.cfg')) -or
                -not (Test-Path -LiteralPath $python)) { throw "Existing $VenvPath is not a working venv. Choose another -VenvPath; nothing was overwritten." }
            Invoke-Checked $python @('-c', 'import sys; sys.exit(sys.version_info[:2] != (3, 11))')
            if (-not (Test-Path -LiteralPath $marker)) {
                # An existing editable install must belong to this exact checkout.
                $ownershipCode = "import importlib.metadata as m,json,pathlib,sys; d=json.loads(m.distribution('mlai-food-recommendation').read_text('direct_url.json') or '{}'); sys.exit(not (d.get('dir_info',{}).get('editable') and d.get('url','').rstrip('/').casefold()==pathlib.Path.cwd().as_uri().rstrip('/').casefold()))"
                $ownedEnvironment = $false
                try { & $python -c $ownershipCode 2>$null; $ownedEnvironment = ($LASTEXITCODE -eq 0) }
                catch { $ownedEnvironment = $false }
                if (-not $ownedEnvironment) { throw "Cannot establish ownership of $VenvPath. Choose a new path, e.g. -VenvPath .venv-team. Existing environment preserved." }
            } elseif ((Get-Content -LiteralPath $marker -Raw).Trim() -ne $PSScriptRoot) {
                throw 'Environment marker belongs to another checkout. Choose a new VenvPath.'
            }
        } else {
            Invoke-Checked $launcher ($launcherArgs + @('-m', 'venv', $environmentPath))
            Set-Content -LiteralPath $marker -Value $PSScriptRoot
        }
        Initialize-CudaTorch $python
        Invoke-Checked $python @('-m', 'pip', 'install', '-e', '.[test,ai1,ai3,gemini,db,backend]')
        if ($hasNvidia) {
            try { Invoke-Checked $python @('-m', 'pip', 'install', '-e', '.[slm]') }
            catch {
                $slmInstallFailed = $true
                Write-Warning "Local SLM dependencies could not be installed; Gemini fallback remains usable when configured. $_"
            }
            # Check again after dependency resolution, including the tiny CUDA
            # operation; never silently finish with a CPU-only replacement.
            $status = Test-Torch $python
            if ($status.state -in @('cpu', 'missing')) { throw 'Dependency installation left Torch missing or CPU-only. Action: install CUDA-enabled PyTorch' }
        }
        $artifactArgs = @('-m', 'scripts.setup_artifacts')
        if ($AI1ArtifactZip) { $artifactArgs += @('--zip', $AI1ArtifactZip) }
        Invoke-Checked $python $artifactArgs
        if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }

        if (Get-Command git -ErrorAction SilentlyContinue) {
            $lfsAvailable = $false
            try { & git lfs version 2>$null; $lfsAvailable = ($LASTEXITCODE -eq 0) }
            catch { $lfsAvailable = $false }
            if ($lfsAvailable) {
                $lfsFiles = @(& git lfs ls-files --name-only)
                if ($LASTEXITCODE -ne 0) { throw 'Unable to list tracked LFS files.' }
                $pending = @($lfsFiles | Where-Object {
                    if (-not (Test-Path -LiteralPath $_)) { $true }
                    else {
                        $reader = [IO.File]::OpenRead((Join-Path $PSScriptRoot $_))
                        try {
                            $bytes = New-Object byte[] 128
                            $length = $reader.Read($bytes, 0, 128)
                            $length -eq 0 -or [Text.Encoding]::UTF8.GetString($bytes, 0, $length).StartsWith('version https://git-lfs.github.com/spec/v1')
                        } finally { $reader.Dispose() }
                    }
                })
                if ($pending.Count -gt 0) {
                    try { Invoke-Checked 'git' @('lfs', 'pull', "--include=$($pending -join ',')") }
                    catch { Write-Warning "LFS download failed. Check Git remote access, then run git lfs pull. $_" }
                }
            } else { Write-Warning 'Git LFS missing. Install Git LFS, run git lfs install and git lfs pull to materialize the AI2 adapter.' }
        } else { Write-Warning 'Git missing; install Git and Git LFS to restore the tracked AI2 adapter.' }
    }
    Write-Host 'Recommend AI1_EMBEDDING_DEVICE=cpu alongside Qwen. Local SLM remains opt-in; .env is never overwritten.'
    $pipReady = $true
    try { Invoke-Checked $python @('-m', 'pip', 'check') }
    catch { $pipReady = $false; Write-Warning "Dependency consistency check failed: $_" }
    $reportPath = [IO.Path]::GetTempFileName()
    try {
        & $python 'scripts/preflight.py' '--report-json' $reportPath
        $preflightExit = $LASTEXITCODE
        $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
        if (-not $report) { throw 'Preflight did not produce a capability report.' }
        foreach ($property in $report.PSObject.Properties) {
            if ($property.Name -eq 'Frontend' -and (-not $VerifyOnly -or $SkipFrontend)) { continue }
            $capabilities[$property.Name] = $property.Value
        }
    } finally { Remove-Item -LiteralPath $reportPath -Force }
    if (-not $hasNvidia -or $slmInstallFailed) { $capabilities['Local SLM'] = 'UNAVAILABLE' }
    if (-not $pipReady) { $capabilities['Core Python environment'] = 'FAILED' }
    if (-not $VerifyOnly) {
        Install-Frontend
        if ($WithDatabase) {
            $capabilities['PostgreSQL'] = 'UNAVAILABLE'
            Start-Database $python
            $capabilities['PostgreSQL'] = 'READY'
        } else { Write-Host 'Optional PostgreSQL skipped. Use -WithDatabase to start it; Docker is not required for AI-only setup.' }
    }
    if (-not $pipReady -or $preflightExit -ne 0) { throw 'Setup checks failed. Review the capability summary and diagnostics.' }
    Write-Host "Setup verified. Use $python; see docs/setup.md for activation and offline regression commands."
    Write-Host 'Backend : .\.venv\Scripts\python -m uvicorn backend.main:create_production_app --factory --port 8000'
    Write-Host 'Frontend: cd src\frontend ; npm run dev   (then open http://localhost:3000)'
} finally {
    Write-Host "`nSetup capability summary (READY means setup checks passed, not inference tested):"
    foreach ($entry in $capabilities.GetEnumerator()) { Write-Host "$($entry.Key): $($entry.Value)" }
    Write-Host 'Configure the OpenRouter chain using .env.example. Gemini and local Qwen are optional paths. No API was called.'
    Pop-Location
}
