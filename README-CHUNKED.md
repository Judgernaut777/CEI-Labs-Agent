# CEI Labs Agent - Chunked Distribution

This directory contains the CEI Labs Agent offline package split into 41 parts for distribution via GitHub.

## Quick Start (One-Click)

### Windows (PowerShell)
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
irm https://raw.githubusercontent.com/Judgernaut777/CEI-Labs-Agent/main/one-click-install.ps1 | iex
```

**Note:** The `Set-ExecutionPolicy` command is required on most Windows systems to allow running PowerShell scripts. This is a one-time setting per user.

### Linux/Mac (Bash)
```bash
curl -fsSL https://raw.githubusercontent.com/Judgernaut777/CEI-Labs-Agent/main/one-click-install.sh | bash
```

The one-click installer will:
1. Download all 41 package parts (~3.8 GB)
2. Reassemble into `ctf-agent-offline.tar.gz`
3. Extract the package
4. Run the installer automatically

## For Distributors (Uploading to GitHub)

Upload these files to a GitHub Release:

1. All `ctf-agent-part-*` files (41 parts, ~95MB each)
2. `ctf-agent-manifest.txt` (checksums)
3. `one-click-install.ps1` (Windows)
4. `one-click-install.sh` (Linux/Mac)
5. `README-CHUNKED.md` (this file)

**Recommended release settings:**
- Tag: `v0.1.0-offline`
- Title: `Offline Package - One-Click Installer`

## Manual Download (Alternative)

If you prefer to download manually:

1. Download all `ctf-agent-part-*` files
2. Reassemble:
   - **Windows**: `Get-Content ctf-agent-part-* -Raw | Set-Content ctf-agent-offline.tar.gz -NoNewline`
   - **Linux/Mac**: `cat ctf-agent-part-* > ctf-agent-offline.tar.gz`
3. Extract: `tar -xzf ctf-agent-offline.tar.gz`
4. Install: `cd ctf-agent-package && ./install.ps1` (Windows) or `./install.sh` (Linux/Mac)

## Verification

Verify the reassembled file:
```bash
sha256sum ctf-agent-offline.tar.gz
```

Expected size: ~3.8 GB

## Contents

| File | Description |
|------|-------------|
| `ctf-agent-part-aa` through `bo` | Package parts (41 files) |
| `ctf-agent-manifest.txt` | SHA256 checksums |
| `one-click-install.ps1` | Windows one-click installer |
| `one-click-install.sh` | Linux/Mac one-click installer |
| `README-CHUNKED.md` | This file |

## Support

For issues, see: https://github.com/Judgernaut777/CEI-Labs-Agent
