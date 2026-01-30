// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/metatx/ERC2771Forwarder.sol";

/**
 * @title DAHAOForwarder
 * @dev ERC2771 Forwarder for DAHAO meta-transactions (gasless voting).
 *
 * This contract enables gasless voting by:
 * 1. Accepting signed ForwardRequests from users
 * 2. Verifying the signature is from the claimed sender
 * 3. Executing the call with the user as msg.sender (via ERC2771Context)
 *
 * Gasless Voting Flow:
 *
 *   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
 *   │   Mobile    │     │   DAHAO     │     │   DAHAO     │     │   DAHAO     │
 *   │    User     │────►│   Node      │────►│  Forwarder  │────►│  Governor   │
 *   └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
 *        │                    │                   │                   │
 *        │ 1. Sign intent     │                   │                   │
 *        │    (vote + reason) │                   │                   │
 *        │                    │                   │                   │
 *        │ 2. Submit to node  │                   │                   │
 *        │────────────────────►                   │                   │
 *        │                    │                   │                   │
 *        │                    │ 3. Validate       │                   │
 *        │                    │    signature      │                   │
 *        │                    │    + reasoning    │                   │
 *        │                    │                   │                   │
 *        │                    │ 4. Build          │                   │
 *        │                    │    ForwardRequest │                   │
 *        │                    │───────────────────►                   │
 *        │                    │                   │                   │
 *        │                    │                   │ 5. Verify sig     │
 *        │                    │                   │    Execute call   │
 *        │                    │                   │───────────────────►
 *        │                    │                   │                   │
 *        │                    │                   │   6. castVote()   │
 *        │                    │                   │   with user as    │
 *        │                    │                   │   msg.sender      │
 *
 * ForwardRequest Structure (EIP-712 typed data):
 * {
 *   from: address,      // User's address
 *   to: address,        // DAHAOGovernor address
 *   value: uint256,     // 0 for voting
 *   gas: uint256,       // Gas limit for the call
 *   nonce: uint256,     // User's nonce (for replay protection)
 *   deadline: uint48,   // Request expiration timestamp
 *   data: bytes         // Encoded function call (castVoteWithReasoningHash)
 * }
 *
 * The user signs this request, and the DAHAO Node submits it to this
 * forwarder contract, paying the gas fees.
 */
contract DAHAOForwarder is ERC2771Forwarder {
    /**
     * @dev Constructor sets the forwarder name for EIP-712 domain.
     */
    constructor() ERC2771Forwarder("DAHAOForwarder") {}

    /**
     * @dev Returns the domain separator for EIP-712 signatures.
     * Useful for clients building ForwardRequests.
     */
    function domainSeparator() external view returns (bytes32) {
        return _domainSeparatorV4();
    }
}
