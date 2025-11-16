---
title: "Mermaid Export Test Document"
date: 2025-11-16
author: "Obsidian Export System"
tags: [test, mermaid, export]
---

# Mermaid Export Test Document

This document contains various Mermaid diagram types to test the export pipeline.

## 1. Flowchart

```mermaid
flowchart TD
    Start([Start Export]) --> Detect[Detect Client]
    Detect --> Parse[Parse Markdown]
    Parse --> FindMermaid{Mermaid<br/>Diagrams?}
    FindMermaid -->|Yes| Render[Render with<br/>mermaid-filter]
    FindMermaid -->|No| Skip[Skip Rendering]
    Render --> Embed[Embed Images]
    Skip --> Export[Generate Output]
    Embed --> Export
    Export --> Success([Export Complete])

    style Start fill:#4A90E2,color:#fff
    style Success fill:#7CB342,color:#fff
    style FindMermaid fill:#FF7043,color:#fff
```

**Expected**: Flowchart with colored nodes showing export pipeline

---

## 2. Sequence Diagram

```mermaid
sequenceDiagram
    participant User
    participant Obsidian
    participant Pandoc
    participant MermaidFilter
    participant Output

    User->>Obsidian: Trigger Export (Cmd+P)
    Obsidian->>Pandoc: Send Markdown + Config
    Pandoc->>MermaidFilter: Process Mermaid Blocks

    loop For Each Diagram
        MermaidFilter->>MermaidFilter: Parse Syntax
        MermaidFilter->>MermaidFilter: Render to PNG
        MermaidFilter->>Pandoc: Return Image Path
    end

    Pandoc->>Output: Generate Final Document
    Output-->>User: Display/Save Result

    Note over MermaidFilter: Uses .mermaid-config.json<br/>for styling
```

**Expected**: Sequence diagram showing export workflow

---

## 3. Class Diagram

```mermaid
classDiagram
    class ExportPipeline {
        +String configPath
        +Array~String~ logLayers
        +export() Document
        +validate() Boolean
    }

    class PandocWrapper {
        +String pandocPath
        +Array~String~ args
        +execute() Result
    }

    class MermaidFilter {
        +String theme
        +Number width
        +Number height
        +render(String code) Image
    }

    class Logger {
        +String logDir
        +write(String message)
        +rotate()
    }

    ExportPipeline --> PandocWrapper : uses
    PandocWrapper --> MermaidFilter : calls
    ExportPipeline --> Logger : logs to
    MermaidFilter --> Logger : logs to
```

**Expected**: UML class diagram of export architecture

---

## 4. State Diagram

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Validating : Start Export
    Validating --> Processing : Valid
    Validating --> Error : Invalid
    Processing --> Rendering : Mermaid Found
    Processing --> Exporting : No Mermaid
    Rendering --> Exporting : Render Complete
    Exporting --> Success : Export OK
    Exporting --> Error : Export Failed
    Success --> [*]
    Error --> Idle : Reset

    note right of Processing
        Wrapper logs to
        /tmp/obsidian-exports/
    end note
```

**Expected**: State machine showing export states

---

## 5. Gantt Chart

```mermaid
gantt
    title Obsidian Export Pipeline Timeline
    dateFormat YYYY-MM-DD
    section Setup
    Install Dependencies     :done, setup1, 2025-01-01, 1d
    Configure Plugins        :done, setup2, 2025-01-02, 1d
    section Development
    Create Wrapper Script    :done, dev1, 2025-01-03, 2d
    Build Monitor Tool       :done, dev2, 2025-01-04, 2d
    Implement Alerts         :active, dev3, 2025-01-05, 1d
    section Testing
    Unit Tests               :test1, 2025-01-06, 1d
    Integration Tests        :test2, 2025-01-07, 1d
    section Deployment
    Document System          :doc1, 2025-01-08, 1d
    Deploy to Production     :deploy1, 2025-01-09, 1d
```

**Expected**: Timeline chart of development phases

---

## 6. Entity Relationship Diagram

```mermaid
erDiagram
    EXPORT ||--o{ LOG_FILE : generates
    EXPORT ||--|{ MERMAID_DIAGRAM : contains
    EXPORT }o--|| CONFIG : uses
    LOG_FILE }o--|| LOG_LAYER : belongs_to
    MERMAID_DIAGRAM }o--|| THEME : styled_by

    EXPORT {
        string id PK
        datetime timestamp
        string format
        string status
    }

    LOG_FILE {
        string id PK
        string export_id FK
        string layer
        string path
    }

    MERMAID_DIAGRAM {
        string id PK
        string export_id FK
        string type
        string code
    }

    CONFIG {
        string path PK
        json settings
        datetime updated
    }
```

**Expected**: ER diagram showing data relationships

---

## 7. Pie Chart

```mermaid
pie title Export Success Rate
    "Successful Exports" : 95
    "Mermaid Errors" : 3
    "Config Errors" : 1
    "System Errors" : 1
```

**Expected**: Pie chart showing success metrics

---

## 8. Git Graph

```mermaid
gitGraph
    commit id: "Initial setup"
    commit id: "Add Pandoc config"
    branch feature/mermaid-support
    checkout feature/mermaid-support
    commit id: "Install mermaid-filter"
    commit id: "Add wrapper script"
    checkout main
    commit id: "Update docs"
    checkout feature/mermaid-support
    commit id: "Add monitoring"
    checkout main
    merge feature/mermaid-support
    commit id: "Release v1.0"
```

**Expected**: Git branch visualization

---

## Export Instructions

### To Test This Document:

1. **Start monitoring**:
   ```bash
   cd /Volumes/code/repos/litellm
   ./obsidian-monitor.sh
   ```

2. **Enable alerts** (optional):
   ```bash
   ./obsidian-export-alert.sh --daemon
   ```

3. **Export from Obsidian**:
   - Open this file in Obsidian
   - Press `Cmd+P`
   - Type "Export" and select format (HTML/PDF)
   - Wait for completion notification

4. **Verify output**:
   ```bash
   open /tmp/obsidian-exports/
   ```

5. **Check logs**:
   - Monitor shows real-time logs in 4 panes
   - Logs persist in `/tmp/obsidian-exports/*.log`

### Expected Results:

- ✅ All 8 Mermaid diagrams render correctly
- ✅ Images embedded in output document
- ✅ No errors in wrapper.log
- ✅ Success notification from alert system
- ✅ Output file opens automatically

### Troubleshooting:

If any diagram fails to render:

1. Check `mermaid.log` for syntax errors
2. Verify `.mermaid-config.json` exists
3. Run validation: `./validate-obsidian-setup.sh`
4. Check mermaid-filter: `mermaid-filter --version`

---

## Notes

- **Config Location**: `/Volumes/code/repos/litellm/.mermaid-config.json`
- **Log Directory**: `/tmp/obsidian-exports/`
- **Wrapper Script**: `obsidian-export-wrapper.sh`
- **Architecture**: 5-layer debug logging
- **Monitoring**: tmux 4-pane layout
- **Alerts**: fswatch + macOS notifications

**Generated**: 2025-11-16
**Version**: 1.0
**Status**: Test Document
