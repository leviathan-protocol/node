# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start (Local Development)

```bash
# 1. Install dependencies
uv sync

# 2. Start local Avalanche L1 blockchain
./scripts/setup_dahao_subnet.sh

# 3. Deploy contracts (requires Node 22)
cd contracts && npm install && source ~/.nvm/nvm.sh && nvm use 22 && npx hardhat run scripts/deploy_subnet.js --network dahaoSubnet && cd ..

# 4. Set relayer key (EWOQ test key)
export RELAYER_PRIVATE_KEY="56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027"

# 5. Start Ollama
ollama serve & ollama pull qwen3:14b

# 6. Run Observer Mode
python main.py --mode observer --config config_dahao_subnet.yaml
```

## Build and Run Commands

This project uses `uv` for Python package management.

```bash
# Install dependencies
uv sync

# Run the sidecar (Decider Mode - autonomous voting)
uv run python main.py --mode decider

# Run the sidecar (Observer Mode - API gateway for mobile voting)
uv run python main.py --mode observer

# Syntax check all modules
uv run python -m py_compile main.py config/*.py chain/*.py brain/*.py sidecar/*.py models/*.py data/*.py api/*.py modes/*.py

# Run tests
uv run pytest tests/ -v

# Test imports
uv run python -c "from data import SharedLaw; print(SharedLaw().summary())"
```

## Operation Modes

The sidecar supports two operation modes:

| Mode | Description | Use Case |
|------|-------------|----------|
| **Decider** | Autonomous voting agent | Validators running their own nodes |
| **Observer** | API gateway for mobile clients | Gasless voting for mobile users |

### Decider Mode (Default)
```bash
python main.py --mode decider --fork fork.yaml
```
- Polls chain for new proposals
- Uses LLM to make voting decisions based on Fork principles
- Submits votes automatically using node wallet

### Observer Mode
```bash
python main.py --mode observer --host 0.0.0.0 --port 8000
```
- Runs FastAPI server for mobile clients
- Validates signed voting intents
- Executes votes on behalf of users (gasless)
- Supports both Cosmos (Authz) and EVM (meta-transactions)

## Multi-Chain Support

The sidecar supports both Cosmos SDK and EVM chains via the Chain Adapter pattern:

| Chain Type | Networks | Authorization | Gasless Mechanism |
|------------|----------|---------------|-------------------|
| **Cosmos** | DAHAO, Cosmos Hub | Authz Module | MsgExec |
| **EVM** | Avalanche, Ethereum | Token Delegation | EIP-2771 Meta-Tx |

### Chain Adapter Pattern
```python
from chain.adapter import create_chain_adapter
from config.settings import ChainConfig

# Cosmos chain
cosmos_config = ChainConfig(type="cosmos", chain_id="dahao")
cosmos_adapter = create_chain_adapter(cosmos_config)

# EVM chain (Local DAHAO Subnet - PRIMARY)
evm_config = ChainConfig(type="evm", chain_id="43210", rpc_url="http://127.0.0.1:9654/ext/bc/.../rpc")
evm_adapter = create_chain_adapter(evm_config)

# Both implement the same interface
proposals = adapter.fetch_proposals()
result = adapter.submit_vote_on_behalf(voter, proposal_id, vote, signature)
```

## Prerequisites

### For Cosmos Chains (Decider Mode)

1. **DAHAO Chain Running**:
   ```bash
   cd dahao && ignite chain serve
   ```
   This starts gRPC on `localhost:9090`.

2. **Wallet Mnemonic**:
   ```bash
   export LEVIATHAN_MNEMONIC="your twenty four word mnemonic phrase here ..."
   ```

### For EVM Chains - PRIMARY: Local DAHAO Subnet

Run a private Avalanche L1 blockchain for local development. This is the **recommended approach** - free, fast, and fully isolated.

```bash
# 1. Start the DAHAO Subnet
./scripts/setup_dahao_subnet.sh

# 2. Deploy contracts to subnet
cd contracts && npx hardhat run scripts/deploy_subnet.js --network dahaoSubnet

# 3. Set relayer key (EWOQ test key - auto-funded)
export RELAYER_PRIVATE_KEY="56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027"

# 4. Run Observer Mode
python main.py --mode observer --config config_dahao_subnet.yaml
```

**DAHAO Subnet Details:**

