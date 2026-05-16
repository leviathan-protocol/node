# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start (Local Development)

```bash
# 1. Install dependencies
uv sync

# 2. Start local Avalanche L1 blockchain
./scripts/setup_leviathan_subnet.sh

# 3. Deploy contracts (requires Node 22)
cd contracts && npm install && source ~/.nvm/nvm.sh && nvm use 22 && npx hardhat run scripts/deploy_leviathan.js --network leviathanSubnet && cd ..

# 4. Set relayer key (EWOQ test key)
export RELAYER_PRIVATE_KEY="56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027"

# 5. Start Ollama
ollama serve & ollama pull qwen3:14b

# 6. Run Validator Node
python node/validator.py
```

## Build and Run Commands

This project uses `uv` for Python package management.

```bash
# Install dependencies
uv sync

# Run the validator node (listens for quests, verifies with LLM)
uv run python node/validator.py

# Run the sidecar (Observer Mode - API gateway)
uv run python main.py --mode observer

# Syntax check all modules
uv run python -m py_compile main.py config/*.py chain/*.py brain/*.py sidecar/*.py data/*.py api/*.py modes/*.py adapter/*.py validator/*.py node/*.py

# Test imports
uv run python -c "from data import SharedLaw; print(SharedLaw().summary())"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Leviathan Protocol                        │
│                                                              │
│   ┌──────────┐    ┌──────────┐    ┌──────────────────┐      │
│   │  Agent   │───►│ QuestBoard│◄───│   Validator Node │      │
│   │  (AI)    │    │ Contract │    │   (Python+LLM)   │      │
│   └──────────┘    └────┬─────┘    └────────┬─────────┘      │
│        │               │                    │                │
│        ▼               ▼                    ▼                │
│   ┌──────────┐    ┌──────────┐        ┌──────────┐          │
│   │ Reputation│    │  Token   │        │  Ollama  │          │
│   │ (XP/Rank)│    │ (LVTN)   │        │  Server  │          │
│   └──────────┘    └──────────┘        └──────────┘          │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
                   ┌───────────┐
                   │ Avalanche │
                   │    L1     │
                   └───────────┘
```

## Quest Workflow

```
1. Sponsor creates quest (tokens locked)
         │
         ▼
2. Agent claims quest
         │
         ▼
3. Agent submits proof (GitHub, IPFS link)
         │
         ▼
4. Validator Node verifies with LLM
         │
    ┌────┴────┐
    ▼         ▼
APPROVED   REJECTED
    │         │
    ▼         ▼
Agent gets   Quest returns
85% bounty   to Open status
```

## Project Structure

