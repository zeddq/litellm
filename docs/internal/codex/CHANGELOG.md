# Changelog

## [1.3.0] - 2025-11-16

### Fixed
- **Poetry 2.x Compatibility**: Removed `--no-update` flag which doesn't exist in Poetry 2.2.1+
- Lock file regeneration now deletes old lock file before regenerating for clean state
- Updated both `setup_poetry_mirrors.sh` and `fixed_setup_poetry.sh`

### Changed
- Lock file handling now uses `rm -f poetry.lock && poetry lock` instead of `poetry lock --no-update`
- Updated documentation to reflect Poetry 2.x compatibility
- Improved error messages during lock file regeneration

## [1.2.0] - 2025-11-16

### Fixed
- **Lock File Handling**: Added automatic lock file regeneration when out of sync
- Scripts now check `poetry check --lock` before installing
- Automatically runs `poetry lock --no-update` if lock file is stale
- Prevents "pyproject.toml changed significantly" error

### Changed
- Both `setup_poetry_mirrors.sh` and `fixed_setup_poetry.sh` now validate lock files
- Better error messages for lock file issues

## [1.1.0] - 2025-11-16

### Fixed
- **Poetry 2.2.1 Compatibility**: Removed `installer.modern-installation` setting that doesn't exist in Poetry 2.2.1
- Changed to use `installer.parallel false` instead for better compatibility
- Added `2>/dev/null || true` to all Poetry config commands for graceful error handling
- Updated all three scripts: `setup_poetry_mirrors.sh`, `fixed_setup_poetry.sh`, and `diagnose_poetry_ssl.sh`

### Changed
- All Poetry config commands now fail gracefully if settings don't exist
- Improved error handling in orchestrator script

## [1.0.0] - 2025-11-16

### Added
- Initial release with comprehensive Poetry setup for Codex Universal Docker
- **setup.sh**: Smart orchestrator that tries multiple approaches
- **fixed_setup_poetry.sh**: SSL patching approach for Python 3.13+
- **setup_poetry_mirrors.sh**: PyPI mirror approach (Aliyun, Tencent, Tsinghua, Douban)
- **diagnose_poetry_ssl.sh**: Comprehensive diagnostic tool
- **test_ssl_patch.py**: SSL verification testing
- Full documentation (README.md, QUICK_START.md, INTEGRATION_EXAMPLE.md)

### Features
- Automatic MITM proxy detection
- Python 3.13+ SSL verification flag handling (VERIFY_X509_STRICT, VERIFY_X509_PARTIAL_CHAIN)
- Smart fallback strategies
- Mirror accessibility testing
- Comprehensive error reporting
- Poetry 1.x and 2.x compatibility

---

**Note**: All scripts are tested with Poetry 2.2.1 and Python 3.13.8
