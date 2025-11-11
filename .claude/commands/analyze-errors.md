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

2. **Git Version Control** - For ALL version control operations
   - Use Git commands with merge preference (NOT rebase)
   - Base branch: `agor_init` (all feature branches branch from here)
   - Create feature branches: `git checkout -b fix/<TOPIC>`
   - Commit frequently: `git commit -m "description"`
   - Merge with: `git merge --no-ff` for explicit merge commits

3. **Agor MCP** - For creating isolated worktrees AND spawning parallel subsessions
   - Use `agor.create_worktree()` to create session-scoped worktrees
   - Use `agor.spawn_subsession()` to spawn agents in dedicated worktrees
   - **CRITICAL**: Each subagent must run in its own spawned subsession + worktree
   - Automatic cleanup when session ends
   - Enables true parallel work without branch switching
   - **Do NOT use Task command** - use Agor spawn subsession instead

4. **Context7 MCP** (Optional) - For fetching documentation when needed
   - Use for library/framework documentation
   - Example: "Get me documentation about [technology]"

5. **GitHub MCP** - For automated PR creation (MANDATORY in Phase 4)
   - Used to push branches and create pull requests
   - Fully automated, no user approval required
   - Required for workflow completion

## 👥 Specialist Sub-Agents

You will coordinate these specialist agents **in parallel where possible**.

**CRITICAL**: All agents MUST be spawned using `agor.spawn_subsession()` in dedicated worktrees. DO NOT use Task command.

### 1. **Architect Agent** (`backend-architect`)

**Role:** Design the fix strategy with parallel execution plan

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

- `python-expert` - Deep Python expertise, async/await, type systems
- `web-dev` - Full-stack web development, React, TypeScript, FastAPI

**Selection Strategy:**

- **If problem nature is clear:**
  - **Python-heavy** (async, type errors, imports, mocking) → `python-expert`
  - **Web-focused** (API endpoints, request handling, FastAPI, React) → `web-dev`
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
   git status  # Check repo state first
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

   **Use Agor MCP spawn subsession** (not Task command):

   ```python
   # Spawn architect in main orchestration worktree
   agor.spawn_subsession(
       worktree_name=f"fix-errors-{date}-main",
       agent_type="backend-architect",
       instruction="""
   Analyze these [N] error groups and design a PARALLEL fix strategy:

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
      - Use python-expert if: Python-specific (async, types, mocking)
      - Use web-dev if: Web-focused (APIs, FastAPI, endpoints)
      - Random selection if: Ambiguous or could go either way
   7. Integration/merge strategy (how to combine fixes safely)
   """,
       session_id=current_session_id
   )
   ```

5. **Review and optimize parallel plan**
   - Verify no circular dependencies
   - Ensure maximum parallelization
   - Identify shared file conflicts (groups touching same files → serialize)
   - **Assign coder agents** (python-expert vs web-dev)
   - **Document assignment reasoning** (clear choice vs. random A/B test)
   - Plan merge strategy

### Phase 3: Parallel Implementation

6. **Create Agor worktrees for isolated parallel work**

   Use Agor MCP to create worktrees for each error group:

   ```python
   # Get current Agor session ID (available in context)
   session_id = get_current_agor_session_id()
   
   # Main worktree for orchestration and merging
   agor.create_worktree(
       name=f"fix-errors-{date}-main",
       base_branch="agor_init",
       session_id=session_id,
       auto_cleanup=True
   )

   # For each error group, create isolated worktree:
   agor.create_worktree(
       name=f"fix-group-{group_name_1}-{timestamp}",
       base_branch="agor_init",
       session_id=session_id,
       auto_cleanup=True
   )

   agor.create_worktree(
       name=f"fix-group-{group_name_2}-{timestamp}",
       base_branch="agor_init",
       session_id=session_id,
       auto_cleanup=True
   )

   # Continue for all error groups...
   ```

   **Worktree naming convention**: `fix-group-[descriptive-name]-[timestamp]`
   - Example: `fix-group-auth-errors-20250112`
   - Example: `fix-group-api-format-20250112`

   **Benefits**:
   - Complete isolation per error group (no branch conflicts)
   - No branch switching overhead
   - Automatic cleanup when session ends
   - Session-scoped tracking

