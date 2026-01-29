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
uv run python -m py_compile main.py config/*.py chain/*.py brain/*.py sidecar/*.py models/*.py data/*.py

# Test imports
uv run python -c "from data import SharedLaw; print(SharedLaw().summary())"
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
│  └────┬─────┘   └────┬─────┘   └────────┬─────────┘    │
│       │              │                   │              │
│       ▼              ▼                   ▼              │
│  ┌──────────┐  ┌──────────┐        ┌──────────┐        │
│  │ Wallet   │  │  Shared  │        │   Fork   │        │
│  │(mnemonic)│  │   Law    │        │ (values) │        │
│  └──────────┘  └──────────┘        └──────────┘        │
└─────────────────────────────────────────────────────────┘
         │              │                   │
         ▼              ▼                   ▼
   ┌───────────┐  ┌───────────┐      ┌───────────┐
   │  Cosmos   │  │  data/    │      │  Ollama   │  (HTTP)
   │   Chain   │  │  *.json   │      │  Server   │
   └───────────┘  └───────────┘      └───────────┘
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
│   └── fork.py             # Fork model with validation against shared law
├── chain/
│   ├── client.py           # LedgerClient + gRPC channel wrapper
│   ├── governance.py       # Proposal fetching, vote submission
│   └── wallet.py           # LocalWallet.from_mnemonic()
├── brain/
│   ├── llm.py              # Ollama wrapper with JSON schema
│   ├── prompts.py          # Voting prompts with shared law context
│   └── decision.py         # Fork + Proposal + SharedLaw → VoteDecision
├── sidecar/
│   ├── loop.py             # Async polling loop
│   ├── state.py            # Processed proposal tracking
│   └── logger.py           # Enhanced decision audit logging
├── models/
│   ├── proposal.py         # Proposal dataclass
│   └── vote.py             # VoteChoice enum, VoteDecision
├── data/
│   ├── __init__.py         # SharedLaw, models exports
│   ├── models.py           # Pydantic models for Term, Principle, Rule, etc.
│   ├── loader.py           # SharedLaw class - loads and parses data/*.json
│   ├── sync.py             # IPFS sync support for shared law updates
│   ├── terms.json          # Universal vocabulary (@purpose, @vote, etc.)
│   ├── principles.json     # Core principles (locked and unlocked)
│   ├── rules.json          # Governance rules
│   ├── governance.json     # Thresholds, timing, automation settings
│   └── domains.json        # Domain registry
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

### SharedLaw Loading
```python
from data import SharedLaw

# Load from default data/ directory
shared_law = SharedLaw()

# Access terms, principles, rules
term = shared_law.get_term("@purpose")
locked = shared_law.get_locked_principles()
threshold = shared_law.get_threshold("principle_modification")
```

### Fork Validation Against Shared Law
```python
from config.fork import Fork, ForkValidationError
from data import SharedLaw

fork = Fork.from_yaml("fork.yaml")
shared_law = SharedLaw()

try:
    fork.validate_against(shared_law)
    print("Fork is valid")
except ForkValidationError as e:
    print(f"Violations: {e.violations}")
```

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

### fork.yaml (Simple Format - Backward Compatible)
```yaml
name: "Security-First Validator"
principles:
  - "Prioritize network security over feature velocity"
  - "Support decentralization"
voting_style: "cautious"
abstain_threshold: 0.6
```

### fork.yaml (Enhanced Format - With Shared Law References)
```yaml
name: "Security-First Validator"
inherits: "dahao-core v1.0.0"
uses_terms:
  - "@protection"
  - "@harm"
  - "@evidence"
principles:
  - statement: "Prioritize network security over feature velocity"
    aligns_with: "@precautionary_default"
  - statement: "Support decentralization"
    aligns_with: "@democratic_evolution"
voting_style: "cautious"
abstain_threshold: 0.6
```

## Shared Law Data Files

The `data/` directory contains the DAHAO governance framework:

| File | Purpose |
|------|---------|
| `terms.json` | Universal vocabulary (@purpose, @vote, @evidence, etc.) |
| `principles.json` | Core principles (6 locked, 3 unlocked) |
| `rules.json` | Executable governance rules |
| `governance.json` | Thresholds, timing, automation settings |
| `domains.json` | Registry of domain instances |

### Locked Principles (Cannot Be Violated)
- `@purpose_primacy` - All decisions must serve stated purpose
- `@democratic_evolution` - Evolve through collective deliberation
- `@transparency` - All governance publicly visible
- `@precautionary_default` - Err toward protection when uncertain
- `@protection_asymmetry` - Easier to add protections than remove
- `@inheritance_integrity` - Domains can't violate core locked principles

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
2. Query LLM for voting decision (with shared law context)
3. Submit vote transaction
4. Log decision to `decisions.log`

## Decision Logging

All votes logged to `decisions.log` with:
- Timestamp, proposal ID/title
- Vote choice and confidence
- LLM reasoning
- SHA256 hash of reasoning (for future Proof of Alignment)
- **Enhanced fields** (when shared law loaded):
  - Terms referenced
  - Principles aligned
  - Locked constraints
  - Governance version

## CLI Arguments

```bash
python main.py --fork simulation/alice.yaml \
               --wallet "mnemonic words..." \
               --state simulation/state_alice.json \
               --data-dir data/ \
               --skip-fork-validation \
               --name Alice
```

| Argument | Description |
|----------|-------------|
| `--fork` | Path to fork.yaml |
| `--wallet` | 24-word mnemonic |
| `--state` | State file path |
| `--data-dir` | Shared law data directory |
| `--skip-fork-validation` | Skip fork validation against shared law |
| `--name` | Agent name for logs |
| `--log-level` | DEBUG, INFO, WARNING, ERROR |

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
- **httpx**: HTTP client (used by ollama and IPFS sync)

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `'NetworkConfig' has no attribute 'grpc_channel'` | CosmPy API change | Use `parse_url()` + `grpc.insecure_channel()` |
| `Model not found in Ollama` | Model not pulled | Run `ollama pull <model-name>` |
| `Invalid mnemonic length` | Set address instead of mnemonic | Use 24-word phrase, not cosmos1... address |
| `Failed to connect to Ollama` | Ollama not running | Run `ollama serve` |
| Proposal title shows "Unknown" | Protobuf `Any` type not unpacked | Use `content.Unpack(TextProposal())` to extract |
| LLM abstains on all proposals | No description extracted | Fix protobuf parsing (see pattern above) |
| `ForkValidationError` | Fork violates shared law | Fix fork.yaml or use `--skip-fork-validation` |
| `SharedLawLoadError` | Missing data/*.json files | Ensure data/ directory has all JSON files |
