# Infrastructure Guide

This document describes the infrastructure components required to run the DAHAO Sidecar.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Host Machine                               │
│                                                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│  │  DAHAO Sidecar  │    │  Cosmos Chain   │    │     Ollama      │     │
│  │    (Python)     │    │    (dahaod)     │    │   (LLM Server)  │     │
│  │                 │    │                 │    │                 │     │
│  │  Port: N/A      │    │  gRPC: 9090     │    │  HTTP: 11434    │     │
│  │  (client only)  │    │  RPC:  26657    │    │                 │     │
│  │                 │    │  API:  1317     │    │                 │     │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘     │
│           │                      │                      │               │
│           │    gRPC queries      │                      │               │
│           ├──────────────────────┤                      │               │
│           │    vote transactions │                      │               │
│           │                      │                      │               │
│           │         LLM inference (HTTP POST)           │               │
│           ├─────────────────────────────────────────────┤               │
│           │                                             │               │
│  ┌────────┴────────┐                                                    │
│  │   Shared Law    │    (Local data/ directory or IPFS sync)           │
│  │   data/*.json   │                                                    │
│  └─────────────────┘                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. DAHAO Sidecar (This Project)

**Purpose:** Autonomous governance voting agent with shared law enforcement

**Requirements:**
- Python 3.11+
- ~100MB disk space
- ~200MB RAM
- Network access to chain and Ollama

**Ports:** None (outbound connections only)

**Environment Variables:**
| Variable | Required | Description |
|----------|----------|-------------|
| `LEVIATHAN_MNEMONIC` | Yes | 24-word wallet mnemonic |

**Data Files:**
| File | Purpose | Required |
|------|---------|----------|
| `data/terms.json` | Universal vocabulary | Yes |
| `data/principles.json` | Core principles (locked/unlocked) | Yes |
| `data/rules.json` | Governance rules | Yes |
| `data/governance.json` | Thresholds and timing | Yes |
| `data/domains.json` | Domain registry | Yes |

### 2. Cosmos Chain (DAHAO)

**Purpose:** Blockchain network with governance module

**Options:**

#### Local Development (Ignite)
```bash
# Install Ignite CLI
brew install ignite

# Scaffold and run
ignite scaffold chain dahao
cd dahao
ignite chain serve
```

**Ports:**
| Port | Protocol | Purpose |
|------|----------|---------|
| 9090 | gRPC | Blockchain queries and transactions |
| 26657 | HTTP | Tendermint RPC |
| 1317 | HTTP | REST API |
| 26656 | TCP | P2P networking |

**Resources (local dev):**
- ~500MB disk
- ~500MB RAM
- 1 CPU core

#### Production (Validator Node)
For production, connect to an existing network:
```yaml
# config.yaml
chain:
  chain_id: "dahao-mainnet-1"
  grpc_url: "grpc+http://validator.dahao.network:9090"
```

### 3. Ollama (LLM Server)

**Purpose:** Local LLM inference for voting decisions

**Installation:**
```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Start server
ollama serve
```

**Ports:**
| Port | Protocol | Purpose |
|------|----------|---------|
| 11434 | HTTP | LLM API |

**Models (choose one):**
| Model | Size | VRAM | Quality |
|-------|------|------|---------|
| `qwen3:14b` | 9GB | 10GB | High |
| `qwen3:8b` | 5GB | 6GB | Medium |
| `llama3.1:8b` | 5GB | 6GB | Medium |
| `mistral:7b` | 4GB | 5GB | Medium |

```bash
# Pull a model
ollama pull qwen3:14b
```

**Resources:**
- GPU recommended (NVIDIA, Apple Silicon, or AMD)
- 8-16GB VRAM depending on model
- CPU-only possible but slow

### 4. Identity Adapter (adapter/)

**Purpose:** Convert external persona.json files to valid Fork configurations

**Components:**

| Module | Purpose |
|--------|---------|
| `models.py` | Persona Pydantic model |
| `loader.py` | PersonaLoader with search paths |
| `mapper.py` | LLM-based PersonaMapper |
| `prompts.py` | LLM schemas and prompt templates |
| `cache.py` | ForkCache for caching compiled Forks |

**Mapping Flow:**
```
persona.json → PersonaLoader → Persona → PersonaMapper → Fork → Validation
                                              │
                                              ▼
                                        LLM (Ollama)
                                              │
                                              ▼
                                        ForkCache (~/.cache/dahao/forks/)
```

**Key Validation:**
- `aligns_with` MUST reference principles (`@precautionary_default`), NOT terms (`@protection`)
- Generated Fork is validated against locked principles before use
- Invalid personas fail-fast with descriptive error messages

**Cache Location:** `~/.cache/dahao/forks/fork_{hash}.yaml`

**Cache Invalidation:** Hash includes persona content + shared_law version

### 5. Shared Law Data (data/)

**Purpose:** DAHAO governance framework files

**Source Options:**

#### Local (Default)
Files stored in `data/` directory:
```
data/
├── terms.json          # 15 universal terms
├── principles.json     # 9 principles (6 locked)
├── rules.json          # 13 governance rules
├── governance.json     # Thresholds, timing
└── domains.json        # Domain registry
```

#### IPFS Sync (Optional)
For decentralized updates, use the sync module:
```python
from data import SharedLawSync

sync = SharedLawSync()
if sync.is_outdated("QmXxx..."):  # IPFS CID
    sync.sync_from_ipfs("QmXxx...")
```

**IPFS Gateway Configuration:**
```python
sync = SharedLawSync(
    local_dir=Path("data"),
    ipfs_gateway="https://ipfs.io",  # or your own gateway
    timeout=30.0
)
```

## Network Configuration

### Firewall Rules (Production)

**Sidecar Host (outbound only):**
```
ALLOW OUT TCP to <chain-node>:9090  # gRPC
ALLOW OUT TCP to localhost:11434    # Ollama (if local)
ALLOW OUT TCP to ipfs.io:443        # IPFS sync (optional)
```

**Chain Node:**
```
ALLOW IN TCP 9090 from <sidecar-host>  # gRPC
ALLOW IN TCP 26656 from 0.0.0.0/0      # P2P (if validator)
```

### TLS/SSL

For production gRPC connections:
```yaml
# config.yaml
chain:
  grpc_url: "grpc+https://secure.dahao.network:9090"
```

## Deployment Options

### Option 1: Single Machine (Development)

All components on one machine:
```
┌─────────────────────────────────┐
│         Development Host        │
│                                 │
│  Sidecar ──► Chain (localhost)  │
│     │                           │
│     └──────► Ollama (localhost) │
│     │                           │
│     └──────► data/ (local)      │
└─────────────────────────────────┘
```

```bash
# Terminal 1: Chain
cd dahao && ignite chain serve

# Terminal 2: Ollama
ollama serve

# Terminal 3: Sidecar
export LEVIATHAN_MNEMONIC="..."
uv run python main.py
```

### Option 2: Separate LLM Server

Ollama on dedicated GPU machine:
```
┌──────────────────┐     ┌──────────────────┐
│   Sidecar Host   │     │    GPU Server    │
│                  │     │                  │
│  Sidecar ────────┼────►│  Ollama:11434    │
│     │            │     │                  │
└─────┼────────────┘     └──────────────────┘
      │
      ▼
┌──────────────────┐
│   Chain Node     │
│   gRPC:9090      │
└──────────────────┘
```

```yaml
# config.yaml
llm:
  ollama_host: "http://gpu-server.local:11434"
```

### Option 3: Docker Compose

```yaml
# docker-compose.yml
version: '3.8'
services:
  sidecar:
    build: .
    environment:
      - LEVIATHAN_MNEMONIC=${LEVIATHAN_MNEMONIC}
    depends_on:
      - ollama
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./fork.yaml:/app/fork.yaml
      - ./data:/app/data  # Shared law data
      - ./decisions.log:/app/decisions.log

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  ollama_data:
```

### Option 4: Kubernetes

```yaml
# k8s/sidecar-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dahao-sidecar
spec:
  replicas: 1  # Only 1 replica per wallet!
  selector:
    matchLabels:
      app: dahao-sidecar
  template:
    spec:
      containers:
      - name: sidecar
        image: dahao-sidecar:latest
        env:
        - name: LEVIATHAN_MNEMONIC
          valueFrom:
            secretKeyRef:
              name: sidecar-secrets
              key: mnemonic
        volumeMounts:
        - name: config
          mountPath: /app/config.yaml
          subPath: config.yaml
        - name: data
          mountPath: /app/data
      volumes:
      - name: config
        configMap:
          name: sidecar-config
      - name: data
        configMap:
          name: shared-law-data  # Or use PVC for IPFS sync
```

### Option 5: Swarm Simulation (Multi-Agent)

Run 5 agents with different worldviews on a single machine:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Swarm Simulation Host                           │
│                                                                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │  Alice  │ │   Bob   │ │ Charlie │ │  Dave   │ │   Eve   │           │
│  │ (Nature)│ │ (Capit.)│ │(Anarch.)│ │(Conform)│ │ (Hacker)│           │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘           │
│       │           │           │           │           │                 │
│       └───────────┴───────────┼───────────┴───────────┘                 │
│                               │                                         │
│                               ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │               Shared: Ollama + Shared Law (data/)               │   │
│  │                    localhost:11434                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                               │                                         │
│                               ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    DAHAO Chain (1 Node)                         │   │
│  │                    localhost:9090                               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Resource Requirements:**
- CPU: 4+ cores (1 per agent + overhead)
- RAM: 16GB+ (shared LLM + 5 agents)
- GPU: 10GB+ VRAM (single shared model)

**Setup:**
```bash
# 1. Generate test wallets
dahaod keys add sim_alice --keyring-backend test
dahaod keys add sim_bob --keyring-backend test
dahaod keys add sim_charlie --keyring-backend test
dahaod keys add sim_dave --keyring-backend test
dahaod keys add sim_eve --keyring-backend test

# 2. Fund wallets (10M stake each)
./simulation/fund_wallets.sh

# 3. Run swarm
uv run python simulation_swarm.py
```

**Agent Configuration (Persona-based):**

The swarm now uses persona.json files by default, which are converted to Forks at runtime via LLM mapping:

| Agent | Persona File | Archetype | Wallet |
|-------|--------------|-----------|--------|
| Alice | `simulation/alice_persona.json` | Deep Ecologist | sim_alice |
| Bob | `simulation/bob_persona.json` | Rational Capitalist | sim_bob |
| Charlie | `simulation/charlie_persona.json` | Libertarian Decentralist | sim_charlie |
| Dave | `simulation/dave_persona.json` | Institutional Conformist | sim_dave |
| Eve | `simulation/eve_persona.json` | Security Researcher | sim_eve |

**Persona to Fork Mapping:**

At startup, each agent's persona is converted to a Fork:
1. LLM maps `core_values` → `principles` with `aligns_with` references
2. `decision_style` → `voting_style` and `abstain_threshold`
3. Validation ensures Fork respects locked principles
4. Agents with violating personas fail-fast and don't start

**Note:** Bob's "Rational Capitalist" persona may fail validation if values conflict with locked principles like `@protection_asymmetry`.

**Simulation Results (Actual Test):**

| Proposal | Alice | Bob | Charlie | Dave | Eve |
|----------|-------|-----|---------|------|-----|
| Block Size Increase | NO | YES | NO | NO | ABSTAIN |
| IBC Untested Chain | NO | YES | NO | NO | **VETO** |
| Mandatory Audits | YES | NO | NO | YES | YES |

Key insight: Same LLM, same proposals, same shared law, different votes based on Fork values.

## Monitoring

### Health Checks

**Chain connectivity:**
```bash
grpcurl -plaintext localhost:9090 list
```

**Ollama:**
```bash
curl http://localhost:11434/api/tags
```

**Shared Law:**
```bash
python -c "from data import SharedLaw; print(SharedLaw().summary())"
```

**Sidecar logs:**
```bash
tail -f decisions.log | jq .
```

### Metrics to Monitor

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Wallet balance | Chain query | < 10000 stake |
| Proposals missed | decisions.log | Any |
| LLM latency | Ollama logs | > 60s |
| Vote TX failures | Sidecar logs | Any |
| Shared law version | data/governance.json | Outdated |

### Log Aggregation

```bash
# decisions.log format (JSON lines)
{"timestamp": "...", "proposal_id": 1, "vote": "YES", "governance_version": "1.0.0", ...}

# Parse with jq
cat decisions.log | jq -r '[.timestamp, .proposal_id, .vote, .governance_version] | @tsv'

# Filter by governance version
cat decisions.log | jq 'select(.governance_version == "1.0.0")'
```

## Security Considerations

### Wallet Security

1. **Never commit mnemonic** - Use environment variables or secrets manager
2. **Minimum balance** - Keep only enough for gas fees
3. **Separate wallet** - Don't use validator operator key

### Shared Law Integrity

1. **Validate data files** - Check JSON validity before use
2. **Version tracking** - Log governance_version with every decision
3. **IPFS pinning** - If using IPFS sync, verify content hashes

### Network Security

1. **Firewall** - Restrict inbound connections
2. **TLS** - Use encrypted gRPC for remote chains
3. **VPN** - Consider VPN for Ollama if remote

### Operational Security

1. **Single instance** - Only one sidecar per wallet (avoid double-voting)
2. **Audit logs** - Preserve decisions.log for accountability
3. **Principle review** - Regularly review fork.yaml principles
4. **Shared law updates** - Review before syncing from IPFS

## Backup and Recovery

### State Files

| File | Purpose | Backup? |
|------|---------|---------|
| `sidecar_state.json` | Processed proposals | Optional (regenerates) |
| `decisions.log` | Audit trail | Yes |
| `fork.yaml` | Voting principles | Yes (if using fork mode) |
| `*_persona.json` | External personas | Yes (if using persona mode) |
| `config.yaml` | Configuration | Yes |
| `data/*.json` | Shared law | Yes (version controlled) |
| `~/.cache/dahao/forks/*.yaml` | Cached persona-to-fork mappings | Optional (regenerates) |

### Recovery Procedure

1. Restore `fork.yaml`, `config.yaml`, and `data/` directory
2. Set `LEVIATHAN_MNEMONIC` environment variable
3. Start sidecar - it will resume from current voting period
4. (Optional) Restore `decisions.log` for audit continuity

## Resource Sizing

### Minimum (Development)
- CPU: 2 cores
- RAM: 8GB (4GB for Ollama + 4GB for chain)
- Disk: 10GB
- GPU: None (CPU inference, slow)

### Recommended (Production)
- CPU: 4 cores
- RAM: 16GB
- Disk: 50GB SSD
- GPU: 8GB+ VRAM (NVIDIA RTX 3070+ or Apple M1+)

### High Performance
- CPU: 8 cores
- RAM: 32GB
- Disk: 100GB NVMe
- GPU: 16GB+ VRAM (NVIDIA RTX 4080+ or Apple M2 Pro+)
