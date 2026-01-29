#!/usr/bin/env python3
"""
DAHAO Observer Mode Simulation - Phone SML vs Node Validator Test

Simulates realistic mobile-to-node voting flow with different sized LLMs:
- Phone SML (Small Model on device): qwen3:4b - Fast but may make mistakes
- Node Observer (Large Validator): qwen3:14b - Thorough semantic validation

This tests the "semantic firewall" where the smaller on-device model may
produce inconsistent reasoning that the larger node model should catch.

Architecture:
  ┌─────────────────┐        ┌─────────────────┐
  │  Mock Phone     │        │  Observer Node  │
  │  (qwen3:4b)     │───────►│  (qwen3:14b)    │
  │                 │ HTTP   │                 │
  │  - Persona      │        │  - Signature ✓  │
  │  - Decision     │        │  - Authz ✓      │
  │  - Sign Intent  │        │  - Semantic ✓   │
  └─────────────────┘        └─────────────────┘

Prerequisites:
  1. Pull models: ollama pull qwen3:4b && ollama pull qwen3:14b
  2. Start Observer: python main.py --mode=observer --port=8080
  3. Run simulation: python simulation_observer.py

Usage:
  # Run with all default personas
  python simulation_observer.py --node=http://localhost:8080

  # Run specific persona
  python simulation_observer.py --persona=simulation/alice_persona.json

  # Run multiple rounds
  python simulation_observer.py --rounds=5

  # Use different phone model
  python simulation_observer.py --phone-model=qwen3:1.8b
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import ollama

# Add project root to path
sys.path.insert(0, ".")

from adapter.models import Persona
from validator.signature import create_test_keypair, sign_payload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ANSI colors for output
COLORS = {
    "phone": "\033[96m",    # Cyan
    "node": "\033[93m",     # Yellow
    "success": "\033[92m",  # Green
    "error": "\033[91m",    # Red
    "reset": "\033[0m",
}


# JSON schema for phone SML response
PHONE_DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "vote": {"type": "string", "enum": ["YES", "NO", "ABSTAIN", "NO_WITH_VETO"]},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["vote", "reasoning", "confidence"],
}


@dataclass
class PhoneDecision:
    """Decision from the phone's on-device SML."""
    vote: str
    reasoning: str
    confidence: float
    model: str
    latency_ms: int


@dataclass
class SimulationResult:
    """Result of a single simulation round."""
    persona_name: str
    proposal_id: int
    proposal_title: str
    phone_decision: PhoneDecision
    node_response: dict
    accepted: bool
    rejection_reason: str | None = None


