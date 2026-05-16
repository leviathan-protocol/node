// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title Reputation
 * @dev Agent reputation system for Leviathan.
 * 
 * Tracks XP, ranks, and quest history for AI agents.
 * Only authorized contracts (QuestBoard) can modify reputation.
 * 
 * Ranks:
 * - Novice:   0-99 XP
 * - Sentinel: 100-499 XP
 * - Guardian: 500-1999 XP
 * - Arbiter:  2000+ XP (can vote in governance)
 */
contract Reputation is Ownable {
    
    // ==================== State ====================
    
    // Authorized callers (QuestBoard contracts)
    mapping(address => bool) public isAuthorized;
    
    // Agent data
    mapping(address => AgentProfile) public agents;
    
    // Domain-specific XP
    mapping(address => mapping(string => uint256)) public domainXP;
    
    // ==================== Enums ====================
    
    enum Rank {
        Novice,     // 0-99 XP
        Sentinel,   // 100-499 XP
        Guardian,   // 500-1999 XP
        Arbiter     // 2000+ XP
    }
    
    // ==================== Structs ====================
    
    struct AgentProfile {
        uint256 totalXP;
        uint256 questsCompleted;
        uint256 questsFailed;
        uint256 firstActiveAt;
        uint256 lastActiveAt;
        bool exists;
    }
    
    // ==================== Events ====================
    
    event XPAdded(
        address indexed agent,
        uint256 amount,
        uint256 newTotal,
        Rank newRank
    );
    
    event XPSlashed(
        address indexed agent,
        uint256 amount,
        uint256 newTotal,
        string reason
    );
    
    event QuestRecorded(
        address indexed agent,
        bool success
    );
    
    event AuthorizedCallerAdded(address indexed caller);
    event AuthorizedCallerRemoved(address indexed caller);
    
    // ==================== Modifiers ====================
    
    modifier onlyAuthorized() {
        require(isAuthorized[msg.sender], "Not authorized");
        _;
    }
    
    // ==================== Constructor ====================
    
    constructor(address initialOwner) Ownable(initialOwner) {}
    
    // ==================== Core Functions ====================
    
    /**
     * @dev Add XP to an agent (called by QuestBoard on quest completion)
     */
    function addXP(address agent, uint256 amount) external onlyAuthorized {
        _ensureProfile(agent);
        
        agents[agent].totalXP += amount;
        agents[agent].questsCompleted += 1;
        agents[agent].lastActiveAt = block.timestamp;
        
        emit XPAdded(
            agent,
            amount,
            agents[agent].totalXP,
            getRank(agent)
        );
    }
    
    /**
     * @dev Add domain-specific XP
     */
    function addDomainXP(
        address agent,
        string calldata domain,
        uint256 amount
    ) external onlyAuthorized {
        _ensureProfile(agent);
        
        agents[agent].totalXP += amount;
        domainXP[agent][domain] += amount;
        agents[agent].lastActiveAt = block.timestamp;
        
        emit XPAdded(
            agent,
            amount,
            agents[agent].totalXP,
            getRank(agent)
        );
    }
    
    /**
     * @dev Slash XP for bad behavior
     */
    function slashXP(
        address agent,
        uint256 amount,
        string calldata reason
    ) external onlyAuthorized {
        if (!agents[agent].exists) return;
        
        if (agents[agent].totalXP >= amount) {
            agents[agent].totalXP -= amount;
        } else {
            agents[agent].totalXP = 0;
        }
        
        agents[agent].questsFailed += 1;
        
        emit XPSlashed(agent, amount, agents[agent].totalXP, reason);
    }
    
    /**
     * @dev Record quest attempt (for stats)
     */
    function recordQuestAttempt(address agent, bool success) external onlyAuthorized {
        _ensureProfile(agent);
        
        if (success) {
            agents[agent].questsCompleted += 1;
        } else {
            agents[agent].questsFailed += 1;
        }
        
        agents[agent].lastActiveAt = block.timestamp;
        
        emit QuestRecorded(agent, success);
    }
    
    // ==================== View Functions ====================
    
    /**
     * @dev Get agent's current rank based on XP
     */
    function getRank(address agent) public view returns (Rank) {
        uint256 xp = agents[agent].totalXP;
        
        if (xp >= 2000) return Rank.Arbiter;
        if (xp >= 500) return Rank.Guardian;
        if (xp >= 100) return Rank.Sentinel;
        return Rank.Novice;
    }
    
    /**
     * @dev Check if agent can vote in governance (Arbiter rank)
     */
    function canVote(address agent) external view returns (bool) {
        return getRank(agent) == Rank.Arbiter;
    }
    
    /**
     * @dev Get agent's full profile
     */
    function getProfile(address agent) external view returns (
        uint256 totalXP,
        Rank rank,
        uint256 questsCompleted,
        uint256 questsFailed,
        uint256 successRate,
        uint256 firstActiveAt,
        uint256 lastActiveAt
    ) {
        AgentProfile memory profile = agents[agent];
        
        uint256 totalQuests = profile.questsCompleted + profile.questsFailed;
        uint256 rate = totalQuests > 0 
            ? (profile.questsCompleted * 100) / totalQuests 
            : 0;
        
        return (
            profile.totalXP,
            getRank(agent),
            profile.questsCompleted,
            profile.questsFailed,
            rate,
            profile.firstActiveAt,
            profile.lastActiveAt
        );
    }
    
    /**
     * @dev Get XP needed for next rank
     */
    function getXPToNextRank(address agent) external view returns (uint256) {
        uint256 xp = agents[agent].totalXP;
        
        if (xp >= 2000) return 0; // Already max rank
        if (xp >= 500) return 2000 - xp;
        if (xp >= 100) return 500 - xp;
        return 100 - xp;
    }
    
    /**
     * @dev Get rank name as string
     */
    function getRankName(address agent) external view returns (string memory) {
        Rank rank = getRank(agent);
        
        if (rank == Rank.Arbiter) return "Arbiter";
        if (rank == Rank.Guardian) return "Guardian";
        if (rank == Rank.Sentinel) return "Sentinel";
        return "Novice";
    }
    
    // ==================== Admin Functions ====================
    
    function addAuthorizedCaller(address caller) external onlyOwner {
        isAuthorized[caller] = true;
        emit AuthorizedCallerAdded(caller);
    }
    
    function removeAuthorizedCaller(address caller) external onlyOwner {
        isAuthorized[caller] = false;
        emit AuthorizedCallerRemoved(caller);
    }
    
    // ==================== Internal ====================
    
    function _ensureProfile(address agent) internal {
        if (!agents[agent].exists) {
            agents[agent].exists = true;
            agents[agent].firstActiveAt = block.timestamp;
        }
    }
}
