# Obsidian PDF Export Testing Suite - Index

Complete reference guide to all testing documentation and scripts.

## 📖 Documentation Files

### 1. TEST_SUITE_README.md
**Purpose:** Main entry point for the testing suite
**Audience:** Everyone (start here)
**Contents:**
- Complete overview of testing suite
- Quick start guide
- Script descriptions
- Usage examples
- Troubleshooting guide

**When to use:** First time using the test suite, need quick reference

---

### 2. OBSIDIAN_MERMAID_TEST_PLAN.md (60 KB, 1,700+ lines)
**Purpose:** Comprehensive testing strategy and procedures
**Audience:** QA testers, detailed implementers
**Contents:**
- 53+ detailed test cases with step-by-step procedures
- 5 test phases (Unit, Integration, E2E, Performance, Error)
- Validation criteria and success metrics
- Performance benchmarks and targets
- Troubleshooting decision trees
- Test reporting templates
- Appendices with examples and references

**When to use:**
- Need detailed test procedures
- Planning test execution
- Creating test reports
- Troubleshooting complex issues

**Key Sections:**
- Section 1: Test Phases Overview
- Section 2: Test Cases (8 diagram types, 5 logging layers, 5 scripts, 4 configs, 5 error scenarios)
- Section 3: Validation Criteria (success metrics, quality benchmarks)
- Section 4: Testing Procedures (step-by-step instructions)
- Section 5: Test Reporting (templates and tracking)
- Section 6: Regression Testing
- Section 7: Test Automation
- Section 8: Troubleshooting Decision Tree
- Section 9: Test Environment Requirements
- Section 10: Success Metrics and KPIs
- Section 11: Test Schedule
- Section 12: Appendices

---

### 3. TESTING_STRATEGY_SUMMARY.md (11 KB, 480+ lines)
**Purpose:** Executive summary and quick reference
**Audience:** Project managers, developers, quick overview
**Contents:**
- High-level testing strategy overview
- Deliverables summary
- Test coverage matrix
- Key features and benefits
- Implementation roadmap
- Quick start guide
- Performance targets summary

**When to use:**
- Need executive overview
- Presenting to stakeholders
- Understanding overall strategy
- Quick reference for key metrics

---

### 4. TEST_CHECKLIST.md (6.4 KB, 280+ lines)
**Purpose:** Quick reference checklist for daily testing
**Audience:** Testers, developers doing quick validation
**Contents:**
- Pre-test setup checklist
- Quick test commands
- Manual test procedures (condensed)
- Quality validation checklists
- Common issues quick reference
- Test results recording templates

**When to use:**
- Daily testing activities
- Quick validation after changes
- Recording test results
- Common issue troubleshooting

---

### 5. TESTING_INDEX.md (this file)
**Purpose:** Navigation hub for all testing documentation
**Audience:** Everyone
**Contents:**
- Index of all documentation
- Script reference guide
- File organization
- Quick links

**When to use:** Finding the right documentation

---

## 🤖 Automated Test Scripts

### 1. run-all-tests.sh (Master Runner)
**Purpose:** Execute all test suites in sequence
**Duration:** 15-20 minutes
**Prerequisites:** All scripts present, environment validated

**Suites Run:**
1. Setup Validation (validate-setup.sh)
2. Log Validation (validate-logs.sh)
3. Diagram Tests (test-all-diagrams.sh)
4. Performance Benchmarks (benchmark-performance.sh)
5. Regression Tests (run-regression-tests.sh)

**Output:**
- `test-results-YYYYMMDD-HHMMSS/test-summary.txt`
- Individual suite logs
- Collected artifacts (CSV, PDFs)

**Usage:**
```bash
./run-all-tests.sh
```

**Exit Codes:**
- 0: All tests passed
- 1: One or more tests failed

---

### 2. test-all-diagrams.sh (Diagram Testing)
**Purpose:** Test all 8 Mermaid diagram types
**Duration:** 5-10 minutes
**Prerequisites:** Test documents exist (test-*.md)

