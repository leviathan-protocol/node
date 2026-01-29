# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and Run Commands

This project uses `uv` for Python package management.

```bash
# Install dependencies
uv sync

# Run the sidecar
uv run python main.py

# Syntax check all modules
uv run python -m py_compile main.py config/*.py chain/*.py brain/*.py sidecar/*.py models/*.py

# Test imports
uv run python -c "from chain.governance import GovernanceClient; print('OK')"
```

## Prerequisites

Before running the sidecar:

1. **DAHAO Chain Running**:
   ```bash
   # Scaffold if needed (run from home dir to avoid path issues)
   cd ~
   ignite scaffold chain dahao
   mv dahao <project-dir>/

   # Start the chain
   cd <project-dir>/dahao
   ignite chain serve
   ```
   This starts gRPC on `localhost:9090`.

2. **Ollama Running** with a model:
   ```bash
   ollama serve  # if not already running
   ollama pull qwen3:14b  # or ministral-3:8b
   ```

3. **Wallet Mnemonic** (use one from `ignite chain serve` output):
   ```bash
   # Replace with YOUR 24-word mnemonic from ignite chain serve output
   export LEVIATHAN_MNEMONIC="your twenty four word mnemonic phrase here ..."
   ```
   **Note:** Do NOT use a cosmos1... address. Use the 24-word mnemonic phrase.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    DAHAO Sidecar (Python)               │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐    │
│  │  Chain   │◄──│ Sidecar  │──►│      Brain       │    │
│  │ (CosmPy) │   │  Loop    │   │    (Ollama)      │    │
│  └────┬─────┘   └──────────┘   └────────┬─────────┘    │
│       │                                  │              │
│       ▼                                  ▼              │
│  ┌──────────┐                      ┌──────────┐        │
│  │ Wallet   │                      │   Fork   │        │
│  │(mnemonic)│                      │ (values) │        │
│  └──────────┘                      └──────────┘        │
└─────────────────────────────────────────────────────────┘
         │                                  │
         ▼                                  ▼
   ┌───────────┐                    ┌───────────┐
   │  Cosmos   │  (gRPC)            │  Ollama   │  (HTTP)
   │   Chain   │                    │  Server   │
   └───────────┘                    └───────────┘
```

## Project Structure

```
leviathan/
├── main.py                 # Entry point with CLI args support
├── config.yaml             # Chain, LLM, sidecar settings
├── fork.yaml               # User's voting principles
├── simulation_swarm.py     # Multi-agent simulation runner
├── decisions.log           # Audit trail of all votes
├── config/
│   ├── settings.py         # Pydantic settings
│   └── fork.py             # Fork model with persona support
├── chain/
│   ├── client.py           # LedgerClient + gRPC channel wrapper
│   ├── governance.py       # Proposal fetching, vote submission
│   └── wallet.py           # LocalWallet.from_mnemonic()
├── brain/
│   ├── llm.py              # Ollama wrapper with JSON schema
│   ├── prompts.py          # Voting prompt templates with persona
│   └── decision.py         # Fork + Proposal → VoteDecision
├── sidecar/
│   ├── loop.py             # Async polling loop
│   ├── state.py            # Processed proposal tracking
│   └── logger.py           # Decision audit logging
├── models/
│   ├── proposal.py         # Proposal dataclass
│   └── vote.py             # VoteChoice enum, VoteDecision
└── simulation/
    ├── alice.yaml          # Nature Mother persona
    ├── bob.yaml            # Capitalist persona
    ├── charlie.yaml        # Anarchist persona
    ├── dave.yaml           # Conformist persona
    ├── eve.yaml            # Hacker persona
    ├── wallets.yaml        # Test wallet mnemonics
    └── fund_wallets.sh     # Script to fund test wallets
```

## Key Implementation Patterns

### CosmPy Wallet Creation
```python
# CORRECT - use factory method
wallet = LocalWallet.from_mnemonic(mnemonic, prefix="cosmos")
```

### CosmPy Governance Queries
```python
# LedgerClient has no .gov attribute - create stub from channel
from cosmpy.protos.cosmos.gov.v1beta1.query_pb2_grpc import QueryStub
from cosmpy.aerial.urls import parse_url

parsed = parse_url(grpc_url)
channel = grpc.insecure_channel(parsed.host_and_port)
gov_client = QueryStub(channel)
response = gov_client.Proposals(request)
```

### CosmPy Transaction Lifecycle
```python
# Transaction state machine: Draft → Sealed → Final
tx = Transaction()
tx.add_message(msg)

