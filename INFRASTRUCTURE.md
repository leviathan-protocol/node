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
└───────────┴─────────────────────────────────────────────┴───────────────┘
```

## Components

### 1. DAHAO Sidecar (This Project)

**Purpose:** Autonomous governance voting agent

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

## Network Configuration

### Firewall Rules (Production)

**Sidecar Host (outbound only):**
```
ALLOW OUT TCP to <chain-node>:9090  # gRPC
ALLOW OUT TCP to localhost:11434    # Ollama (if local)
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
      volumes:
      - name: config
        configMap:
          name: sidecar-config
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
│  │                    Shared Ollama (1 LLM)                        │   │
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

**Agent Configuration:**

| Agent | Fork File | Wallet | State File |
|-------|-----------|--------|------------|
| Alice | `simulation/alice.yaml` | sim_alice | `simulation/state_alice.json` |
| Bob | `simulation/bob.yaml` | sim_bob | `simulation/state_bob.json` |
| Charlie | `simulation/charlie.yaml` | sim_charlie | `simulation/state_charlie.json` |
| Dave | `simulation/dave.yaml` | sim_dave | `simulation/state_dave.json` |
| Eve | `simulation/eve.yaml` | sim_eve | `simulation/state_eve.json` |

**Simulation Results (Actual Test):**

| Proposal | Alice | Bob | Charlie | Dave | Eve |
|----------|-------|-----|---------|------|-----|
| Block Size Increase | NO | YES | NO | NO | ABSTAIN |
| IBC Untested Chain | NO | YES | NO | NO | **VETO** |
| Mandatory Audits | YES | NO | NO | YES | YES |

Key insight: Same LLM, same proposals, different votes based on Fork values.

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

### Log Aggregation

```bash
# decisions.log format (JSON lines)
{"timestamp": "...", "proposal_id": 1, "vote": "YES", ...}

# Parse with jq
cat decisions.log | jq -r '[.timestamp, .proposal_id, .vote] | @tsv'
```

## Security Considerations

### Wallet Security

1. **Never commit mnemonic** - Use environment variables or secrets manager
2. **Minimum balance** - Keep only enough for gas fees
3. **Separate wallet** - Don't use validator operator key

### Network Security

1. **Firewall** - Restrict inbound connections
2. **TLS** - Use encrypted gRPC for remote chains
3. **VPN** - Consider VPN for Ollama if remote

### Operational Security

1. **Single instance** - Only one sidecar per wallet (avoid double-voting)
2. **Audit logs** - Preserve decisions.log for accountability
3. **Principle review** - Regularly review fork.yaml principles

## Backup and Recovery

### State Files

| File | Purpose | Backup? |
|------|---------|---------|
| `sidecar_state.json` | Processed proposals | Optional (regenerates) |
| `decisions.log` | Audit trail | Yes |
| `fork.yaml` | Voting principles | Yes |
| `config.yaml` | Configuration | Yes |

### Recovery Procedure

1. Restore `fork.yaml` and `config.yaml`
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
