# Kimi Subconscious - Quick Start

## Installation

```bash
cd /Users/ikornii/Documents/_ai-warehouse/kimi-subconscious
pip install -e .
```

## First-Time Setup

```bash
# 1. Configure with your Letta API key
kimisub setup

# 2. Install daily consolidation schedule (1 AM)
./scripts/install-launchd.sh

# 3. Enable Phoenix mode (auto-restart)
kimisub phoenix enable
```

## Daily Usage

### 🚀 Option A: KIMISABE (Recommended)

One command to rule them all:

```bash
# Launch daemon + Kimi with full memory integration
kimisabe

# Work normally. When you say "remember this..."
# Kimi auto-restarts with new context (using --continue, no data loss).

# When done for the day
kimisend
```

### Option B: Manual Control

```bash
# Start daemon separately
kimisub daemon start

# Use Kimi normally in another terminal
kimi

# Stop daemon when done
kimisub daemon stop
```

### Option C: One-shot Sync

```bash
# When you want to sync memories manually
kimisub sync

# Or for daily consolidation
kimisub consolidate
```

## The "I Know Kung-Fu" Flow

```bash
# Terminal 1: Start daemon
$ kimisub daemon --start

# Terminal 2: Use Kimi
$ cd ~/my-project
$ kimi

Kimi> Hello! How can I help?

You> Remember: I always want explicit type annotations

Kimi> Got it.

[... daemon detects insight, sends to Letta ...]
[... guidance arrives, Phoenix triggers ...]

[Kimisub] Restarting Kimi with new context: Memory updated

# Kimi auto-restarts

Kimi> Session continued. Note from Subconscious:
Kimi> "Tracking: explicit type annotation preference"

You> 🕶️
```

## Commands

| Command | Description |
|---------|-------------|
| `kimisabe` | 🚀 **Start daemon + launch Kimi** (one command) |
| `kimisend` | Stop daemon at end of day |
| `kimisub setup` | Configure API key and import agent |
| `kimisub sync` | Manual sync of current project |
| `kimisub consolidate` | Daily memory consolidation |
| `kimisub daemon start` | Start background watcher |
| `kimisub daemon stop` | Stop background watcher |
| `kimisub phoenix enable` | Enable auto-restart mode |
| `kimisub phoenix disable` | Disable auto-restart |
| `kimisub guidance` | View current SUBCONSCIOUS.md |
| `kimisub status` | Show project status |
| `kimisub config` | Show configuration |

## What Gets Remembered

The daemon automatically detects:

- **Explicit**: "remember", "don't forget", "important"
- **Corrections**: "no", "wrong", "actually"
- **Errors**: 3+ tool failures in a row
- **Hotspots**: Same file edited 3+ times
- **Breakthroughs**: "finally", "works!", "figured it out"

## Files

- `SUBCONSCIOUS.md` - Injected into Kimi at session start
- `~/.kimi-subconscious/` - State storage
- `~/.kimi/sessions/` - Kimi's session data (read-only)

## Troubleshooting

**"kimisub: command not found"**
```bash
# Make sure pip install location is in PATH
export PATH="$HOME/.local/bin:$PATH"
```

**"No Letta API key"**
```bash
kimisub setup
```

**"Daemon not syncing"**
```bash
# Check if daemon is running
kimisub daemon --status

# Check logs
ls ~/Library/Application\ Support/kimi-subconscious/
```

**"Phoenix not restarting"**
```bash
# Make sure it's enabled
kimisub config  # Check "Phoenix Mode"

# Restart daemon after enabling
kimisub daemon --stop
kimisub daemon --start
```

## Uninstall

```bash
# Remove launchd job
launchctl unload ~/Library/LaunchAgents/com.kimisub.consolidate.plist
rm ~/Library/LaunchAgents/com.kimisub.consolidate.plist

# Uninstall package
pip uninstall kimi-subconscious

# Remove data (optional)
rm -rf ~/Library/Application\ Support/kimi-subconscious/
```