```
leviathan/
├── main.py                     # Entry point with --mode flag
├── config_leviathan_subnet.yaml # EVM config (Local Avalanche L1)
├── fork.yaml                   # User's voting principles
├── pyproject.toml              # uv project config
│
├── node/                       # Validator Node
│   ├── __init__.py
│   └── validator.py            # Quest verification with LLM
│
├── adapter/                    # Persona/Fork adapter pattern
│   ├── __init__.py
│   ├── loader.py               # Model loading utilities
│   ├── mapper.py               # Data transformation
│   ├── models.py               # Domain data models
│   ├── cache.py                # Caching layer
│   └── prompts.py              # Adapter prompts
│
├── api/                        # REST API server
│   ├── __init__.py
│   ├── server.py               # FastAPI app factory
│   └── routes/
│       ├── __init__.py
│       ├── audit.py            # /api/v1/audit_action endpoint
│       └── status.py           # /api/v1/status endpoint
│
├── brain/                      # LLM integration
│   ├── __init__.py
│   ├── llm.py                  # Ollama wrapper
│   ├── prompts.py              # Voting prompts
│   └── decision.py             # Vote decision logic
│
├── chain/                      # EVM chain support
│   ├── __init__.py
│   ├── adapter.py              # ChainAdapter ABC + factory
│   ├── evm_adapter.py          # EVM implementation
│   ├── evm_client.py           # Web3.py client
│   ├── evm_meta_tx.py          # EIP-2771 meta-transactions
│   ├── governance.py           # Governance queries
│   └── wallet.py               # Wallet manager
│
├── config/                     # Configuration
│   ├── __init__.py
│   ├── settings.py             # Pydantic settings
│   └── fork.py                 # Fork model with validation
│
├── contracts/                  # Solidity contracts (EVM)
│   ├── src/
│   │   ├── LeviathanToken.sol      # ERC20Votes token (1B supply)
│   │   ├── LeviathanGovernor.sol   # Governor with ERC2771Context
│   │   ├── LeviathanForwarder.sol  # EIP-2771 Forwarder
│   │   ├── QuestBoard.sol          # Job marketplace for AI agents
│   │   └── Reputation.sol          # XP/Rank system for agents
│   ├── scripts/
│   │   ├── deploy_leviathan.js     # Full deployment (Token+Quest+Rep)
│   │   ├── deploy_subnet.js        # Deploy to local subnet
│   │   └── deploy_fuji.js          # Deploy to Fuji testnet
│   └── hardhat.config.js
│
├── data/                       # Shared Law data files
│   ├── __init__.py
│   ├── loader.py               # Data loading utilities
│   ├── models.py               # Data models
│   ├── sync.py                 # Data synchronization
│   ├── terms.json
│   ├── principles.json
│   ├── rules.json
│   ├── governance.json
│   ├── domains.json
│   └── security/               # Security audit data
│       ├── security_terms.json
│       ├── security_principles.json
│       └── security_rules.json
│
├── docs/
│   └── PROTOCOL.md             # Protocol documentation
│
├── modes/                      # Operation modes
│   ├── __init__.py
│   └── auditor.py              # Security auditor (Runtime Guardian)
│
├── sidecar/                    # Core sidecar loop
│   ├── __init__.py
│   ├── loop.py                 # Main polling/voting loop
│   ├── logger.py               # Logging utilities
│   └── state.py                # State management
│
├── scripts/
│   ├── setup_leviathan_subnet.sh   # Start local Avalanche L1
│   └── simulate_moltbook.py        # Security audit simulation
│
├── simulation/                 # Security simulation
│   ├── justitia_fork.yaml          # Justitia persona
│   └── security_test_scenarios.json
│
└── validator/                  # Validation layer
    ├── __init__.py
    ├── signature.py            # ECDSA signature verification
    └── semantic.py             # Reasoning consistency validation
```

## Solidity Contracts

### LeviathanToken.sol
- ERC20 with ERC20Votes for governance
- ERC20Permit for gasless approvals
- Total supply: 1,000,000,000 LVTN

### QuestBoard.sol
- Decentralized job marketplace for AI agents
- Sponsors lock bounty tokens when creating quests
- Agents claim quests, submit proof, get paid
- Fee distribution: 85% agent, 10% validator, 5% treasury

### Reputation.sol
- XP-based ranking system for agents
- Ranks: Novice (0-99) → Sentinel (100-499) → Guardian (500-1999) → Arbiter (2000+)
- Arbiter rank required for governance voting
- Domain-specific XP tracking

### LeviathanGovernor.sol
- OpenZeppelin Governor with extensions
- ERC2771Context for meta-transactions
- Voting delay: 1 day, period: 1 week, quorum: 4%

### LeviathanForwarder.sol
- ERC2771Forwarder for meta-transactions
- EIP-712 typed data signing
- Nonce-based replay protection

## Deploying Contracts

```bash
cd contracts
npm install
source ~/.nvm/nvm.sh && nvm use 22
npx hardhat compile

# Full deployment (Token + QuestBoard + Reputation)
npx hardhat run scripts/deploy_leviathan.js --network leviathanSubnet

# Or just governance contracts
npx hardhat run scripts/deploy_subnet.js --network leviathanSubnet
```

## Configuration

