"""
Leviathan Validator Node

Listens to QuestBoard contract events and validates quest completions
using LLM-powered analysis.

This is the "Oracle" that connects AI verification to blockchain payments.
"""

import asyncio
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from web3 import Web3
from web3.contract import Contract
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# ==================== Configuration ====================

@dataclass
class NodeConfig:
    """Validator node configuration."""
    rpc_url: str = os.getenv("RPC_URL", "http://127.0.0.1:9650/ext/bc/leviathan/rpc")
    private_key: str = os.getenv("VALIDATOR_PRIVATE_KEY", "")
    questboard_address: str = os.getenv("QUESTBOARD_ADDRESS", "")
    llm_endpoint: str = os.getenv("LLM_ENDPOINT", "http://localhost:11434/api/generate")
    llm_model: str = os.getenv("LLM_MODEL", "qwen2.5:14b")
    poll_interval: int = 5  # seconds


# ==================== Contract ABI (Minimal) ====================

QUESTBOARD_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "questId", "type": "uint256"},
            {"indexed": True, "name": "agent", "type": "address"},
            {"indexed": False, "name": "proofUrl", "type": "string"}
        ],
        "name": "ProofSubmitted",
        "type": "event"
    },
    {
        "inputs": [{"name": "questId", "type": "uint256"}],
        "name": "getQuest",
        "outputs": [
            {
                "components": [
                    {"name": "id", "type": "uint256"},
                    {"name": "sponsor", "type": "address"},
                    {"name": "agent", "type": "address"},
                    {"name": "validator", "type": "address"},
                    {"name": "domain", "type": "string"},
                    {"name": "description", "type": "string"},
                    {"name": "proofUrl", "type": "string"},
                    {"name": "bounty", "type": "uint256"},
                    {"name": "deadline", "type": "uint256"},
                    {"name": "xpReward", "type": "uint256"},
                    {"name": "status", "type": "uint8"},
                    {"name": "createdAt", "type": "uint256"},
                    {"name": "completedAt", "type": "uint256"}
                ],
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "questId", "type": "uint256"},
            {"name": "approved", "type": "bool"}
        ],
        "name": "verifyQuest",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"name": "limit", "type": "uint256"}],
        "name": "getPendingVerification",
        "outputs": [
            {
                "components": [
                    {"name": "id", "type": "uint256"},
                    {"name": "sponsor", "type": "address"},
                    {"name": "agent", "type": "address"},
                    {"name": "validator", "type": "address"},
                    {"name": "domain", "type": "string"},
                    {"name": "description", "type": "string"},
                    {"name": "proofUrl", "type": "string"},
                    {"name": "bounty", "type": "uint256"},
                    {"name": "deadline", "type": "uint256"},
                    {"name": "xpReward", "type": "uint256"},
                    {"name": "status", "type": "uint8"},
                    {"name": "createdAt", "type": "uint256"},
                    {"name": "completedAt", "type": "uint256"}
                ],
                "name": "",
                "type": "tuple[]"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    }
]


# ==================== LLM Verifier ====================

class LLMVerifier:
    """Verifies quest proofs using local LLM."""
    
    def __init__(self, endpoint: str, model: str):
        self.endpoint = endpoint
        self.model = model
    
    async def verify_proof(
        self,
        quest_description: str,
        proof_url: str,
        domain: str
    ) -> tuple[bool, str]:
        """
        Analyze proof and return (approved, reasoning).
        
        For demo purposes, this uses a simple heuristic.
        In production, this would fetch the proof and analyze with LLM.
        """
        import aiohttp
        
        prompt = f"""You are a validator node for the Leviathan Protocol.
Your job is to verify if an AI agent has completed a quest.

QUEST DOMAIN: {domain}
QUEST DESCRIPTION: {quest_description}
PROOF URL: {proof_url}

Analyze if this proof URL seems legitimate for the given quest.
Consider:
1. Does the URL format make sense? (GitHub, IPFS, etc.)
2. Does the domain match the quest type?
3. Is there any indication of malicious activity?

Respond with ONLY a JSON object:
{{"approved": true/false, "reasoning": "brief explanation"}}
"""
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.endpoint,
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        llm_response = json.loads(result.get("response", "{}"))
                        return (
                            llm_response.get("approved", False),
                            llm_response.get("reasoning", "No reasoning provided")
                        )
        except Exception as e:
            print(f"⚠️  LLM verification failed: {e}")
        
        # Fallback: Simple heuristic for demo
        return self._fallback_verify(proof_url, domain)
    
    def _fallback_verify(self, proof_url: str, domain: str) -> tuple[bool, str]:
        """Simple heuristic when LLM is unavailable."""
        # Basic URL validation
        if not proof_url or len(proof_url) < 10:
            return False, "Invalid proof URL"
        
        # Check for known good patterns
        good_patterns = [
            "github.com",
            "ipfs.io",
            "arweave.net",
            "gist.github.com"
        ]
        
        if any(p in proof_url.lower() for p in good_patterns):
            return True, f"Proof URL matches trusted pattern"
        
        # Check for suspicious patterns
        bad_patterns = [
            "evil",
            "hack",
            "scam",
            "localhost"
        ]
        
        if any(p in proof_url.lower() for p in bad_patterns):
            return False, "Proof URL contains suspicious pattern"
        
        # Default: approve with warning
        return True, "Proof URL format acceptable (manual review recommended)"


# ==================== Validator Node ====================

