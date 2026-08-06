# CEI Labs Agent - One-Click Installer
# Downloads, reassembles, extracts, and installs the package automatically

$ErrorActionPreference = 'Stop'

# Clear screen for dramatic effect
Clear-Host

# ASCII Art Banner
$banner = @"

 ██████╗███████╗██╗    ██╗      █████╗ ██████╗ ███████╗
██╔════╝██╔════╝██║    ██║     ██╔══██╗██╔══██╗██╔════╝
██║     █████╗  ██║    ██║     ███████║██████╔╝███████╗
██║     ██╔══╝  ██║    ██║     ██╔══██║██╔══██╗╚════██║
╚██████╗███████╗██║    ███████╗██║  ██║██████╔╝███████║
 ╚═════╝╚══════╝╚═╝    ╚══════╝╚═╝  ╚═╝╚═════╝ ╚══════╝

                    AGENT INSTALLER
"@

Write-Host $banner -ForegroundColor Cyan
Write-Host ""
Write-Host "  ═══════════════════════════════════════════════════════════" -ForegroundColor DarkGray
Write-Host ""

$BaseUrl = "https://github.com/Judgernaut777/CEI-Labs-Agent/releases/download/v0.1.0-offline"
$OutputFile = "ctf-agent-offline.tar.gz"
$ExtractDir = "ctf-agent-package"
$Parts = @(
    "ctf-agent-part-aa", "ctf-agent-part-ab", "ctf-agent-part-ac", "ctf-agent-part-ad",
    "ctf-agent-part-ae", "ctf-agent-part-af", "ctf-agent-part-ag", "ctf-agent-part-ah",
    "ctf-agent-part-ai", "ctf-agent-part-aj", "ctf-agent-part-ak", "ctf-agent-part-al",
    "ctf-agent-part-am", "ctf-agent-part-an", "ctf-agent-part-ao", "ctf-agent-part-ap",
    "ctf-agent-part-aq", "ctf-agent-part-ar", "ctf-agent-part-as", "ctf-agent-part-at",
    "ctf-agent-part-au", "ctf-agent-part-av", "ctf-agent-part-aw", "ctf-agent-part-ax",
    "ctf-agent-part-ay", "ctf-agent-part-az", "ctf-agent-part-ba", "ctf-agent-part-bb",
    "ctf-agent-part-bc", "ctf-agent-part-bd", "ctf-agent-part-be", "ctf-agent-part-bf",
    "ctf-agent-part-bg", "ctf-agent-part-bh", "ctf-agent-part-bi", "ctf-agent-part-bj",
    "ctf-agent-part-bk", "ctf-agent-part-bl", "ctf-agent-part-bm", "ctf-agent-part-bn",
    "ctf-agent-part-bo"
)

# Step 1: Download and reassemble
Write-Host "  ┌─────────────────────────────────────────────────────────┐" -ForegroundColor Yellow
Write-Host "  │  STEP 1: DOWNLOADING PACKAGE PARTS                      │" -ForegroundColor Yellow
Write-Host "  └─────────────────────────────────────────────────────────┘" -ForegroundColor Yellow
Write-Host ""
Write-Host "      Preparing to download $($Parts.Count) parts (~3.8 GB total)..." -ForegroundColor Gray
Write-Host "      This may take 5-15 minutes depending on your connection." -ForegroundColor Gray
Write-Host ""

$total = $Parts.Count
$current = 0
$startTime = Get-Date

$output = [System.IO.File]::Create($OutputFile)
try {
    foreach ($part in $Parts) {
        $current++
        $percent = [math]::Round(($current / $total) * 100)
        $url = "$BaseUrl/$part"
        
        # Calculate progress bar
        $barLength = 30
        $filled = [math]::Round(($percent / 100) * $barLength)
        $empty = $barLength - $filled
        $bar = "█" * $filled + "░" * $empty
        
        Write-Host "      ┌──────────────────────────────────────────────────┐" -ForegroundColor DarkGray
        Write-Host "      │  [$bar] $percent%  │" -ForegroundColor Cyan
        Write-Host "      │  Part $current of $total : $part" -ForegroundColor White
        Write-Host "      └──────────────────────────────────────────────────┘" -ForegroundColor DarkGray
        
        try {
            $response = Invoke-WebRequest -Uri $url -Method Get -UseBasicParsing
            $bytes = $response.Content
            $output.Write($bytes, 0, $bytes.Length)
            
            # Calculate download speed
            $elapsed = (Get-Date) - $startTime
            $downloaded = $current * 95MB  # Approximate
            $speed = [math]::Round($downloaded / $elapsed.TotalSeconds / 1MB, 1)
            Write-Host "      Downloaded: $([math]::Round($downloaded / 1GB, 2)) GB | Speed: $speed MB/s" -ForegroundColor Green
            Write-Host ""
        } catch {
            Write-Host "      ✗ ERROR downloading $part : $_" -ForegroundColor Red
            throw
        }
    }
} finally {
    $output.Close()
}