account = ledger.query_account(wallet.address())
gas_limit, fee = ledger.estimate_gas_and_fee_for_tx(tx)

tx.seal(SigningCfg.direct(wallet.public_key(), account.sequence), fee=fee)
tx.sign(wallet.signer(), chain_id, account.number)
tx.complete()

submitted_tx = ledger.broadcast_tx(tx)
```

### Protobuf Any Type Unpacking (v1beta1 Proposals)
```python
# Proposal content is wrapped in protobuf Any type - must unpack
from cosmpy.protos.cosmos.gov.v1beta1.gov_pb2 import TextProposal

if hasattr(proto_proposal, "content") and proto_proposal.content:
    content = proto_proposal.content
    if "TextProposal" in content.type_url:
        text_proposal = TextProposal()
        if content.Unpack(text_proposal):
            title = text_proposal.title
            description = text_proposal.description
```

### Ollama Structured Output (JSON Schema)
```python
import ollama

VOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "vote": {"type": "string", "enum": ["YES", "NO", "ABSTAIN", "NO_WITH_VETO"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string"},
    },
    "required": ["vote", "confidence", "reasoning"],
}

response = client.chat(
    model="qwen3:14b",
    messages=messages,
    format=VOTE_SCHEMA,  # Forces structured JSON output
)
```

## Configuration Files

### config.yaml
```yaml
chain:
  chain_id: "dahao"
  grpc_url: "grpc+http://localhost:9090"
  fee_denom: "stake"
  address_prefix: "cosmos"

llm:
  model_name: "qwen3:14b"
  ollama_host: "http://localhost:11434"
  n_ctx: 8192

sidecar:
  poll_interval_seconds: 60
  max_retries: 3
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

## Testing

### Create a Test Proposal
In a separate terminal (while chain is running):
```bash
cd dahao
dahaod tx gov submit-proposal --title="Test Proposal" \
  --description="Testing the sidecar" \
  --type="Text" \
  --deposit="10000000stake" \
  --from=alice --yes
```

### Check Sidecar Logs
The sidecar will:
1. Detect the new proposal
2. Query LLM for voting decision
3. Submit vote transaction
4. Log decision to `decisions.log`

## Decision Logging

All votes logged to `decisions.log` with:
- Timestamp, proposal ID/title
- Vote choice and confidence
- LLM reasoning
- SHA256 hash of reasoning (for future Proof of Alignment)

## Swarm Simulation

Run 5 agents with different worldviews voting on the same proposals:

```bash
# Generate wallets
dahaod keys add sim_alice --keyring-backend test
# ... repeat for bob, charlie, dave, eve

# Fund wallets
./simulation/fund_wallets.sh

# Run swarm
uv run python simulation_swarm.py
```

### CLI Arguments

```bash
python main.py --fork simulation/alice.yaml \
               --wallet "mnemonic words..." \
               --state simulation/state_alice.json \
               --name Alice
```

### Agent Personas

| Agent | Worldview | Voting Tendency |
|-------|-----------|-----------------|
| Alice | Nature Mother | Biocentric, eco-focused |
| Bob | Capitalist | Profit-driven, growth-focused |
| Charlie | Anarchist | Decentralization maximalist |
| Dave | Conformist | Status quo defender |
| Eve | Hacker | Security researcher |

## Dependencies

- **cosmpy**: Cosmos SDK Python client
- **ollama**: Local LLM inference via Ollama
- **pydantic-settings**: Configuration management
- **pyyaml**: YAML config parsing
- **httpx**: HTTP client (used by ollama)

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `'NetworkConfig' has no attribute 'grpc_channel'` | CosmPy API change | Use `parse_url()` + `grpc.insecure_channel()` |
| `Model not found in Ollama` | Model not pulled | Run `ollama pull <model-name>` |
| `Invalid mnemonic length` | Set address instead of mnemonic | Use 24-word phrase, not cosmos1... address |
| `Failed to connect to Ollama` | Ollama not running | Run `ollama serve` |
| Proposal title shows "Unknown" | Protobuf `Any` type not unpacked | Use `content.Unpack(TextProposal())` to extract |
| LLM abstains on all proposals | No description extracted | Fix protobuf parsing (see pattern above) |
