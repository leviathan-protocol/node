#!/bin/bash
#
# DAHAO Subnet Setup Script
#
# Creates and deploys a local Avalanche L1 blockchain for DAHAO governance.
# This is similar to running `ignite chain serve` for Cosmos - our own private chain.
#
# Usage:
#   ./scripts/setup_dahao_subnet.sh
#
# After running, you'll have:
#   - RPC URL: http://127.0.0.1:9650/ext/bc/dahao/rpc
#   - Chain ID: 43210
#   - Pre-funded EWOQ test account with 1M native tokens
#
# EWOQ Test Key (DO NOT USE IN PRODUCTION):
#   Address: 0x8db97C7cEcE249c2b98bDC0226Cc4C2A57BF52FC
#   Private Key: 56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}           DAHAO Subnet Setup (Avalanche L1)                ${NC}"
echo -e "${BLUE}============================================================${NC}"
echo

# Configuration
BLOCKCHAIN_NAME="dahao"
CHAIN_ID="43210"
TOKEN_SYMBOL="DAHAO"

# Step 1: Check/Install Avalanche CLI
echo -e "${YELLOW}Step 1: Checking Avalanche CLI...${NC}"

export PATH=~/bin:$PATH

if ! command -v avalanche &> /dev/null; then
    echo -e "${YELLOW}Avalanche CLI not found. Installing...${NC}"
    curl -sSfL https://raw.githubusercontent.com/ava-labs/avalanche-cli/main/scripts/install.sh | sh -s
    export PATH=~/bin:$PATH
fi

AVALANCHE_VERSION=$(avalanche --version)
echo -e "${GREEN}✓ Avalanche CLI: ${AVALANCHE_VERSION}${NC}"
echo

# Step 2: Clean existing network state
echo -e "${YELLOW}Step 2: Cleaning existing network state...${NC}"

# Stop any running local network
avalanche network stop 2>/dev/null || true

# Remove existing blockchain config if it exists
if avalanche blockchain list 2>/dev/null | grep -q "$BLOCKCHAIN_NAME"; then
    echo -e "${YELLOW}Removing existing '$BLOCKCHAIN_NAME' blockchain config...${NC}"
    avalanche blockchain delete "$BLOCKCHAIN_NAME" --force 2>/dev/null || true
fi

# Clean local network state
avalanche network clean --force 2>/dev/null || true

echo -e "${GREEN}✓ Clean state${NC}"
echo

# Step 3: Create DAHAO blockchain
echo -e "${YELLOW}Step 3: Creating '$BLOCKCHAIN_NAME' blockchain...${NC}"
echo -e "   Chain ID: ${CHAIN_ID}"
echo -e "   Token: ${TOKEN_SYMBOL}"
echo -e "   VM: Subnet-EVM"
echo

# EWOQ test address as ValidatorManager controller
EWOQ_ADDRESS="0x8db97C7cEcE249c2b98bDC0226Cc4C2A57BF52FC"

avalanche blockchain create "$BLOCKCHAIN_NAME" \
    --evm \
    --evm-chain-id "$CHAIN_ID" \
    --evm-token "$TOKEN_SYMBOL" \
    --proof-of-authority \
    --validator-manager-owner "$EWOQ_ADDRESS" \
    --test-defaults \
    --force

echo -e "${GREEN}✓ Blockchain created${NC}"
echo

# Step 4: Deploy locally
echo -e "${YELLOW}Step 4: Deploying '$BLOCKCHAIN_NAME' locally...${NC}"

avalanche blockchain deploy "$BLOCKCHAIN_NAME" --local --ewoq

echo -e "${GREEN}✓ Blockchain deployed${NC}"
echo

# Step 5: Get deployment info
echo -e "${YELLOW}Step 5: Getting deployment info...${NC}"

# Get the RPC URL from the deployment
RPC_URL=$(avalanche blockchain describe "$BLOCKCHAIN_NAME" 2>/dev/null | grep -E "RPC URL|Localhost" | head -1 | awk '{print $NF}' || echo "http://127.0.0.1:9650/ext/bc/$BLOCKCHAIN_NAME/rpc")

echo
echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}                   Deployment Summary                       ${NC}"
echo -e "${BLUE}============================================================${NC}"
echo
echo -e "${GREEN}DAHAO Subnet is now running!${NC}"
echo
echo -e "Network Configuration:"
echo -e "  Blockchain Name: ${GREEN}${BLOCKCHAIN_NAME}${NC}"
echo -e "  Chain ID:        ${GREEN}${CHAIN_ID}${NC}"
echo -e "  Token Symbol:    ${GREEN}${TOKEN_SYMBOL}${NC}"
echo -e "  RPC URL:         ${GREEN}http://127.0.0.1:9650/ext/bc/${BLOCKCHAIN_NAME}/rpc${NC}"
echo
echo -e "Pre-funded EWOQ Test Account (DO NOT USE IN PRODUCTION):"
echo -e "  Address:         ${GREEN}0x8db97C7cEcE249c2b98bDC0226Cc4C2A57BF52FC${NC}"
echo -e "  Private Key:     ${GREEN}56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027${NC}"
echo -e "  Balance:         ${GREEN}1,000,000 ${TOKEN_SYMBOL}${NC}"
echo
echo -e "${BLUE}============================================================${NC}"
echo
echo -e "Next Steps:"
echo -e "  1. Deploy contracts:"
echo -e "     ${YELLOW}cd contracts && npx hardhat run scripts/deploy_subnet.js --network dahaoSubnet${NC}"
echo
echo -e "  2. Update config_dahao_subnet.yaml with contract addresses"
echo
echo -e "  3. Run Observer Mode:"
echo -e "     ${YELLOW}python main.py --mode observer --config config_dahao_subnet.yaml${NC}"
echo
echo -e "To stop the network:"
echo -e "  ${YELLOW}avalanche network stop${NC}"
echo
echo -e "To restart the network:"
echo -e "  ${YELLOW}avalanche network start${NC}"
echo

# Export for use in other scripts
echo "# DAHAO Subnet Environment Variables" > /tmp/dahao_subnet_env.sh
echo "export DAHAO_RPC_URL=\"http://127.0.0.1:9650/ext/bc/${BLOCKCHAIN_NAME}/rpc\"" >> /tmp/dahao_subnet_env.sh
echo "export DAHAO_CHAIN_ID=\"${CHAIN_ID}\"" >> /tmp/dahao_subnet_env.sh
echo "export EWOQ_ADDRESS=\"0x8db97C7cEcE249c2b98bDC0226Cc4C2A57BF52FC\"" >> /tmp/dahao_subnet_env.sh
echo "export EWOQ_PRIVATE_KEY=\"56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027\"" >> /tmp/dahao_subnet_env.sh

echo -e "Environment variables saved to: ${GREEN}/tmp/dahao_subnet_env.sh${NC}"
echo -e "Source with: ${YELLOW}source /tmp/dahao_subnet_env.sh${NC}"