class ValidatorNode:
    """
    Leviathan Validator Node.
    
    Responsibilities:
    1. Monitor QuestBoard for submitted proofs
    2. Verify proofs using LLM
    3. Submit verification transactions
    """
    
    def __init__(self, config: NodeConfig):
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url))
        self.account = self.w3.eth.account.from_key(config.private_key)
        self.contract: Optional[Contract] = None
        self.verifier = LLMVerifier(config.llm_endpoint, config.llm_model)
        
        # Stats
        self.stats = {
            "verified": 0,
            "rejected": 0,
            "errors": 0,
            "started_at": datetime.now().isoformat()
        }
    
    def connect(self) -> bool:
        """Connect to blockchain and contract."""
        try:
            if not self.w3.is_connected():
                print("❌ Cannot connect to RPC")
                return False
            
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.config.questboard_address),
                abi=QUESTBOARD_ABI
            )
            
            print(f"✅ Connected to {self.config.rpc_url}")
            print(f"📋 QuestBoard: {self.config.questboard_address}")
            print(f"🔑 Validator: {self.account.address}")
            
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    async def verify_quest(self, quest_id: int, approved: bool) -> bool:
        """Submit verification transaction."""
        try:
            # Build transaction
            tx = self.contract.functions.verifyQuest(
                quest_id,
                approved
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "gas": 200000,
                "gasPrice": self.w3.eth.gas_price
            })
            
            # Sign and send
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            
            if receipt.status == 1:
                print(f"   ✅ TX confirmed: {tx_hash.hex()[:16]}...")
                return True
            else:
                print(f"   ❌ TX failed: {tx_hash.hex()[:16]}...")
                return False
                
        except Exception as e:
            print(f"   ❌ TX error: {e}")
            return False
    
    async def process_pending_quests(self):
        """Check for and process pending verifications."""
        try:
            # Get pending quests
            pending = self.contract.functions.getPendingVerification(10).call()
            
            if not pending:
                return
            
            print(f"\n📬 Found {len(pending)} pending verification(s)")
            
            for quest in pending:
                quest_id = quest[0]
                agent = quest[2]
                domain = quest[4]
                description = quest[5]
                proof_url = quest[6]
                bounty = quest[7]
                
                print(f"\n🔍 Verifying Quest #{quest_id}")
                print(f"   Agent: {agent[:10]}...")
                print(f"   Domain: {domain}")
                print(f"   Bounty: {Web3.from_wei(bounty, 'ether')} LVTN")
                print(f"   Proof: {proof_url[:50]}...")
                
                # LLM verification
                approved, reasoning = await self.verifier.verify_proof(
                    description, proof_url, domain
                )
                
                print(f"   🤖 LLM Verdict: {'✅ APPROVED' if approved else '❌ REJECTED'}")
                print(f"   📝 Reasoning: {reasoning}")
                
                # Submit to chain
                success = await self.verify_quest(quest_id, approved)
                
                if success:
                    if approved:
                        self.stats["verified"] += 1
                    else:
                        self.stats["rejected"] += 1
                else:
                    self.stats["errors"] += 1
                    
        except Exception as e:
            print(f"❌ Processing error: {e}")
            self.stats["errors"] += 1
    
    async def run(self):
        """Main loop."""
        print("\n" + "=" * 60)
        print("🐙 LEVIATHAN VALIDATOR NODE")
        print("=" * 60)
        
        if not self.connect():
            return
        
        print(f"\n🔄 Polling every {self.config.poll_interval}s for pending quests...")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                await self.process_pending_quests()
                await asyncio.sleep(self.config.poll_interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down...")
            self._print_stats()
    
    def _print_stats(self):
        """Print session statistics."""
        print("\n" + "=" * 60)
        print("📊 SESSION STATISTICS")
        print("=" * 60)
        print(f"   Started: {self.stats['started_at']}")
        print(f"   Verified: {self.stats['verified']}")
        print(f"   Rejected: {self.stats['rejected']}")
        print(f"   Errors: {self.stats['errors']}")
        print("=" * 60)


# ==================== CLI ====================

def load_deployment() -> dict:
    """Load deployment addresses from JSON."""
    paths = [
        Path("contracts/deployments/localhost.json"),
        Path("contracts/deployments/leviathan.json"),
        Path("deployments/localhost.json")
    ]
    
    for path in paths:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    
    return {}


async def main():
    """Entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Leviathan Validator Node")
    parser.add_argument("--rpc", help="RPC URL")
    parser.add_argument("--questboard", help="QuestBoard contract address")
    parser.add_argument("--key", help="Validator private key")
    parser.add_argument("--interval", type=int, default=5, help="Poll interval (seconds)")
    args = parser.parse_args()
    
    # Load deployment if exists
    deployment = load_deployment()
    
    config = NodeConfig(
        rpc_url=args.rpc or os.getenv("RPC_URL") or "http://127.0.0.1:9650/ext/bc/leviathan/rpc",
        private_key=args.key or os.getenv("VALIDATOR_PRIVATE_KEY") or "",
        questboard_address=args.questboard or deployment.get("contracts", {}).get("questBoard", ""),
        poll_interval=args.interval
    )
    
    if not config.private_key:
        print("❌ VALIDATOR_PRIVATE_KEY required")
        print("   Set via environment variable or --key argument")
        return
    
    if not config.questboard_address:
        print("❌ QUESTBOARD_ADDRESS required")
        print("   Set via environment variable or --questboard argument")
        return
    
    node = ValidatorNode(config)
    await node.run()


if __name__ == "__main__":
    asyncio.run(main())
