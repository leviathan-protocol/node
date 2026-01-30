// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/governance/Governor.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorSettings.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorCountingSimple.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorVotes.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorVotesQuorumFraction.sol";
import "@openzeppelin/contracts/metatx/ERC2771Context.sol";

/**
 * @title DAHAOGovernor
 * @dev Governance contract for DAHAO with meta-transaction support.
 *
 * Features:
 * - GovernorSettings: Configurable voting delay, period, and proposal threshold
 * - GovernorCountingSimple: For, Against, Abstain voting
 * - GovernorVotes: Uses ERC20Votes for voting power
 * - GovernorVotesQuorumFraction: Quorum as percentage of total supply
 * - ERC2771Context: Meta-transactions for gasless voting
 *
 * Gasless Voting Flow (via DAHAO Observer Mode):
 * 1. User signs voting intent (proposal_id, support, reasoning_hash)
 * 2. DAHAO Node validates signature and reasoning consistency
 * 3. Node submits meta-transaction via DAHAOForwarder
 * 4. Forwarder calls castVoteWithReasoningHash() with user as msg.sender
 *
 * Configuration:
 * - Voting Delay: 1 day (user can prepare after proposal created)
 * - Voting Period: 1 week (time to vote)
 * - Proposal Threshold: 0 (anyone with tokens can propose)
 * - Quorum: 4% of total supply
 */
contract DAHAOGovernor is
    Governor,
    GovernorSettings,
    GovernorCountingSimple,
    GovernorVotes,
    GovernorVotesQuorumFraction,
    ERC2771Context
{
    /// @notice Mapping of proposal ID to voter address to reasoning IPFS hash
    mapping(uint256 => mapping(address => bytes32)) public reasoningHashes;

    /// @notice Emitted when a vote is cast with a reasoning hash
    event VoteCastWithReasoning(
        address indexed voter,
        uint256 indexed proposalId,
        uint8 support,
        uint256 weight,
        bytes32 reasoningHash
    );

    /**
     * @dev Constructor initializes the governor with token and forwarder.
     * @param _token The ERC20Votes token used for voting power
     * @param _trustedForwarder The ERC2771 forwarder for meta-transactions
     */
    constructor(
        IVotes _token,
        address _trustedForwarder
    )
        Governor("DAHAOGovernor")
        GovernorSettings(
            1 days,    // Voting delay: 1 day
            1 weeks,   // Voting period: 1 week
            0          // Proposal threshold: 0 tokens (anyone can propose)
        )
        GovernorVotes(_token)
        GovernorVotesQuorumFraction(4) // 4% quorum
        ERC2771Context(_trustedForwarder)
    {}

    // ==================== Reasoning Hash Extension ====================

    /**
     * @dev Cast a vote with a reasoning hash (IPFS CID).
     *
     * The reasoning hash should be the IPFS CID of the voter's reasoning.
     * This enables:
     * 1. On-chain proof that reasoning was provided
     * 2. Off-chain retrieval and verification of reasoning
     * 3. Semantic validation by DAHAO nodes before execution
     *
     * @param proposalId The ID of the proposal
     * @param support The vote type (0=Against, 1=For, 2=Abstain)
     * @param reasoningHash IPFS hash (bytes32) of the reasoning document
     * @return weight The voting weight used
     */
    function castVoteWithReasoningHash(
        uint256 proposalId,
        uint8 support,
        bytes32 reasoningHash
    ) public virtual returns (uint256 weight) {
        address voter = _msgSender();

        // Store reasoning hash
        reasoningHashes[proposalId][voter] = reasoningHash;

        // Cast the actual vote
        weight = _castVote(proposalId, voter, support, "");

        emit VoteCastWithReasoning(voter, proposalId, support, weight, reasoningHash);

        return weight;
    }

    /**
     * @dev Get the reasoning hash for a voter on a proposal.
     * @param proposalId The proposal ID
     * @param voter The voter address
     * @return The reasoning hash (bytes32)
     */
    function getReasoningHash(uint256 proposalId, address voter)
        public
        view
        returns (bytes32)
    {
        return reasoningHashes[proposalId][voter];
    }

    // ==================== ERC2771 Context Overrides ====================

    /**
     * @dev Override _msgSender to support meta-transactions.
     * Returns the actual sender when called via trusted forwarder.
     */
    function _msgSender()
        internal
        view
        override(Context, ERC2771Context)
        returns (address)
    {
        return ERC2771Context._msgSender();
    }

    /**
     * @dev Override _msgData to support meta-transactions.
     */
    function _msgData()
        internal
        view
        override(Context, ERC2771Context)
        returns (bytes calldata)
    {
        return ERC2771Context._msgData();
    }

    /**
     * @dev Override _contextSuffixLength for ERC2771.
     */
    function _contextSuffixLength()
        internal
        view
        override(Context, ERC2771Context)
        returns (uint256)
    {
        return ERC2771Context._contextSuffixLength();
    }

    // ==================== Required Overrides ====================

    /**
     * @dev Override required by Solidity for multiple inheritance.
     */
    function votingDelay()
        public
        view
        override(Governor, GovernorSettings)
        returns (uint256)
    {
        return super.votingDelay();
    }

    /**
     * @dev Override required by Solidity for multiple inheritance.
     */
    function votingPeriod()
        public
        view
        override(Governor, GovernorSettings)
        returns (uint256)
    {
        return super.votingPeriod();
    }

    /**
     * @dev Override required by Solidity for multiple inheritance.
     */
    function quorum(uint256 blockNumber)
        public
        view
        override(Governor, GovernorVotesQuorumFraction)
        returns (uint256)
    {
        return super.quorum(blockNumber);
    }

    /**
     * @dev Override required by Solidity for multiple inheritance.
     */
    function proposalThreshold()
        public
        view
        override(Governor, GovernorSettings)
        returns (uint256)
    {
        return super.proposalThreshold();
    }
}
