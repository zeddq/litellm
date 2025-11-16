#!/bin/bash
# Automated performance benchmarking for Mermaid diagram exports
# Part of Obsidian PDF Export Test Suite

set -e

# Configuration
OUTPUT_FILE="performance-results.csv"
TEMP_DIR="/tmp/perf-bench-$$"
mkdir -p "$TEMP_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

DIAGRAM_TYPES=("flowchart" "sequence" "class" "state" "er" "gantt" "pie" "git")

echo "========================================="
echo "Performance Benchmarking Suite"
echo "========================================="
echo "Start time: $(date)"
echo

# Create CSV header
echo "Diagram_Type,Duration_Seconds,Memory_MB,CPU_Percent,File_Size_KB,Status" > "$OUTPUT_FILE"

# Performance targets (from test plan)
declare -A TARGETS_SIMPLE=(
    ["flowchart"]=2
    ["sequence"]=3
    ["class"]=2
    ["state"]=2
    ["er"]=2
    ["gantt"]=3
    ["pie"]=1
    ["git"]=2
)

# Track results
ON_TARGET=0
ABOVE_TARGET=0
FAILED=0

for type in "${DIAGRAM_TYPES[@]}"; do
    echo "========================================="
    echo "Benchmarking: $type"
    echo "========================================="

    input="test-$type.md"
    output="$TEMP_DIR/$type-bench.pdf"
    time_stats="$TEMP_DIR/time-stats-$type.txt"

    # Check if input exists
    if [ ! -f "$input" ]; then
        echo -e "${RED}❌ Input file not found: $input${NC}"
        echo "$type,0,0,0,0,FAILED" >> "$OUTPUT_FILE"
        ((FAILED++))
        continue
    fi

    # Measure execution time with resource monitoring
    start=$(date +%s.%N)

    # Run export with time monitoring
    if /usr/bin/time -l ./pandoc-wrapper.sh "$input" -o "$output" 2> "$time_stats"; then
        end=$(date +%s.%N)
        duration=$(echo "$end - $start" | bc)

        # Extract memory usage from time output (macOS specific)
        if [[ "$OSTYPE" == "darwin"* ]]; then
            memory_bytes=$(grep "maximum resident set size" "$time_stats" | awk '{print $1}')
            memory_mb=$((memory_bytes / 1024 / 1024))

            cpu_percent=$(grep "percent of CPU" "$time_stats" | awk '{print $1}' | tr -d '%' || echo "0")
        else
            # Linux fallback
            memory_kb=$(grep "Maximum resident set size" "$time_stats" | awk '{print $6}')
            memory_mb=$((memory_kb / 1024))

            cpu_percent=$(grep "Percent of CPU" "$time_stats" | awk '{print $1}' | tr -d '%' || echo "0")
        fi

        # Get output file size
        if [ -f "$output" ]; then
            file_size_bytes=$(stat -f%z "$output" 2>/dev/null || stat -c%s "$output")
            file_size_kb=$((file_size_bytes / 1024))
        else
            file_size_kb=0
        fi

        # Check against target
        target=${TARGETS_SIMPLE[$type]}
        status="PASS"

        if (( $(echo "$duration > $target" | bc -l) )); then
            status="ABOVE_TARGET"
            echo -e "${YELLOW}⚠️  Duration: ${duration}s (target: ${target}s)${NC}"
            ((ABOVE_TARGET++))
        else
            echo -e "${GREEN}✅ Duration: ${duration}s (target: ${target}s)${NC}"
            ((ON_TARGET++))
        fi

        echo "  Memory: ${memory_mb}MB"
        echo "  CPU: ${cpu_percent}%"
        echo "  File: ${file_size_kb}KB"

        # Record results
        echo "$type,$duration,$memory_mb,$cpu_percent,$file_size_kb,$status" >> "$OUTPUT_FILE"
    else
        echo -e "${RED}❌ Export failed${NC}"
        echo "$type,0,0,0,0,FAILED" >> "$OUTPUT_FILE"
        ((FAILED++))
    fi

    echo
done

# Generate summary report
echo "========================================="
echo "Performance Summary"
echo "========================================="

if [ -f "$OUTPUT_FILE" ]; then
    awk -F',' '
    NR>1 && $2 != "0" {
        sum_dur+=$2;
        sum_mem+=$3;
        sum_cpu+=$4;
        sum_size+=$5;
        count++
    }
    END {
        if (count > 0) {
            printf "Average Duration: %.2f s\n", sum_dur/count
            printf "Average Memory: %.0f MB\n", sum_mem/count
            printf "Average CPU: %.0f %%\n", sum_cpu/count
            printf "Average File Size: %.0f KB\n", sum_size/count
        }
    }' "$OUTPUT_FILE"
fi

echo
echo "Results by target:"
echo "  On target: $ON_TARGET"
echo "  Above target: $ABOVE_TARGET"
echo "  Failed: $FAILED"

total=$((ON_TARGET + ABOVE_TARGET + FAILED))
if [ $total -gt 0 ]; then
    pass_rate=$(echo "scale=1; $ON_TARGET * 100 / $total" | bc)
    echo "  Pass rate: ${pass_rate}%"
fi

echo
echo "Detailed results: $OUTPUT_FILE"
echo

# Identify slowest exports
echo "Slowest exports:"
tail -n +2 "$OUTPUT_FILE" | sort -t',' -k2 -rn | head -3 | while IFS=',' read -r type dur mem cpu size status; do
    echo "  $type: ${dur}s"
done

# Cleanup
rm -rf "$TEMP_DIR"

echo
echo "========================================="
echo "End time: $(date)"
echo "========================================="

# Exit code based on results
if [ $FAILED -gt 0 ]; then
    exit 1
elif [ $ABOVE_TARGET -gt 0 ]; then
    exit 2  # Warning: some tests above target
else
    exit 0
fi
