#!/bin/bash
# Install launchd job for daily Kimi Subconscious consolidation

PLIST_SOURCE="$(dirname "$0")/com.kimisub.consolidate.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.kimisub.consolidate.plist"

echo "Installing Kimi Subconscious consolidation schedule..."

# Check if kimisub is in PATH
if ! command -v kimisub &> /dev/null; then
    echo "Error: kimisub not found in PATH"
    echo "Please ensure kimisub is installed and in your PATH before installing the schedule"
    exit 1
fi

# Copy plist
cp "$PLIST_SOURCE" "$PLIST_DEST"

# Update path to kimisub in plist
KIMISUB_PATH=$(which kimisub)
sed -i '' "s|/usr/local/bin/kimisub|$KIMISUB_PATH|g" "$PLIST_DEST"

# Load the job
launchctl load "$PLIST_DEST"

echo "Installed: $PLIST_DEST"
echo "Consolidation will run daily at 1:00 AM"
echo ""
echo "To verify it's loaded:"
echo "  launchctl list | grep kimisub"
echo ""
echo "To uninstall:"
echo "  launchctl unload $PLIST_DEST"
echo "  rm $PLIST_DEST"
