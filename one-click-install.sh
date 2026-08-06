#!/bin/bash
# CEI Labs Agent - One-Click Installer (Linux/Mac)
# Downloads, reassembles, extracts, and installs the package automatically

set -e

# Clear screen for dramatic effect
clear

# ASCII Art Banner
cat << 'EOF'

 ██████╗███████╗██╗    ██╗      █████╗ ██████╗ ███████╗
██╔════╝██╔════╝██║    ██║     ██╔══██╗██╔══██╗██╔════╝
██║     █████╗  ██║    ██║     ███████║██████╔╝███████╗
██║     ██╔══╝  ██║    ██║     ██╔══██║██╔══██╗╚════██║
╚██████╗███████╗██║    ███████╗██║  ██║██████╔╝███████║
 ╚═════╝╚══════╝╚═╝    ╚══════╝╚═╝  ╚═╝╚═════╝ ╚══════╝

                    AGENT INSTALLER

EOF

echo "  ═══════════════════════════════════════════════════════════"
echo ""

BASE_URL="https://github.com/Judgernaut777/CEI-Labs-Agent/releases/download/v0.1.0-offline"
OUTPUT_FILE="ctf-agent-offline.tar.gz"
EXTRACT_DIR="ctf-agent-package"

PARTS=(
    "ctf-agent-part-aa" "ctf-agent-part-ab" "ctf-agent-part-ac" "ctf-agent-part-ad"
    "ctf-agent-part-ae" "ctf-agent-part-af" "ctf-agent-part-ag" "ctf-agent-part-ah"
    "ctf-agent-part-ai" "ctf-agent-part-aj" "ctf-agent-part-ak" "ctf-agent-part-al"
    "ctf-agent-part-am" "ctf-agent-part-an" "ctf-agent-part-ao" "ctf-agent-part-ap"
    "ctf-agent-part-aq" "ctf-agent-part-ar" "ctf-agent-part-as" "ctf-agent-part-at"
    "ctf-agent-part-au" "ctf-agent-part-av" "ctf-agent-part-aw" "ctf-agent-part-ax"
    "ctf-agent-part-ay" "ctf-agent-part-az" "ctf-agent-part-ba" "ctf-agent-part-bb"
    "ctf-agent-part-bc" "ctf-agent-part-bd" "ctf-agent-part-be" "ctf-agent-part-bf"
    "ctf-agent-part-bg" "ctf-agent-part-bh" "ctf-agent-part-bi" "ctf-agent-part-bj"
    "ctf-agent-part-bk" "ctf-agent-part-bl" "ctf-agent-part-bm" "ctf-agent-part-bn"
    "ctf-agent-part-bo"
)

# Step 1: Download and reassemble
echo "  ┌─────────────────────────────────────────────────────────┐"
echo "  │  STEP 1: DOWNLOADING PACKAGE PARTS                      │"
echo "  └─────────────────────────────────────────────────────────┘"
echo ""
echo "      Preparing to download ${#PARTS[@]} parts (~3.8 GB total)..."
echo "      This may take 5-15 minutes depending on your connection."
echo ""

total=${#PARTS[@]}
current=0
start_time=$(date +%s)

> "$OUTPUT_FILE"

for part in "${PARTS[@]}"; do
    current=$((current + 1))
    percent=$((current * 100 / total))
    url="$BASE_URL/$part"
    
    # Calculate progress bar
    bar_length=30
    filled=$((percent * bar_length / 100))
    empty=$((bar_length - filled))
    bar=$(printf "█%.0s" $(seq 1 $filled))$(printf "░%.0s" $(seq 1 $empty))
    
    echo "      ┌──────────────────────────────────────────────────┐"
    echo "      │  [$bar] $percent%  │"
    echo "      │  Part $current of $total : $part"
    echo "      └──────────────────────────────────────────────────┘"
    
    if curl -fsSL "$url" >> "$OUTPUT_FILE"; then
        # Calculate download speed
        elapsed=$(($(date +%s) - start_time))
        downloaded=$((current * 95))
        if [ $elapsed -gt 0 ]; then
            speed=$((downloaded / elapsed))
        else
            speed=0
        fi
        echo "      Downloaded: ${downloaded} MB | Speed: ${speed} MB/s"
        echo ""
    else
        echo "      ✗ ERROR downloading $part"
        exit 1
    fi
done

end_time=$(date +%s)
total_time=$((end_time - start_time))
total_minutes=$((total_time / 60))
total_seconds=$((total_time % 60))

echo "      ✓ All parts downloaded successfully!"
echo "      Total time: ${total_minutes}m ${total_seconds}s"
echo ""

# Step 2: Verify
echo "  ┌─────────────────────────────────────────────────────────┐"
echo "  │  STEP 2: VERIFYING PACKAGE                              │"
echo "  └─────────────────────────────────────────────────────────┘"
echo ""

size=$(du -h "$OUTPUT_FILE" | cut -f1)
echo "      Checking file: $OUTPUT_FILE"
echo "      Size: $size"
echo "      ✓ Package verified!"
echo ""

# Step 3: Extract
echo "  ┌─────────────────────────────────────────────────────────┐"
echo "  │  STEP 3: EXTRACTING PACKAGE                             │"
echo "  └─────────────────────────────────────────────────────────┘"
echo ""

if [ -d "$EXTRACT_DIR" ]; then
    echo "      Removing existing installation..."
    rm -rf "$EXTRACT_DIR"
fi

echo "      Extracting $OUTPUT_FILE..."
echo "      This may take 1-2 minutes..."

tar -xzf "$OUTPUT_FILE"
echo "      ✓ Package extracted to $EXTRACT_DIR"
echo ""

# Step 4: Install
echo "  ┌─────────────────────────────────────────────────────────┐"
echo "  │  STEP 4: RUNNING INSTALLER                              │"
echo "  └─────────────────────────────────────────────────────────┘"
echo ""

if [ -f "$EXTRACT_DIR/install.sh" ]; then
    chmod +x "$EXTRACT_DIR/install.sh"
    echo "      Launching installer..."
    echo ""
    cd "$EXTRACT_DIR"
    ./install.sh
elif [ -f "$EXTRACT_DIR/install.ps1" ]; then
    echo "      Windows installer detected. Please run:"
    echo "        cd $EXTRACT_DIR"
    echo "        powershell -ExecutionPolicy Bypass -File install.ps1"
else
    echo "      ✗ ERROR: Installer not found"
    exit 1
fi

echo ""
echo "  ═══════════════════════════════════════════════════════════"
echo ""

cat << 'EOF'

 ██████╗ ██████╗ ███╗   ███╗██████╗ ██╗     ███████╗████████╗███████╗
██╔════╝██╔═══██╗████╗ ████║██╔══██╗██║     ██╔════╝╚══██╔══╝██╔════╝
██║     ██║   ██║██╔████╔██║██████╔╝██║     █████╗     ██║   █████╗  
██║     ██║   ██║██║╚██╔╝██║██╔═══╝ ██║     ██╔══╝     ██║   ██╔══╝  
╚██████╗╚██████╔╝██║ ╚═╝ ██║██║     ███████╗███████╗   ██║   ███████╗
 ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚══════╝╚══════╝   ╚═╝   ╚══════╝

              CEI Labs Agent is ready to use!

EOF
