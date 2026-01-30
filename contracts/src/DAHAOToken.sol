// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title DAHAOToken
 * @dev ERC20 token with voting capabilities for DAHAO governance.
 *
 * Features:
 * - ERC20Permit: Gasless approvals via signatures (EIP-2612)
 * - ERC20Votes: Delegation and voting power tracking for governance
 * - ERC20Burnable: Token burning capability
 * - Ownable: Admin functions for future upgrades
 *
 * Initial supply: 1,000,000 DAHAO tokens minted to deployer
 *
 * Usage for gasless voting:
 * 1. User delegates voting power to themselves or a representative
 * 2. User signs voting intent off-chain
 * 3. Relayer executes vote via DAHAOGovernor using meta-transactions
 */
contract DAHAOToken is ERC20, ERC20Burnable, ERC20Permit, ERC20Votes, Ownable {
    /// @notice Initial token supply: 1 million tokens with 18 decimals
    uint256 public constant INITIAL_SUPPLY = 1_000_000 * 10**18;

    /**
     * @dev Constructor mints initial supply to the deployer.
     * @param initialOwner Address to receive initial supply and ownership
     */
    constructor(address initialOwner)
        ERC20("DAHAO", "DAHAO")
        ERC20Permit("DAHAO")
        Ownable(initialOwner)
    {
        _mint(initialOwner, INITIAL_SUPPLY);
    }

    /**
     * @dev Mint new tokens (only owner).
     * @param to Address to receive minted tokens
     * @param amount Amount to mint
     */
    function mint(address to, uint256 amount) public onlyOwner {
        _mint(to, amount);
    }

    // ==================== Required Overrides ====================

    /**
     * @dev Override required by Solidity for multiple inheritance.
     */
    function _update(address from, address to, uint256 value)
        internal
        override(ERC20, ERC20Votes)
    {
        super._update(from, to, value);
    }

    /**
     * @dev Override required by Solidity for multiple inheritance.
     */
    function nonces(address owner)
        public
        view
        override(ERC20Permit, Nonces)
        returns (uint256)
    {
        return super.nonces(owner);
    }
}
