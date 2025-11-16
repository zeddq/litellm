# Plugin Configuration Backups

These configuration files should be copied to the respective plugin directories AFTER installing the plugins from Obsidian's Community Plugins browser.

## Installation Instructions:

### 1. Install Plugins First (Obsidian GUI)
1. Open Obsidian → Settings → Community Plugins
2. Click "Browse" and search for each plugin:
   - **Pandoc** (by OliverBalfour)
   - **Show Hidden Files** (by polyipseity) - OPTIONAL
   - **Console Debugger** - OPTIONAL
3. Install and Enable each plugin
4. Restart Obsidian

### 2. Copy Configuration Files

After plugins are installed, copy the config files:

```bash
# For Pandoc plugin
cp /Volumes/code/repos/litellm/.obsidian/plugin-configs-backup/obsidian-pandoc-data.json \
   /Volumes/code/repos/litellm/.obsidian/plugins/obsidian-pandoc/data.json

# For Show Hidden Files plugin
cp /Volumes/code/repos/litellm/.obsidian/plugin-configs-backup/show-hidden-files-data.json \
   /Volumes/code/repos/litellm/.obsidian/plugins/show-hidden-files/data.json

# For Console Debugger plugin
cp /Volumes/code/repos/litellm/.obsidian/plugin-configs-backup/console-debugger-data.json \
   /Volumes/code/repos/litellm/.obsidian/plugins/console-debugger/data.json
```

### 3. Restart Obsidian

The plugins will now use the custom configurations with verbose logging enabled.

## What These Configs Do:

- **obsidian-pandoc-data.json**: Configures Pandoc export with mermaid-filter integration
- **show-hidden-files-data.json**: Enables viewing of `.obsidian/` and other hidden files
- **console-debugger-data.json**: Enables verbose debug logging to files

---

**Note**: The configuration files are ready but plugins must be installed first to avoid Obsidian freezing.