class PhoneSML:
    """Simulates the Small Language Model running on a mobile device.

    Uses a smaller, faster model (like qwen3:4b) that may occasionally
    produce inconsistent reasoning that should be caught by the node.
    """

    def __init__(self, model: str = "qwen3:4b", ollama_host: str = "http://localhost:11434"):
        self.model = model
        self.client = ollama.Client(host=ollama_host)
        logger.info(f"{COLORS['phone']}Phone SML initialized: {model}{COLORS['reset']}")

    def decide(self, persona: Persona, proposal: dict) -> PhoneDecision:
        """Generate a voting decision based on persona and proposal.

        Args:
            persona: User's persona with values and decision style.
            proposal: Proposal dict with id, title, description.

        Returns:
            PhoneDecision with vote, reasoning, and confidence.
        """
        # Build prompt for on-device decision
        system_prompt = f"""You are simulating an on-device AI assistant for a user with the archetype: {persona.archetype}.

Your role is to help the user make governance voting decisions based on their personal values.

USER'S CORE VALUES:
{chr(10).join(f'- {v}' for v in persona.core_values)}

USER'S DECISION STYLE:
{persona.decision_style}

Based ONLY on these values, decide how the user would vote on the given proposal.
Be authentic to the persona - don't try to be balanced if the persona isn't."""

        user_prompt = f"""GOVERNANCE PROPOSAL:
Title: {proposal['title']}
Description: {proposal['description']}

Based on the user's values and decision style, decide how they would vote.
Respond with your decision in JSON format."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        start_time = time.time()

        try:
            response = self.client.chat(
                model=self.model,
                messages=messages,
                format=PHONE_DECISION_SCHEMA,
                options={"temperature": 0.7},  # Some randomness for realistic variation
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Parse response
            content = response["message"]["content"]
            decision_data = json.loads(content)

            return PhoneDecision(
                vote=decision_data["vote"],
                reasoning=decision_data["reasoning"],
                confidence=decision_data["confidence"],
                model=self.model,
                latency_ms=latency_ms,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse phone SML response: {e}")
            # Return a default abstain on parse error
            return PhoneDecision(
                vote="ABSTAIN",
                reasoning="Failed to generate decision",
                confidence=0.0,
                model=self.model,
                latency_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            logger.error(f"Phone SML error: {e}")
            raise


class MockPhoneClient:
    """Simulates a mobile phone with on-device SML connecting to Observer node."""

    def __init__(
        self,
        persona: Persona,
        node_url: str = "http://localhost:8080",
        phone_model: str = "qwen3:4b",
    ):
        self.persona = persona
        self.node_url = node_url.rstrip("/")
        self.http_client = httpx.Client(base_url=self.node_url, timeout=60)
        self.sml = PhoneSML(model=phone_model)

        # Generate wallet
        priv_key, pub_key = create_test_keypair()
        self.private_key = priv_key
        self.public_key = pub_key
        self.public_key_b64 = base64.b64encode(pub_key).decode()

        # Generate address from pubkey
        pubkey_hash = hashlib.sha256(pub_key).digest()[:20]
        self.address = "cosmos1" + pubkey_hash.hex()[:38]

        self.session_token: str | None = None
        self.registered = False

        logger.info(
            f"{COLORS['phone']}Phone client created for {persona.archetype} "
            f"({self.address[:20]}...){COLORS['reset']}"
        )

    def connect_and_register(self) -> bool:
        """Complete the connection and registration flow."""
        try:
            # Get invite
            resp = self.http_client.get("/api/v1/invite")
            resp.raise_for_status()
            invite_code = resp.json()["invite_code"]

            # Connect
            resp = self.http_client.post("/api/v1/connect", json={"invite_code": invite_code})
            resp.raise_for_status()
            self.session_token = resp.json()["session_token"]

            # Register
            resp = self.http_client.post(
                "/api/v1/register",
                json={
                    "session_token": self.session_token,
                    "voter_address": self.address,
                    "authz_tx_hash": f"MOCK_TX_{self.persona.user_id}",
                    "pub_key": self.public_key_b64,
                },
            )
            resp.raise_for_status()
            self.registered = True

            logger.info(f"{COLORS['success']}✓ Registered: {self.persona.archetype}{COLORS['reset']}")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"Registration failed: {e.response.status_code} - {e.response.json()}")
            return False

    def get_proposals(self) -> list[dict]:
        """Fetch active proposals from the node."""
        resp = self.http_client.get("/api/v1/proposals")
        resp.raise_for_status()
        return resp.json()["proposals"]

    def vote_on_proposal(self, proposal: dict) -> SimulationResult:
        """Use on-device SML to decide and submit vote.

        This is where the magic happens:
        1. Phone's small LLM generates decision based on persona
        2. Decision is signed with private key
        3. Sent to node for validation by larger LLM
        """
        logger.info(
            f"\n{COLORS['phone']}📱 [{self.persona.archetype}] "
            f"Processing: {proposal['title'][:50]}...{COLORS['reset']}"
        )

        # Step 1: On-device SML makes decision
        decision = self.sml.decide(self.persona, proposal)

        logger.info(
            f"   SML Decision: {decision.vote} (confidence: {decision.confidence:.2f}, "
            f"latency: {decision.latency_ms}ms)"
        )
        logger.info(f"   Reasoning: {decision.reasoning[:80]}...")

        # Step 2: Create and sign intent
        intent = {
            "proposal_id": proposal["id"],
            "voter_address": self.address,
            "vote_option": decision.vote,
            "public_reasoning": decision.reasoning,
            "confidence_score": decision.confidence,
            "timestamp": int(time.time()),
            "nonce": hashlib.sha256(f"{time.time()}{self.address}".encode()).hexdigest()[:16],
        }

        signature = sign_payload(intent, self.private_key)

        # Step 3: Submit to node
        logger.info(f"   {COLORS['node']}Submitting to Node...{COLORS['reset']}")

        resp = self.http_client.post(
            "/api/v1/submit_vote",
            json={
                **intent,
                "intent_signature": signature,
                "pub_key": self.public_key_b64,
            },
        )

        node_response = resp.json()

        if resp.status_code == 200:
            logger.info(
                f"   {COLORS['success']}✓ ACCEPTED by Node - TX: {node_response['tx_hash'][:16]}...{COLORS['reset']}"
            )
            return SimulationResult(
                persona_name=self.persona.archetype,
                proposal_id=proposal["id"],
                proposal_title=proposal["title"],
                phone_decision=decision,
                node_response=node_response,
                accepted=True,
            )
        else:
            detail = node_response.get("detail", {})
            rejection_reason = f"{detail.get('stage', 'unknown')}: {detail.get('error', 'unknown')}"
            logger.info(
                f"   {COLORS['error']}✗ REJECTED by Node - {rejection_reason}{COLORS['reset']}"
            )
            if detail.get("detail"):
                logger.info(f"   Detail: {detail['detail'][:80]}...")

            return SimulationResult(
                persona_name=self.persona.archetype,
                proposal_id=proposal["id"],
                proposal_title=proposal["title"],
                phone_decision=decision,
                node_response=node_response,
                accepted=False,
                rejection_reason=rejection_reason,
            )

    def close(self):
        """Clean up resources."""
        self.http_client.close()


def load_personas(persona_paths: list[str]) -> list[Persona]:
    """Load personas from JSON files."""
    personas = []
    for path in persona_paths:
        try:
            persona = Persona.from_json_file(path)
            personas.append(persona)
            logger.info(f"Loaded persona: {persona.archetype} from {path}")
        except Exception as e:
            logger.warning(f"Failed to load persona from {path}: {e}")
    return personas


def run_simulation(
    node_url: str,
    personas: list[Persona],
    phone_model: str,
    rounds: int = 1,
) -> list[SimulationResult]:
    """Run the full simulation.

    Args:
        node_url: URL of the Observer mode node.
        personas: List of personas to simulate.
        phone_model: Model to use for phone SML.
        rounds: Number of voting rounds per persona.

    Returns:
        List of simulation results.
    """
    results: list[SimulationResult] = []

    # Create phone clients for each persona
    phones: list[MockPhoneClient] = []
    for persona in personas:
        phone = MockPhoneClient(persona, node_url, phone_model)
        if phone.connect_and_register():
            phones.append(phone)
        else:
            logger.warning(f"Skipping {persona.archetype} - registration failed")

    if not phones:
        logger.error("No phones registered successfully")
        return results

    # Get proposals once
    proposals = phones[0].get_proposals()
    if not proposals:
        logger.error("No proposals available")
        return results

    logger.info(f"\n{'='*60}")
    logger.info(f"Starting simulation: {len(phones)} personas, {len(proposals)} proposals, {rounds} rounds")
    logger.info(f"Phone SML: {phone_model}")
    logger.info(f"{'='*60}\n")

    # Run voting rounds
    for round_num in range(rounds):
        if rounds > 1:
            logger.info(f"\n{'='*40}")
            logger.info(f"ROUND {round_num + 1}/{rounds}")
            logger.info(f"{'='*40}")

        for phone in phones:
            for proposal in proposals:
                try:
                    result = phone.vote_on_proposal(proposal)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error voting: {e}")

    # Clean up
    for phone in phones:
        phone.close()

    return results


def print_summary(results: list[SimulationResult]):
    """Print a summary of simulation results."""
    print(f"\n{'='*60}")
    print("SIMULATION SUMMARY")
    print(f"{'='*60}")

    total = len(results)
    accepted = sum(1 for r in results if r.accepted)
    rejected = total - accepted

    print(f"\nTotal votes: {total}")
    print(f"  {COLORS['success']}Accepted: {accepted}{COLORS['reset']}")
    print(f"  {COLORS['error']}Rejected: {rejected}{COLORS['reset']}")

    if rejected > 0:
        print(f"\n{COLORS['error']}Rejections by stage:{COLORS['reset']}")
        rejection_stages: dict[str, int] = {}
        for r in results:
            if not r.accepted and r.rejection_reason:
                stage = r.rejection_reason.split(":")[0]
                rejection_stages[stage] = rejection_stages.get(stage, 0) + 1

        for stage, count in sorted(rejection_stages.items(), key=lambda x: -x[1]):
            print(f"  - {stage}: {count}")

    print(f"\nVotes by persona:")
    persona_results: dict[str, dict] = {}
    for r in results:
        if r.persona_name not in persona_results:
            persona_results[r.persona_name] = {"accepted": 0, "rejected": 0, "votes": {}}
        if r.accepted:
            persona_results[r.persona_name]["accepted"] += 1
        else:
            persona_results[r.persona_name]["rejected"] += 1

        vote = r.phone_decision.vote
        persona_results[r.persona_name]["votes"][vote] = \
            persona_results[r.persona_name]["votes"].get(vote, 0) + 1

    for persona, stats in sorted(persona_results.items()):
        status = f"{COLORS['success']}✓{stats['accepted']}{COLORS['reset']}" if stats['accepted'] else ""
        if stats['rejected']:
            status += f" {COLORS['error']}✗{stats['rejected']}{COLORS['reset']}"
        votes_str = ", ".join(f"{v}:{c}" for v, c in stats['votes'].items())
        print(f"  {persona}: {status} ({votes_str})")

    # Check for semantic rejections (the interesting ones!)
    semantic_rejections = [r for r in results if r.rejection_reason and "semantic" in r.rejection_reason.lower()]
    if semantic_rejections:
        print(f"\n{COLORS['error']}⚠️  Semantic Firewall Catches:{COLORS['reset']}")
        for r in semantic_rejections:
            print(f"  - {r.persona_name} on '{r.proposal_title[:40]}...'")
            print(f"    Vote: {r.phone_decision.vote}, Reasoning: {r.phone_decision.reasoning[:60]}...")


def main():
    parser = argparse.ArgumentParser(
        description="DAHAO Observer Mode Simulation - Phone SML vs Node Validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--node",
        default="http://localhost:8080",
        help="Observer node URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--persona",
        action="append",
        help="Path to persona.json file (can specify multiple)",
    )
    parser.add_argument(
        "--phone-model",
        default="qwen3:4b",
        help="LLM model for phone SML (default: qwen3:4b)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="Number of voting rounds (default: 1)",
    )
    parser.add_argument(
        "--all-personas",
        action="store_true",
        help="Use all personas in simulation/ directory",
    )

    args = parser.parse_args()

    # Determine which personas to use
    if args.persona:
        persona_paths = args.persona
    elif args.all_personas:
        # Find all persona files in simulation/
        persona_paths = list(Path("simulation").glob("*_persona.json"))
        if not persona_paths:
            logger.error("No persona files found in simulation/")
            sys.exit(1)
        persona_paths = [str(p) for p in persona_paths]
    else:
        # Default: use a few test personas
        default_personas = [
            "simulation/alice_persona.json",
            "simulation/bob_persona.json",
            "simulation/eve_persona.json",
        ]
        persona_paths = [p for p in default_personas if Path(p).exists()]
        if not persona_paths:
            logger.error(
                "No default personas found. Create simulation/*_persona.json files or use --persona"
            )
            sys.exit(1)

    # Load personas
    personas = load_personas(persona_paths)
    if not personas:
        logger.error("No personas loaded successfully")
        sys.exit(1)

    # Run simulation
    print(f"\n{'='*60}")
    print("DAHAO Observer Mode Simulation")
    print(f"Phone SML: {args.phone_model} (small, fast, may make mistakes)")
    print(f"Node Validator: qwen3:14b (large, thorough semantic check)")
    print(f"{'='*60}\n")

    results = run_simulation(
        node_url=args.node,
        personas=personas,
        phone_model=args.phone_model,
        rounds=args.rounds,
    )

    # Print summary
    print_summary(results)

    # Exit with error if all votes rejected
    if results and all(not r.accepted for r in results):
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
