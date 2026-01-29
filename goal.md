# DAHAO Sidecar v2: Observer Mode Migration

## Branch Name
`feature/observer-mode-gasless-authz`

---

## Executive Summary

Transform the existing DAHAO Sidecar from a **"Decider"** (makes voting decisions itself) into an **"Observer/Gateway"** (validates and relays voting decisions from mobile clients). This enables a **Gasless Voting** architecture where users sign voting intents on their phones, and the Node pays gas fees on their behalf using Cosmos Authz.

---

## Current State (v1 - Decider Mode)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Persona   │────▶│   Sidecar   │────▶│  Blockchain │
│   (local)   │     │  (decides)  │     │  (MsgVote)  │
└─────────────┘     └─────────────┘     └─────────────┘
                          │
                          ▼
                    ┌─────────────┐
                    │   Ollama    │
                    │   (LLM)     │
                    └─────────────┘
```

- Sidecar loads persona/fork locally
- Sidecar's LLM makes voting decisions
- Sidecar signs transactions with its own wallet
- Single-user, single-node model

---

## Target State (v2 - Observer Mode)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Mobile    │────▶│   Sidecar   │────▶│  Blockchain │────▶│   Record    │
│   (SML)     │     │ (validates) │     │  (MsgExec)  │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
      │                   │
      │ Intent + Sig      │ Semantic Check
      │                   ▼
      │             ┌─────────────┐
      │             │   Ollama    │
      │             │ (Observer)  │
      │             └─────────────┘
      │
      ▼
┌─────────────┐
│  On-Device  │
│    LLM      │
│  (Private)  │
└─────────────┘
```

- Mobile app (Flutter) makes voting decisions using on-device SML
- Persona NEVER leaves the phone (privacy preserved)
- Mobile signs **intent** (not full TX) and sends to Node
- Node validates: signature, authz grant, semantic consistency
- Node wraps intent in MsgExec and broadcasts (Node pays gas)
- Multi-user capable (future: Hive mode)

---

## Key Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Transaction Signing** | Intent-based (not full TX) | Mobile doesn't need to construct Cosmos TX |
| **Gas Payment** | Node pays via MsgExec | "Gasless" UX for users |
| **Authorization** | Cosmos Authz (MsgGrant) | Secure delegation, MsgVote only |
| **Persona Location** | Phone only | Maximum privacy |
| **Node Role** | Semantic Firewall | Validates reasoning consistency |
| **Backward Compatibility** | Dual mode (--mode flag) | Existing tests keep working |

---

## API Contract

### Base URL
`http://<node-ip>:<port>/api/v1`

### Endpoints

#### 1. GET /pair
Generate QR code data for mobile pairing.

**Response:**
```json
{
  "node_address": "cosmos1node...",
  "chain_id": "dahao-1",
  "ip": "192.168.1.5",
  "port": 8080,
  "session_token": "uuid-v4",
  "session_secret": "6-digit-code",
  "expires_at": "2026-01-30T12:00:00Z"
}
```

#### 2. POST /register
Complete pairing after mobile scans QR and grants authz.

**Request:**
```json
{
  "session_token": "uuid-from-qr",
  "session_secret": "6-digit-from-qr",
  "voter_address": "cosmos1alice...",
  "authz_tx_hash": "ABC123...",
  "pub_key": "base64-encoded-pubkey"
}
```

**Response:**
```json
{
  "status": "registered",
  "voter_address": "cosmos1alice...",
  "grant_expires_at": "2026-04-30T12:00:00Z"
}
```

#### 3. GET /proposals
List active proposals in voting period.

**Response:**
```json
{
  "proposals": [
    {
      "id": 42,
      "title": "Increase Block Size",
      "description": "...",
      "voting_start": "2026-01-28T00:00:00Z",
      "voting_end": "2026-02-01T00:00:00Z"
    }
  ]
}
```

#### 4. POST /submit_vote
Submit a signed voting intent.

**Request:**
```json
{
  "proposal_id": 42,
  "voter_address": "cosmos1alice...",
  "vote_option": "NO",
  "public_reasoning": "This proposal violates @protection principle...",
  "confidence_score": 0.95,
  "timestamp": 1706612345,
  "nonce": "random-8-bytes-hex",
  "intent_signature": "base64-ecdsa-signature",
  "pub_key": "base64-pubkey"
}
```

**Response (Success):**
```json
{
  "status": "broadcasted",
  "tx_hash": "A1B2C3...",
  "audit_log": "Reasoning consistent with SharedLaw."
}
```

**Response (Rejected):**
```json
{
  "status": "rejected",
  "error": "semantic_inconsistency",
  "detail": "Vote is NO but reasoning supports the proposal."
}
```

#### 5. GET /status
Node health and statistics.

**Response:**
```json
{
  "mode": "observer",
  "chain_connected": true,
  "llm_connected": true,
  "registered_voters": 5,
  "pending_proposals": 2,
  "node_balance": "50000stake"
}
```