7. **Execute Batch 1 (Independent Groups) - PARALLEL**

   **Launch multiple Coder agents simultaneously using Agor spawn subsession:**

   **CRITICAL**: Each agent MUST be spawned via `agor.spawn_subsession()` in its dedicated worktree.

   ```python
   # Agent 1 (python-expert chosen - Python-heavy group)
   agor.spawn_subsession(
       worktree_name=f"fix-group-{group_1_name}-{timestamp}",
       agent_type="python-expert",
       instruction=f"""
   Fix error group: {group_1_details}
   
   Group: {group_1_name}
   Selection: [Deliberate / Random A/B Test]
   
   Root cause analysis:
   - Use JetBrains MCP to explore codebase
   - Research GitHub issues, docs, community solutions
   - If blocked, request problem-solver-specialist assistance
   
   Implementation:
   - Use JetBrains MCP for all file operations
   - Work in THIS worktree: fix-group-{group_1_name}
   - Commit after each logical change: git commit -m 'Fix: [specific change]'
   
   Validation:
   - Run affected tests
   - Verify no regressions
   
   Return:
   - Files modified, commits created, test results
   - **Performance metrics:** time spent, blockers encountered, success rate
   """,
       session_id=current_session_id
   )

   # Agent 2 (web-dev chosen - Web-focused group)
   agor.spawn_subsession(
       worktree_name=f"fix-group-{group_2_name}-{timestamp}",
       agent_type="web-dev",
       instruction=f"""
   Fix error group: {group_2_details}
   
   [Same structure as Agent 1, different group]
   """,
       session_id=current_session_id
   )

   # Agent 3 (random selection - ambiguous group)
   import random
   agent_type = random.choice(["python-expert", "web-dev"])
   
   agor.spawn_subsession(
       worktree_name=f"fix-group-{group_3_name}-{timestamp}",
       agent_type=agent_type,
       instruction=f"""
   Fix error group: {group_3_details}
   
   Selection: Random A/B Test (coin flip selected: {agent_type})
   
   [Same structure as Agent 1, different group]
   """,
       session_id=current_session_id
   )

   # Continue spawning subsessions for all Batch 1 groups...
   # Each group gets its own worktree + spawned subsession
   ```

   **Key Points:**
   - Each `agor.spawn_subsession()` call is non-blocking (runs in parallel)
   - Each subsession works in its own isolated worktree
   - No Task command usage - pure Agor MCP architecture
   - Session ID ties all subsessions together for tracking

8. **Await Batch 1 completion and integrate**
   - Wait for all Batch 1 agents to complete
   - **Record agent performance:**
     - Agent type used
     - Time taken
     - Success/failure
     - Quality of solution
     - Blockers encountered
   - Review all fixes
   - **Merge to main branch:**

     ```bash
     # Switch to main orchestration worktree
     cd fix-errors-[date]-main
     
     # Ensure on correct base
     git checkout agor_init
     
     # Merge each group's fixes (prefer merge over rebase)
     git merge --no-ff fix-group-[name-1] -m "Merge: Fix group 1 - [description]"
     git merge --no-ff fix-group-[name-2] -m "Merge: Fix group 2 - [description]"
     # etc.
     ```

   - Run full test suite to check for conflicts
   - Resolve any merge conflicts using Git

9. **Execute Batch 2 (Dependent on Batch 1) - PARALLEL**
   - Same parallel agent spawning as Batch 1
   - Continue A/B testing with random selections
   - Each agent works from new worktree based on merged agor_init
   - Create new worktrees for each group in Batch 2
   - Execute fixes in parallel
   - Record performance metrics
   - Merge back to agor_init using Git

10. **Repeat for Batch 3, 4, etc.**
    - Continue until all batches completed
    - Each batch waits for previous batch to merge
    - Within each batch, maximize parallelization
    - Keep tracking agent performance

### Phase 4: Final Verification & Reporting (Sequential)

11. **Comprehensive validation**
    - Switch to main orchestration worktree (fix-errors-[date]-main)
    - Ensure all merges completed to agor_init branch
    - Run complete test suite
    - Check for regressions
    - Verify all original errors resolved
    - Review all commits

12. **Generate parallel execution report with A/B insights**

