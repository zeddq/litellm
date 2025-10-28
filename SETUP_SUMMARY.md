# PyCharm Environment Launcher - Setup Summary

## ✅ Files Created

### Main Scripts
1. **pycharm-env-launcher.sh** - Main launcher that loads environment variables
2. **pycharm-project-switcher.sh** - Closes PyCharm and reopens with new project's environment
3. **setup-pycharm-env.sh** - Automated installation script
4. **test-env-launcher.sh** - Test script to verify setup

### Documentation
5. **PYCHARM_ENV_LAUNCHER_README.md** - Complete usage guide
6. **SETUP_SUMMARY.md** - This file
7. **.env.example** - Template for environment variables

### Configuration Updates
8. **.gitignore** - Updated to exclude .env files from git

---

## 🚀 Quick Start Guide

### Step 1: Run Setup Script

```bash
cd /Users/cezary/litellm
./setup-pycharm-env.sh
```

This will:
- Copy scripts to `~/bin/`
- Add shell aliases to your `.zshrc` or `.bashrc`
- Make everything executable
- Create helper functions

### Step 2: Reload Your Shell

```bash
# For Zsh (macOS default)
source ~/.zshrc

# For Bash
source ~/.bashrc
```

### Step 3: Create Your .env File

```bash
# Copy the example
cp .env.example .env

# Edit with your real values
nano .env
```

Example `.env` content:
```bash
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here
OPENAI_API_KEY=sk-your-actual-key-here
CUSTOM_VAR=my_value
```

**Important:** `.env` is in `.gitignore` so your secrets won't be committed!

### Step 4: Test the Setup (Optional)

```bash
./test-env-launcher.sh
```

Should output:
```
✓ Found .env file
✓ Environment variables detected
✓ Test PASSED!
```

### Step 5: Launch PyCharm

```bash
# From current directory
pycharm-env

# Or specify a path
pycharm-env /Users/cezary/litellm
```

---

## 📋 Available Commands After Setup

| Command | Description |
|---------|-------------|
| `pycharm-env` | Launch PyCharm with environment from current dir |
| `pycharm-env ~/path` | Launch PyCharm with specific project |
| `pycharm-here` | Quick shortcut for current directory |
| `pycharm-open ~/path` | Open project from anywhere |
| `pycharm-switch ~/path` | Close & reopen with new project's env |

---

## 🔧 How It Solves Your Problem

### Before
- PyCharm launched from GUI (dock/Spotlight) doesn't see environment variables
- MCP extensions can't access `ANTHROPIC_API_KEY`
- Plugins fail due to missing env vars
- Run configurations need manual env var setup

### After
- Launch PyCharm with: `pycharm-env`
- All environment variables loaded at startup
- MCP extensions have access to env vars
- Plugins work correctly
- Run configurations inherit env vars automatically

---

## 🎯 Special Feature: Project Switching

**Problem:** You have multiple projects with different environment variables.

**Solution:** Use the project switcher!

```bash
# Working on project A
pycharm-env ~/projects/project-a

# Want to switch to project B?
pycharm-switch ~/projects/project-b
```

This will:
1. Close the current PyCharm instance
2. Load environment from `~/projects/project-b/.env` or `.envrc`
3. Relaunch PyCharm with new environment
4. All plugins/MCP get the new project's env vars

---

## 📦 Integration with Your Existing Setup

### Works With
- ✅ **Poetry** - Your existing `poetry.lock` and `pyproject.toml`
- ✅ **direnv** - If you have `.envrc`, it's loaded first
- ✅ **.env files** - Fallback if direnv not available
- ✅ **EnvFile plugin** - Still works for per-config overrides
- ✅ **JetBrains Toolbox** - Detects `charm` command
- ✅ **Standalone PyCharm** - Detects app bundle

### Your Current Project Structure
```
/Users/cezary/litellm/
├── .envrc                          # Already exists (currently commented)
├── .env.example                    # ✨ NEW - Template
├── .env                            # ✨ CREATE THIS (git-ignored)
├── pycharm-env-launcher.sh         # ✨ NEW
├── pycharm-project-switcher.sh     # ✨ NEW
├── setup-pycharm-env.sh            # ✨ NEW
├── test-env-launcher.sh            # ✨ NEW
├── config.yaml
├── poetry.lock
├── pyproject.toml
└── ... your project files
```

---

## 🔐 Security Best Practices

### ✅ DO
- Keep real secrets in `.env` (git-ignored)
- Commit `.env.example` with dummy values
- Use project switcher for multi-project work
- Check `~/.pycharm-env-launcher.log` if issues occur

### ❌ DON'T
- Don't commit `.env` to git (it's already in .gitignore)
- Don't put real API keys in `.envrc` without securing it
- Don't share your `.env` file with others

---

## 🐛 Troubleshooting

### PyCharm doesn't launch
```bash
# Check which PyCharm you have
which charm || which pycharm || ls /Applications/PyCharm*.app

# Test manually
/Applications/PyCharm.app/Contents/MacOS/pycharm .
```

### Environment variables not loaded
```bash
# Check .env format (no spaces around =, no 'export')
cat .env

# Test loading manually
cd /Users/cezary/litellm
source <(grep -v '^#' .env | sed 's/^/export /')
echo $ANTHROPIC_API_KEY
```

### direnv issues
```bash
# Allow .envrc
direnv allow

# Check status
direnv status
```

### Logs
```bash
# View launcher logs
tail -f ~/.pycharm-env-launcher.log
```

---

## 📖 Next Steps

1. ✅ Run `./setup-pycharm-env.sh`
2. ✅ Reload shell: `source ~/.zshrc`
3. ✅ Create `.env` from `.env.example`
4. ✅ Test: `./test-env-launcher.sh`
5. ✅ Launch: `pycharm-env`
6. ✅ Verify in PyCharm Python Console:
   ```python
   import os
   print(os.getenv('ANTHROPIC_API_KEY'))
   ```

---

## 📚 Full Documentation

See **PYCHARM_ENV_LAUNCHER_README.md** for complete documentation including:
- Advanced features
- macOS Automator app creation
- Linux support
- Customization options
- Uninstallation instructions

---

## 🎉 You're All Set!

Your PyCharm will now have access to environment variables for all GUI extensions and MCP plugins!

**Need help?** Check the logs at `~/.pycharm-env-launcher.log`
