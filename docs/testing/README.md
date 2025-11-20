# Obsidian PDF Export Testing Suite

Complete testing infrastructure for Obsidian PDF export system with Mermaid diagram support.

## 📦 What's Included

This testing suite provides everything needed to validate the Obsidian PDF export system:

### Documentation (3 files, 77.4 KB)
- **OBSIDIAN_MERMAID_TEST_PLAN.md** (60 KB) - Comprehensive test plan with 53+ test cases
- **TESTING_STRATEGY_SUMMARY.md** (11 KB) - Executive summary and quick reference
- **TEST_CHECKLIST.md** (6.4 KB) - Quick reference checklist for daily testing

### Automated Test Scripts (5 files, 26.8 KB)
- **run-all-tests.sh** (6.0 KB) - Master test runner, executes all suites
- **run-regression-tests.sh** (6.3 KB) - Regression testing suite
- **validate-logs.sh** (5.7 KB) - Log validation and quality checks
- **benchmark-performance.sh** (4.9 KB) - Performance benchmarking
- **test-all-diagrams.sh** (3.9 KB) - Diagram type testing

### Test Data (1 file, 3.8 KB)
- **TEST_MATRIX.csv** - Test case tracking matrix (53 test cases)

**Total: 9 files, 108 KB, 4,186 lines of code/documentation**

## 🚀 Quick Start

### 1. Prerequisites Check
```bash
# Verify all dependencies installed
./validate-setup.sh
```

### 2. Run First Test
```bash
# Test all diagram types
./test-all-diagrams.sh
```

### 3. Run Full Test Suite
```bash
# Execute all tests (15-20 minutes)
./run-all-tests.sh
```

### 4. Review Results
```bash
# Check summary
cat test-results-*/test-summary.txt

# Check performance data
cat test-results-*/performance-results.csv
```

## 📊 Test Coverage

### Test Distribution
- **53 total test cases** across 7 categories
- **15 critical** tests (must pass)
- **8 high priority** tests
- **4 medium priority** tests
- **60% automated**, 40% manual validation

### Test Categories
| Category | Tests | Automated | Manual |
|----------|-------|-----------|--------|
| Mermaid Diagrams | 8 | ✅ | ✅ |
| Logging Layers | 5 | ❌ | ✅ |
| Scripts | 5 | ✅ | ✅ |
| Configuration | 4 | ✅ | ✅ |
| Error Handling | 5 | ✅ | ✅ |
| Integration | 5 | Partial | ✅ |
| End-to-End | 4 | Partial | ✅ |
| Performance | 12 | ✅ | ❌ |
| Regression | 5 | ✅ | ✅ |

## 🎯 Test Scripts Overview

### run-all-tests.sh - Master Test Runner
**Purpose:** Execute all test suites in sequence
**Duration:** 15-20 minutes
**Output:** Consolidated test results in `test-results-*/`

**Usage:**
```bash
./run-all-tests.sh
```

**Features:**
- Runs 5 test suites sequentially
- Color-coded output (pass/fail/warn)
- Collects all artifacts
- Generates summary report
- Exit code: 0=pass, 1=fail

---

### test-all-diagrams.sh - Diagram Type Tests
**Purpose:** Test all 8 Mermaid diagram types
**Duration:** 5-10 minutes
**Output:** `/tmp/diagram-tests-*/`

**Usage:**
```bash
./test-all-diagrams.sh
```

**Tests:**
- Flowchart export
- Sequence diagram export
- Class diagram export
- State diagram export
- ER diagram export
- Gantt chart export
- Pie chart export
- Git graph export

**For Each Test:**
- Exports to PDF
- Measures duration
- Checks file size
- Validates output exists
- Logs to individual file

---

### validate-logs.sh - Log Quality Validation
**Purpose:** Validate log file structure and content
**Duration:** 1-2 minutes
**Output:** Console output + validation report

**Usage:**
```bash
./validate-logs.sh ~/.obsidian-pandoc/logs
```

**Checks:**
- Log files exist (wrapper.log, pandoc.log, mermaid.log)
- Timestamps valid (ISO 8601 format)
- Component tags present ([WRAPPER], [PANDOC], [MERMAID])
- File sizes reasonable (<10MB)
- Recent activity detected
- Error counts reported

---

### benchmark-performance.sh - Performance Testing
**Purpose:** Measure export performance metrics
**Duration:** 10-15 minutes
**Output:** `performance-results.csv`

**Usage:**
```bash
./benchmark-performance.sh
```

**Measures:**
- Export duration per diagram type
- Memory usage (MB)
- CPU utilization (%)
- Output file size (KB)

**Compares Against Targets:**
- Flowchart: <2s
- Sequence: <3s
- Class: <2s
- State: <2s
- ER: <2s
- Gantt: <3s
- Pie: <1s
- Git: <2s

