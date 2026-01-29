#!/bin/bash
# Submit test proposals to the DAHAO chain
# Run from the leviathan/ directory after starting the chain

set -e

CHAIN_DIR="../dahao"
PROPOSALS_DIR="simulation/proposals"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "  DAHAO Test Proposal Submission"
echo "=============================================="
echo ""

# Check if dahaod is available
if ! command -v dahaod &> /dev/null; then
    echo "dahaod not found. Make sure the chain is built."
    echo "Run: cd dahao && ignite chain build"
    exit 1
fi

# Submit each proposal with a delay
submit_proposal() {
    local file=$1
    local name=$(basename "$file" .json)

    echo -e "${YELLOW}Submitting: ${name}${NC}"

    dahaod tx gov submit-proposal "$file" \
        --from alice \
        --keyring-backend test \
        --chain-id dahao \
        --yes \
        --output json 2>/dev/null | jq -r '.txhash // "submitted"'

    echo -e "${GREEN}  ✓ Submitted${NC}"
    echo ""

    # Wait for tx to be processed
    sleep 3
}

# Submit all proposals
for proposal in "$PROPOSALS_DIR"/*.json; do
    if [ -f "$proposal" ]; then
        submit_proposal "$proposal"
    fi
done

echo "=============================================="
echo "  All proposals submitted!"
echo "  Run: dahaod q gov proposals"
echo "=============================================="
