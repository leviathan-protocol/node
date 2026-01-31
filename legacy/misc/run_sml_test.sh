#!/bin/bash
# SML Semantic Firewall Test Suite
# Tests persona-based voting decisions through the Observer Mode API

set -e

# Configuration
OBSERVER_URL="${OBSERVER_URL:-http://localhost:8080}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "  SML Semantic Firewall Test Suite"
echo "=============================================="
echo ""
echo "Observer URL: $OBSERVER_URL"
echo "Project Dir: $PROJECT_DIR"
echo ""

# Check if Observer is running
echo "Checking Observer Mode..."
if ! curl -s "$OBSERVER_URL/api/v1/status" > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Observer Mode is not running at $OBSERVER_URL${NC}"
    echo "Start it with: python main.py --mode observer --config config_dahao_subnet.yaml"
    exit 1
fi
echo -e "${GREEN}Observer is running${NC}"
echo ""

# Define test cases: persona + proposal ID + expected vote
# Format: "persona:proposal_id:expected_vote"
#
# Proposals:
#   1: Solar Panel Installation (eco-friendly)
#   2: Mining Operations (profit + environmental risk - ambiguous)
#   3: Community Education Program
#   4: AI Trading Bot
#   5: Coal Power Plant (anti-environmental)
#
TEST_CASES=(
    # eco_warrior should support green, reject harmful
    "eco_warrior:1:YES"     # Solar Panels - YES (clear green benefit)
    "eco_warrior:5:NO"      # Coal Power Plant - NO (clear environmental harm)

    # profit_maximizer - clear profit with no downsides
    "profit_maximizer:4:YES"  # AI Trading Bot - YES (ROI, no risk)

    # community_builder should support community initiatives
    "community_builder:3:YES"  # Community Education - YES (clear community benefit)

    # tech_progressive should support tech innovation
    "tech_progressive:4:YES"   # AI Trading Bot - YES (tech innovation)
)

PASSED=0
FAILED=0

echo "Running ${#TEST_CASES[@]} test cases..."
echo ""

for test_case in "${TEST_CASES[@]}"; do
    IFS=':' read -r persona proposal_id expected_vote <<< "$test_case"

    echo "----------------------------------------"
    echo -e "${YELLOW}Test: $persona voting on proposal #$proposal_id${NC}"
    echo "Expected: $expected_vote"

    # Run the mock phone with this persona/proposal
    cd "$PROJECT_DIR"

    # Capture output and exit code
    # Use --use-local-proposals to test with diverse proposals
    output=$(python tests/mock_phone_sml.py \
        --persona "$persona" \
        --proposal-id "$proposal_id" \
        --node-url "$OBSERVER_URL" \
        --use-ewoq \
        --use-local-proposals 2>&1) || true

    # Extract the vote from output
    actual_vote=$(echo "$output" | grep -oE "VOTE: (YES|NO|ABSTAIN)" | head -1 | cut -d' ' -f2)
    status_code=$(echo "$output" | grep -oE "Status: [0-9]+" | head -1 | cut -d' ' -f2)

    echo "Actual vote: $actual_vote"
    echo "API Status: $status_code"

    # Check result
    if [[ "$actual_vote" == "$expected_vote" && "$status_code" == "200" ]]; then
        echo -e "${GREEN}PASSED${NC}"
        ((PASSED++))
    else
        echo -e "${RED}FAILED${NC}"
        echo "Output:"
        echo "$output" | tail -20
        ((FAILED++))
    fi

    echo ""

    # Small delay between tests
    sleep 1
done

echo "=============================================="
echo "  Test Results"
echo "=============================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo "Total: $((PASSED + FAILED))"
echo ""

if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed${NC}"
    exit 1
fi
