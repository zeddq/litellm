# PyCharm Environment Launcher 🚀

Launches PyCharm with environment variables from `.envrc` or `.env` files, making them available to GUI extensions, MCP plugins, and all IDE features.

## Problem Solved

PyCharm launched from macOS dock/Spotlight doesn't inherit environment variables from:
- `.envrc` (direnv)
- `.env` files
- Shell configurations (`.bashrc`, `.zshrc`)

This causes issues with:
- MCP servers needing API keys
- Plugins requiring environment configuration
- Run configurations expecting specific env vars
- IDE-level tools and extensions

## Solution

Launch PyCharm through a shell script that:
1. Loads `.envrc` (via direnv) or `.env` files
2. Exports variables to environment
3. Launches PyCharm with inherited environment
4. Works with GUI applications (proper macOS app launching)

---

## Quick Start

### 1. Run Setup

```bash
cd /Users/cezary/litellm
./setup-pycharm-env.sh
```

This installs:
- `pycharm-env-launcher.sh` → Main launcher
- `pycharm-project-switcher.sh` → Project switcher
- Shell aliases and functions

### 2. Reload Shell

```bash
# Bash
source ~/.bashrc  # or ~/.bash_profile

# Zsh
source ~/.zshrc
```

### 3. Create Environment File

In your project directory:

```bash
# Option A: Create .env file
cat > .env <<EOF
OPENAI_API_KEY=sk-test-key-12345678901234567890
ANTHROPIC_API_KEY=sk-ant-...
CUSTOM_VAR=my_value
DATABASE_URL=postgresql://localhost/mydb
EOF

# Option B: Create .envrc for direnv
cat > .envrc <<EOF
export OPENAI_API_KEY=sk-test-key-12345678901234567890
export ANTHROPIC_API_KEY=sk-ant-...
export CUSTOM_VAR=my_value
EOF

direnv allow
```

### 4. Launch PyCharm

```bash
# From current directory
pycharm-env

# From any directory
pycharm-env ~/path/to/project

# Quick launch current dir
pycharm-here

# Open specific project
pycharm-open ~/my/awesome/project
```

---

## Usage

### Basic Commands

```bash
# Launch PyCharm with environment from current directory
pycharm-env

# Launch with specific project
pycharm-env ~/projects/my-app

# Launch from current directory (shortcut)
pycharm-here

# Open project from anywhere
pycharm-open ~/projects/another-app
```

### Switching Projects

When you want to open a **different** project with **its own** environment variables:

```bash
# This will:
# 1. Close current PyCharm
# 2. Load new project's .env/.envrc
# 3. Relaunch PyCharm with new environment
pycharm-switch ~/projects/other-project
```

**Why?** PyCharm's environment is set at startup. Opening a new project from within PyCharm won't reload env vars. The switcher restarts PyCharm with the new project's environment.

---

## How It Works

### Environment Loading Priority

1. **direnv** (if installed and `.envrc` exists and is allowed)
2. **.env.local** (if exists)
3. **.env** (if exists)
4. System environment (fallback)

### What Gets Access?

✅ **Has access to environment variables:**
- PyCharm IDE itself
- MCP servers and extensions
- Python Console (`Tools → Python Console`)
- Terminal window (`Tools → Terminal`)
- Run configurations
- Debug configurations
- External tools
- All plugins loaded at startup

❌ **Limitations:**
- Variables are loaded at **startup only**
- Opening new projects from GUI won't reload vars (use `pycharm-switch`)
- Changing `.env` requires relaunching PyCharm

---

## Advanced Features

### Logging

All launches are logged to: `~/.pycharm-env-launcher.log`

```bash
# View recent launches
tail -f ~/.pycharm-env-launcher.log
```

### Environment Variable Masking

The launcher automatically masks sensitive values in logs:
- `API_KEY`, `TOKEN`, `SECRET`, `PASSWORD` → Shows only first 10 and last 4 chars
- Example: `OPENAI_API_KEY=sk-test-ke...1234`

### Manual Script Usage

If you don't want aliases, call scripts directly:

```bash
~/bin/pycharm-env-launcher.sh ~/my/project
~/bin/pycharm-project-switcher.sh ~/other/project
```

---

## Integration with PyCharm Features

### EnvFile Plugin (Optional)

For per-run-configuration control:

1. Install: `Settings → Plugins → EnvFile`
2. Configure: `Run → Edit Configurations → EnvFile tab → Enable → Add .env`

**Note:** With the launcher, **this is optional** because env vars are already loaded at IDE level.

### Poetry Integration

Your existing Poetry project will work seamlessly:

```bash
# Launch PyCharm with env
pycharm-env

# In PyCharm terminal (environment is already loaded):
poetry run python your_script.py
```

Environment variables are available to:
- `poetry run` commands
- `poetry shell`
- All Python interpreters

---

## Troubleshooting

### PyCharm doesn't launch

**Check PyCharm installation:**
```bash
# Try manual detection
which charm       # JetBrains Toolbox
which pycharm     # Standalone
ls /Applications/PyCharm*.app  # macOS app bundles
```

