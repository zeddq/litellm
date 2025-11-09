# Parallel Error Analysis and Fixing Workflow

Command: `/ultrathink:ultrathink Analyze and fix all issues in the newest
error log file from ./logs/errors/ using parallel workflows with A/B agent
testing`

## 🎯 Mission

You are the Coordinator Agent orchestrating a **parallel error resolution
workflow with A/B testing**. Your mission: identify, categorize, and
systematically fix all errors found in the most recent log file from
`./logs/errors/` by **grouping errors of the same nature and executing
parallel fix workflows** for maximum efficiency. Additionally,
**experiment with different coder agents** to identify which performs
best for specific problem types.

## 🔧 MANDATORY TOOLING REQUIREMENTS

**CRITICAL - You MUST use these tools exclusively:**

1. **JetBrains MCP Server** - For ALL file operations and codebase exploration
   - Use `find_files_by_glob`, `get_file_text_by_path`, `search_in_files_by_text`
   - DO NOT use bash commands like `cat`, `grep`, `find`, `ls`
   - Leverage IDE's semantic search and symbol navigation

2. **Jujutsu (jj) Version Control** - For ALL version control operations
   - Use `jj` commands exclusively (NOT git)
   - Create bookmarks before making changes: `jj new && jj bookmark new <TOPIC>`
   - Commit frequently: `jj commit -m "description"`
   - Use `jj undo` for safe rollbacks

3. **Context7 MCP** (Optional) - For fetching documentation when needed
   - Use for library/framework documentation
   - Example: "Get me documentation about [technology]"

## 👥 Specialist Sub-Agents

You will coordinate these specialist agents **in parallel where possible**:

### 1. **Architect Agent** (`backend-architect:backend-architect`)

web-dev:web-dev**Role:** Design the fix strategy with parallel execution plan

**Tasks:**

- Analyze error patterns and group by nature/theme
- Design high-level fix strategy with priorities
- **Identify independent vs. dependent error groups**
- **Create parallel execution plan** (which groups can run simultaneously)
- Consider architectural implications

**Deliverable:** Structured fix plan with:

- Error groups categorized by nature
- Dependency graph showing blocking relationships
- Parallel execution batches
- Time estimates per group

### 2. **Coder Agents** (Choose per group for A/B testing)

**Available Agents:**

- `python-expert:python-expert` - Deep Python expertise, async/await, type systems
- `web-dev:web-dev` - Full-stack web development, React, TypeScript, FastAPI

**Selection Strategy:**

- **If problem nature is clear:**
  - **Python-heavy** (async, type errors, imports, mocking) → `python-expert:python-expert`
  - **Web-focused** (API endpoints, request handling, FastAPI, React) → `web-dev:web-dev`
- **If unsure or ambiguous:**
  - **Randomly select** one agent per group
  - **Track performance** for future learning
  - Document which agent was used for each group

**Tasks:**

- Research root causes using GitHub issues, documentation, community solutions
- Implement fixes following architect's plan
- Validate fixes with tests
- Handle complex debugging scenarios
- Work independently on assigned error groups

**Deliverable:** Working fixes with verification steps

### 3. **Problem Solver Specialist** (`problem-solver-specialist:1-problem-solver-specialist`)

**Role:** Deep investigation when coder agents need additional research
**Tasks:**

- Advanced debugging with GitHub issues mining
- Perplexity deep research for obscure issues
- Browser automation testing
- Multi-source documentation analysis

**Use When:** Coder agents encounter blockers or need deeper investigation

## 📋 Parallel Execution Workflow

### Phase 1: Discovery & Thematic Grouping (Sequential)

1. **Locate newest log file**

   ```bash
   jj status  # Check repo state first
   # Use JetBrains MCP: find_files_by_glob(pattern="logs/errors/*.log")
   # Sort by modification time, select newest
   ```

2. **Extract and categorize all errors**
   - Use JetBrains MCP `get_file_text_by_path` to read log
   - Extract: error messages, stack traces, failure patterns, affected tests
   - **Group errors by nature:**
     - **Authentication errors** (401, 403, token issues)
     - **API format mismatches** (response structure, missing keys)
     - **Configuration issues** (missing files, wrong paths)
     - **Dependency problems** (import errors, missing packages)
     - **Test infrastructure** (mock issues, fixture problems)
     - **Type errors** (async/await, isinstance checks)
     - **Database/persistence** (schema, connection issues)
     - **Streaming/async** (generator issues, async iterator problems)
     - Custom groups as needed

3. **Create error group summary**
   For each group, document:
   - Nature/theme description
   - Count of errors
   - Example error messages (2-3 representative samples)
   - Affected files/modules
   - Technology context (Python-heavy vs. web-focused)
   - Initial severity assessment

### Phase 2: Architectural Planning (Sequential)