$totalTime = (Get-Date) - $startTime
Write-Host "      ✓ All parts downloaded successfully!" -ForegroundColor Green
Write-Host "      Total time: $($totalTime.Minutes)m $($totalTime.Seconds)s" -ForegroundColor Gray
Write-Host ""

# Step 2: Verify
Write-Host "  ┌─────────────────────────────────────────────────────────┐" -ForegroundColor Yellow
Write-Host "  │  STEP 2: VERIFYING PACKAGE                              │" -ForegroundColor Yellow
Write-Host "  └─────────────────────────────────────────────────────────┘" -ForegroundColor Yellow
Write-Host ""

$fileInfo = Get-Item $OutputFile
$sizeGB = [math]::Round($fileInfo.Length / 1GB, 2)
Write-Host "      Checking file: $OutputFile" -ForegroundColor Gray
Write-Host "      Size: $sizeGB GB" -ForegroundColor Cyan
Write-Host "      ✓ Package verified!" -ForegroundColor Green
Write-Host ""

# Step 3: Extract
Write-Host "  ┌─────────────────────────────────────────────────────────┐" -ForegroundColor Yellow
Write-Host "  │  STEP 3: EXTRACTING PACKAGE                             │" -ForegroundColor Yellow
Write-Host "  └─────────────────────────────────────────────────────────┘" -ForegroundColor Yellow
Write-Host ""

if (Test-Path $ExtractDir) {
    Write-Host "      Removing existing installation..." -ForegroundColor Gray
    Remove-Item -Path $ExtractDir -Recurse -Force
}

Write-Host "      Extracting $OutputFile..." -ForegroundColor Cyan
Write-Host "      This may take 1-2 minutes..." -ForegroundColor Gray

tar -xzf $OutputFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "      ✗ ERROR: Extraction failed" -ForegroundColor Red
    exit 1
}

Write-Host "      ✓ Package extracted to $ExtractDir" -ForegroundColor Green
Write-Host ""

# Step 4: Install
Write-Host "  ┌─────────────────────────────────────────────────────────┐" -ForegroundColor Yellow
Write-Host "  │  STEP 4: RUNNING INSTALLER                              │" -ForegroundColor Yellow
Write-Host "  └─────────────────────────────────────────────────────────┘" -ForegroundColor Yellow
Write-Host ""

$installScript = Join-Path $ExtractDir "install.ps1"
if (Test-Path $installScript) {
    Write-Host "      Launching installer..." -ForegroundColor Cyan
    Write-Host ""
    
    # Run the installer
    & $installScript
} else {
    Write-Host "      ✗ ERROR: Installer not found at $installScript" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  ═══════════════════════════════════════════════════════════" -ForegroundColor DarkGray
Write-Host ""

$completeBanner = @"

 ██████╗ ██████╗ ███╗   ███╗██████╗ ██╗     ███████╗████████╗███████╗
██╔════╝██╔═══██╗████╗ ████║██╔══██╗██║     ██╔════╝╚══██╔══╝██╔════╝
██║     ██║   ██║██╔████╔██║██████╔╝██║     █████╗     ██║   █████╗  
██║     ██║   ██║██║╚██╔╝██║██╔═══╝ ██║     ██╔══╝     ██║   ██╔══╝  
╚██████╗╚██████╔╝██║ ╚═╝ ██║██║     ███████╗███████╗   ██║   ███████╗
 ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚══════╝╚══════╝   ╚═╝   ╚══════╝

              CEI Labs Agent is ready to use!
"@

Write-Host $completeBanner -ForegroundColor Green
Write-Host ""