---

## File Structure Changes

### New Files to Create

```
leviathan/
├── api/
│   ├── __init__.py
│   ├── server.py              # FastAPI application
│   ├── dependencies.py        # Shared dependencies (DB, LLM, Chain)
│   └── routes/
│       ├── __init__.py
│       ├── pair.py            # GET /pair
│       ├── register.py        # POST /register
│       ├── proposals.py       # GET /proposals
│       ├── vote.py            # POST /submit_vote
│       └── status.py          # GET /status
│
├── validator/
│   ├── __init__.py
│   ├── signature.py           # Intent signature verification (ECDSA)
│   ├── authz.py               # Cosmos Authz grant checking
│   └── semantic.py            # LLM reasoning consistency check
│
├── modes/
│   ├── __init__.py
│   ├── decider.py             # Original mode (refactored from loop.py)
│   └── observer.py            # New mode (API server)
│
├── chain/
│   ├── ... (existing)
│   └── authz.py               # NEW: MsgExec wrapper for voting on behalf
│
├── store/
│   ├── __init__.py
│   └── voters.py              # Registered voter management (SQLite or JSON)
│
└── tests/
    ├── ... (existing)
    ├── mock_phone.py          # Simulates mobile client for testing
    └── test_observer_mode.py  # Integration tests for new mode
```

### Modified Files

| File | Changes |
|------|---------|
| `main.py` | Add `--mode` flag (decider/observer), route to appropriate mode |
| `config/settings.py` | Add API server settings (host, port, cors) |
| `config.yaml` | Add `api:` section |
| `brain/prompts.py` | Add semantic validation prompt |

---

## Implementation Tasks

### Phase 1: API Skeleton (Priority: HIGH)

- [ ] **Task 1.1**: Create `api/server.py` with FastAPI app
  - CORS middleware for Flutter
  - Exception handlers
  - Lifespan events for startup/shutdown

- [ ] **Task 1.2**: Implement `GET /pair` endpoint
  - Generate UUID session_token
  - Generate 6-digit session_secret
  - Store in memory (dict) with expiration
  - Return node_address from config

- [ ] **Task 1.3**: Implement `POST /register` endpoint
  - Validate session_token + session_secret
  - Store voter_address + pub_key
  - (Mock) Verify authz_tx_hash on chain

- [ ] **Task 1.4**: Implement `GET /status` endpoint
  - Return mode, connection status, voter count

### Phase 2: Validators (Priority: HIGH)

- [ ] **Task 2.1**: Implement `validator/signature.py`
  ```python
  def verify_intent_signature(
      payload: dict,
      signature: bytes,
      pub_key: bytes
  ) -> bool:
      """
      1. Create canonical JSON (sorted keys, no spaces)
      2. SHA256 hash
      3. ECDSA verify (secp256k1 curve)
      """
  ```

- [ ] **Task 2.2**: Implement `validator/authz.py`
  ```python
  def check_authz_grant(
      ledger_client,
      granter: str,  # voter_address
      grantee: str   # node_address
  ) -> AuthzResult:
      """
      Query /cosmos.authz.v1beta1.Query/Grants
      Check for MsgVote authorization
      Return grant status and expiration
      """
  ```

### Phase 3: Semantic Validator (Priority: HIGH)

- [ ] **Task 3.1**: Implement `validator/semantic.py`
  ```python
  def validate_reasoning(
      proposal_text: str,
      vote_option: str,
      public_reasoning: str,
      shared_law: SharedLaw
  ) -> ValidationResult:
      """
      Use LLM to check if reasoning is consistent with:
      1. The vote option chosen
      2. The proposal content
      3. SharedLaw principles
      
      Detect hallucinations and contradictions.
      """
  ```

- [ ] **Task 3.2**: Create semantic validation prompt in `brain/prompts.py`

### Phase 4: Vote Submission (Priority: HIGH)

- [ ] **Task 4.1**: Implement `chain/authz.py`
  ```python
  def vote_on_behalf(
      ledger_client,
      node_wallet,
      voter_address: str,
      proposal_id: int,
      vote_option: VoteOption
  ) -> str:  # returns tx_hash
      """
      1. Create MsgVote with voter=voter_address
      2. Wrap in MsgExec with grantee=node_address
      3. Sign with node_wallet
      4. Broadcast and return tx_hash
      """
  ```

- [ ] **Task 4.2**: Implement `POST /submit_vote` endpoint
  - Pipeline: signature → authz → semantic → broadcast
  - Proper error responses for each failure type

- [ ] **Task 4.3**: Implement `GET /proposals` endpoint
  - Reuse existing `governance.fetch_voting_proposals()`

### Phase 5: Mode Integration (Priority: MEDIUM)

- [ ] **Task 5.1**: Refactor `sidecar/loop.py` → `modes/decider.py`
  - Extract as standalone mode
  - No functional changes, just reorganization

