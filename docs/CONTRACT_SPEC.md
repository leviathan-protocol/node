# CONTRACT_SPEC.md — Leviathan Protocol Smart Contracts v2.0

> Implementation specification for all on-chain contracts.
> This document is the single source of truth for Claude Code or any developer implementing contracts.

**Chain:** Avalanche L1 Subnet (EVM) · Chain ID `43210` · Solidity `^0.8.24`
**Dependencies:** OpenZeppelin Contracts v5.x
**Architecture:** [ARCHITECTURE.md v2.0.0](./ARCHITECTURE.md)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Deployment Order & Dependencies](#2-deployment-order--dependencies)
3. [Core Contracts](#3-core-contracts)
   - 3.1 [LeviathanToken](#31-leviathantoken)
   - 3.2 [CoreReputation](#32-corereputation)
   - 3.3 [NodeRegistry](#33-noderegistry)
   - 3.4 [LeviathanForwarder](#34-leviathanforwarder)
   - 3.5 [DomainRegistry](#35-domainregistry)
   - 3.6 [CoreGovernor](#36-coregovernor)
   - 3.7 [DomainFactory](#37-domainfactory)
4. [Domain Contracts (Factory-Deployed)](#4-domain-contracts-factory-deployed)
   - 4.1 [DomainToken](#41-domaintoken)
   - 4.2 [DomainQuestBoard](#42-domainquestboard)
   - 4.3 [DomainGovernor](#43-domaingovernor)
5. [Cross-Contract Integration Map](#5-cross-contract-integration-map)
6. [Migration from v1 Contracts](#6-migration-from-v1-contracts)
7. [Security Considerations](#7-security-considerations)
8. [Test Requirements](#8-test-requirements)

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CORE LAYER (deploy once)                     │
│                                                                     │
│  LeviathanToken    CoreReputation    NodeRegistry    CoreGovernor   │
│  ($LVTN ERC20)     (XP + Ranks)      (Validators)   (XP-Weighted)  │
│                                                                     │
│  DomainRegistry    DomainFactory     LeviathanForwarder             │
│  (Domain catalog)  (Deploys domains) (Gasless meta-TX)              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ DomainFactory.createDomain()
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   DOMAIN LAYER (per domain, factory-deployed)        │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Domain: "security"                                          │    │
│  │  DomainToken ($SEC) · DomainQuestBoard · DomainGovernor     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Domain: "animal-welfare"                                    │    │
│  │  DomainToken ($AWL) · DomainQuestBoard · DomainGovernor     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ... more domains created via governance proposals ...              │
└─────────────────────────────────────────────────────────────────────┘
```

**Key design principles:**
- XP = power, not tokens. Governance is XP-weighted quadratic voting.
- Economy is earned. Domains progress through maturity stages before tokens flow.
- Multi-validator consensus. No single node can approve quests or slash agents.
- Federation tax. 1% of all domain quest revenue flows to core treasury.
- Gasless participation. ERC2771 meta-transactions for all governance actions.
- Soulbound reputation. XP cannot be transferred, only earned or slashed.

---

## 2. Deployment Order & Dependencies

Contracts must be deployed in this exact order due to constructor dependencies:

| Step | Contract | Constructor Needs | Post-Deploy Config |
|------|----------|-------------------|--------------------|
| 1 | `LeviathanToken` | `initialOwner` | — |
| 2 | `CoreReputation` | `initialOwner` | — |
| 3 | `NodeRegistry` | `initialOwner`, `reputationContract`, `stakingToken` | — |
| 4 | `LeviathanForwarder` | — | — |
| 5 | `DomainRegistry` | `initialOwner` | — |
| 6 | `CoreGovernor` | `reputation`, `forwarder`, `domainRegistry` | `CoreReputation.addAuthorized(coreGovernor)` |
| 7 | `DomainFactory` | `domainRegistry`, `coreReputation`, `nodeRegistry`, `forwarder`, `coreTreasury` | `DomainRegistry.setFactory(domainFactory)` |

**Post-deploy wiring:**
```
CoreReputation.addAuthorized(CoreGovernor)      // Governor can award governance XP
CoreReputation.addAuthorized(DomainFactory)     // Factory can register domain XP namespaces
DomainRegistry.setFactory(DomainFactory)        // Only factory can register domains
NodeRegistry.addAuthorized(CoreGovernor)        // Governor can slash nodes via governance
```

---

## 3. Core Contracts

### 3.1 LeviathanToken

> `$LVTN` — Core governance token. Used for node staking and domain seeding. NOT used for voting power (that's XP).

**Status:** EXISTS — minor changes needed (symbol fix, remove mint)

**File:** `contracts/src/LeviathanToken.sol`

#### Changes from v1
| Change | Reason |
|--------|--------|
| Symbol `"Leviathan"` → `"LVTN"` | Proper ticker |
| Remove `mint()` function | Fixed supply, no inflation |
| Add `STAKING_ALLOCATION`, `TREASURY_ALLOCATION` constants | Transparent supply distribution |

#### Storage

```solidity
uint256 public constant INITIAL_SUPPLY = 1_000_000_000 * 10**18;  // 1B tokens
uint256 public constant STAKING_ALLOCATION = 300_000_000 * 10**18; // 30% for node staking rewards
uint256 public constant TREASURY_ALLOCATION = 200_000_000 * 10**18; // 20% core treasury
// Remaining 50% to deployer for initial distribution
```

#### Interface

```solidity
// Inherited from ERC20, ERC20Burnable, ERC20Permit, ERC20Votes, Ownable
// No custom functions beyond constructor
constructor(address initialOwner)
    ERC20("Leviathan", "LVTN")
    ERC20Permit("Leviathan")
    Ownable(initialOwner)
```

#### Events
Standard ERC20 events only. No custom events.

#### Access Control
- `Ownable` — for emergency functions only (pause, etc.)
- No `mint()` — supply is fixed at deployment

---

### 3.2 CoreReputation

> Soulbound XP tracking across core and all domains. Tracks rank gates. Cannot be transferred.

**Status:** EXISTS as `Reputation.sol` — needs significant restructure

**File:** `contracts/src/CoreReputation.sol` (rename from `Reputation.sol`)

#### Changes from v1
| Change | Reason |
|--------|--------|
| Rename to `CoreReputation` | Clarity in federation model |
| `domainXP` keyed by `uint256 domainId` not `string` | Gas efficiency, type safety |
| Add `coreXP` separate from domain XP | Core participation XP (governance) is distinct |
| Add `getDomainRank()` | Per-domain rank gates |
| Add `getVotingPower()` | Quadratic XP-weighted: `sqrt(xp)` |
| Make soulbound explicit | `transfer()` reverts always |
| Remove `recordQuestAttempt()` | Redundant with `addXP`/`slashXP` |

#### Storage

```solidity
// Authorized callers (QuestBoards, Governor, Factory)
mapping(address => bool) public isAuthorized;

// Core XP (earned through core governance participation)
mapping(address => uint256) public coreXP;

// Domain XP (earned through domain quests + domain governance)
// agent => domainId => xp
mapping(address => mapping(uint256 => uint256)) public domainXP;

// Aggregate stats
mapping(address => AgentProfile) public agents;

// Registered domain IDs (set by DomainFactory)
mapping(uint256 => bool) public registeredDomains;

struct AgentProfile {
    uint256 totalXP;          // coreXP + sum(all domainXP) — cached for gas
    uint256 questsCompleted;
    uint256 questsFailed;
    uint256 firstActiveAt;
    uint256 lastActiveAt;
    bool exists;
}

enum Rank {
    Novice,     // 0-99 XP
    Sentinel,   // 100-499 XP
    Guardian,   // 500-1999 XP
    Arbiter     // 2000+ XP
}
```

#### Interface

```solidity
// ── XP Management (onlyAuthorized) ──

/// @notice Add core XP (governance participation)
function addCoreXP(address agent, uint256 amount) external onlyAuthorized;

/// @notice Add domain-specific XP (quest completion, domain governance)
function addDomainXP(address agent, uint256 domainId, uint256 amount) external onlyAuthorized;

/// @notice Slash XP for violations. Slashes from domain first, then core.
function slashXP(address agent, uint256 amount, uint256 domainId, bytes32 reasonHash) external onlyAuthorized;

// ── Registration (onlyAuthorized — called by DomainFactory) ──

/// @notice Register a new domain ID for XP tracking
function registerDomain(uint256 domainId) external onlyAuthorized;

// ── View Functions (public) ──

/// @notice Get rank based on XP in a context (0 = core, N = domainId)
function getRank(address agent, uint256 context) public view returns (Rank);

/// @notice Get rank from core XP
function getCoreRank(address agent) public view returns (Rank);

/// @notice Get rank from domain XP
function getDomainRank(address agent, uint256 domainId) public view returns (Rank);

/// @notice Quadratic voting power: sqrt(xp) scaled to 1e18
/// @param context 0 = core XP, N = domain XP
function getVotingPower(address agent, uint256 context) public view returns (uint256);

/// @notice Check minimum rank gate
function meetsRank(address agent, uint256 context, Rank minimumRank) public view returns (bool);

/// @notice Full profile view
function getProfile(address agent) external view returns (AgentProfile memory);

/// @notice Get XP for a specific domain
function getDomainXPValue(address agent, uint256 domainId) external view returns (uint256);

// ── Admin (onlyOwner) ──

function addAuthorized(address caller) external onlyOwner;
function removeAuthorized(address caller) external onlyOwner;
```

#### Events

```solidity
event CoreXPAdded(address indexed agent, uint256 amount, uint256 newCoreXP, Rank newRank);
event DomainXPAdded(address indexed agent, uint256 indexed domainId, uint256 amount, uint256 newDomainXP, Rank newRank);
event XPSlashed(address indexed agent, uint256 amount, uint256 indexed domainId, bytes32 reasonHash);
event DomainRegistered(uint256 indexed domainId);
event AuthorizedCallerAdded(address indexed caller);
event AuthorizedCallerRemoved(address indexed caller);
```

#### Rank Thresholds

```solidity
uint256 constant SENTINEL_THRESHOLD = 100;
uint256 constant GUARDIAN_THRESHOLD = 500;
uint256 constant ARBITER_THRESHOLD = 2000;
```

#### Voting Power Calculation

```solidity
/// @dev Quadratic: sqrt(xp) * 1e18 for precision
/// Uses Babylonian method for integer sqrt
function getVotingPower(address agent, uint256 context) public view returns (uint256) {
    uint256 xp = context == 0 ? coreXP[agent] : domainXP[agent][context];
    if (xp == 0) return 0;
    return sqrt(xp) * 1e18;
}
```

---

### 3.3 NodeRegistry

> Validator registration, staking, verdict tracking, slashing. Nodes must stake $LVTN to participate.

**Status:** NEW — does not exist yet

**File:** `contracts/src/NodeRegistry.sol`

#### Storage

```solidity
IERC20 public stakingToken;           // $LVTN
ICoreReputation public reputation;

uint256 public constant MIN_STAKE = 10_000 * 10**18;  // 10k LVTN minimum
uint256 public constant SLASH_PERCENT = 10;             // 10% slash per offense
uint256 public constant QUORUM_SIZE = 3;                // minimum validators per verdict

mapping(address => Node) public nodes;
address[] public activeNodes;

// Verdict tracking
mapping(bytes32 => Verdict) public verdicts;             // verdictId => Verdict
mapping(bytes32 => mapping(address => bool)) public hasVoted; // verdictId => node => voted

struct Node {
    uint256 stakedAmount;
    uint256 registeredAt;
    uint256 verdictsSubmitted;
    uint256 verdictsCorrect;       // agreed with majority
    uint256 slashCount;
    bool active;
}

struct Verdict {
    bytes32 subjectHash;           // hash of what's being validated
    VerdictType verdictType;
    uint256 approvalsCount;
    uint256 rejectionsCount;
    uint256 quorumNeeded;
    bool settled;
    bool outcome;                  // true = approved, false = rejected
    bytes32[] reasoningHashes;     // IPFS hashes of each node's reasoning
}

enum VerdictType {
    AGENT_ONBOARDING,              // Core alignment check
    DOMAIN_ALIGNMENT,              // Domain-specific alignment
    QUEST_VERIFICATION,            // Proof of quest completion
    SECURITY_AUDIT,                // Security action validation
    GOVERNANCE_PROPOSAL,           // Proposal validation
    BEHAVIOR_REVIEW                // Agent behavior audit
}
```

#### Interface

```solidity
// ── Node Management ──

/// @notice Register as a validator node. Transfers MIN_STAKE from caller.
function registerNode() external;

/// @notice Increase stake above minimum
function addStake(uint256 amount) external;

/// @notice Deregister and begin unstaking cooldown
function deregisterNode() external;

/// @notice Withdraw stake after cooldown period (7 days)
function withdrawStake() external;

// ── Verdict System ──

/// @notice Create a new verdict for multi-node consensus
/// @param subjectHash Hash of the subject being validated
/// @param verdictType Type of validation
/// @param quorumNeeded Number of votes needed (minimum QUORUM_SIZE)
/// @return verdictId Unique verdict identifier
function createVerdict(
    bytes32 subjectHash,
    VerdictType verdictType,
    uint256 quorumNeeded
) external returns (bytes32 verdictId);

/// @notice Submit a verdict vote (only active nodes)
/// @param verdictId The verdict to vote on
/// @param approve True = approve, false = reject
/// @param reasoningHash IPFS hash of reasoning document
function submitVerdictVote(
    bytes32 verdictId,
    bool approve,
    bytes32 reasoningHash
) external;

/// @notice Settle a verdict once quorum is reached
/// @return outcome True if approved, false if rejected
function settleVerdict(bytes32 verdictId) external returns (bool outcome);

// ── Slashing (onlyAuthorized — Governor or automated) ──

/// @notice Slash a node's stake for misbehavior
function slashNode(address node, bytes32 reasonHash) external onlyAuthorized;

// ── View Functions ──

function getNode(address node) external view returns (Node memory);
function getActiveNodeCount() external view returns (uint256);
function getVerdict(bytes32 verdictId) external view returns (Verdict memory);
function isActiveNode(address node) external view returns (bool);
function getNodeReliability(address node) external view returns (uint256 percent);
```

#### Events

```solidity
event NodeRegistered(address indexed node, uint256 stakedAmount);
event NodeDeregistered(address indexed node);
event StakeAdded(address indexed node, uint256 amount, uint256 newTotal);
event StakeWithdrawn(address indexed node, uint256 amount);
event NodeSlashed(address indexed node, uint256 slashAmount, bytes32 reasonHash);

event VerdictCreated(bytes32 indexed verdictId, bytes32 subjectHash, VerdictType verdictType, uint256 quorumNeeded);
event VerdictVoteSubmitted(bytes32 indexed verdictId, address indexed node, bool approve, bytes32 reasoningHash);
event VerdictSettled(bytes32 indexed verdictId, bool outcome, uint256 approvals, uint256 rejections);
```

#### Key Logic

```solidity
// Verdict ID generation
verdictId = keccak256(abi.encodePacked(subjectHash, verdictType, block.timestamp, msg.sender));

// Settlement condition
require(v.approvalsCount + v.rejectionsCount >= v.quorumNeeded, "Quorum not reached");
v.outcome = v.approvalsCount > v.rejectionsCount;

// Node reliability
reliability = (node.verdictsCorrect * 100) / node.verdictsSubmitted;
```

---

### 3.4 LeviathanForwarder

> ERC2771 meta-transaction forwarder for gasless participation.

**Status:** EXISTS — no changes needed

**File:** `contracts/src/LeviathanForwarder.sol`

```solidity
// Unchanged from v1. Simple ERC2771Forwarder wrapper.
contract LeviathanForwarder is ERC2771Forwarder {
    constructor() ERC2771Forwarder("LeviathanForwarder") {}
    function domainSeparator() external view returns (bytes32) {
        return _domainSeparatorV4();
    }
}
```

---

### 3.5 DomainRegistry

> Catalog of all domains, their maturity stages, principles hashes, and contract addresses.

**Status:** NEW — does not exist yet

**File:** `contracts/src/DomainRegistry.sol`

#### Storage

```solidity
address public factory;     // Only DomainFactory can register domains
address public owner;

uint256 public domainCount;
mapping(uint256 => Domain) public domains;
mapping(string => uint256) public domainIdBySlug;   // "security" => 1

struct Domain {
    uint256 id;
    string slug;                    // "security", "animal-welfare"
    string name;                    // "Security Domain"
    bytes32 principlesHash;         // IPFS hash of domain principles
    MaturityStage stage;
    address tokenContract;          // DomainToken address
    address questBoard;             // DomainQuestBoard address
    address governor;               // DomainGovernor address
    address treasury;               // Domain treasury address
    uint256 createdAt;
    uint256 stageUpdatedAt;
    bool active;
}

enum MaturityStage {
    CONSTITUTIONAL,    // Stage 1: Governance only, no economy
    PRE_ECONOMY,       // Stage 2: Sponsor quests, limited economy
    ACTIVE_ECONOMY     // Stage 3: Full marketplace, system quests
}

// Stage transition criteria (configurable by CoreGovernor)
struct StageRequirements {
    uint256 minCitizens;            // Minimum active citizens
    uint256 minParticipationRate;   // % of citizens voting (scaled 1e4)
    uint256 minConstitutionAge;     // Seconds since creation
    uint256 minQuestsCompleted;     // For PRE_ECONOMY → ACTIVE_ECONOMY
    uint256 minTreasuryBalance;     // For PRE_ECONOMY → ACTIVE_ECONOMY
    uint256 minValidatorReliability;// % reliability threshold (scaled 1e4)
}

mapping(MaturityStage => StageRequirements) public stageRequirements;
```

#### Interface

```solidity
// ── Domain Registration (onlyFactory) ──

/// @notice Register a new domain (called by DomainFactory)
function registerDomain(
    string calldata slug,
    string calldata name,
    bytes32 principlesHash,
    address tokenContract,
    address questBoard,
    address governor,
    address treasury
) external onlyFactory returns (uint256 domainId);

// ── Stage Transitions (onlyFactory or onlyOwner in Phase 1) ──

/// @notice Advance domain to next maturity stage
/// @dev Checks all StageRequirements are met
function advanceStage(uint256 domainId) external;

// ── Domain Updates (onlyDomainGovernor) ──

/// @notice Update principles hash after domain governance vote
function updatePrinciples(uint256 domainId, bytes32 newPrinciplesHash) external onlyDomainGovernor(domainId);

// ── Configuration (onlyOwner → later onlyCoreGovernor) ──

/// @notice Set stage transition requirements
function setStageRequirements(MaturityStage stage, StageRequirements calldata req) external onlyOwner;

/// @notice Set the factory address
function setFactory(address _factory) external onlyOwner;

// ── View Functions ──

function getDomain(uint256 domainId) external view returns (Domain memory);
function getDomainBySlug(string calldata slug) external view returns (Domain memory);
function getDomainStage(uint256 domainId) external view returns (MaturityStage);
function getDomainContracts(uint256 domainId) external view returns (address token, address questBoard, address governor);
function isDomainActive(uint256 domainId) external view returns (bool);
function getDomainCount() external view returns (uint256);
```

#### Events

```solidity
event DomainRegistered(uint256 indexed domainId, string slug, string name, bytes32 principlesHash);
event DomainStageAdvanced(uint256 indexed domainId, MaturityStage oldStage, MaturityStage newStage);
event DomainPrinciplesUpdated(uint256 indexed domainId, bytes32 oldHash, bytes32 newHash);
event StageRequirementsUpdated(MaturityStage indexed stage, StageRequirements requirements);
event DomainDeactivated(uint256 indexed domainId);
```

---

### 3.6 CoreGovernor

> Core governance. XP-weighted quadratic voting. Tiered approval thresholds. Reasoning-attached votes.

**Status:** EXISTS as `LeviathanGovernor.sol` — needs MAJOR rewrite

**File:** `contracts/src/CoreGovernor.sol` (rename from `LeviathanGovernor.sol`)

#### Changes from v1
| Change | Reason |
|--------|--------|
| Rename to `CoreGovernor` | Clarity — domain governors are separate |
| Remove OZ Governor inheritance | OZ Governor is token-weighted; we need XP-weighted |
| Custom proposal + voting from scratch | XP-weighted quadratic voting with tiered thresholds |
| Add proposal categories | Different thresholds: standard (60%), constitutional (95%), immutable (reverts) |
| Add reasoning requirement | Every vote must include IPFS reasoning hash |
| Add rollback window | 24h delay before execution |
| Keep ERC2771 | Gasless voting still needed |

#### Storage

```solidity
ICoreReputation public reputation;
IDomainRegistry public domainRegistry;

uint256 public proposalCount;
mapping(uint256 => Proposal) public proposals;
mapping(uint256 => mapping(address => Vote)) public votes;  // proposalId => voter => Vote

uint256 public constant VOTING_DELAY = 1 days;
uint256 public constant VOTING_PERIOD = 7 days;
uint256 public constant EXECUTION_DELAY = 1 days;   // 24h rollback window
uint256 public constant MIN_PROPOSER_RANK = 1;      // Sentinel minimum to propose

enum ProposalCategory {
    STANDARD,          // 60% approval — normal governance
    CONSTITUTIONAL,    // 95% approval — principle changes
    IMMUTABLE          // Always reverts — cannot modify immutable principles
}

enum ProposalState {
    PENDING,           // Created, waiting for voting delay
    ACTIVE,            // Voting open
    DEFEATED,          // Did not reach threshold
    SUCCEEDED,         // Passed, waiting execution delay
    QUEUED,            // In execution delay (rollback window)
    EXECUTED,          // Done
    CANCELLED,         // Cancelled by proposer or governance
    EXPIRED            // Execution window passed
}

struct Proposal {
    uint256 id;
    address proposer;
    ProposalCategory category;
    string title;
    bytes32 descriptionHash;       // IPFS hash of full proposal
    bytes32 principlesHash;        // New principles hash (if constitutional)

    // Execution
    address[] targets;
    uint256[] values;
    bytes[] calldatas;

    // Timing
    uint256 createdAt;
    uint256 votingStartsAt;
    uint256 votingEndsAt;
    uint256 executionWindowEndsAt;

    // Tallies (stored as sqrt(xp) * 1e18 sums)
    uint256 forVotes;
    uint256 againstVotes;
    uint256 abstainVotes;

    ProposalState state;
    bool executed;
}

struct Vote {
    uint8 support;          // 0 = against, 1 = for, 2 = abstain
    uint256 votingPower;    // sqrt(coreXP) at vote time
    bytes32 reasoningHash;  // IPFS hash — MANDATORY
    bool hasVoted;
}
```

#### Interface

```solidity
// ── Proposals ──

/// @notice Create a governance proposal
/// @dev Proposer must be Sentinel rank or above in core
function propose(
    ProposalCategory category,
    string calldata title,
    bytes32 descriptionHash,
    address[] calldata targets,
    uint256[] calldata values,
    bytes[] calldata calldatas
) external returns (uint256 proposalId);

/// @notice Create a constitutional proposal (principle changes)
function proposeConstitutional(
    string calldata title,
    bytes32 descriptionHash,
    bytes32 newPrinciplesHash,
    address[] calldata targets,
    uint256[] calldata values,
    bytes[] calldata calldatas
) external returns (uint256 proposalId);

/// @notice Cancel a proposal (only proposer, only before voting starts)
function cancel(uint256 proposalId) external;

// ── Voting ──

/// @notice Cast vote with mandatory reasoning
/// @param proposalId Proposal to vote on
/// @param support 0 = against, 1 = for, 2 = abstain
/// @param reasoningHash IPFS hash of reasoning (CANNOT be bytes32(0))
function castVote(
    uint256 proposalId,
    uint8 support,
    bytes32 reasoningHash
) external;

// ── Execution ──

/// @notice Execute a succeeded proposal after execution delay
function execute(uint256 proposalId) external;

// ── View Functions ──

function getProposal(uint256 proposalId) external view returns (Proposal memory);
function getProposalState(uint256 proposalId) external view returns (ProposalState);
function getVote(uint256 proposalId, address voter) external view returns (Vote memory);
function getApprovalThreshold(ProposalCategory category) public pure returns (uint256);
function hasVoted(uint256 proposalId, address voter) external view returns (bool);
function quorumReached(uint256 proposalId) external view returns (bool);
```

#### Events

```solidity
event ProposalCreated(
    uint256 indexed proposalId,
    address indexed proposer,
    ProposalCategory category,
    string title,
    bytes32 descriptionHash,
    uint256 votingStartsAt,
    uint256 votingEndsAt
);
event VoteCast(
    address indexed voter,
    uint256 indexed proposalId,
    uint8 support,
    uint256 votingPower,
    bytes32 reasoningHash
);
event ProposalExecuted(uint256 indexed proposalId);
event ProposalCancelled(uint256 indexed proposalId);
event ProposalStateChanged(uint256 indexed proposalId, ProposalState oldState, ProposalState newState);
```

#### Key Logic: Approval Thresholds

```solidity
function getApprovalThreshold(ProposalCategory category) public pure returns (uint256) {
    if (category == ProposalCategory.STANDARD) return 6000;        // 60.00%
    if (category == ProposalCategory.CONSTITUTIONAL) return 9500;  // 95.00%
    revert("Immutable proposals cannot pass");                     // IMMUTABLE always reverts
}

// Threshold check (scaled to 1e4 = 100.00%)
function _thresholdMet(uint256 proposalId) internal view returns (bool) {
    Proposal storage p = proposals[proposalId];
    uint256 totalCast = p.forVotes + p.againstVotes;  // abstains don't count
    if (totalCast == 0) return false;
    uint256 approvalRate = (p.forVotes * 10000) / totalCast;
    return approvalRate >= getApprovalThreshold(p.category);
}
```

#### Key Logic: Voting Power

```solidity
// Voting power is sqrt(coreXP) at the time of voting
// This is quadratic: an agent with 4x XP gets only 2x voting power
function _getVotingPower(address voter) internal view returns (uint256) {
    return reputation.getVotingPower(voter, 0); // 0 = core context
}
```

---

### 3.7 DomainFactory

> Atomically deploys a complete domain (Token + QuestBoard + Governor). Phase 1: admin-gated. Phase 2: governance-gated.

**Status:** NEW — does not exist yet

**File:** `contracts/src/DomainFactory.sol`

#### Storage

```solidity
IDomainRegistry public registry;
ICoreReputation public coreReputation;
INodeRegistry public nodeRegistry;
address public forwarder;
address public coreTreasury;
address public owner;

bool public governanceGated;   // false = admin creates, true = governance creates
```

#### Interface

```solidity
/// @notice Deploy a complete domain: Token + QuestBoard + Governor
/// @param slug URL-safe identifier ("security", "animal-welfare")
/// @param name Human-readable name ("Security Domain")
/// @param tokenName ERC20 name ("Security Token")
/// @param tokenSymbol ERC20 symbol ("SEC")
/// @param initialTokenSupply Initial supply minted to domain treasury
/// @param principlesHash IPFS hash of domain principles document
/// @return domainId The registered domain ID
function createDomain(
    string calldata slug,
    string calldata name,
    string calldata tokenName,
    string calldata tokenSymbol,
    uint256 initialTokenSupply,
    bytes32 principlesHash
) external returns (uint256 domainId);

/// @notice Switch from admin-gated to governance-gated domain creation
function enableGovernanceGating() external onlyOwner;

// ── View ──

function getDeployedDomain(uint256 domainId) external view returns (
    address token,
    address questBoard,
    address governor,
    address treasury
);
```

#### Events

```solidity
event DomainCreated(
    uint256 indexed domainId,
    string slug,
    address token,
    address questBoard,
    address governor,
    address treasury
);
event GovernanceGatingEnabled();
```

#### Key Logic: Atomic Deployment

```solidity
function createDomain(...) external returns (uint256 domainId) {
    require(!governanceGated || msg.sender == coreGovernor, "Governance vote required");

    // 1. Deploy DomainToken
    DomainToken token = new DomainToken(tokenName, tokenSymbol, initialTokenSupply);

    // 2. Deploy treasury (simple address, token minted here)
    address treasury = address(token); // tokens held by token contract initially
    // OR deploy a minimal treasury contract

    // 3. Deploy DomainQuestBoard
    DomainQuestBoard questBoard = new DomainQuestBoard(
        address(token),
        address(coreReputation),
        address(nodeRegistry),
        treasury,
        coreTreasury,        // core treasury for federation tax
        domainId             // will be set after registration
    );

    // 4. Deploy DomainGovernor
    DomainGovernor governor = new DomainGovernor(
        address(coreReputation),
        forwarder,
        domainId
    );

    // 5. Register in DomainRegistry
    domainId = registry.registerDomain(
        slug, name, principlesHash,
        address(token), address(questBoard), address(governor), treasury
    );

    // 6. Register domain in CoreReputation for XP tracking
    coreReputation.registerDomain(domainId);

    // 7. Wire permissions
    token.transferOwnership(address(governor));       // Governor controls token
    questBoard.setDomainId(domainId);                 // Set the domain ID
    coreReputation.addAuthorized(address(questBoard)); // QuestBoard can award XP

    emit DomainCreated(domainId, slug, address(token), address(questBoard), address(governor), treasury);
}
```

---

## 4. Domain Contracts (Factory-Deployed)

These contracts are deployed by `DomainFactory` for each domain. They share common patterns but operate independently per domain.

### 4.1 DomainToken

> Per-domain ERC20 token with voting support. Minted to domain treasury on creation.

**Status:** NEW — does not exist yet

**File:** `contracts/src/DomainToken.sol`

```solidity
// Simple ERC20 + ERC20Votes
// No special logic — token economics enforced by QuestBoard and Governor

contract DomainToken is ERC20, ERC20Burnable, ERC20Permit, ERC20Votes, Ownable {
    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply
    )
        ERC20(name_, symbol_)
        ERC20Permit(name_)
        Ownable(msg.sender)  // Factory deploys, then transfers ownership to Governor
    {
        _mint(msg.sender, initialSupply);  // Minted to factory, transferred to treasury
    }

    // No mint function — supply controlled by governance
    // Owner (DomainGovernor) can mint via governance proposal if needed

    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }

    // Standard overrides for ERC20Votes
    function _update(address from, address to, uint256 value) internal override(ERC20, ERC20Votes) {
        super._update(from, to, value);
    }

    function nonces(address owner_) public view override(ERC20Permit, Nonces) returns (uint256) {
        return super.nonces(owner_);
    }
}
```

---

### 4.2 DomainQuestBoard

> Per-domain quest marketplace with multi-validator verification and 85/9/5/1 fee split.

**Status:** EXISTS as `QuestBoard.sol` — needs MAJOR rewrite

**File:** `contracts/src/DomainQuestBoard.sol` (rename from `QuestBoard.sol`)

#### Changes from v1
| Change | Reason |
|--------|--------|
| Rename to `DomainQuestBoard` | Per-domain, not global |
| Multi-validator verification via NodeRegistry | No single validator can approve |
| Fee split: 85/9/5/1 | Agent/validators/domain/core federation tax |
| Quest sources: SPONSOR, SYSTEM, GOVERNANCE | Track where quests come from |
| Rank gates on quest claims | Higher-value quests need higher rank |
| Maturity stage awareness | Only SPONSOR quests in PRE_ECONOMY, all types in ACTIVE_ECONOMY |
| Domain XP not core XP | Quest completion awards domain-specific XP |

#### Storage

```solidity
IERC20 public rewardToken;              // DomainToken
ICoreReputation public reputation;
INodeRegistry public nodeRegistry;
IDomainRegistry public domainRegistry;

uint256 public domainId;
address public domainTreasury;
address public coreTreasury;

uint256 public questCounter;

// Fee percentages (scaled to 1e4 = 100.00%)
uint256 public constant AGENT_FEE = 8500;       // 85%
uint256 public constant VALIDATOR_FEE = 900;     // 9%
uint256 public constant DOMAIN_FEE = 500;        // 5%
uint256 public constant CORE_FEE = 100;          // 1% federation tax

mapping(uint256 => Quest) public quests;
mapping(uint256 => bytes32) public questVerdictIds;   // questId => NodeRegistry verdictId

enum QuestSource {
    SPONSOR,       // External sponsor created and funded
    SYSTEM,        // System-generated (Phase 2, ACTIVE_ECONOMY only)
    GOVERNANCE     // Created via governance proposal (Phase 2)
}

enum QuestStatus {
    OPEN,
    CLAIMED,
    PROOF_SUBMITTED,
    VERIFICATION_PENDING,   // Multi-node verdict in progress
    COMPLETED,
    REJECTED,
    CANCELLED,
    EXPIRED
}

struct Quest {
    uint256 id;
    address sponsor;
    address agent;
    QuestSource source;
    QuestStatus status;
    string description;
    bytes32 proofHash;             // IPFS hash of submitted proof
    uint256 bounty;
    uint256 xpReward;
    uint256 deadline;
    Rank minimumRank;              // Rank gate for claiming
    uint256 createdAt;
    uint256 completedAt;
}
```

#### Interface

```solidity
// ── Quest Creation ──

/// @notice Create a sponsor-funded quest
function createQuest(
    string calldata description,
    uint256 bounty,
    uint256 xpReward,
    uint256 deadline,
    Rank minimumRank
) external returns (uint256 questId);

/// @notice Create a system quest (Phase 2, onlyAuthorized)
function createSystemQuest(
    string calldata description,
    uint256 bounty,
    uint256 xpReward,
    uint256 deadline,
    Rank minimumRank
) external onlyAuthorized returns (uint256 questId);

/// @notice Cancel quest (only sponsor, only if OPEN)
function cancelQuest(uint256 questId) external;

// ── Agent Actions ──

/// @notice Claim an open quest (must meet rank gate)
function claimQuest(uint256 questId) external;

/// @notice Submit proof of completion
function submitProof(uint256 questId, bytes32 proofHash) external;

// ── Verification (triggered by NodeRegistry verdict settlement) ──

/// @notice Called after NodeRegistry verdict settles
/// @dev Only callable by NodeRegistry or authorized verifier
function settleQuest(uint256 questId, bool approved) external;

// ── View Functions ──

function getQuest(uint256 questId) external view returns (Quest memory);
function getQuestsByStatus(QuestStatus status, uint256 limit) external view returns (Quest[] memory);
function getDomainId() external view returns (uint256);
```

#### Events

```solidity
event QuestCreated(uint256 indexed questId, address indexed sponsor, QuestSource source, uint256 bounty, uint256 xpReward, Rank minimumRank);
event QuestClaimed(uint256 indexed questId, address indexed agent);
event ProofSubmitted(uint256 indexed questId, address indexed agent, bytes32 proofHash);
event QuestCompleted(uint256 indexed questId, address indexed agent, uint256 agentReward, uint256 validatorReward, uint256 domainFee, uint256 coreFee);
event QuestRejected(uint256 indexed questId, address indexed agent);
event QuestCancelled(uint256 indexed questId);
event QuestExpired(uint256 indexed questId);
```

#### Key Logic: Fee Distribution

```solidity
function _distributeRewards(Quest storage quest) internal {
    uint256 bounty = quest.bounty;

    uint256 agentAmount    = (bounty * AGENT_FEE) / 10000;      // 85%
    uint256 validatorAmount = (bounty * VALIDATOR_FEE) / 10000;  // 9%
    uint256 domainAmount   = (bounty * DOMAIN_FEE) / 10000;      // 5%
    uint256 coreAmount     = bounty - agentAmount - validatorAmount - domainAmount; // 1% (dust-safe)

    rewardToken.safeTransfer(quest.agent, agentAmount);
    // Validator reward distributed by NodeRegistry based on verdict participation
    rewardToken.safeTransfer(address(nodeRegistry), validatorAmount);
    rewardToken.safeTransfer(domainTreasury, domainAmount);
    rewardToken.safeTransfer(coreTreasury, coreAmount);
}
```

#### Key Logic: Rank Gate

```solidity
function claimQuest(uint256 questId) external {
    Quest storage quest = quests[questId];
    require(quest.status == QuestStatus.OPEN, "Not open");
    require(block.timestamp < quest.deadline, "Expired");
    require(
        reputation.meetsRank(msg.sender, domainId, quest.minimumRank),
        "Rank too low"
    );
    quest.agent = msg.sender;
    quest.status = QuestStatus.CLAIMED;
    emit QuestClaimed(questId, msg.sender);
}
```

#### Key Logic: Multi-Validator Verification Flow

```solidity
function submitProof(uint256 questId, bytes32 proofHash) external {
    Quest storage quest = quests[questId];
    require(quest.agent == msg.sender, "Not assigned");
    require(quest.status == QuestStatus.CLAIMED, "Not claimed");

    quest.proofHash = proofHash;
    quest.status = QuestStatus.VERIFICATION_PENDING;

    // Create verdict in NodeRegistry for multi-node consensus
    bytes32 verdictId = nodeRegistry.createVerdict(
        keccak256(abi.encodePacked(domainId, questId, proofHash)),
        INodeRegistry.VerdictType.QUEST_VERIFICATION,
        3  // quorum of 3 nodes
    );
    questVerdictIds[questId] = verdictId;

    emit ProofSubmitted(questId, msg.sender, proofHash);
}
```

---

### 4.3 DomainGovernor

> Per-domain governance. Domain XP-weighted voting. Can be stricter than core, never weaker.

**Status:** NEW — does not exist yet

**File:** `contracts/src/DomainGovernor.sol`

#### Storage

```solidity
ICoreReputation public reputation;
uint256 public domainId;

// Same proposal structure as CoreGovernor but uses domain XP
uint256 public proposalCount;
mapping(uint256 => Proposal) public proposals;
mapping(uint256 => mapping(address => Vote)) public votes;

uint256 public constant VOTING_DELAY = 1 days;
uint256 public constant VOTING_PERIOD = 5 days;      // Shorter than core (domains move faster)
uint256 public constant EXECUTION_DELAY = 12 hours;   // Shorter rollback window

// Same enums and structs as CoreGovernor
// (ProposalCategory, ProposalState, Proposal, Vote)
```

#### Interface

```solidity
// Same interface as CoreGovernor but:
// - Uses domain XP for voting power: reputation.getVotingPower(voter, domainId)
// - Can only execute actions on domain contracts (token, questBoard, registry update)
// - Cannot weaken core principles

function propose(...) external returns (uint256 proposalId);
function castVote(uint256 proposalId, uint8 support, bytes32 reasoningHash) external;
function execute(uint256 proposalId) external;
function getProposal(uint256 proposalId) external view returns (Proposal memory);
function getProposalState(uint256 proposalId) external view returns (ProposalState);
```

#### Key Difference from CoreGovernor

```solidity
function _getVotingPower(address voter) internal view returns (uint256) {
    // Domain XP, not core XP
    return reputation.getVotingPower(voter, domainId);
}
```

---

## 5. Cross-Contract Integration Map

```
LeviathanToken ──stake──► NodeRegistry
                ──seed───► DomainFactory ──creates──► DomainToken
                                                      DomainQuestBoard
                                                      DomainGovernor

CoreReputation ◄──addCoreXP──── CoreGovernor (governance participation)
               ◄──addDomainXP── DomainQuestBoard (quest completion)
               ◄──addDomainXP── DomainGovernor (domain governance participation)
               ◄──slashXP────── NodeRegistry (verdict-based slashing)
               ──getVotingPower──► CoreGovernor (core votes)
               ──getVotingPower──► DomainGovernor (domain votes)
               ──meetsRank──────► DomainQuestBoard (rank gates)

NodeRegistry ◄──registerNode──── Validator nodes
             ◄──submitVerdictVote── Validator nodes
             ──settleVerdict──► DomainQuestBoard (quest approval/rejection)
             ──slashNode──────► (self, on misbehavior)

DomainRegistry ◄──registerDomain── DomainFactory
               ◄──advanceStage──── CoreGovernor (governance vote)
               ◄──updatePrinciples── DomainGovernor

DomainQuestBoard ──federation tax (1%)──► Core Treasury
                 ──domain fee (5%)──────► Domain Treasury
                 ──validator fee (9%)───► NodeRegistry (→ validators)
                 ──agent reward (85%)───► Agent

LeviathanForwarder ──meta-tx──► CoreGovernor
                   ──meta-tx──► DomainGovernor
                   ──meta-tx──► DomainQuestBoard
```

---

## 6. Migration from v1 Contracts

| v1 File | Action | v2 File |
|---------|--------|---------|
| `LeviathanToken.sol` | **MODIFY** — fix symbol, remove mint | `LeviathanToken.sol` |
| `Reputation.sol` | **REWRITE** → separate core/domain XP, voting power | `CoreReputation.sol` |
| `LeviathanGovernor.sol` | **REWRITE** → custom XP-weighted, not OZ Governor | `CoreGovernor.sol` |
| `QuestBoard.sol` | **REWRITE** → multi-validator, fee split, rank gates | `DomainQuestBoard.sol` |
| `LeviathanForwarder.sol` | **KEEP** — no changes | `LeviathanForwarder.sol` |
| — | **CREATE** | `NodeRegistry.sol` |
| — | **CREATE** | `DomainRegistry.sol` |
| — | **CREATE** | `DomainFactory.sol` |
| — | **CREATE** | `DomainToken.sol` |
| — | **CREATE** | `DomainGovernor.sol` |

**Migration steps:**
1. Create new files, do NOT delete old files yet
2. Implement and test each contract individually
3. Write integration tests for cross-contract flows
4. Deploy to local subnet for end-to-end testing
5. Remove old files only after v2 contracts pass all tests

---

## 7. Security Considerations

### Access Control Matrix

| Function | Who Can Call | Enforcement |
|----------|-------------|-------------|
| `addCoreXP` | CoreGovernor | `onlyAuthorized` |
| `addDomainXP` | DomainQuestBoard, DomainGovernor | `onlyAuthorized` |
| `slashXP` | NodeRegistry (via verdict) | `onlyAuthorized` |
| `registerNode` | Anyone with MIN_STAKE | Stake transfer |
| `submitVerdictVote` | Active nodes only | `require(nodes[msg.sender].active)` |
| `createQuest` | Anyone (sponsor) | Token transfer |
| `claimQuest` | Citizens meeting rank gate | `meetsRank()` check |
| `settleQuest` | NodeRegistry verdict callback | `onlyAuthorized` |
| `propose` (core) | Sentinel+ rank | `meetsRank(SENTINEL)` |
| `castVote` | Any citizen with core XP | `require(coreXP > 0)` |
| `createDomain` | Admin (Phase 1) / CoreGovernor (Phase 2) | `onlyOwner` / `onlyCoreGovernor` |
| `advanceStage` | Admin (Phase 1) / CoreGovernor (Phase 2) | Criteria check |

### Reentrancy
- All token transfers use `ReentrancyGuard`
- Quest settlement is atomic: verify → distribute → update state
- External calls (NodeRegistry ↔ QuestBoard) use checks-effects-interactions

### Integer Overflow
- Solidity 0.8.24 has built-in overflow checks
- Fee calculations use `bounty - sum` for dust safety (last recipient gets remainder)

### Front-running
- Quest claims are first-come-first-served (acceptable for MVP)
- Votes use commit-reveal if needed in Phase 2
- Verdict votes are independent (no knowledge of other nodes' votes until settlement)

### Upgradeability
- Phase 1: No proxy pattern. Direct deployment. Redeploy if needed.
- Phase 2: Consider UUPS proxy for core contracts if governance demands it.

---

## 8. Test Requirements

### Unit Tests (per contract)

| Contract | Test File | Key Tests |
|----------|-----------|-----------|
| LeviathanToken | `test/LeviathanToken.test.js` | Fixed supply, no mint, permit, delegation |
| CoreReputation | `test/CoreReputation.test.js` | Core XP, domain XP, rank thresholds, voting power (sqrt), soulbound, authorization |
| NodeRegistry | `test/NodeRegistry.test.js` | Register/deregister, staking, verdicts, quorum, slashing, reliability tracking |
| CoreGovernor | `test/CoreGovernor.test.js` | Propose, vote (quadratic), thresholds (60%/95%), execution delay, reasoning requirement, cancel |
| DomainFactory | `test/DomainFactory.test.js` | Atomic deployment, wiring, admin vs governance gating |
| DomainRegistry | `test/DomainRegistry.test.js` | Register, stage transitions, requirements, principles update |
| DomainToken | `test/DomainToken.test.js` | Standard ERC20, ownership, mint gating |
| DomainQuestBoard | `test/DomainQuestBoard.test.js` | Create, claim, prove, multi-validator verify, fee split (85/9/5/1), rank gates, maturity awareness |
| DomainGovernor | `test/DomainGovernor.test.js` | Domain XP voting, domain-scoped execution |
| LeviathanForwarder | `test/LeviathanForwarder.test.js` | Meta-tx forwarding, signature verification |

### Integration Tests

| Flow | File | Description |
|------|------|-------------|
| Full quest lifecycle | `test/integration/QuestLifecycle.test.js` | Sponsor creates → agent claims → submits proof → 3 nodes vote → settlement → fee distribution → XP awarded |
| Domain creation | `test/integration/DomainCreation.test.js` | Factory deploys all 3 contracts → registered in DomainRegistry → XP namespace created |
| Governance lifecycle | `test/integration/Governance.test.js` | Propose → vote period → threshold check → execution delay → execute |
| Node slashing | `test/integration/NodeSlashing.test.js` | Node submits bad verdict → majority disagrees → stake slashed |
| Stage transition | `test/integration/StageTransition.test.js` | Domain meets criteria → governance proposal → stage advances → new features unlock |

---

## Appendix: Interface Files

Create these interfaces for cross-contract calls:

**`contracts/src/interfaces/ICoreReputation.sol`**
```solidity
interface ICoreReputation {
    function addCoreXP(address agent, uint256 amount) external;
    function addDomainXP(address agent, uint256 domainId, uint256 amount) external;
    function slashXP(address agent, uint256 amount, uint256 domainId, bytes32 reasonHash) external;
    function registerDomain(uint256 domainId) external;
    function getVotingPower(address agent, uint256 context) external view returns (uint256);
    function meetsRank(address agent, uint256 context, uint8 minimumRank) external view returns (bool);
    function getCoreRank(address agent) external view returns (uint8);
    function getDomainRank(address agent, uint256 domainId) external view returns (uint8);
    function addAuthorized(address caller) external;
}
```

**`contracts/src/interfaces/INodeRegistry.sol`**
```solidity
interface INodeRegistry {
    enum VerdictType { AGENT_ONBOARDING, DOMAIN_ALIGNMENT, QUEST_VERIFICATION, SECURITY_AUDIT, GOVERNANCE_PROPOSAL, BEHAVIOR_REVIEW }
    function createVerdict(bytes32 subjectHash, VerdictType verdictType, uint256 quorumNeeded) external returns (bytes32);
    function settleVerdict(bytes32 verdictId) external returns (bool);
    function isActiveNode(address node) external view returns (bool);
    function getActiveNodeCount() external view returns (uint256);
}
```

**`contracts/src/interfaces/IDomainRegistry.sol`**
```solidity
interface IDomainRegistry {
    enum MaturityStage { CONSTITUTIONAL, PRE_ECONOMY, ACTIVE_ECONOMY }
    function registerDomain(string calldata slug, string calldata name, bytes32 principlesHash, address token, address questBoard, address governor, address treasury) external returns (uint256);
    function getDomainStage(uint256 domainId) external view returns (MaturityStage);
    function getDomainContracts(uint256 domainId) external view returns (address token, address questBoard, address governor);
    function isDomainActive(uint256 domainId) external view returns (bool);
    function setFactory(address factory) external;
}
```

---

*This specification is the implementation contract between architecture and code. Every function signature, every event, every storage variable defined here is canonical. Claude Code or any developer implementing these contracts should follow this spec exactly.*

*Version: 2.0.0 · Date: 2026-02-06 · Companion: ARCHITECTURE.md v2.0.0*