**Output Format (CSV):**
```csv
Diagram_Type,Duration_Seconds,Memory_MB,CPU_Percent,File_Size_KB,Status
flowchart,1.8,180,45,120,PASS
sequence,2.9,210,52,145,PASS
gantt,28.5,320,78,250,ABOVE_TARGET
```

---

### run-regression-tests.sh - Regression Suite
**Purpose:** Ensure no functionality breakage after changes
**Duration:** 5-10 minutes
**Output:** `/tmp/obsidian-regression-*/regression-results.txt`

**Usage:**
```bash
./run-regression-tests.sh
```

**Test Areas:**
- Core functionality (diagram exports)
- Script functionality (wrapper, validator, monitor, alerts)
- Dependencies (pandoc, node, mermaid-filter)
- Configuration (YAML, JSON validity)
- Logging (directory, files, format)
- Error handling (missing files, syntax errors)

**Total Tests:** 20+ regression checks

---

## 📋 Test Matrix

Track test execution status in `TEST_MATRIX.csv`:

**Fields:**
- Test_ID (e.g., TC-MD-001)
- Category (Diagram, Logging, Script, etc.)
- Test_Name (descriptive name)
- Priority (Critical, High, Medium, Low)
- Automated (Yes/No)
- Manual (Yes/No)
- Status (Not Run, Pass, Fail, Skip)
- Duration (execution time)
- Notes (comments)
- Last_Run (timestamp)

**Update After Each Test Run:**
```bash
# Example: Mark TC-MD-001 as passed
sed -i '' 's/TC-MD-001,.*,Not Run/TC-MD-001,...,Pass,3.2s,Perfect rendering,2025-11-16/' TEST_MATRIX.csv
```

## 🎨 Test Output

### Color Coding
All test scripts use color-coded output:
- 🟢 **Green (✅)** - Test passed
- 🔴 **Red (❌)** - Test failed
- 🟡 **Yellow (⚠️)** - Warning or above target

### Example Output
```
=========================================
Testing: flowchart diagram
=========================================
✅ SUCCESS: flowchart
  Duration: 1.8s
  File size: 120KB

=========================================
Testing: gantt diagram
=========================================
⚠️  Duration: 28.5s (target: 3s)
  Memory: 320MB
  CPU: 78%
```

## 📈 Performance Benchmarks

### Target Metrics (Simple Diagrams)
| Diagram Type | Target | Acceptable | Unacceptable |
|--------------|--------|------------|--------------|
| Flowchart | <2s | <5s | >5s |
| Sequence | <3s | <7s | >7s |
| Class | <2s | <6s | >6s |
| State | <2s | <5s | >5s |
| ER | <2s | <6s | >6s |
| Gantt | <3s | <25s | >25s |
| Pie | <1s | <3s | >3s |
| Git | <2s | <7s | >7s |

### Resource Targets
- **Memory:** <500MB peak
- **CPU:** <80% single core
- **Disk I/O:** <100MB/s
- **Temp files:** Cleaned within 5s

## 🔍 Troubleshooting

### Test Script Fails to Run
```bash
# Check permissions
ls -l *.sh

# Make executable
chmod +x *.sh

# Check shell
bash --version  # Requires bash 4+
```

### No Test Data
```bash
# Scripts expect test documents like:
# - test-flowchart.md
# - test-sequence.md
# - test-class.md
# etc.

# Create from main test plan templates
# or from Coder agent implementation
```

### Permission Errors
```bash
# Ensure log directory writable
mkdir -p ~/.obsidian-pandoc/logs
chmod 755 ~/.obsidian-pandoc/logs

# Check temp directory
ls -ld /tmp
```

### Dependencies Missing
```bash
# Run setup validator
./validate-setup.sh

# Install missing dependencies
brew install pandoc
npm install -g mermaid-filter
npm install -g @mermaid-js/mermaid-cli
```

## 📚 Documentation Guide

### For Quick Testing
**Start here:** `TEST_CHECKLIST.md`
- Quick command reference
- Pre-test setup list
- Manual test procedures
- Common issues reference

### For Comprehensive Testing
**Read:** `OBSIDIAN_MERMAID_TEST_PLAN.md`
- Full test plan (60 KB)
- 53+ detailed test cases
- Step-by-step procedures
- Troubleshooting decision trees
- Performance benchmarks
- Success criteria
- Test reporting templates

### For Executive Overview
**Review:** `TESTING_STRATEGY_SUMMARY.md`
- High-level summary
- Implementation roadmap
- Key metrics and targets
- Quick start guide

## 🔄 Testing Workflow

### Initial Testing (Week 1)
```bash
# Day 1-2: Setup
./validate-setup.sh
./validate-logs.sh

# Day 3-4: Unit tests
./test-all-diagrams.sh
# Review each PDF output

# Day 5: Configuration
# Manual config validation
```

### Ongoing Testing (Weekly)
```bash
# Every week during development
./run-regression-tests.sh

# Every 2 weeks
./benchmark-performance.sh

# Monthly
./run-all-tests.sh
```