13. **🚀 Automatic PR Creation and Push**

    **CRITICAL - This step is MANDATORY and fully automated:**

    After generating the final report and verifying all fixes, the orchestrator MUST:

    a) **Auto-generate PR title and description** based on fixes:

    ```
    PR Title Format:
    "Fix: [N] errors across [M] groups - [primary_error_theme]"

    Examples:
    - "Fix: 25 errors across 5 groups - Authentication and API format issues"
    - "Fix: 10 async/await errors in streaming endpoints"

    PR Description Template:
    ## Summary
    Resolved [N] errors from log file: `[log_filename]`

    ## Error Groups Fixed
    [For each group:]
    - **[Group Name]** ([N] errors) - [Brief description]
      - Agent: [python-expert/web-dev]
      - Assignment: [Deliberate/Random A/B Test]
      - Time: [duration]
      - Status: ✅ FIXED

    ## Test Results
    - Tests passing: [N/N]
    - Regressions: [None/List]

    ## A/B Testing Insights
    **Agent Performance:**
    - python-expert: [N] groups, [X]% success rate
    - web-dev: [N] groups, [X]% success rate
    
    [Brief summary of strengths/weaknesses observed]

    ## Files Modified
    [List of modified files with change summary]

    ## Parallel Execution Efficiency
    - Total time: [duration]
    - Time saved vs sequential: [duration]
    - Batches executed: [N]

    ## Verification
    - [x] All original errors resolved
    - [x] Full test suite passing
    - [x] No new regressions introduced

    ---
    🤖 Auto-generated by /analyze-errors orchestrator
    📊 Session ID: [agor_session_id]
    ```

    b) **Push current branch to upstream** using GitHub MCP:

    ```python
    # Get current branch name
    current_branch = subprocess.check_output(
        ["git", "branch", "--show-current"],
        text=True
    ).strip()
    
    # Push to remote
    subprocess.run(["git", "push", "origin", current_branch], check=True)

    # Create PR using GitHub MCP
    github_mcp.create_pull_request(
        base_branch="agor_init",
        head_branch=current_branch,
        title=auto_generated_title,
        body=auto_generated_description,
        draft=False  # Ready for review immediately
    )
    ```

    **Requirements**:
    - ✅ No user approval required - fully automated
    - ✅ Base branch: `agor_init` (ALWAYS)
    - ✅ PR includes all commits from error fixing workflow
    - ✅ PR description includes complete context for reviewers
    - ✅ Push happens AFTER final validation passes
    - ✅ If any tests fail but fixes are complete, document in PR
    - ✅ Mark as draft if critical failures exist

    **Error Handling**:
    - If GitHub MCP unavailable: Log error, save PR content to `PR_DRAFT_[timestamp].md`
    - If push fails: Retry once with `--force-with-lease`, then notify and save draft
    - If PR already exists for branch: Update existing PR description instead
    - If authentication fails: Save draft and notify orchestrator

    **Output**:
    ```
    ✅ PR Created Successfully
    - URL: https://github.com/[org]/[repo]/pull/[number]
    - Branch: [current_branch] → agor_init
    - Status: Open / Draft
    - Errors fixed: [N]
    - Agent performance: python-expert ([N] groups), web-dev ([N] groups)
    - Parallelization: Saved [duration] vs sequential execution
    ```

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
- Git commits created
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
python-expert (spawned via Agor subsessions)
- Groups handled: [N]
- Deliberate assignments: [N]
- Random assignments: [N]
- Success rate: [X]%
- Avg time per group: [duration]
- Strengths observed: [list]
- Weaknesses observed: [list]

web-dev (spawned via Agor subsessions)
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
- Worktrees created
- Git branches merged

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
def select_agent_and_spawn(group, worktree_name, instruction):
    """
    Select appropriate agent type and spawn subsession in dedicated worktree.
    CRITICAL: Always use agor.spawn_subsession() - NEVER use Task command.
    """
    # Analyze group characteristics
    tech_context = analyze_tech_context(group)

    if tech_context == "PYTHON_HEAVY":
        # Async, types, mocking, imports, decorators
        agent_type = "python-expert"
        reason = "Deliberate (Python-focused)"
    
    elif tech_context == "WEB_FOCUSED":
        # FastAPI, endpoints, routing, HTTP, request handling
        agent_type = "web-dev"
        reason = "Deliberate (Web-focused)"
    
    elif tech_context == "MIXED" or tech_context == "UNCLEAR":
        # Random selection for A/B testing
        import random
        agent_type = random.choice(["python-expert", "web-dev"])
        reason = "Random A/B Test"
    
    # Spawn subsession in dedicated worktree
    agor.spawn_subsession(
        worktree_name=worktree_name,
        agent_type=agent_type,
        instruction=instruction,
        session_id=current_session_id
    )
    
    return agent_type, reason
```

**Tech Context Classification:**

- **PYTHON_HEAVY**: AsyncIO, type checking, mock objects, import errors, decorators, generators
- **WEB_FOCUSED**: API endpoints, request/response, FastAPI routers, HTTP methods, authentication
- **MIXED**: Touches both Python internals and web layer
- **UNCLEAR**: Insufficient context to determine

## ⚠️ Constraints & Guidelines

- **Use Git with merge preference** - Always use `git merge --no-ff`, base branch is `agor_init`
- **Use Agor MCP for worktrees AND subsessions** - CRITICAL requirements:
  - Create isolated worktrees per error group for parallel work
  - Spawn each subagent via `agor.spawn_subsession()` in its dedicated worktree
  - **NEVER use Task command** - only Agor spawn subsession
  - Each subsession = 1 worktree = 1 error group
- **Never use bash for file ops** - Only JetBrains MCP
- **One agent per error group** - No agent handles multiple groups simultaneously
- **Wait for batch completion** - Don't start Batch N+1 until Batch N merges
- **Commit atomically** - Each agent commits independently in their worktree
- **Test before merging** - Validate each group's fixes before integration
- **Document agent assignments** - Track deliberate vs. random choices
- **Record performance metrics** - Time, success rate, blockers
- **Handle failures gracefully** - If an agent fails, document why and try alternative
- **Automated PR creation** - MUST create PR after final validation using GitHub MCP

## 🎬 Begin

Start by locating the newest error log, then proceed with:

1. **Thematic grouping** by error nature
2. **Agent assignment** (deliberate or random)
3. **Parallel execution** with A/B testing
4. **Performance tracking** for future optimization
