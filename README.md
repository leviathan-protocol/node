# DAHAO Sidecar

An autonomous governance voting sidecar for Cosmos SDK chains. Uses local LLM inference to make principled voting decisions based on user-defined values ("Fork") while respecting the DAHAO shared governance framework.

## Features

- Polls chain for active governance proposals
- Evaluates proposals using local LLM (Ollama)
- Votes according to user-defined principles
- **Validates forks against DAHAO shared law** (locked principles, terms)
- **Includes governance context in LLM prompts** (thresholds, constraints)
- Full audit trail with reasoning hashes (for future Proof of Alignment)
- Supports Cosmos SDK v1 and v1beta1 governance modules

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Start Prerequisites

**Terminal 1 - DAHAO Chain:**
```bash
cd dahao
ignite chain serve
```

**Terminal 2 - Ollama:**
```bash
ollama serve
ollama pull qwen3:14b
```

### 3. Configure

```bash
# Set wallet mnemonic (24 words from ignite output)
export LEVIATHAN_MNEMONIC="your twenty four word mnemonic phrase here ..."
```

Edit `fork.yaml` to define your voting principles:

**Simple format (backward compatible):**
```yaml
name: "My Validator"
principles:
  - "Prioritize network security"
  - "Support decentralization"
voting_style: "cautious"
abstain_threshold: 0.6
```

**Enhanced format (with shared law references):**
```yaml
name: "My Validator"
inherits: "dahao-core v1.0.0"
uses_terms:
  - "@protection"
  - "@harm"
principles:
  - statement: "Prioritize network security"
    aligns_with: "@precautionary_default"
  - statement: "Support decentralization"
    aligns_with: "@democratic_evolution"
voting_style: "cautious"
abstain_threshold: 0.6
```

### 4. Run

```bash
uv run python main.py
```

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                    DAHAO Sidecar                        │
│                                                         │
│   Chain ◄──── Sidecar Loop ────► Brain (Ollama)        │
│     │              │                   │                │
│     ▼              ▼                   ▼                │
│  Wallet      Shared Law             Fork               │
│            (terms, rules,         (values)            │
│             principles)                                │
└─────────────────────────────────────────────────────────┘
```

1. **Load**: Loads DAHAO shared law (terms, principles, rules, governance)
2. **Validate**: Validates fork against locked principles
3. **Poll**: Fetches proposals in voting period from chain
4. **Evaluate**: Sends proposal + Fork + shared law context to LLM
5. **Decide**: LLM returns structured JSON: `{vote, confidence, reasoning}`
6. **Vote**: Submits signed MsgVote transaction to chain
7. **Log**: Records decision with enhanced context to `decisions.log`

## DAHAO Shared Law

The sidecar enforces the DAHAO governance framework through shared law files in `data/`:

| File | Purpose |
|------|---------|
| `terms.json` | Universal vocabulary (@purpose, @vote, @evidence, etc.) |
| `principles.json` | Core principles (6 locked, 3 unlocked) |
| `rules.json` | Governance rules (thresholds, processes) |
| `governance.json` | Meta-configuration (timing, automation) |
| `domains.json` | Domain registry |

### Locked Principles

These principles CANNOT be violated by any fork:

| Principle | Statement |
|-----------|-----------|
| `@purpose_primacy` | All decisions must serve stated purpose |
| `@democratic_evolution` | Evolve through collective deliberation |
| `@transparency` | All governance publicly visible |
| `@precautionary_default` | Err toward protection when uncertain |
| `@protection_asymmetry` | Easier to add protections than remove |
| `@inheritance_integrity` | Domains can't violate core locked principles |

## Configuration

### config.yaml

```yaml
chain:
  chain_id: "dahao"
  grpc_url: "grpc+http://localhost:9090"
  fee_denom: "stake"
  address_prefix: "cosmos"
  gas_limit: 200000
  fee_amount: 1000

llm:
  model_name: "qwen3:14b"
  ollama_host: "http://localhost:11434"
  n_ctx: 8192

sidecar:
  poll_interval_seconds: 60
  max_retries: 3
```

### CLI Arguments

```bash
python main.py \
  --fork fork.yaml \
  --wallet "24-word mnemonic..." \
  --data-dir data/ \
  --skip-fork-validation \
  --name "MyValidator" \
  --log-level INFO
