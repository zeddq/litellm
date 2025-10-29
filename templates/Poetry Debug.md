# Poetry Setup Debug

## System Information

```python
import sys
import os
import platform
from pathlib import Path

print("=" * 70)
print("SYSTEM INFORMATION")
print("=" * 70)

print(f"\nPlatform: {platform.platform()}")
print(f"Python: {sys.version}")
print(f"Executable: {sys.executable}")
print(f"Prefix: {sys.prefix}")
print(f"Base Prefix: {sys.base_prefix}")

# Check if in venv
in_venv = sys.prefix != sys.base_prefix
print(f"\nIn virtualenv: {in_venv}")

print(f"\nCurrent directory: {os.getcwd()}")
print(f"\nPATH entries:")
for i, p in enumerate(os.environ.get('PATH', '').split(os.pathsep)[:5], 1):
    print(f"  {i}. {p}")

print(f"\nPYTHONPATH entries:")
for i, p in enumerate(sys.path[:10], 1):
    print(f"  {i}. {p}")
```

## Poetry Detection

<%*
const info = await tp.user.poetry_helper(tp).info();
tR += "```json\n";
tR += JSON.stringify(info, null, 2);
tR += "\n```\n";
_%>

## Find Poetry Executable

```python
import subprocess
import sys
from pathlib import Path

print("=" * 70)
print("POETRY DETECTION")
print("=" * 70)

# Check common locations
locations = []

if sys.platform == "win32":
    locations = [
        Path.home() / "AppData/Roaming/Python/Python311/Scripts/poetry.exe",
        Path.home() / "AppData/Roaming/Python/Python310/Scripts/poetry.exe",
        Path("C:/Program Files/Python311/Scripts/poetry.exe"),
    ]
else:
    locations = [
        Path("/usr/local/bin/poetry"),
        Path("/opt/homebrew/bin/poetry"),
        Path.home() / ".local/bin/poetry",
        Path.home() / ".poetry/bin/poetry",
    ]

print("\nChecking common Poetry locations:")
found = []
for loc in locations:
    exists = loc.exists()
    symbol = "✓" if exists else "✗"
    print(f"  {symbol} {loc}")
    if exists:
        found.append(loc)

# Check PATH
print("\nChecking PATH:")
cmd = "where" if sys.platform == "win32" else "which"
try:
    result = subprocess.run(
        [cmd, "poetry"],
        capture_output=True,
        text=True,
        timeout=5
    )
    if result.returncode == 0:
        print(f"  ✓ Found in PATH: {result.stdout.strip()}")
        found.append(Path(result.stdout.strip()))
    else:
        print(f"  ✗ Not found in PATH")
except Exception as e:
    print(f"  ✗ Error checking PATH: {e}")

if found:
    print(f"\n✓ Poetry found at {len(found)} location(s)")
    print(f"  Using: {found[0]}")
else:
    print("\n✗ Poetry not found!")
    print("  Install from: https://python-poetry.org/docs/#installation")
```

## Find Poetry Project

```python
from pathlib import Path

print("=" * 70)
print("POETRY PROJECT DETECTION")
print("=" * 70)

# Get note path
note_path = Path(@note_path)
print(f"\nNote path: {note_path}")

# Search for pyproject.toml
print("\nSearching for pyproject.toml:")
current = note_path.parent
found_project = None

for level in range(15):
    pyproject = current / "pyproject.toml"
    indent = "  " * level
    
    if pyproject.exists():
        # Check if it's a Poetry project
        content = pyproject.read_text()
        is_poetry = "[tool.poetry]" in content
        
        if is_poetry:
            print(f"{indent}✓ {current} (Poetry project)")
            found_project = current
            break
        else:
            print(f"{indent}⚠ {current} (not Poetry)")
    else:
        print(f"{indent}✗ {current}")
    
    parent = current.parent
    if parent == current:
        print(f"{indent}  (reached filesystem root)")
        break
    current = parent

if found_project:
    print(f"\n✓ Poetry project found: {found_project}")
    
    # Read project info
    pyproject = found_project / "pyproject.toml"
    content = pyproject.read_text()
    
    import re
    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
    version_match = re.search(r'version\s*=\s*"([^"]+)"', content)
    
    if name_match:
        print(f"  Name: {name_match.group(1)}")
    if version_match:
        print(f"  Version: {version_match.group(1)}")
else:
    print("\n✗ No Poetry project found in directory tree")
```

## Test Poetry Command

```python
import subprocess
from pathlib import Path

print("=" * 70)
print("POETRY COMMAND TEST")
print("=" * 70)

# Find poetry (reuse code from above)
poetry_path = None
locations = [
    Path("/usr/local/bin/poetry"),
    Path.home() / ".local/bin/poetry",
]

for loc in locations:
    if loc.exists():
        poetry_path = loc
        break

if not poetry_path:
    print("✗ Poetry not found")
else:
    print(f"✓ Using Poetry: {poetry_path}")
    
    # Try to get venv info
    if found_project:
        print(f"\nRunning: poetry env info --path")
        print(f"  In directory: {found_project}")
        
        try:
            result = subprocess.run(
                [str(poetry_path), "env", "info", "--path"],
                cwd=str(found_project),
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                venv_path = result.stdout.strip()
                print(f"\n✓ Venv found: {venv_path}")
                
                # Check Python
                if sys.platform == "win32":
                    python_path = Path(venv_path) / "Scripts" / "python.exe"
                else:
                    python_path = Path(venv_path) / "bin" / "python"
                
                print(f"  Python: {python_path}")
                print(f"  Exists: {python_path.exists()}")
                
            else:
                print(f"\n✗ Poetry command failed:")
                print(f"  Error: {result.stderr}")
        except Exception as e:
            print(f"\n✗ Error running Poetry: {e}")
    else:
        print("\n⚠ No project found, skipping venv check")
```

## Recommendations

```python
print("=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)

recommendations = []

# Check if Poetry is installed
if not found:
    recommendations.append("📦 Install Poetry: https://python-poetry.org/docs/#installation")

# Check if project exists
if not found_project:
    recommendations.append("📁 Create Poetry project: cd to desired directory and run 'poetry init'")

# Check if venv exists
elif poetry_path and found_project:
    try:
        result = subprocess.run(
            [str(poetry_path), "env", "info", "--path"],
            cwd=str(found_project),
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            recommendations.append(f"🔧 Initialize venv: cd {found_project} && poetry install")
    except:
        pass

if not recommendations:
    recommendations.append("✓ Everything looks good!")
    recommendations.append("💡 Use 'Poetry Note' template for new notes")

for rec in recommendations:
    print(f"\n{rec}")
```
