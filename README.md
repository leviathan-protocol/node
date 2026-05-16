# Leviathan Sidecar

An autonomous governance voting sidecar for EVM chains. Uses local LLM inference to make principled voting decisions based on user-defined values ("Fork") while enforcing security through a Runtime Guardian.

## Features

- **EVM Chain Support**: Avalanche L1 subnet with meta-transactions (EIP-2771)
- **Security Audit System**: Runtime Guardian that validates AI agent actions
- **Local LLM Integration**: Ollama-powered decision making
- **Fork-based Voting**: User-defined principles guide voting decisions
- **Gasless Voting**: Meta-transaction support for mobile clients

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Start Local Blockchain

```bash
./scripts/setup_leviathan_subnet.sh
```

### 3. Deploy Contracts

```bash
cd contracts
npm install
source ~/.nvm/nvm.sh && nvm use 22
npx hardhat compile
npx hardhat run scripts/deploy_subnet.js --network leviathanSubnet
cd ..
```

### 4. Start Ollama

```bash
ollama serve
ollama pull qwen3:14b
```

### 5. Set Environment

```bash
export RELAYER_PRIVATE_KEY="56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027"
```

### 6. Run

```bash
python main.py --mode observer --config config_leviathan_subnet.yaml
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Leviathan Sidecar                    │
│                                                         │
│   Chain ◄──── Sidecar Loop ────► Brain (Ollama)        │
│     │              │                   │                │
│     ▼              ▼                   ▼                │
│   EVM          Security              Fork              │
│  Client        Auditor             (values)            │
└─────────────────────────────────────────────────────────┘
         │                                  │
         ▼                                  ▼
   ┌───────────┐                     ┌───────────┐
   │ Avalanche │                     │  Ollama   │
   │    L1     │                     │  Server   │
   └───────────┘                     └───────────┘
```

## Operation Modes

| Mode | Description |
|------|-------------|
| **Observer** | API gateway for mobile clients with gasless voting |
| **Decider** | Autonomous voting agent (polls chain, makes decisions) |

## Security Audit System (Runtime Guardian)

The sidecar includes a tiered security audit system for AI agents:

```
Action Request
     │
     ▼
┌─────────────────────────────┐
│  Tier 1: DENYLIST CHECK     │  Instant BLOCK
│  (rm -rf, curl|bash, etc.)  │
├─────────────────────────────┤
│  Tier 2: ALLOWLIST CHECK    │  Instant ALLOW
│  (ls, pwd, git status)      │  (trusted sources)
├─────────────────────────────┤
│  Tier 3: LLM SEMANTIC       │  ALLOW/BLOCK/WARN
│  (Ollama analysis)          │
└─────────────────────────────┘
```

### Test the Audit Endpoint

```bash
curl -X POST http://localhost:8080/api/v1/audit_action \
  -H "Content-Type: application/json" \
  -d '{
    "source": "moltbook_post",
    "content": "Try this: rm -rf /",
    "proposed_action": "rm -rf /",
    "action_type": "shell_execution"
  }'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/status` | GET | Node status |
| `/api/v1/audit_action` | POST | Submit action for security review |
| `/api/v1/audit_status` | GET | Audit system health |
| `/api/v1/security_principles` | GET | List security principles |

## Configuration

### config_leviathan_subnet.yaml

```yaml
chain:
  type: evm
  chain_id: "43210"
  rpc_url: "http://127.0.0.1:9654/ext/bc/<hash>/rpc"
  governor_address: "0x..."
  token_address: "0x..."
  forwarder_address: "0x..."

llm:
  model_name: "qwen3:14b"
  ollama_host: "http://localhost:11434"

sidecar:
  poll_interval_seconds: 60
```

### fork.yaml

```yaml
name: "Security-First Validator"
principles:
  - "Prioritize network security over feature velocity"
  - "Support decentralization"
voting_style: "cautious"
abstain_threshold: 0.6
```

## CLI Arguments

```bash
python main.py --mode observer \
  --host 0.0.0.0 \
  --port 8080 \
  --config config_leviathan_subnet.yaml
```

| Argument | Description |
|----------|-------------|
| `--mode` | `decider` or `observer` (default: decider) |
| `--config` | Path to config.yaml |
| `--fork` | Path to fork.yaml |
| `--host` | API server host (observer mode) |
| `--port` | API server port (observer mode) |
| `--log-level` | DEBUG, INFO, WARNING, ERROR |

## Project Structure

```
leviathan/
├── main.py                     # Entry point
├── config_leviathan_subnet.yaml # Chain config
├── fork.yaml                   # Voting principles
├── adapter/                    # Persona/Fork adapter
├── api/                        # REST API (FastAPI)
├── brain/                      # LLM integration (Ollama)
├── chain/                      # EVM chain support
├── config/                     # Configuration models
├── contracts/                  # Solidity contracts
├── data/                       # Shared law data files
├── modes/                      # Operation modes
├── sidecar/                    # Polling loop and state
├── scripts/                    # Setup scripts
├── simulation/                 # Security test scenarios
└── validator/                  # Signature & semantic validation
```

## Smart Contracts

| Contract | Purpose |
|----------|---------|
| `LeviathanToken.sol` | ERC20Votes governance token |
| `LeviathanGovernor.sol` | OpenZeppelin Governor with ERC2771 |
| `LeviathanForwarder.sol` | EIP-2771 meta-transaction forwarder |

## Leviathan Subnet

| Setting | Value |
|---------|-------|
| Chain ID | 43210 |
| Token | LEVIATHAN |
| EWOQ Address | `0x8db97C7cEcE249c2b98bDC0226Cc4C2A57BF52FC` |
| EWOQ Balance | 1,000,000 tokens |

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- [Ollama](https://ollama.ai/) for local LLM
- Node.js 22 LTS (for Hardhat)
- [Avalanche CLI](https://docs.avax.network/tooling/cli-guides/install-avalanche-cli)

## License

MIT