**Edit launcher script** if PyCharm is in a custom location:
```bash
nano ~/bin/pycharm-env-launcher.sh
# Modify find_pycharm() function
```

### Environment variables not loading

**Check if .envrc is allowed (direnv):**
```bash
cd /Users/cezary/litellm
direnv status
# If not allowed:
direnv allow
```

**Check .env file format:**
```bash
# Good format:
VARIABLE_NAME=value
ANOTHER_VAR="quoted value"

# Bad format (will be skipped):
export VARIABLE_NAME=value  # Remove 'export'
VARIABLE_NAME = value       # No spaces around =
```

**Test variable loading:**
```bash
cd /Users/cezary/litellm
source ~/bin/pycharm-env-launcher.sh .

# Check if variables are in environment:
echo $OPENAI_API_KEY
```

### MCP extension still can't see variables

**Verify PyCharm was launched via script:**
```bash
# Check log file
tail ~/.pycharm-env-launcher.log

# Should show:
# [INFO] Environment loaded via direnv
# [SUCCESS] PyCharm launched!
```

**Test in PyCharm Python Console:**
```python
import os
print(os.getenv('OPENAI_API_KEY'))  # Should print your key
```

If it works in console but not in MCP, the MCP server might need restart:
1. Close PyCharm completely
2. Relaunch with `pycharm-env`
3. Check MCP server status in IDE

### Switching projects doesn't work

**Check if osascript works:**
```bash
osascript -e 'tell application "PyCharm" to quit'
```

**If error, try force kill:**
```bash
pkill -f PyCharm
pycharm-env ~/new/project
```

---

## Security Best Practices

### Protecting Secrets

```bash
# Add .env to .gitignore (IMPORTANT!)
echo ".env" >> .gitignore
echo ".env.local" >> .gitignore

# Commit .env.example instead
cat > .env.example <<EOF
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
CUSTOM_VAR=example_value
EOF

git add .env.example
git commit -m "Add environment template"
```

### Team Setup

1. **Share** `.env.example` (committed to git)
2. **Don't share** `.env` (in .gitignore)
3. **Document** required variables in README

```bash
# New team member setup:
cp .env.example .env
# Edit .env with real values
nano .env
```

---

## Uninstallation

```bash
# Remove scripts
rm ~/bin/pycharm-env-launcher.sh
rm ~/bin/pycharm-project-switcher.sh
rm ~/bin/pycharm-env-wrapper-for-automator.sh

# Remove aliases from shell config
# Edit and remove the PyCharm Environment Launcher section:
nano ~/.zshrc  # or ~/.bashrc

# Remove log file
rm ~/.pycharm-env-launcher.log
```

---

## Files Created

```
~/bin/
├── pycharm-env-launcher.sh        # Main launcher
├── pycharm-project-switcher.sh    # Project switcher
└── pycharm-env-wrapper-for-automator.sh  # macOS app wrapper

~/.pycharm-env-launcher.log         # Launch logs

Your shell config (~/.zshrc or ~/.bashrc):
└── Aliases and functions added
```

---

## FAQ

### Q: Do I need direnv?

**No**, but it's recommended. The launcher works with:
- `.envrc` + direnv (preferred)
- `.env` files (automatic fallback)
- Both (direnv takes precedence)

### Q: Will this work on Linux?

**Yes**, the scripts detect the OS and adapt. On Linux:
- Uses `pkill` instead of `osascript`
- Works with PyCharm installed via Toolbox, Snap, or .tar.gz

### Q: Can I use this with other JetBrains IDEs?

**Yes**, you can modify the scripts to support:
- IntelliJ IDEA
- WebStorm
- DataGrip
- etc.

Just change the app name in `find_pycharm()` and `close_pycharm()` functions.

### Q: What about Windows?

**Not currently supported**. The scripts are written for macOS/Linux. For Windows:
- Use PowerShell version (contribution welcome!)
- Set environment variables in system settings
- Use PyCharm's built-in EnvFile plugin

### Q: Does this affect other PyCharm instances?

**No**, each launch is independent. If you:
1. Launch `pycharm-env ~/project1`
2. Launch `pycharm-env ~/project2` (separate instance)

Each will have its own project's environment variables.

---

## Contributing

Found a bug or want to improve? The scripts are in:
- `/Users/cezary/litellm/pycharm-env-launcher.sh`
- `/Users/cezary/litellm/pycharm-project-switcher.sh`
- `/Users/cezary/litellm/setup-pycharm-env.sh`

---

## Credits

Created to solve the "PyCharm GUI can't see my environment variables" problem.

Inspired by:
- direnv project
- JetBrains Toolbox CLI
- The pain of debugging MCP servers 😅

---

## Support

If you need help:
1. Check logs: `~/.pycharm-env-launcher.log`
2. Test manually: `~/bin/pycharm-env-launcher.sh .`
3. Verify environment: `env | grep API_KEY`

Happy coding! 🎉
