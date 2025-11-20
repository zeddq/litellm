# Obsidian PDF Export - Test Checklist

Quick reference for testing the Obsidian PDF export system with Mermaid support.

## Pre-Test Setup Checklist

```
□ All dependencies installed (run ./validate-setup.sh)
□ Test vault created
□ Test documents ready (8 diagram types)
□ Log directory exists and writable (~/.obsidian-pandoc/logs)
□ tmux installed (for monitoring)
□ Environment variables set (if needed)
```

## Quick Test Commands

```bash
# 1. Validate setup
./validate-setup.sh

# 2. Run all diagram tests
./test-all-diagrams.sh

# 3. Validate logs
./validate-logs.sh ~/.obsidian-pandoc/logs

# 4. Performance benchmark
./benchmark-performance.sh

# 5. Regression tests
./run-regression-tests.sh

# 6. Master test runner (all tests)
./run-all-tests.sh
```

## Manual Testing Checklist

### Test 1: Single Diagram Export
```
□ Open test document with one diagram type
□ Start log monitoring (tmux with 4 panes)
□ Execute export via Obsidian Plugin
□ Monitor all 5 logging layers
□ Open generated PDF
□ Verify diagram quality
□ Check logs for errors
□ Record results
```

### Test 2: All Diagram Types
```
□ Open mermaid-test-document.md
□ Execute export
□ Wait for completion
□ Open PDF
□ For each diagram type:
  □ Diagram visible
  □ No rendering errors
  □ Text readable
  □ Layout correct
□ Check log summary
□ Document issues
```

### Test 3: Error Injection
```
□ Create document with intentional error
□ Execute export
□ Verify graceful failure
□ Check error message quality
□ Confirm error includes:
  □ Clear description
  □ Component identification
  □ Root cause
  □ Fix suggestions
  □ Log file path
□ Test recovery (fix and re-export)
```

### Test 4: Performance Benchmark
```
□ Run benchmark script
□ Review results CSV
□ Compare against targets
□ Identify slow diagram types
□ Document findings
```

### Test 5: Monitoring System
```
□ Start monitoring script
□ Start alert script
□ Perform normal exports (no alerts expected)
□ Inject error condition
□ Verify alert triggered within 30s
□ Check alert content
□ Stop monitoring scripts
```

## Log Validation Checklist

```
□ All log files created (wrapper.log, pandoc.log, mermaid.log)
□ Logs contain timestamps (ISO 8601 format)
□ Component tags present ([WRAPPER], [PANDOC], [MERMAID])
□ No permission errors
□ File sizes reasonable (<10MB)
□ Recent activity visible
□ Error entries reviewed
```

## Diagram Quality Checklist

For each diagram in PDF:

```
□ Diagram visible and complete
□ Resolution adequate (>200 DPI)
□ Text readable at 100% zoom
□ No pixelation or artifacts
□ Colors distinguishable (if applicable)
□ Layout not overlapping
□ All nodes/elements present
□ Relationships correct
□ Labels positioned properly
□ No page breaks mid-diagram
```

## Performance Validation Checklist

```
□ Export time within targets (<30s typical)
□ Memory usage acceptable (<500MB peak)
□ CPU usage reasonable (<80%)
□ No memory leaks
□ Temp files cleaned up
□ Log file growth controlled
```

## Error Handling Validation Checklist

```
□ Missing dependencies detected
□ Invalid syntax errors clear
□ Permission errors handled gracefully
□ Network failures managed (if applicable)
□ Disk space issues detected
□ Recovery procedures work
□ Error messages actionable
```

## Integration Validation Checklist

```
□ Obsidian Plugin → Wrapper chain works
□ Wrapper → Pandoc → Mermaid chain works
□ Logs flow through all 5 layers
□ Alerts trigger from log entries
□ Monitoring detects export events
□ Configuration files loaded correctly
```

## Test Results Recording

```
Test Date: _______________
Tester: _______________
Environment: macOS _______

Results:
□ Unit Tests: ___/15 passed
□ Integration Tests: ___/10 passed
□ E2E Tests: ___/8 passed
□ Performance Tests: ___/8 passed
□ Error Tests: ___/12 passed

Overall Pass Rate: ______%

Issues Found: _____
Critical: _____
High: _____
Medium: _____
Low: _____

Notes:
_______________________________
_______________________________
_______________________________
```

## Post-Test Checklist

```
□ Test results recorded
□ Test matrix updated
□ Bug reports filed
□ Performance data saved
□ PDF outputs archived
□ Logs reviewed and summarized
□ Test report generated
□ Cleanup completed (temp files removed)
□ Next steps identified
```

## Regression Testing Checklist

Run after any code/config changes:

```
□ All 8 diagram types still export
□ Logs generated for all 5 layers
□ PDF quality maintained
□ No new errors in logs
□ Performance within benchmarks
□ All scripts execute without errors
□ Configuration files still valid
□ Error handling still works
□ Recovery procedures still work
□ Backward compatibility confirmed
```

## Quick Diagnostic Commands

```bash
# Check dependencies
pandoc --version
node --version
npm list -g mermaid-filter

# Check logs
ls -lht ~/.obsidian-pandoc/logs/
grep -i error ~/.obsidian-pandoc/logs/*.log | tail -20

# Check system resources
top -l 1 | grep -E "^CPU|^PhysMem"

# Test basic export
echo "# Test" | pandoc -o /tmp/test.pdf && echo "✅ OK"

# Check for orphaned processes
ps aux | grep -E "pandoc|mermaid|node"

# Check disk space
df -h ~
```

## Common Issues Quick Reference

| Issue | Quick Fix |
|-------|-----------|
| Pandoc not found | `brew install pandoc` |
| mermaid-filter not found | `npm install -g mermaid-filter` |
| Permission denied | `chmod +x script.sh` |
| Invalid Mermaid syntax | Validate at mermaid.live |
| Logs not writable | `chmod 755 ~/.obsidian-pandoc/logs` |
| PDF empty | Check filter path in pandoc.yaml |
| Export slow | Close other apps, check CPU/memory |
| Alert not triggering | Verify alert script running |

## Test Phases Quick Reference

**Phase 1: Unit Testing (2-3 hours)**
- Test individual components in isolation
- All scripts, configs, dependencies

**Phase 2: Integration Testing (3-4 hours)**
- Test component interactions
- Full logging chain, export workflow

**Phase 3: E2E Testing (4-5 hours)**
- Test complete user workflows
- All diagram types, error scenarios

**Phase 4: Performance Testing (2-3 hours)**
- Benchmark all diagram types
- Measure resources, identify bottlenecks

**Phase 5: Error Testing (3-4 hours)**
- Test error handling and recovery
- All failure scenarios

**Total Estimated Time: 14-19 hours**

---

**For detailed test procedures, see: OBSIDIAN_MERMAID_TEST_PLAN.md**
