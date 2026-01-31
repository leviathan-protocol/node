## TASK: Add SML (Small Language Model) to mock_phone_evm.py

Create a realistic phone simulator that uses a small LLM (qwen3:4b) to make voting decisions based on a persona, then submits to Observer Mode for semantic validation.

### Goal
Test the full flow:
1. Phone (SML) analyzes proposal with persona → generates reasoning
2. Phone signs and sends to Observer
3. Observer (larger LLM) validates reasoning consistency
4. If consistent → vote submitted to DAHAO Subnet

### Files to Create/Modify

#### 1. Create `tests/mock_phone_sml.py`
```python
"""
Mock Phone with SML (Small Language Model)

Simulates a mobile phone that:
1. Has a user persona (values, priorities)
2. Uses small LLM (qwen3:4b) to analyze proposals
3. Generates voting decision + reasoning
4. Signs with EIP-712 and submits to Observer

Usage:
    python tests/mock_phone_sml.py --node-url http://localhost:8000 --persona eco_warrior
"""

Features needed:

PERSONAS = {
    "eco_warrior": {
        "name": "Eco Warrior",
        "description": "Prioritizes environmental sustainability above all",
        "values": ["environment", "sustainability", "green energy", "conservation"],
        "against": ["pollution", "deforestation", "fossil fuels", "mining"]
    },
    "profit_maximizer": {
        "name": "Profit Maximizer",  
        "description": "Focuses on economic growth and returns",
        "values": ["profit", "efficiency", "growth", "ROI"],
        "against": ["excessive regulation", "wasteful spending"]
    },
    "community_builder": {
        "name": "Community Builder",
        "description": "Values community welfare and inclusion",
        "values": ["community", "fairness", "accessibility", "education"],
        "against": ["exclusion", "centralization", "inequality"]
    },
    "tech_progressive": {
        "name": "Tech Progressive",
        "description": "Believes in technological advancement",
        "values": ["innovation", "technology", "automation", "AI"],
        "against": ["stagnation", "outdated systems"]
    }
}

class SMLPhoneClient:
    def __init__(self, node_url: str, persona: str, ollama_host: str = "http://localhost:11434"):
        self.node_url = node_url
        self.persona = PERSONAS[persona]
        self.ollama_host = ollama_host
        self.model = "qwen3:4b"  # Small model for phone
        self.wallet = generate_test_wallet()
    
    def analyze_proposal(self, proposal: dict) -> dict:
        """Use SML to analyze proposal based on persona"""
        prompt = f"""
You are acting as a voter with this persona:
Name: {self.persona['name']}
Description: {self.persona['description']}
Values: {', '.join(self.persona['values'])}
Against: {', '.join(self.persona['against'])}

Analyze this governance proposal and decide how to vote:

Proposal ID: {proposal['id']}
Title: {proposal['title']}
Description: {proposal['description']}

Based on your persona, respond with:
1. VOTE: YES, NO, or ABSTAIN
2. REASONING: 2-3 sentences explaining why (must reference your persona's values)
3. CONFIDENCE: 0.0 to 1.0

Format your response as:
VOTE: [YES/NO/ABSTAIN]
REASONING: [your reasoning]
CONFIDENCE: [0.0-1.0]
"""
        response = self._call_ollama(prompt)
        return self._parse_response(response)
    
    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama with the small model"""
        # Use /no_think or /nothink for faster responses if supported
        ...
    
    def _parse_response(self, response: str) -> dict:
        """Parse SML response into structured format"""
        ...
    
    def create_and_sign_vote(self, proposal_id: int, decision: dict) -> dict:
        """Create EIP-712 signed vote request"""
        ...
    
    def submit_vote(self, proposal_id: int) -> dict:
        """Full flow: analyze → decide → sign → submit"""
        # 1. Get proposal details (or use mock)
        proposal = self.get_proposal(proposal_id)
        
        # 2. Analyze with SML
        decision = self.analyze_proposal(proposal)
        print(f"SML Decision: {decision['vote']} (confidence: {decision['confidence']})")
        print(f"SML Reasoning: {decision['reasoning']}")
        
        # 3. Sign with EIP-712
        signed_request = self.create_and_sign_vote(proposal_id, decision)
        
        # 4. Submit to Observer
        response = requests.post(
            f"{self.node_url}/api/v1/submit_vote",
            json=signed_request
        )
        return response.json()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-url", default="http://localhost:8000")
    parser.add_argument("--persona", choices=list(PERSONAS.keys()), default="eco_warrior")
    parser.add_argument("--proposal-id", type=int, default=1)
    parser.add_argument("--ollama-host", default="http://localhost:11434")
    args = parser.parse_args()
    
    client = SMLPhoneClient(
        node_url=args.node_url,
        persona=args.persona,
        ollama_host=args.ollama_host
    )
    
    print(f"📱 Mock Phone with SML")
    print(f"   Persona: {client.persona['name']}")
    print(f"   Model: {client.model}")
    print(f"   Node: {args.node_url}")
    print()
    
    result = client.submit_vote(args.proposal_id)
    print(f"Result: {result}")
```

#### 2. Create mock proposals for testing

