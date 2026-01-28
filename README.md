# DAHAO Sidecar

An autonomous governance voting sidecar for Cosmos SDK chains. Uses local LLM inference to make principled voting decisions based on user-defined values ("Fork").

## Features

- Polls chain for active governance proposals
- Evaluates proposals using local LLM (Ollama)
- Votes according to user-defined principles
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
```yaml
name: "My Validator"
principles:
  - "Prioritize network security"
  - "Support decentralization"
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
│  Wallet        decisions.log        Fork               │
│                                    (values)            │
└─────────────────────────────────────────────────────────┘
```

1. **Poll**: Fetches proposals in voting period from chain
2. **Evaluate**: Sends proposal + Fork principles to LLM
3. **Decide**: LLM returns structured JSON: `{vote, confidence, reasoning}`
4. **Vote**: Submits signed MsgVote transaction to chain
5. **Log**: Records decision with reasoning hash to `decisions.log`

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

### fork.yaml

Define your validator's voting principles:

```yaml
name: "Security-First Validator"
principles:
  - "Prioritize network security over feature velocity"
  - "Support decentralization and resist centralization of power"
  - "Require clear documentation and audit trails for all changes"
  - "Favor proposals with thorough security audits"
  - "Oppose inflationary tokenomics changes"
voting_style: "cautious"  # cautious, moderate, or aggressive
abstain_threshold: 0.6    # Abstain if confidence below this
```

## Decision Logging

All votes are logged to `decisions.log` in JSON format:

```json
{
  "timestamp": "2026-01-28T18:12:48.353876Z",
  "proposal_id": 1,
  "proposal_title": "Increase Block Size",
  "fork_name": "Security-First Validator",
  "vote": "NO",
  "confidence": 0.85,
  "llm_reasoning": "Increasing block size risks centralization...",
  "reasoning_hash": "6345fe1fa25f20b80b20ee9dea2a03ce759479175c472d7a0d11a97fb92741a8"
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
└── models/              # Data models
```

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- [Ollama](https://ollama.ai/) for local LLM
- [Ignite CLI](https://ignite.com/) for local chain (or any Cosmos SDK chain)

## License

MIT