4. **Spawn Architect Agent**

   ```
   Task: backend-architect:backend-architect
   Prompt: "Analyze these [N] error groups and design a PARALLEL fix strategy:

   [For each group:]
   Group 1: [Name] - [Count] errors
   Nature: [Description]
   Examples: [Error samples]
   Affected: [Files/modules]
   Tech Context: [Python-heavy / Web-focused / Mixed]

   Provide:
   1. Priority matrix (P0-Critical/P1-High/P2-Medium/P3-Low)
   2. Dependency analysis - which groups block others?
   3. Parallel execution batches:
      - Batch 1: [Independent groups that can run simultaneously]
      - Batch 2: [Groups dependent on Batch 1]
      - Batch 3: [Groups dependent on Batch 2]
      - etc.
   4. Time estimates per group
   5. Recommended approach for each group
   6. **Agent recommendation per group:**
      - Use python-expert:python-expert if: Python-specific (async, types, mocking)
      - Use web-dev:web-dev if: Web-focused (APIs, FastAPI, endpoints)
      - Random selection if: Ambiguous or could go either way
   7. Integration/merge strategy (how to combine fixes safely)"
   ```

5. **Review and optimize parallel plan**
   - Verify no circular dependencies
   - Ensure maximum parallelization
   - Identify shared file conflicts (groups touching same files → serialize)
   - **Assign coder agents** (python-expert vs web-dev)
   - **Document assignment reasoning** (clear choice vs. random A/B test)
   - Plan merge strategy

### Phase 3: Parallel Implementation

6. **Create Jujutsu bookmark structure**

   ```bash
   jj new && jj bookmark new fix-errors-[date]-main

   # For each error group, create a child bookmark:
   jj new && jj bookmark new fix-group-[group-name-1]
   jj new main && jj bookmark new fix-group-[group-name-2]
   # etc.
   ```

7. **Execute Batch 1 (Independent Groups) - PARALLEL**

   **Launch multiple Coder agents simultaneously:**

   ```
   // Agent 1 (python-expert chosen - Python-heavy group)
   Task: python-expert:python-expert
   Group: [Group 1 name]
   Bookmark: fix-group-[name-1]
   Selection: [Deliberate / Random A/B Test]
   Prompt: "Fix error group: [Group 1 details]

   Root cause analysis:
   - Use JetBrains MCP to explore codebase
   - Research GitHub issues, docs, community solutions
   - If blocked, request problem-solver-specialist assistance

   Implementation:
   - Use JetBrains MCP for all file operations
   - Work in bookmark: fix-group-[name-1]
   - Commit after each logical change: jj commit -m 'Fix: [specific change]'

   Validation:
   - Run affected tests
   - Verify no regressions

   Return:
   - Files modified, commits created, test results
   - **Performance metrics:** time spent, blockers encountered, success rate"

   // Agent 2 (web-dev chosen - Web-focused group)
   Task: web-dev:web-dev
   Group: [Group 2 name]
   Bookmark: fix-group-[name-2]
   Selection: [Deliberate / Random A/B Test]
   Prompt: [Same structure, different group]

   // Agent 3 (random selection - ambiguous group)
   Task: [randomly choose: python-expert:python-expert OR web-dev:web-dev]
   Group: [Group 3 name]
   Bookmark: fix-group-[name-3]
   Selection: Random A/B Test (coin flip)
   Prompt: [Same structure, different group]

   // Continue for all Batch 1 groups...
   ```

8. **Await Batch 1 completion and integrate**
   - Wait for all Batch 1 agents to complete
   - **Record agent performance:**
     - Agent type used
     - Time taken
     - Success/failure
     - Quality of solution
     - Blockers encountered
   - Review all fixes
   - **Merge to main bookmark:**

     ```bash
     jj new fix-errors-[date]-main
     jj bookmark set -r @ fix-group-[name-1]  # Merge group 1
     jj new @
     jj bookmark set -r @ fix-group-[name-2]  # Merge group 2
     # etc.
     ```

   - Run full test suite to check for conflicts
   - Resolve any merge conflicts

9. **Execute Batch 2 (Dependent on Batch 1) - PARALLEL**
   - Same parallel agent spawning as Batch 1
   - Continue A/B testing with random selections
   - Each agent works from the merged main bookmark
   - Create child bookmarks for each group
   - Execute fixes in parallel
   - Record performance metrics
   - Merge back to main

10. **Repeat for Batch 3, 4, etc.**
    - Continue until all batches completed
    - Each batch waits for previous batch to merge
    - Within each batch, maximize parallelization
    - Keep tracking agent performance

### Phase 4: Final Verification & Reporting (Sequential)

11. **Comprehensive validation**
    - Switch to main bookmark
    - Run complete test suite
    - Check for regressions
    - Verify all original errors resolved
    - Review all commits

12. **Generate parallel execution report with A/B insights**

## 📊 Output Format

Provide a structured report with:

### 1. **Executive Summary**

- Total errors found: [N]
- Error groups identified: [N]
- Errors fixed: [N] ([X]%)
- Errors remaining: [N] ([X]%)
- Total time: [duration]
- **Parallelization efficiency**: [time saved vs. sequential]
- **Agent performance summary**: [python-expert vs web-dev comparison]

### 2. **Error Grouping Analysis**