### config_leviathan_subnet.yaml (Local Avalanche L1)
```yaml
chain:
  type: evm
  chain_id: "43210"
  rpc_url: "http://127.0.0.1:9654/ext/bc/<blockchain_hash>/rpc"
  token_address: "0x..."
  quest_board_address: "0x..."
  reputation_address: "0x..."

llm:
  model_name: "qwen3:14b"
  ollama_host: "http://localhost:11434"

sidecar:
  poll_interval_seconds: 60
```

### fork.yaml (Voting Principles)
```yaml
name: "Security-First Validator"
principles:
  - "Prioritize network security over feature velocity"
  - "Support decentralization and resist centralization of power"
voting_style: "cautious"
abstain_threshold: 0.6
```

## CLI Arguments

```bash
# Run validator node (primary mode)
python node/validator.py

# Run observer mode API (status + security audit)
python main.py --mode observer \
    --host 0.0.0.0 \
    --port 8080 \
    --config config_leviathan_subnet.yaml
```

| Argument | Description |
|----------|-------------|
| `--mode` | `observer` (API server mode) |
| `--config` | Path to config.yaml |
| `--host` | API server host (observer mode) |
| `--port` | API server port (observer mode) |
| `--data-dir` | Shared law data directory |
| `--log-level` | DEBUG, INFO, WARNING, ERROR |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/status` | GET | Node status |
| `/api/v1/audit_action` | POST | Submit action for security review |
| `/api/v1/audit_status` | GET | Check audit system health |
| `/api/v1/security_principles` | GET | List active security principles |

## Security Audit System (Runtime Guardian)

The sidecar includes a security audit system for AI agents.

### Audit Flow (Tiered Approach)

```
Action Request
     │
     ▼
┌─────────────────────────────┐
│  Tier 1: DENYLIST CHECK     │  < 10ms
│  (rm -rf, curl|bash, etc.)  │
│         │ BLOCK             │
├─────────┼───────────────────┤
│  Tier 2: ALLOWLIST CHECK    │  < 10ms
│  (ls, pwd, git status)      │
│  (trusted sources only)     │
│         │ ALLOW             │
├─────────┼───────────────────┤
│  Tier 3: LLM SEMANTIC       │  1-5 sec
│  (Ollama analysis)          │
│         │ ALLOW/BLOCK/WARN  │
└─────────┴───────────────────┘
```

### Verdicts

| Verdict | Meaning | Agent Action |
|---------|---------|-------------|
| `ALLOW` | Safe to execute | Proceed |
| `BLOCK` | Dangerous, do not execute | Stop + notify user |
| `WARN` | Risky, needs confirmation | Ask user before proceeding |
| `SANDBOX` | Run in isolated container | Execute in Docker sandbox |

## Leviathan Subnet (Local Development)

| Setting | Value |
|---------|-------|
| Chain ID | 43210 |
| RPC URL | `http://127.0.0.1:9654/ext/bc/<blockchain_hash>/rpc` |
| Token Symbol | LVTN |
| EWOQ Test Address | `0x8db97C7cEcE249c2b98bDC0226Cc4C2A57BF52FC` |
| EWOQ Private Key | `56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027` |
| EWOQ Balance | 1,000,000,000 LVTN |

**Subnet Management:**
```bash
# Start the subnet
./scripts/setup_leviathan_subnet.sh

# Stop the subnet
avalanche network stop

# Restart the subnet
avalanche network start

# View subnet info
avalanche blockchain describe leviathan
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `RELAYER_PRIVATE_KEY` | EVM relayer private key (0x...) |

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `No RELAYER_PRIVATE_KEY set` | Missing env var for EVM | `export RELAYER_PRIVATE_KEY="0x..."` |
| `QuestBoard address not configured` | Missing contract address | Update config after deploy |
| `Contracts not compiled` | Missing artifacts | `cd contracts && npx hardhat compile` |
| Node.js version error | Hardhat requires Node 22 LTS | `nvm use 22` |
| `avalanche: command not found` | Avalanche CLI not in PATH | `export PATH=~/bin:$PATH` |
| Leviathan Subnet not responding | Subnet stopped | `avalanche network start` |
| RPC URL changed after restart | Blockchain hash regenerated | Re-run `setup_leviathan_subnet.sh` |