- [ ] **Task 5.2**: Create `modes/observer.py`
  - Start FastAPI server
  - Initialize dependencies (chain, llm, store)

- [ ] **Task 5.3**: Update `main.py`
  ```python
  @click.option('--mode', type=click.Choice(['decider', 'observer']), default='decider')
  def main(mode, ...):
      if mode == 'decider':
          run_decider_mode(...)
      else:
          run_observer_mode(...)
  ```

### Phase 6: Testing (Priority: MEDIUM)

- [ ] **Task 6.1**: Create `tests/mock_phone.py`
  - Generate test wallet
  - Sign intents
  - Call API endpoints
  - Test happy path and error cases

- [ ] **Task 6.2**: Write integration tests
  - Valid intent → broadcasted
  - Invalid signature → rejected
  - Missing authz → rejected
  - Inconsistent reasoning → rejected

---

## Technical Notes

### Intent Signature Format

Mobile signs the **canonical JSON** of the intent payload:

```python
# Canonical JSON (deterministic)
import json
canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))

# Hash
import hashlib
digest = hashlib.sha256(canonical.encode()).digest()

# Sign (secp256k1)
from ecdsa import SigningKey, SECP256k1
signature = private_key.sign_digest(digest, sigencode=sigencode_der)
```

### MsgExec Structure

```python
from cosmpy.protos.cosmos.authz.v1beta1.tx_pb2 import MsgExec
from cosmpy.protos.cosmos.gov.v1beta1.tx_pb2 import MsgVote

# Inner message (the actual vote)
vote_msg = MsgVote(
    proposal_id=42,
    voter="cosmos1alice...",  # The user who granted authz
    option=VOTE_OPTION_NO
)

# Outer message (node executes on behalf)
exec_msg = MsgExec(
    grantee="cosmos1node...",  # Node's address
    msgs=[vote_msg.SerializeToString()]
)
```

### Semantic Validation Prompt

```
TASK: Constitutional Consistency Audit

SHARED LAW PRINCIPLES:
{locked_principles}

PROPOSAL TEXT:
{proposal_text}

USER'S VOTE: {vote_option}
USER'S REASONING: "{public_reasoning}"

QUESTION: Does the reasoning logically support the vote choice given the proposal content and constitutional principles?

Detect:
- Contradictions (vote says NO but reasoning supports YES)
- Hallucinations (reasoning mentions things not in proposal)
- Constitutional violations (reasoning violates locked principles)

RESPOND IN JSON:
{
  "consistent": true/false,
  "issues": ["list of detected issues"],
  "recommendation": "accept/reject"
}
```

---

## Configuration Changes

### config.yaml additions

```yaml
api:
  host: "0.0.0.0"
  port: 8080
  cors_origins:
    - "http://localhost:*"
    - "capacitor://localhost"
    - "http://localhost"
  session_expiry_minutes: 30

observer:
  require_authz: true
  semantic_validation: true
  min_confidence_score: 0.5
```

---

## Success Criteria

1. **API Working**: Can hit all endpoints with curl/Postman
2. **Signature Verification**: Invalid signatures rejected
3. **Authz Check**: Votes without grants rejected
4. **Semantic Firewall**: Contradictory reasoning rejected
5. **MsgExec Broadcast**: Valid intents result in on-chain votes
6. **Backward Compatible**: `--mode=decider` still works as before
7. **Mock Phone Test**: `mock_phone.py` can complete full flow

---

## Dependencies to Add

```toml
# pyproject.toml additions
fastapi = "^0.109.0"
uvicorn = "^0.27.0"
python-multipart = "^0.0.6"
ecdsa = "^0.18.0"
```

---

## Out of Scope (Future Work)

- [ ] Flutter app implementation
- [ ] Push notifications for new proposals
- [ ] Hive mode (multi-persona)
- [ ] Persistent voter storage (currently in-memory)
- [ ] Rate limiting
- [ ] TLS/HTTPS
- [ ] WebSocket for real-time updates

---

## Commands

```bash
# Create branch
git checkout -b feature/observer-mode-gasless-authz

# Install new dependencies
uv add fastapi uvicorn python-multipart ecdsa

# Run in observer mode
python main.py --mode=observer --port=8080

# Run in decider mode (original behavior)
python main.py --mode=decider --persona persona.json

# Test with mock phone
python tests/mock_phone.py --node=http://localhost:8080

# Run tests
pytest tests/test_observer_mode.py -v
```

---

## References

- Cosmos Authz Module: https://docs.cosmos.network/main/modules/authz
- CosmPy Documentation: https://docs.fetch.ai/cosmpy/
- FastAPI: https://fastapi.tiangolo.com/
- secp256k1 ECDSA: https://github.com/tlsfuzzer/python-ecdsa

---

*This document serves as the complete specification for migrating DAHAO Sidecar to Observer Mode. Follow the tasks in order for best results.*