| Setting | Value |
|---------|-------|
| Chain ID | 43210 |
| RPC URL | `http://127.0.0.1:9654/ext/bc/<blockchain_hash>/rpc` |
| Token Symbol | DAHAO |
| EWOQ Test Address | `0x8db97C7cEcE249c2b98bDC0226Cc4C2A57BF52FC` |
| EWOQ Private Key | `56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027` |
| EWOQ Balance | 1,000,000 DAHAO (native + governance tokens) |

**Subnet Management:**
```bash
# Stop the subnet
avalanche network stop

# Restart the subnet
avalanche network start

# View subnet info
avalanche blockchain describe dahao
```

### For EVM Chains - ALTERNATIVE: Fuji Testnet

For public demos or multi-node testing, use Avalanche Fuji testnet instead.

1. **Deploy Contracts**:
   ```bash
   cd contracts
   npm install
   source ~/.nvm/nvm.sh && nvm use 22
   npx hardhat compile
   npx hardhat run scripts/deploy_fuji.js --network fuji
   ```

2. **Set Relayer Private Key**:
   ```bash
   export RELAYER_PRIVATE_KEY="0x..."  # Your funded wallet
   ```

3. **Fund Relayer Wallet** with test AVAX from [Fuji Faucet](https://faucet.avax.network/).

4. **Run with Fuji config**:
   ```bash
   python main.py --mode observer --config config_fuji.yaml
   ```

### For Both Modes

**Ollama Running** with a model:
```bash
ollama serve
ollama pull qwen3:14b
```

## Architecture

### Decider Mode Architecture
```
┌─────────────────────────────────────────────────────────┐
│                    DAHAO Sidecar (Python)               │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐    │
│  │  Chain   │◄──│ Sidecar  │──►│      Brain       │    │
│  │ Adapter  │   │  Loop    │   │    (Ollama)      │    │
│  └────┬─────┘   └────┬─────┘   └────────┬─────────┘    │
│       │              │                   │              │
│       ▼              ▼                   ▼              │
│  ┌──────────┐  ┌──────────┐        ┌──────────┐        │
│  │ Wallet   │  │  Shared  │        │   Fork   │        │
│  │(mnemonic)│  │   Law    │        │ (values) │        │
│  └──────────┘  └──────────┘        └──────────┘        │
└─────────────────────────────────────────────────────────┘
         │                                  │
         ▼                                  ▼
   ┌───────────┐                     ┌───────────┐
   │  Cosmos/  │                     │  Ollama   │
   │   EVM     │                     │  Server   │
   └───────────┘                     └───────────┘
```

### Observer Mode Architecture (Gasless Voting)
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Mobile    │     │   DAHAO     │     │   Chain     │     │   Smart     │
│    Phone    │────►│   Node      │────►│  Adapter    │────►│  Contract   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
      │                   │                   │                   │
      │ 1. Sign intent    │                   │                   │
      │    (ECDSA/EIP712) │                   │                   │
      │                   │                   │                   │
      │ 2. POST /submit   │                   │                   │
      │────────────────────►                   │                   │
      │                   │                   │                   │
      │                   │ 3. Validate:      │                   │
      │                   │    - Signature    │                   │
      │                   │    - Authorization│                   │
      │                   │    - Reasoning    │                   │
      │                   │                   │                   │
      │                   │ 4. Execute vote   │                   │
      │                   │   (node pays gas) │                   │
      │                   │───────────────────►                   │
      │                   │                   │───────────────────►
```

## Project Structure

```
leviathan/
├── main.py                 # Entry point with --mode flag
├── config.yaml             # Cosmos (Decider Mode)
├── config_dahao_subnet.yaml # EVM PRIMARY (Local Avalanche L1)
├── config_fuji.yaml        # EVM ALTERNATIVE (Fuji testnet)
├── fork.yaml               # User's voting principles
│
├── modes/                  # Operation modes
│   ├── __init__.py
│   ├── decider.py          # Autonomous voting loop
│   └── observer.py         # FastAPI server for mobile
│
├── api/                    # Observer Mode REST API
│   ├── server.py           # FastAPI app factory
│   └── routes/
│       ├── pair.py         # /invite, /connect, /register
│       ├── proposals.py    # /proposals
│       ├── vote.py         # /submit_vote (Cosmos + EVM)
│       └── status.py       # /status
│
├── chain/                  # Multi-chain support
│   ├── adapter.py          # ChainAdapter ABC + factory
│   ├── cosmos_adapter.py   # Cosmos SDK implementation
│   ├── evm_adapter.py      # EVM implementation (Web3.py)
│   ├── evm_client.py       # Low-level Web3 client
│   ├── evm_meta_tx.py      # EIP-2771 meta-transactions
│   ├── client.py           # Legacy Cosmos client
│   ├── governance.py       # Legacy governance queries
│   ├── wallet.py           # Cosmos wallet manager
│   └── authz.py            # Cosmos Authz helpers
│
├── contracts/              # Solidity contracts (EVM)
│   ├── src/
│   │   ├── DAHAOToken.sol      # ERC20Votes governance token
│   │   ├── DAHAOGovernor.sol   # Governor with ERC2771Context
│   │   └── DAHAOForwarder.sol  # EIP-2771 Forwarder
│   ├── scripts/
│   │   ├── deploy_subnet.js    # Deploy to local DAHAO Subnet (PRIMARY)
│   │   └── deploy_fuji.js      # Deploy to Fuji testnet (ALTERNATIVE)
│   └── hardhat.config.js   # Network configuration
│
├── validator/              # Semantic firewall
│   ├── __init__.py
│   ├── signature.py        # ECDSA signature verification
│   ├── authz.py            # Authz grant checking
│   └── semantic.py         # Reasoning consistency validation
│
├── brain/                  # LLM integration
│   ├── llm.py              # Ollama wrapper
│   ├── prompts.py          # Voting prompts
│   └── decision.py         # Vote decision logic
│
├── config/
│   ├── settings.py         # Pydantic settings (Cosmos + EVM)
│   └── fork.py             # Fork model with validation
│
├── models/
│   ├── proposal.py         # Proposal dataclass
│   └── vote.py             # VoteChoice, VoteDecision
│
├── data/                   # Shared Law data files
│   ├── terms.json
│   ├── principles.json
│   ├── rules.json
│   └── governance.json
│
├── tests/
│   ├── test_observer_mode.py   # 19 API tests
│   ├── test_evm_meta_tx.py     # 15 meta-tx tests
│   ├── mock_phone.py           # Cosmos phone simulator
│   ├── mock_phone_evm.py       # EVM phone simulator
│   └── mock_phone_sml.py       # SML phone with persona-based voting
│
└── scripts/
    ├── setup_dahao_subnet.sh  # Start local Avalanche L1
    ├── run_sml_test.sh        # SML semantic firewall tests
    └── demo_meta_tx.py        # EIP-712 signing demo
```

## Configuration Files

### config.yaml (Cosmos - Decider Mode)
```yaml
chain:
  type: cosmos
  chain_id: "dahao"
  grpc_url: "grpc+http://localhost:9090"
  fee_denom: "stake"
  address_prefix: "cosmos"

llm:
  model_name: "qwen3:14b"
  ollama_host: "http://localhost:11434"

sidecar:
  poll_interval_seconds: 60
```

### config_dahao_subnet.yaml (EVM PRIMARY - Local Avalanche L1)
```yaml
chain:
  type: evm
  chain_id: "43210"
  rpc_url: "http://127.0.0.1:9654/ext/bc/<blockchain_hash>/rpc"

  # Contract addresses (auto-generated by deploy_subnet.js)
  governor_address: "0x..."   # DAHAOGovernor
  token_address: "0x..."      # DAHAOToken
  forwarder_address: "0x..."  # DAHAOForwarder

llm:
  model_name: "qwen3:14b"
  ollama_host: "http://localhost:11434"

# Env: RELAYER_PRIVATE_KEY=56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027
```

### config_fuji.yaml (EVM ALTERNATIVE - Fuji Testnet)
```yaml
chain:
  type: evm
  chain_id: "43113"  # Fuji testnet
  rpc_url: "https://api.avax-test.network/ext/bc/C/rpc"

  # Contract addresses (from deploy_fuji.js output)
  governor_address: "0x..."   # DAHAOGovernor
  token_address: "0x..."      # DAHAOToken
  forwarder_address: "0x..."  # DAHAOForwarder

llm:
  model_name: "qwen3:14b"
  ollama_host: "http://localhost:11434"

# Env: RELAYER_PRIVATE_KEY=0x... (your funded wallet)
```

## Key Implementation Patterns

### Chain Adapter Interface
```python
from chain.adapter import ChainAdapter, ChainType

class ChainAdapter(ABC):
    @property
    def chain_type(self) -> ChainType: ...
    @property
    def is_connected(self) -> bool: ...

    def fetch_proposals(self, status: str | None = None) -> list[Proposal]: ...
    def submit_vote(self, voter, proposal_id, vote, private_key) -> VoteResult: ...
    def submit_vote_on_behalf(self, voter, proposal_id, vote, signature) -> VoteResult: ...
    def check_delegation(self, delegator, delegate) -> DelegationInfo: ...
    def get_voting_power(self, address) -> int: ...
```

### EVM Meta-Transaction Flow
```python
from chain.evm_meta_tx import MetaTransactionRelayer, encode_cast_vote

# Build ForwardRequest
relayer = MetaTransactionRelayer(client, forwarder_address, abi)
call_data = encode_cast_vote(proposal_id=42, support=1)  # 1=For
request = relayer.build_forward_request(
    from_addr=user_address,
    to_addr=governor_address,
    data=call_data,
)

# User signs EIP-712 typed data (off-chain)
typed_data = relayer.get_eip712_typed_data(request)
signature = user_wallet.sign_typed_data(typed_data)

# Relayer executes (pays gas)
receipt = relayer.execute_and_wait(request, signature)
```

### Observer Mode Vote Submission
```python
# POST /api/v1/submit_vote

# Cosmos request
{
    "proposal_id": 1,
    "voter_address": "cosmos1...",
    "vote_option": "YES",
    "public_reasoning": "This benefits the network",
    "intent_signature": "<base64>",  # ECDSA signature
    "pub_key": "<base64>"
}

# EVM request
{
    "proposal_id": 1,
    "voter_address": "0x...",
    "vote_option": "YES",
    "public_reasoning": "This benefits the network",
    "eip712_signature": "0x...",  # EIP-712 signature
    "reasoning_hash": "0x..."     # Optional IPFS hash
}
```

### SharedLaw Loading
```python
from data import SharedLaw

shared_law = SharedLaw()
term = shared_law.get_term("@purpose")
locked = shared_law.get_locked_principles()
```

### Fork Validation
```python
from config.fork import Fork, ForkValidationError

fork = Fork.from_yaml("fork.yaml")
try:
    fork.validate_against(shared_law)
except ForkValidationError as e:
    print(f"Violations: {e.violations}")
```

## CLI Arguments

```bash
# Decider Mode
python main.py --mode decider \
    --fork fork.yaml \
    --wallet "mnemonic..." \
    --config config.yaml

# Observer Mode (Local DAHAO Subnet)
python main.py --mode observer \
    --host 0.0.0.0 \
    --port 8000 \
    --config config_dahao_subnet.yaml
```

| Argument | Description |
|----------|-------------|
| `--mode` | `decider` or `observer` (default: decider) |
| `--config` | Path to config.yaml |
| `--fork` | Path to fork.yaml (decider mode) |
| `--wallet` | 24-word mnemonic (Cosmos) |
| `--host` | API server host (observer mode) |
| `--port` | API server port (observer mode) |
| `--data-dir` | Shared law data directory |
| `--skip-fork-validation` | Skip fork validation |
| `--log-level` | DEBUG, INFO, WARNING, ERROR |

## Observer Mode API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/invite` | GET | Get pairing invite code |
| `/api/v1/connect` | POST | Connect with invite code |
| `/api/v1/register` | POST | Register voter address |
| `/api/v1/proposals` | GET | List active proposals |
| `/api/v1/submit_vote` | POST | Submit signed vote |
| `/api/v1/status` | GET | Node status |

## Solidity Contracts (EVM)

### DAHAOToken.sol
- ERC20 with ERC20Votes for governance
- ERC20Permit for gasless approvals
- Initial supply: 1,000,000 DAHAO

### DAHAOGovernor.sol
- OpenZeppelin Governor with extensions
- ERC2771Context for meta-transactions
- Custom `castVoteWithReasoningHash()` function
- Voting delay: 1 day, period: 1 week, quorum: 4%

### DAHAOForwarder.sol
- ERC2771Forwarder for meta-transactions
- EIP-712 typed data signing
- Nonce-based replay protection

### Deploying Contracts
```bash
cd contracts
npm install
source ~/.nvm/nvm.sh && nvm use 22
npx hardhat compile

# PRIMARY: Deploy to local DAHAO Subnet
npx hardhat run scripts/deploy_subnet.js --network dahaoSubnet

# ALTERNATIVE: Deploy to Fuji testnet
npx hardhat run scripts/deploy_fuji.js --network fuji
```

## Testing

### Run All Tests
```bash
uv run pytest tests/ -v
```

### Test Observer Mode
```bash
# Start observer
python main.py --mode observer &

# Run mock phone (Cosmos)
python tests/mock_phone.py --node-url http://localhost:8000

# Run mock phone (EVM)
python tests/mock_phone_evm.py --node-url http://localhost:8000
```

### Test Meta-Transactions
```bash
uv run python scripts/demo_meta_tx.py
```

### Test SML Semantic Firewall
Tests the full flow: Phone (small LLM) → Observer (large LLM) → Blockchain

The SML phone uses qwen3:4b to analyze proposals based on persona values, generates reasoning, and submits to the Observer which validates reasoning consistency using qwen3:14b.

```bash
# Run all SML tests (requires Observer running)
./scripts/run_sml_test.sh

# Test individual persona/proposal combinations
python tests/mock_phone_sml.py --persona eco_warrior --proposal-id 1 --use-ewoq --use-local-proposals
python tests/mock_phone_sml.py --persona profit_maximizer --proposal-id 4 --use-ewoq --use-local-proposals

# List available personas and proposals
python tests/mock_phone_sml.py --list-personas
python tests/mock_phone_sml.py --list-proposals
```

**Test Scenarios:**
| Persona | Proposal | Expected | Rationale |
|---------|----------|----------|-----------|
| eco_warrior | Solar Panels (#1) | YES | Aligns with environmental values |
| eco_warrior | Coal Plant (#5) | NO | Conflicts with environmental values |
| profit_maximizer | AI Trading Bot (#4) | YES | Aligns with profit/ROI values |
| community_builder | Education Program (#3) | YES | Aligns with community values |
| tech_progressive | AI Trading Bot (#4) | YES | Aligns with tech innovation values |

**Key Flags:**
- `--use-ewoq`: Use pre-funded EWOQ test account (has 1M DAHAO tokens)
- `--use-local-proposals`: Use built-in diverse test proposals instead of API

**Requires:** `ollama pull qwen3:4b` (phone) + `ollama pull qwen3:14b` (observer)

## Environment Variables

| Variable | Description |
|----------|-------------|
| `LEVIATHAN_MNEMONIC` | Cosmos wallet mnemonic (24 words) |
| `RELAYER_PRIVATE_KEY` | EVM relayer private key (0x...) |
| `FUJI_RPC_URL` | Custom Avalanche Fuji RPC URL |
| `SNOWTRACE_API_KEY` | Snowtrace API key for verification |

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `No RELAYER_PRIVATE_KEY set` | Missing env var for EVM | `export RELAYER_PRIVATE_KEY="0x..."` |
| `Governor address not configured` | Missing contract address | Update config_dahao_subnet.yaml or config_fuji.yaml |
| `Forwarder ABI not found` | Contracts not compiled | `cd contracts && npx hardhat compile` |
| `Invalid signature` | EIP-712 domain mismatch | Verify chain ID and forwarder address |
| `No voting power` | Tokens not delegated | Call `token.delegate(address)` |
| `not_delegated` error | Has tokens but no voting power | User must delegate to self |
| Node.js version error | Hardhat requires Node 22 LTS | `nvm use 22` |
| `ForkValidationError` | Fork violates shared law | Fix fork.yaml or use `--skip-fork-validation` |
| `avalanche: command not found` | Avalanche CLI not in PATH | `export PATH=~/bin:$PATH` |
| DAHAO Subnet not responding | Subnet stopped | `avalanche network start` |
| `network is not running` | Normal during clean | Not an error, just informational |
| RPC URL changed after restart | Blockchain hash regenerated | Re-run `setup_dahao_subnet.sh` |

## Gasless Voting Flow Summary

### Cosmos (Authz)
1. User grants MsgVote authorization to node
2. User signs voting intent (ECDSA secp256k1)
3. Node validates signature + authz + reasoning
4. Node wraps vote in MsgExec and broadcasts
5. Node pays gas fees

### EVM (Meta-Transactions)
1. User delegates voting power (token.delegate)
2. User signs EIP-712 ForwardRequest
3. Node validates signature + voting power + reasoning
4. Node calls forwarder.execute(request, signature)
5. Forwarder verifies and calls Governor
6. Governor sees user as msg.sender
7. Node pays gas fees