```

| Argument | Description |
|----------|-------------|
| `--fork` | Path to fork.yaml (default: fork.yaml) |
| `--wallet` | 24-word mnemonic (overrides env var) |
| `--data-dir` | Shared law data directory (default: data/) |
| `--skip-fork-validation` | Skip validation against shared law |
| `--name` | Agent name for logs |
| `--log-level` | DEBUG, INFO, WARNING, ERROR |

## Decision Logging

All votes are logged to `decisions.log` in JSON format:

```json
{
  "timestamp": "2026-01-28T18:12:48.353876Z",
  "proposal_id": 1,
  "proposal_title": "Increase Block Size",
  "fork_name": "Security-First Validator",
  "fork_inherits": "dahao-core v1.0.0",
  "vote": "NO",
  "confidence": 0.85,
  "llm_reasoning": "Increasing block size risks centralization...",
  "reasoning_hash": "6345fe1fa25f20b80b20ee9dea2a03ce...",
  "terms_referenced": ["@protection", "@harm"],
  "principles_aligned": ["@precautionary_default"],
  "locked_constraints": ["@purpose_primacy", "@democratic_evolution", ...],
  "governance_version": "1.0.0"
}
```

The `reasoning_hash` is a SHA256 of the reasoning, designed for future on-chain Proof of Alignment submissions.

## Project Structure

```
leviathan/
├── main.py              # Entry point
├── config.yaml          # Chain/LLM settings
├── fork.yaml            # Voting principles
├── decisions.log        # Audit trail
├── config/              # Configuration models
├── chain/               # CosmPy blockchain interaction
├── brain/               # Ollama LLM integration
├── sidecar/             # Polling loop and state
├── models/              # Data models
└── data/                # DAHAO shared law
    ├── terms.json       # Universal vocabulary
    ├── principles.json  # Core principles
    ├── rules.json       # Governance rules
    ├── governance.json  # Meta-configuration
    └── domains.json     # Domain registry
```

## Swarm Simulation - AI Democracy

Test AI democracy with 5 agents voting with different worldviews:

| Agent | Personality | Worldview |
|-------|-------------|-----------|
| Alice | Nature Mother | Biocentric, eco-focused |
| Bob | Capitalist | Profit-driven, growth-focused |
| Charlie | Anarchist | Decentralization maximalist |
| Dave | Conformist | Status quo defender |
| Eve | Hacker | Security researcher |

### Actual Simulation Results

**Proposal #1: Increase Block Size**
| Agent | Vote | Confidence |
|-------|------|------------|
| Alice | NO | 0.70 |
| Bob | **YES** | 0.90 |
| Charlie | NO | 0.75 |
| Dave | NO | 0.60 |
| Eve | ABSTAIN | 0.30 |

**Proposal #2: IBC with Untested Chain**
| Agent | Vote | Confidence |
|-------|------|------------|
| Alice | NO | 0.85 |
| Bob | **YES** | 0.70 |
| Charlie | NO | 0.85 |
| Dave | NO | 0.90 |
| Eve | **NO_WITH_VETO** | 0.95 |

**Proposal #3: Mandatory Security Audits**
| Agent | Vote | Confidence |
|-------|------|------------|
| Alice | **YES** | 0.75 |
| Bob | NO | 0.75 |
| Charlie | NO | 0.95 |
| Dave | **YES** | 0.85 |
| Eve | **YES** | 0.95 |

Key observations:
- Eve (Hacker) used **NO_WITH_VETO** on unaudited IBC - security researcher behavior!
- Bob (Capitalist) voted YES on risky IBC (profit) but NO on audits (cost)
- Charlie (Anarchist) opposed audits because they require "trusted third parties"

### Setup

```bash
# 1. Generate wallets
dahaod keys add sim_alice --keyring-backend test
# ... repeat for bob, charlie, dave, eve

# 2. Fund wallets
./simulation/fund_wallets.sh

# 3. Run swarm
uv run python simulation_swarm.py

# 4. Submit proposals and watch votes
dahaod tx gov submit-proposal /tmp/proposal.json --from alice --yes
```

Each agent evaluates the same proposal through their unique value lens and votes accordingly.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- [Ollama](https://ollama.ai/) for local LLM
- [Ignite CLI](https://ignite.com/) for local chain (or any Cosmos SDK chain)

## License

MIT