```
Group 1: [Name] - [Nature description]
- Count: [N] errors
- Priority: P[0-3]
- Batch: [1/2/3/etc.]
- Dependencies: [None / Depends on Group X, Y]
- Tech Context: [Python-heavy / Web-focused / Mixed]
- Agent Assigned: [python-expert / web-dev]
- Assignment Reason: [Deliberate (Python-focused) / Random A/B Test]
- Example errors: [samples]
```

### 3. **Parallel Execution Timeline**

```
Batch 1 (Parallel - 3 groups, 25 errors total):
├─ Group 1: [Name] - python-expert (deliberate) - 2h - ✅ FIXED
├─ Group 2: [Name] - web-dev (deliberate) - 1.5h - ✅ FIXED
└─ Group 3: [Name] - python-expert (random) - 3h - ✅ FIXED
Wall time: 3h (saved 2.5h vs. sequential)

Batch 2 (Parallel - 2 groups, 10 errors total):
├─ Group 4: [Name] - web-dev (random) - 1h - ✅ FIXED
└─ Group 5: [Name] - python-expert (deliberate) - 1.5h - ✅ FIXED
Wall time: 1.5h (saved 1h vs. sequential)
```

### 4. **Implementation Details per Group**

For each group:

- Root cause identified
- Solution approach
- Files modified (with line counts)
- Jujutsu commits created
- Test results
- **Agent used**: [python-expert / web-dev]
- **Assignment type**: [Deliberate / Random]
- **Performance metrics**:
  - Time spent: [duration]
  - Blockers encountered: [Y/N + description]
  - Tests passing: [N/N]
  - Code quality: [subjective assessment]

### 5. **A/B Testing Insights** 🧪

**Agent Performance Comparison:**

```
python-expert:python-expert
- Groups handled: [N]
- Deliberate assignments: [N]
- Random assignments: [N]
- Success rate: [X]%
- Avg time per group: [duration]
- Strengths observed: [list]
- Weaknesses observed: [list]

web-dev:web-dev
- Groups handled: [N]
- Deliberate assignments: [N]
- Random assignments: [N]
- Success rate: [X]%
- Avg time per group: [duration]
- Strengths observed: [list]
- Weaknesses observed: [list]
```

**Recommendations for Future Runs:**

- Error type X → Use [agent] (based on [reason])
- Error type Y → Use [agent] (based on [reason])
- Ambiguous cases → Continue random selection for more data

### 6. **Integration & Merge Summary**

- Merge conflicts encountered: [N]
- Resolution strategy
- Final test results
- Bookmarks created

### 7. **Remaining Issues** (if any)

- Description
- Why not fixed
- Blocking factors
- Which agent attempted
- Recommended next steps

## ⚡ Parallelization Strategy

**Key Principles:**

1. **Maximize Batch Size**: Put as many independent groups in each batch as possible
2. **Minimize Batches**: Fewer batches = less sequential waiting
3. **Handle File Conflicts**:
   - If two groups modify the same file → serialize them
   - Use file overlap analysis to detect conflicts
4. **Agent Load Balancing**: Distribute complex groups across batches
5. **Early Fast Wins**: Front-load quick fixes in Batch 1 for visible progress
6. **A/B Test Diversity**: Ensure random selections span different error types

## 🎲 Agent Selection Algorithm

For each error group:

```python
def select_agent(group):
    # Analyze group characteristics
    tech_context = analyze_tech_context(group)

    if tech_context == "PYTHON_HEAVY":
        # Async, types, mocking, imports, decorators
        return "python-expert:python-expert", "Deliberate (Python-focused)"

    elif tech_context == "WEB_FOCUSED":
        # FastAPI, endpoints, routing, HTTP, request handling
        return "web-dev:web-dev", "Deliberate (Web-focused)"

    elif tech_context == "MIXED" or tech_context == "UNCLEAR":
        # Random selection for A/B testing
        import random
        agent = random.choice([
            "python-expert:python-expert",
            "web-dev:web-dev"
        ])
        return agent, "Random A/B Test"
```

**Tech Context Classification:**

- **PYTHON_HEAVY**: AsyncIO, type checking, mock objects, import errors, decorators, generators
- **WEB_FOCUSED**: API endpoints, request/response, FastAPI routers, HTTP methods, authentication
- **MIXED**: Touches both Python internals and web layer
- **UNCLEAR**: Insufficient context to determine

## ⚠️ Constraints & Guidelines

- **Never use git commands** - Only Jujutsu (jj)
- **Never use bash for file ops** - Only JetBrains MCP
- **One agent per error group** - No agent handles multiple groups simultaneously
- **Wait for batch completion** - Don't start Batch N+1 until Batch N merges
- **Commit atomically** - Each agent commits independently
- **Test before merging** - Validate each group's fixes before integration
- **Document agent assignments** - Track deliberate vs. random choices
- **Record performance metrics** - Time, success rate, blockers
- **Handle failures gracefully** - If an agent fails, document why and try alternative

## 🎬 Begin

Start by locating the newest error log, then proceed with:

1. **Thematic grouping** by error nature
2. **Agent assignment** (deliberate or random)
3. **Parallel execution** with A/B testing
4. **Performance tracking** for future optimization
