// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title QuestBoard
 * @dev Decentralized job marketplace for AI agents.
 * 
 * Workflow:
 * 1. Sponsor creates quest with bounty (tokens locked)
 * 2. Agent claims the quest
 * 3. Agent submits proof of completion
 * 4. Validator (Node) verifies and releases payment
 * 
 * This is the heart of Leviathan's "Gig Economy for AI Agents"
 */
contract QuestBoard is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ==================== State ====================
    
    IERC20 public rewardToken;
    IReputation public reputationContract;
    
    uint256 public questCounter;
    uint256 public protocolFeePercent = 5; // 5% to treasury
    uint256 public nodeFeePercent = 10;    // 10% to validator node
    
    address public treasury;
    
    // Authorized validator nodes
    mapping(address => bool) public isValidator;
    
    // Quest data
    mapping(uint256 => Quest) public quests;
    
    // ==================== Structs ====================
    
    enum QuestStatus {
        Open,       // Waiting for agent
        Claimed,    // Agent working on it
        Submitted,  // Proof submitted, waiting validation
        Completed,  // Verified and paid
        Cancelled   // Sponsor cancelled (before claim)
    }
    
    struct Quest {
        uint256 id;
        address sponsor;
        address agent;
        address validator;
        string domain;          // "security", "climate", etc.
        string description;
        string proofUrl;        // Submitted evidence
        uint256 bounty;
        uint256 deadline;
        uint256 xpReward;
        QuestStatus status;
        uint256 createdAt;
        uint256 completedAt;
    }
    
    // ==================== Events ====================
    
    event QuestCreated(
        uint256 indexed questId,
        address indexed sponsor,
        string domain,
        uint256 bounty,
        uint256 deadline
    );
    
    event QuestClaimed(
        uint256 indexed questId,
        address indexed agent
    );
    
    event ProofSubmitted(
        uint256 indexed questId,
        address indexed agent,
        string proofUrl
    );
    
    event QuestVerified(
        uint256 indexed questId,
        address indexed agent,
        address indexed validator,
        bool approved,
        uint256 agentReward
    );
    
    event QuestCancelled(
        uint256 indexed questId,
        address indexed sponsor
    );
    
    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);
    
    // ==================== Constructor ====================
    
    constructor(
        address _rewardToken,
        address _treasury,
        address initialOwner
    ) Ownable(initialOwner) {
        rewardToken = IERC20(_rewardToken);
        treasury = _treasury;
    }
    
    // ==================== Sponsor Functions ====================
    
    /**
     * @dev Create a new quest with locked bounty
     * @param domain Quest category (security, climate, etc.)
     * @param description What needs to be done
     * @param bounty Token reward amount
     * @param deadline Timestamp for completion
     * @param xpReward XP points for agent reputation
     */
    function createQuest(
        string calldata domain,
        string calldata description,
        uint256 bounty,
        uint256 deadline,
        uint256 xpReward
    ) external nonReentrant returns (uint256 questId) {
        require(bounty > 0, "Bounty must be > 0");
        require(deadline > block.timestamp, "Deadline must be future");
        require(bytes(description).length > 0, "Description required");
        
        // Transfer bounty from sponsor to contract
        rewardToken.safeTransferFrom(msg.sender, address(this), bounty);
        
        questId = ++questCounter;
        
        quests[questId] = Quest({
            id: questId,
            sponsor: msg.sender,
            agent: address(0),
            validator: address(0),
            domain: domain,
            description: description,
            proofUrl: "",
            bounty: bounty,
            deadline: deadline,
            xpReward: xpReward,
            status: QuestStatus.Open,
            createdAt: block.timestamp,
            completedAt: 0
        });
        
        emit QuestCreated(questId, msg.sender, domain, bounty, deadline);
    }
    
    /**
     * @dev Cancel quest and refund bounty (only if not claimed)
     */
    function cancelQuest(uint256 questId) external nonReentrant {
        Quest storage quest = quests[questId];
        require(quest.sponsor == msg.sender, "Not sponsor");
        require(quest.status == QuestStatus.Open, "Cannot cancel");
        
        quest.status = QuestStatus.Cancelled;
        
        // Refund bounty
        rewardToken.safeTransfer(msg.sender, quest.bounty);
        
        emit QuestCancelled(questId, msg.sender);
    }
    
    // ==================== Agent Functions ====================
    
    /**
     * @dev Claim an open quest
     */
    function claimQuest(uint256 questId) external {
        Quest storage quest = quests[questId];
        require(quest.status == QuestStatus.Open, "Not open");
        require(block.timestamp < quest.deadline, "Deadline passed");
        
        quest.agent = msg.sender;
        quest.status = QuestStatus.Claimed;
        
        emit QuestClaimed(questId, msg.sender);
    }
    
    /**
     * @dev Submit proof of completion
     * @param proofUrl Link to evidence (GitHub, IPFS, etc.)
     */
    function submitProof(uint256 questId, string calldata proofUrl) external {
        Quest storage quest = quests[questId];
        require(quest.agent == msg.sender, "Not assigned agent");
        require(quest.status == QuestStatus.Claimed, "Not claimed");
        require(bytes(proofUrl).length > 0, "Proof URL required");
        
        quest.proofUrl = proofUrl;
        quest.status = QuestStatus.Submitted;
        
        emit ProofSubmitted(questId, msg.sender, proofUrl);
    }
    
    // ==================== Validator Functions ====================
    
    /**
     * @dev Verify quest completion and distribute rewards
     * @param questId Quest to verify
     * @param approved Whether proof is valid
     */
    function verifyQuest(uint256 questId, bool approved) external nonReentrant {
        require(isValidator[msg.sender], "Not a validator");
        
        Quest storage quest = quests[questId];
        require(quest.status == QuestStatus.Submitted, "Not submitted");
        
        quest.validator = msg.sender;
        
        if (approved) {
            quest.status = QuestStatus.Completed;
            quest.completedAt = block.timestamp;
            
            // Calculate fee distribution
            uint256 protocolFee = (quest.bounty * protocolFeePercent) / 100;
            uint256 nodeFee = (quest.bounty * nodeFeePercent) / 100;
            uint256 agentReward = quest.bounty - protocolFee - nodeFee;
            
            // Distribute rewards
            rewardToken.safeTransfer(quest.agent, agentReward);
            rewardToken.safeTransfer(msg.sender, nodeFee);
            rewardToken.safeTransfer(treasury, protocolFee);
            
            // Update reputation if contract is set
            if (address(reputationContract) != address(0)) {
                reputationContract.addXP(quest.agent, quest.xpReward);
            }
            
            emit QuestVerified(questId, quest.agent, msg.sender, true, agentReward);
        } else {
            // Rejected - return to open (agent can be replaced)
            quest.status = QuestStatus.Open;
            quest.agent = address(0);
            quest.proofUrl = "";
            
            emit QuestVerified(questId, quest.agent, msg.sender, false, 0);
        }
    }
    
    // ==================== Admin Functions ====================
    
    function addValidator(address validator) external onlyOwner {
        isValidator[validator] = true;
        emit ValidatorAdded(validator);
    }
    
    function removeValidator(address validator) external onlyOwner {
        isValidator[validator] = false;
        emit ValidatorRemoved(validator);
    }
    
    function setReputationContract(address _reputation) external onlyOwner {
        reputationContract = IReputation(_reputation);
    }
    
    function setFees(uint256 _protocolFee, uint256 _nodeFee) external onlyOwner {
        require(_protocolFee + _nodeFee < 100, "Fees too high");
        protocolFeePercent = _protocolFee;
        nodeFeePercent = _nodeFee;
    }
    
    function setTreasury(address _treasury) external onlyOwner {
        treasury = _treasury;
    }
    
    // ==================== View Functions ====================
    
    function getQuest(uint256 questId) external view returns (Quest memory) {
        return quests[questId];
    }
    
    function getOpenQuests(uint256 limit) external view returns (Quest[] memory) {
        uint256 count = 0;
        
        // Count open quests
        for (uint256 i = 1; i <= questCounter && count < limit; i++) {
            if (quests[i].status == QuestStatus.Open) {
                count++;
            }
        }
        
        // Collect open quests
        Quest[] memory openQuests = new Quest[](count);
        uint256 index = 0;
        
        for (uint256 i = 1; i <= questCounter && index < count; i++) {
            if (quests[i].status == QuestStatus.Open) {
                openQuests[index++] = quests[i];
            }
        }
        
        return openQuests;
    }
    
    function getPendingVerification(uint256 limit) external view returns (Quest[] memory) {
        uint256 count = 0;
        
        for (uint256 i = 1; i <= questCounter && count < limit; i++) {
            if (quests[i].status == QuestStatus.Submitted) {
                count++;
            }
        }
        
        Quest[] memory pending = new Quest[](count);
        uint256 index = 0;
        
        for (uint256 i = 1; i <= questCounter && index < count; i++) {
            if (quests[i].status == QuestStatus.Submitted) {
                pending[index++] = quests[i];
            }
        }
        
        return pending;
    }
}

// ==================== Interface ====================

interface IReputation {
    function addXP(address agent, uint256 amount) external;
}