Since we may not have real proposals on the subnet, create some test proposals:
```python
MOCK_PROPOSALS = [
    {
        "id": 1,
        "title": "Fund Solar Panel Installation",
        "description": "Allocate 100,000 DAHAO to install solar panels on community buildings, reducing carbon footprint by 40%."
    },
    {
        "id": 2,
        "title": "Increase Mining Operations Budget",
        "description": "Expand mining operations to increase token supply. This will boost short-term profits but may impact local environment."
    },
    {
        "id": 3,
        "title": "Community Education Program",
        "description": "Fund free blockchain education workshops for underrepresented communities. Budget: 50,000 DAHAO."
    },
    {
        "id": 4,
        "title": "Implement AI-Powered Trading Bot",
        "description": "Develop and deploy an AI trading bot to maximize treasury returns through automated DeFi strategies."
    }
]
```

#### 3. Add test scenarios

Create `tests/test_sml_semantic_firewall.py`:

Test cases:
1. **Consistent vote**: eco_warrior votes NO on mining proposal → should PASS
2. **Inconsistent vote**: eco_warrior votes YES on mining proposal → should be REJECTED by semantic firewall
3. **Edge case**: profit_maximizer votes YES on mining → should PASS
4. **Confidence threshold**: Low confidence votes

#### 4. Add run script

Create `scripts/run_sml_test.sh`:
```bash
#!/bin/bash

echo "🧪 SML Semantic Firewall Test"
echo "=============================="
echo ""

# Check prerequisites
if ! curl -s http://localhost:8000/api/v1/health > /dev/null; then
    echo "❌ Observer Mode not running. Start with:"
    echo "   python main.py --mode observer --config config_dahao_subnet.yaml"
    exit 1
fi

if ! curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "❌ Ollama not running. Start with:"
    echo "   ollama serve"
    exit 1
fi

echo "✅ Prerequisites OK"
echo ""

# Test 1: Eco warrior on environmental proposal (should pass)
echo "Test 1: Eco Warrior + Solar Panel Proposal"
python tests/mock_phone_sml.py --persona eco_warrior --proposal-id 1
echo ""

# Test 2: Eco warrior on mining proposal (interesting - should vote NO)
echo "Test 2: Eco Warrior + Mining Proposal"
python tests/mock_phone_sml.py --persona eco_warrior --proposal-id 2
echo ""

# Test 3: Profit maximizer on mining proposal (should vote YES)
echo "Test 3: Profit Maximizer + Mining Proposal"
python tests/mock_phone_sml.py --persona profit_maximizer --proposal-id 2
echo ""

# Test 4: Community builder on education proposal
echo "Test 4: Community Builder + Education Proposal"
python tests/mock_phone_sml.py --persona community_builder --proposal-id 3
echo ""

echo "=============================="
echo "🎉 SML Tests Complete!"
```

### Expected Test Output
📱 Mock Phone with SML
Persona: Eco Warrior
Model: qwen3:4b
Node: http://localhost:8000
📋 Proposal: Fund Solar Panel Installation
Allocate 100,000 DAHAO to install solar panels...
🤖 SML Analysis:
VOTE: YES
REASONING: This proposal aligns with my core value of environmental
sustainability. Solar panels reduce carbon footprint and promote
green energy, which I strongly support.
CONFIDENCE: 0.95
✍️ Signing vote with EIP-712...
📤 Submitting to Observer...
🖥️ Observer Response:
Signature: ✅ Valid
Voting Power: ✅ 1000 DAHAO
Semantic Check: ✅ Reasoning consistent with persona
✅ Vote submitted to DAHAO Subnet
TX Hash: 0x...

### Semantic Firewall Test (Inconsistency Detection)

If SML makes a mistake (e.g., eco_warrior votes YES on mining):
🤖 SML Analysis:
VOTE: YES
REASONING: Mining operations could boost economic growth.
CONFIDENCE: 0.6
🖥️ Observer Response:
Signature: ✅ Valid
Voting Power: ✅ 1000 DAHAO
Semantic Check: ❌ REJECTED
Reason: Inconsistent reasoning. Persona "Eco Warrior" values
environment/sustainability but reasoning mentions economic growth
for a mining proposal without addressing environmental concerns.
❌ Vote rejected by semantic firewall

### Dependencies

Make sure Ollama has both models:
```bash
ollama pull qwen3:4b   # Phone (small)
ollama pull qwen3:14b  # Observer (large)
```

### Test Flow Diagram
┌─────────────────────────────────────────────────────────────────────┐
│                         TEST FLOW                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   1. DAHAO Subnet running (./scripts/setup_dahao_subnet.sh)        │
│   2. Contracts deployed (deploy_subnet.js)                          │
│   3. Observer Mode running (--config config_dahao_subnet.yaml)     │
│   4. Ollama running (qwen3:4b + qwen3:14b)                         │
│                                                                     │
│   TEST:                                                             │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐          │
│   │  mock_phone │     │  Observer   │     │   Subnet    │          │
│   │  + qwen3:4b │────►│  + qwen3:14b│────►│  Contract   │          │
│   └─────────────┘     └─────────────┘     └─────────────┘          │
│         │                   │                   │                   │
│   SML decides         Semantic check      Vote recorded            │
│   based on persona    validates or        on blockchain            │
│                       rejects                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

