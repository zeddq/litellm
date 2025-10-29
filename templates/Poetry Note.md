---
created: <% tp.date.now("YYYY-MM-DD HH:mm") %>
project: <% await tp.user.poetry_helper(tp).project_name() %>
tags: [python, poetry]
---

# <% tp.file.title %>

<%*
const info = await tp.user.poetry_helper(tp).info();

if (info.success) {
    tR += `> **Poetry Project**: ${info.projectName}\n`;
    tR += `> **Location**: \`${info.projectDir}\`\n\n`;
} else {
    tR += `> ⚠️ **Warning**: ${info.error}\n\n`;
}
_%>

## Setup

```python {pre}
<% await tp.user.poetry_helper(tp).setup_code() %>
```

## Code

```python
# Your Poetry packages are available here!
import sys
print(f"Python: {sys.executable}")

# Example: use your project packages
try:
    import pandas as pd
    print(f"✓ Pandas: {pd.__version__}")
except ImportError as e:
    print(f"✗ Import failed: {e}")
```

## Notes

- Write your notes here
- Code blocks below will use the Poetry venv automatically