**Tests:**
- Flowchart (TC-MD-001)
- Sequence diagram (TC-MD-002)
- Class diagram (TC-MD-003)
- State diagram (TC-MD-004)
- ER diagram (TC-MD-005)
- Gantt chart (TC-MD-006)
- Pie chart (TC-MD-007)
- Git graph (TC-MD-008)

**Output:**
- `/tmp/diagram-tests-*/`
- Individual PDFs for inspection
- Per-diagram log files
- Summary log

**Usage:**
```bash
./test-all-diagrams.sh
```

**Exit Codes:**
- 0: All diagrams exported successfully
- 1: One or more diagram exports failed

---

### 3. validate-logs.sh (Log Validation)
**Purpose:** Validate log file quality and structure
**Duration:** 1-2 minutes
**Prerequisites:** Logs exist in ~/.obsidian-pandoc/logs/

**Checks:**
- Log files exist (wrapper.log, pandoc.log, mermaid.log)
- Timestamps valid (ISO 8601 format)
- Component tags present
- File sizes reasonable
- Recent activity detected
- Error counts

**Output:**
- Console output (color-coded)
- Validation report

**Usage:**
```bash
./validate-logs.sh [log-directory]
# Default: ~/.obsidian-pandoc/logs
```

**Exit Codes:**
- 0: All validations passed
- 1: Critical issues found

---

### 4. benchmark-performance.sh (Performance Testing)
**Purpose:** Measure export performance metrics
**Duration:** 10-15 minutes
**Prerequisites:** Test documents exist

**Measures:**
- Export duration (seconds)
- Memory usage (MB)
- CPU utilization (%)
- Output file size (KB)

**Compares Against Targets:**
- Defined in TARGETS_SIMPLE array
- From test plan Section 3.3

**Output:**
- `performance-results.csv`
- Console summary

**Usage:**
```bash
./benchmark-performance.sh
```

**Exit Codes:**
- 0: All within targets
- 1: Export failures
- 2: Some above targets (warning)

**Output Format (CSV):**
```
Diagram_Type,Duration_Seconds,Memory_MB,CPU_Percent,File_Size_KB,Status
flowchart,1.8,180,45,120,PASS
```

---

### 5. run-regression-tests.sh (Regression Testing)
**Purpose:** Ensure no functionality breakage after changes
**Duration:** 5-10 minutes
**Prerequisites:** Basic environment setup

**Test Categories:**
- Core functionality (diagram exports)
- Script functionality (wrapper, validator, etc.)
- Dependencies (pandoc, node, mermaid-filter)
- Configuration (YAML, JSON validity)
- Logging (directory, files, format)
- Error handling (missing files, syntax errors)

**Total Checks:** 20+ regression tests

**Output:**
- `/tmp/obsidian-regression-*/regression-results.txt`
- Individual test logs

**Usage:**
```bash
./run-regression-tests.sh
```

**Exit Codes:**
- 0: All regression tests passed
- 1: One or more regressions detected

---

## 📊 Test Data Files

### TEST_MATRIX.csv
**Purpose:** Track test execution status
**Format:** CSV (comma-separated values)

**Fields:**
- Test_ID (e.g., TC-MD-001)
- Category (Diagram, Logging, Script, Config, Error, Integration, E2E, Performance, Regression)
- Test_Name (descriptive)
- Priority (Critical, High, Medium, Low)
- Automated (Yes/No)
- Manual (Yes/No)
- Status (Not Run, Pass, Fail, Skip)
- Duration (execution time)
- Notes (comments)
- Last_Run (timestamp)

**Total Test Cases:** 53

**Usage:**
- Import into spreadsheet for tracking
- Update after each test run
- Generate reports from data

**Update Example:**
```bash
# Mark test as passed
sed -i '' 's/TC-MD-001,.*,Not Run/TC-MD-001,...,Pass,3.2s,Good,2025-11-16/' TEST_MATRIX.csv
```

---

