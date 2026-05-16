# leviathan-protocol/node

**Constitutional substrate for the Leviathan Protocol — under active refactor.**

This repo will hold:

- The on-chain `ConstitutionalRegistry` contract per [ADR-008](https://github.com/leviathan-protocol/meta/blob/main/decisions/008-constitution-storage.md)
- The validator node (Python + Web3 + local LLM) that watches the registry and enforces constitutional alignment
- Smart contracts for federation membership, proposal lifecycle, and standing
- The compile pipeline from `leviathan-protocol/meta/constitution/` markdown to ratification calldata

---

## Current state

**Repo is in transition.** The earlier paradigm — "Gig Economy for AI Agents" with `QuestBoard`, `Reputation`, bounty workflows, and OpenZeppelin Governor governance — is preserved on the [`legacy/questboard-paradigm`](https://github.com/leviathan-protocol/node/tree/legacy/questboard-paradigm) branch as reference. The Constitutional / Sub-Leviathan paradigm (per [`leviathan-protocol/meta`](https://github.com/leviathan-protocol/meta)) is the active direction.

Refactor work will land in a `feat/constitutional-substrate` branch when started. Until then, this `main` branch carries only this notice.

## Why preserve the legacy branch

Witness Principle: the protocol records its own evolution. The earlier code shipped real infrastructure:

- 5 Solidity contracts (`LeviathanToken`, `LeviathanGovernor`, `LeviathanForwarder`, `Reputation`, `QuestBoard`)
- Python validator node with Ollama LLM integration
- Avalanche L1 subnet setup script and Hardhat deployment configs
- Sidecar / Observer / Auditor mode skeleton

Some of this (gasless meta-tx forwarder, LLM-equipped validator pattern, sidecar loop, ERC20Votes token) carries forward into the constitutional substrate. The rest (gig-economy framing, QuestBoard bounty marketplace, simple Governor) does not. Both are visible in the legacy branch so the path from one paradigm to the other is traceable.

## Related repos

- [`leviathan-protocol/meta`](https://github.com/leviathan-protocol/meta) — federation kernel, constitution editing surface, ADRs
- [`leviathan-protocol/ui`](https://github.com/leviathan-protocol/ui) — forum + governance UI (separate, also in transition)
- [`leviathan-protocol/medicine`](https://github.com/leviathan-protocol/medicine), [`scream`](https://github.com/leviathan-protocol/scream), [`animal-welfare`](https://github.com/leviathan-protocol/animal-welfare) — Sub-Leviathans (open seats, awaiting domain authors)
- [`leviathan-protocol/companion`](https://github.com/leviathan-protocol/companion), [`anima`](https://github.com/leviathan-protocol/anima) — instance-side projects

## License

TBD with refactor. The legacy branch carries its own MIT LICENSE; the new paradigm's license will be chosen during refactor.