### Pre-Release Testing
```bash
# Full validation before release
./run-all-tests.sh

# Review all artifacts
ls -lh test-results-*/

# Sign off if pass rate >95%
```

## 📊 Success Metrics

### Pass Rate Requirements
- **Critical tests:** 100% must pass
- **High priority:** 95%+ pass rate
- **All tests:** 90%+ overall pass rate

### Quality Gates
- All PDFs generated successfully
- All diagrams visible in outputs
- All logs show complete chain
- Performance within 20% of targets
- No critical errors in logs

### Exit Codes
All test scripts use consistent exit codes:
- **0** - All tests passed
- **1** - One or more tests failed
- **2** - Tests passed but with warnings

## 🛠️ Customization

### Adding New Tests
1. Add test case to `TEST_MATRIX.csv`
2. Add test procedure to `OBSIDIAN_MERMAID_TEST_PLAN.md`
3. Add automated test to relevant script (if applicable)
4. Update test count in documentation

### Modifying Benchmarks
Edit performance targets in:
- `benchmark-performance.sh` (TARGETS_SIMPLE array)
- `OBSIDIAN_MERMAID_TEST_PLAN.md` (Section 3.3)

### Custom Test Suites
Create new script following pattern:
```bash
#!/bin/bash
# Your custom test suite

# Exit codes: 0=pass, 1=fail, 2=warn
# Color output: use GREEN, RED, YELLOW
# Log to file: tee to $OUTPUT_FILE
```

Add to `run-all-tests.sh`:
```bash
run_suite "Your Suite" "./your-script.sh" "optional"
```

## 📞 Support

### Getting Help
1. Check `TEST_CHECKLIST.md` for quick fixes
2. Review troubleshooting section in main test plan
3. Examine test logs in `test-results-*/`
4. Check individual script logs

### Reporting Issues
Include:
- Test script output
- Relevant log files
- Environment details (macOS version, dependency versions)
- Test matrix status

### Contributing
To improve the test suite:
1. Document findings in test notes
2. Update test matrix with results
3. Add new test cases for uncovered scenarios
4. Suggest performance optimizations

## 📝 File Reference

### Must-Have Files
```
OBSIDIAN_MERMAID_TEST_PLAN.md     - Main test plan
test-all-diagrams.sh              - Diagram testing
validate-logs.sh                  - Log validation
run-all-tests.sh                  - Master runner
TEST_CHECKLIST.md                 - Quick reference
```

### Optional but Recommended
```
benchmark-performance.sh          - Performance testing
run-regression-tests.sh           - Regression testing
TEST_MATRIX.csv                   - Test tracking
TESTING_STRATEGY_SUMMARY.md       - Executive summary
```

### Generated During Testing
```
test-results-YYYYMMDD-HHMMSS/     - Test artifacts
performance-results.csv           - Benchmark data
/tmp/diagram-tests-*/             - Diagram outputs
/tmp/obsidian-regression-*/       - Regression artifacts
```

## 🎓 Learning Path

### Level 1: Beginner
1. Read `TEST_CHECKLIST.md`
2. Run `./validate-setup.sh`
3. Run `./test-all-diagrams.sh`
4. Review generated PDFs

### Level 2: Intermediate
1. Read `TESTING_STRATEGY_SUMMARY.md`
2. Run `./run-all-tests.sh`
3. Analyze test results
4. Update `TEST_MATRIX.csv`

### Level 3: Advanced
1. Read full `OBSIDIAN_MERMAID_TEST_PLAN.md`
2. Perform manual test procedures
3. Customize benchmark targets
4. Integrate with CI/CD

## ⚡ Quick Commands Cheat Sheet

```bash
# Setup validation
./validate-setup.sh

# Single diagram test
./test-all-diagrams.sh

# Log validation
./validate-logs.sh

# Performance test
./benchmark-performance.sh

# Regression test
./run-regression-tests.sh

# Full test suite
./run-all-tests.sh

# View latest results
cat test-results-*/test-summary.txt

# View performance data
cat performance-results.csv

# Clean up old results
rm -rf test-results-*
```

## 📈 Metrics Dashboard (Manual)

Track these over time:
- [ ] Pass rate trending upward
- [ ] Performance improving
- [ ] Error count decreasing
- [ ] Test coverage increasing
- [ ] Mean time to detect (MTTD) decreasing
- [ ] Mean time to resolve (MTTR) decreasing

## 🎉 Success Indicators

You're ready for production when:
- ✅ All critical tests passing
- ✅ Pass rate >95%
- ✅ Performance within targets
- ✅ No errors in logs
- ✅ All diagram types export correctly
- ✅ Error messages clear and actionable
- ✅ Regression tests pass consistently

---

**Version:** 1.0
**Created:** 2025-11-16
**Maintained By:** Tester Agent (Agor Session a89e536a)

For detailed information, see the main test plan: `OBSIDIAN_MERMAID_TEST_PLAN.md`