## 📂 File Organization

```
litellm/
├── Documentation/
│   ├── TEST_SUITE_README.md              ← Start here
│   ├── TESTING_INDEX.md                  ← This file
│   ├── TESTING_STRATEGY_SUMMARY.md       ← Executive summary
│   ├── TEST_CHECKLIST.md                 ← Quick reference
│   └── OBSIDIAN_MERMAID_TEST_PLAN.md     ← Comprehensive plan
│
├── Test Scripts/
│   ├── run-all-tests.sh                  ← Master runner
│   ├── test-all-diagrams.sh              ← Diagram tests
│   ├── validate-logs.sh                  ← Log validation
│   ├── benchmark-performance.sh          ← Performance tests
│   └── run-regression-tests.sh           ← Regression tests
│
├── Test Data/
│   └── TEST_MATRIX.csv                   ← Test tracking
│
└── Test Results/ (generated)
    └── test-results-YYYYMMDD-HHMMSS/
        ├── test-summary.txt
        ├── performance-results.csv
        └── *.log (suite logs)
```

---

## 🚀 Quick Navigation

### I need to...

**...understand the testing suite**
→ Read `TEST_SUITE_README.md`

**...run tests quickly**
→ Use `TEST_CHECKLIST.md` for commands
→ Run `./run-all-tests.sh`

**...get detailed test procedures**
→ Read `OBSIDIAN_MERMAID_TEST_PLAN.md`

**...see performance targets**
→ Check `TESTING_STRATEGY_SUMMARY.md` Section 3.3
→ Or `OBSIDIAN_MERMAID_TEST_PLAN.md` Section 3.3

**...troubleshoot issues**
→ Check `TEST_CHECKLIST.md` Common Issues
→ Or `OBSIDIAN_MERMAID_TEST_PLAN.md` Section 8 (Decision Trees)

**...track test results**
→ Update `TEST_MATRIX.csv`
→ Use templates in `OBSIDIAN_MERMAID_TEST_PLAN.md` Section 5

**...understand test coverage**
→ See `TESTING_STRATEGY_SUMMARY.md`
→ Review `TEST_MATRIX.csv`

**...set up CI/CD**
→ See `OBSIDIAN_MERMAID_TEST_PLAN.md` Section 7.2

---

## 📋 Test Case Reference

### By Test ID
- **TC-MD-001 to TC-MD-008:** Mermaid diagram type tests
- **TC-LOG-001 to TC-LOG-005:** Logging layer tests
- **TC-SCR-001 to TC-SCR-005:** Script functionality tests
- **TC-CFG-001 to TC-CFG-004:** Configuration tests
- **TC-ERR-001 to TC-ERR-005:** Error handling tests
- **TC-INT-001 to TC-INT-005:** Integration tests
- **TC-E2E-001 to TC-E2E-004:** End-to-end tests
- **TC-PERF-001 to TC-PERF-012:** Performance tests
- **TC-REG-001 to TC-REG-005:** Regression tests

### By Priority
- **Critical (15 tests):** Must pass 100%
- **High (8 tests):** Must pass 95%+
- **Medium (4 tests):** Should pass
- **Low (rest):** Nice to pass

### By Automation
- **Automated (32 tests):** Can run via scripts
- **Manual (21 tests):** Require human validation
- **Both (14 tests):** Can be automated but benefit from manual inspection

---

## 🎯 Quick Command Reference

```bash
# Setup and validation
./validate-setup.sh                    # Check environment

# Individual test suites
./test-all-diagrams.sh                # Test diagrams (5-10 min)
./validate-logs.sh                    # Validate logs (1-2 min)
./benchmark-performance.sh            # Benchmark (10-15 min)
./run-regression-tests.sh             # Regression (5-10 min)

# Full test run
./run-all-tests.sh                    # All tests (15-20 min)

# Results
cat test-results-*/test-summary.txt   # View summary
cat performance-results.csv           # View performance
```

---

## 📊 Test Coverage Summary

| Category | Tests | Automated | Manual | Priority Distribution |
|----------|-------|-----------|--------|-----------------------|
| Diagrams | 8 | 8 | 8 | 5 Critical, 2 High, 1 Low |
| Logging | 5 | 0 | 5 | 4 Critical, 1 High |
| Scripts | 5 | 5 | 5 | 3 Critical, 2 High |
| Config | 4 | 3 | 4 | 2 Critical, 2 High |
| Error | 5 | 5 | 5 | 1 Critical, 2 High, 2 Medium |
| Integration | 5 | 3 | 5 | 3 Critical, 2 High |
| E2E | 4 | 2 | 4 | 1 Critical, 2 High, 1 Medium |
| Performance | 12 | 12 | 0 | 12 High |
| Regression | 5 | 5 | 5 | 5 Critical |
| **Total** | **53** | **43** | **41** | **15 Critical, 8 High, 4 Med** |

---

## 🔗 External References

### Obsidian
- Obsidian website: https://obsidian.md
- Obsidian Pandoc Plugin: (search in Community Plugins)

### Pandoc
- Pandoc website: https://pandoc.org
- Pandoc manual: https://pandoc.org/MANUAL.html
- Installation: https://pandoc.org/installing.html

### Mermaid
- Mermaid website: https://mermaid.js.org
- Mermaid Live Editor: https://mermaid.live
- mermaid-filter: https://www.npmjs.com/package/mermaid-filter
- mermaid-cli: https://github.com/mermaid-js/mermaid-cli

### Tools
- Node.js: https://nodejs.org
- tmux: https://github.com/tmux/tmux
- fswatch: https://github.com/emcrisostomo/fswatch

---

## 📈 Success Metrics

**Test Execution:**
- Unit tests: 100% pass required
- Integration tests: 95% pass required
- E2E tests: 90% pass required
- Overall: 95% pass rate

**Performance:**
- Simple diagrams: <5s export time
- Complex diagrams: <30s export time
- Memory: <500MB peak
- CPU: <80% utilization

**Quality:**
- Resolution: >300 DPI
- All diagrams visible
- All text readable
- No artifacts or overlaps

---

## 🛠️ Maintenance

### When to Update Documentation
- New test cases added
- New scripts created
- Performance targets changed
- New features implemented
- Issues discovered and resolved

### Version Control
All test files should be versioned alongside implementation code:
- Use jj (Jujutsu) per CLAUDE.md instructions
- Commit test changes with implementation changes
- Tag test versions with releases

### Test Suite Updates
1. Add new test cases to TEST_MATRIX.csv
2. Update OBSIDIAN_MERMAID_TEST_PLAN.md with procedures
3. Update scripts if automation possible
4. Update this index if new files added
5. Run full regression test

---

## 📞 Getting Help

### For Test Execution Issues
1. Check TEST_CHECKLIST.md Common Issues section
2. Review test script output for specific errors
3. Check individual test logs in test-results-*/
4. See troubleshooting in OBSIDIAN_MERMAID_TEST_PLAN.md Section 8

### For Test Strategy Questions
1. Review TESTING_STRATEGY_SUMMARY.md
2. Consult OBSIDIAN_MERMAID_TEST_PLAN.md relevant sections
3. Check test case details in TEST_MATRIX.csv

### For Script Issues
1. Verify permissions: `ls -l *.sh`
2. Check syntax: `bash -n script.sh`
3. Run with debug: `bash -x script.sh`
4. Review script comments for requirements

---

## ✅ Pre-Implementation Checklist

Before starting implementation:
- [ ] All documentation reviewed
- [ ] Test environment prepared
- [ ] Dependencies installed
- [ ] Test scripts made executable
- [ ] Test matrix initialized
- [ ] Team briefed on test strategy

---

**Version:** 1.0
**Created:** 2025-11-16
**Last Updated:** 2025-11-16
**Maintained By:** Tester Agent (Agor Session a89e536a)

**Status:** Complete and Ready ✅
