# Flask UI for DAHAO Sidecar

This document outlines how to create a Flask-based web UI to monitor and interact with the DAHAO sidecar voting agent.

---

## Available Data Sources

The sidecar has several data sources we can expose via a web UI:

| Source | Type | Description |
|--------|------|-------------|
| `decisions.log` | JSON-lines file | All voting decisions with reasoning |
| `sidecar_state.json` | JSON file | Processed proposal IDs |
| Chain (gRPC) | Live query | Active proposals, vote tallies |
| `fork.yaml` | YAML file | Current voting principles |
| `data/*.json` | JSON files | SharedLaw terms, principles, rules |
| Ollama | HTTP API | LLM status, model info |

---

## Proposed UI Structure

```
┌─────────────────────────────────────────────────────────────────┐
│  DAHAO Sidecar Dashboard                          [Agent: Alice]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Active Props   │  │  Total Votes    │  │  Avg Confidence │ │
│  │       3         │  │      47         │  │     0.78        │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    RECENT DECISIONS                         ││
│  ├─────────────────────────────────────────────────────────────┤│
│  │ #42 | Network Upgrade    | YES    | 0.92 | 2 min ago       ││
│  │ #41 | Treasury Spend     | NO     | 0.85 | 1 hour ago      ││
│  │ #40 | Parameter Change   | ABSTAIN| 0.45 | 3 hours ago     ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ┌──────────────────────────┐ ┌────────────────────────────────┐│
│  │     VOTE DISTRIBUTION    │ │     CONFIDENCE HISTOGRAM       ││
│  │                          │ │                                ││
│  │   YES ████████░░ 68%     │ │  0.9-1.0 ████████ 15          ││
│  │   NO  ███░░░░░░░ 22%     │ │  0.7-0.9 ██████████ 22        ││
│  │   ABS █░░░░░░░░░  8%     │ │  0.5-0.7 ███░░░░░░░  8        ││
│  │   VETO░░░░░░░░░░  2%     │ │  <0.5    █░░░░░░░░░  2        ││
│  └──────────────────────────┘ └────────────────────────────────┘│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Page Structure

### 1. Dashboard (`/`)
Main overview page with:
- **Stats Cards**: Active proposals, total votes, average confidence
- **Recent Decisions Table**: Last 10 decisions with expandable reasoning
- **Vote Distribution Chart**: Pie chart of YES/NO/ABSTAIN/VETO
- **Confidence Histogram**: Distribution of confidence scores
- **Agent Status**: Connected to chain? LLM available?

### 2. Decisions (`/decisions`)
Full decision history:
- **Filterable Table**: Filter by vote type, date range, confidence
- **Search**: Search in proposal titles and reasoning
- **Export**: Download as CSV/JSON
- **Decision Detail Modal**: Full reasoning, principle triggered, hash

### 3. Active Proposals (`/proposals`)
Live proposals from chain:
- **Proposal Cards**: Title, description, voting deadline
- **Vote Countdown**: Time remaining
- **Manual Vote Override**: (Optional) Trigger vote with custom choice
- **Proposal Status**: Already voted? Pending?

### 4. Fork Config (`/fork`)
Current fork configuration:
- **Fork Name & Style**: Display current values
- **Principles List**: All voting principles
- **Alignment Info**: Which SharedLaw principles aligned
- **Edit Fork**: (Optional) Modify fork.yaml via UI

### 5. SharedLaw Explorer (`/sharedlaw`)
Browse governance framework:
- **Terms Tab**: All @terms with definitions
- **Principles Tab**: Locked vs unlocked principles
- **Rules Tab**: Governance rules
- **Thresholds**: Consensus requirements

### 6. Swarm View (`/swarm`) (Optional)
Multi-agent simulation:
- **Agent Cards**: Each agent's status
- **Vote Comparison**: How different agents voted on same proposal
- **Consensus Meter**: Agreement level between agents

---

## API Endpoints

### Core Endpoints

```python
# Dashboard stats
GET /api/stats
Response: {
    "active_proposals": 3,
    "total_votes": 47,
    "avg_confidence": 0.78,
    "vote_distribution": {"YES": 32, "NO": 10, "ABSTAIN": 4, "NO_WITH_VETO": 1},
    "agent_name": "Alice",
    "chain_connected": true,
    "llm_available": true
}

# Recent decisions
GET /api/decisions?limit=10&offset=0
Response: {
    "decisions": [
        {
            "timestamp": "2024-01-15T10:30:00Z",
            "proposal_id": 42,
            "proposal_title": "Network Upgrade",
            "vote": "YES",
            "confidence": 0.92,
            "reasoning": "...",
            "reasoning_hash": "sha256:abc...",
            "principle_triggered": "Prioritize security"
        }
    ],
    "total": 47
}

# Single decision detail
GET /api/decisions/<proposal_id>
Response: { /* full decision entry */ }

# Active proposals from chain
GET /api/proposals
Response: {
    "proposals": [
        {
            "id": 43,
            "title": "New Proposal",
            "description": "...",
            "status": "VOTING_PERIOD",
            "voting_end_time": "2024-01-20T00:00:00Z",
            "already_voted": false
        }
    ]
}

# Fork configuration
GET /api/fork
Response: {
    "name": "Security-First Validator",
    "voting_style": "cautious",
    "abstain_threshold": 0.6,
    "principles": ["...", "..."],
    "inherits": "dahao-core v1.0.0"
}

# SharedLaw data
GET /api/sharedlaw/terms
GET /api/sharedlaw/principles
GET /api/sharedlaw/rules
GET /api/sharedlaw/governance

# System status
GET /api/status
Response: {
    "sidecar_running": true,
    "chain_connected": true,
    "llm_model": "qwen3:14b",
    "llm_available": true,
    "wallet_address": "cosmos1...",
    "wallet_balance": 99000
}
```

### Action Endpoints (Optional)

```python
# Manual vote trigger
POST /api/vote
Body: {"proposal_id": 43, "choice": "YES"}

# Reload fork
POST /api/fork/reload

# Force poll cycle
POST /api/poll
```

---

## Implementation Plan

### Phase 1: Basic Dashboard (Read-Only)

**Files to create:**
```
leviathan/
├── ui/
│   ├── __init__.py
│   ├── app.py              # Flask app factory
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── api.py          # API endpoints
│   │   └── views.py        # HTML routes
│   ├── services/
│   │   ├── __init__.py
│   │   ├── decisions.py    # decisions.log reader
│   │   ├── chain.py        # Chain queries
│   │   └── status.py       # System status checks
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── decisions.html
│   │   └── proposals.html
│   └── static/
│       ├── css/
│       │   └── style.css
│       └── js/
│           └── dashboard.js
└── run_ui.py               # Entry point
```

**Dependencies to add:**
```
flask>=3.0
flask-cors  # For API access from other origins
```

### Phase 2: Real-Time Updates

- Add WebSocket support with Flask-SocketIO
- Push new decisions to connected clients
- Live proposal countdown timers

### Phase 3: Interactive Features

- Manual vote override
- Fork editor
- Agent comparison view

---

## Minimal Flask App Structure

```python
# ui/app.py
from flask import Flask, jsonify, render_template
from pathlib import Path
import json

def create_app(config=None):
    app = Flask(__name__)

    # Configuration
    app.config['DECISIONS_LOG'] = 'decisions.log'
    app.config['FORK_FILE'] = 'fork.yaml'
    app.config['DATA_DIR'] = 'data/'

    if config:
        app.config.update(config)

    # Register blueprints
    from .routes import api, views
    app.register_blueprint(api.bp, url_prefix='/api')
    app.register_blueprint(views.bp)

    return app
```

```python
# ui/routes/api.py
from flask import Blueprint, jsonify, current_app
from ..services import decisions, status

bp = Blueprint('api', __name__)

@bp.route('/stats')
def get_stats():
    log_file = current_app.config['DECISIONS_LOG']
    all_decisions = decisions.load_all(log_file)

    vote_counts = {'YES': 0, 'NO': 0, 'ABSTAIN': 0, 'NO_WITH_VETO': 0}
    total_confidence = 0

    for d in all_decisions:
        vote_counts[d['vote']] = vote_counts.get(d['vote'], 0) + 1
        total_confidence += d['confidence']

    return jsonify({
        'total_votes': len(all_decisions),
        'avg_confidence': total_confidence / len(all_decisions) if all_decisions else 0,
        'vote_distribution': vote_counts,
    })

@bp.route('/decisions')
def get_decisions():
    log_file = current_app.config['DECISIONS_LOG']
    limit = request.args.get('limit', 10, type=int)
    offset = request.args.get('offset', 0, type=int)

    all_decisions = decisions.load_all(log_file)
    # Most recent first
    all_decisions.reverse()

    return jsonify({
        'decisions': all_decisions[offset:offset+limit],
        'total': len(all_decisions),
    })

@bp.route('/status')
def get_status():
    return jsonify(status.get_system_status())
```

```python
# ui/services/decisions.py
import json
from pathlib import Path

def load_all(log_file: str) -> list[dict]:
    """Load all decisions from the log file."""
    path = Path(log_file)
    if not path.exists():
        return []

    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries

def get_stats(log_file: str) -> dict:
    """Calculate stats from decisions."""
    entries = load_all(log_file)

    if not entries:
        return {
            'total': 0,
            'avg_confidence': 0,
            'vote_distribution': {}
        }

    vote_counts = {}
    total_confidence = 0

    for entry in entries:
        vote = entry.get('vote', 'UNKNOWN')
        vote_counts[vote] = vote_counts.get(vote, 0) + 1
        total_confidence += entry.get('confidence', 0)

    return {
        'total': len(entries),
        'avg_confidence': total_confidence / len(entries),
        'vote_distribution': vote_counts,
    }
```

---

## Dashboard Template (Minimal)

```html
<!-- ui/templates/dashboard.html -->
<!DOCTYPE html>
<html>
<head>
    <title>DAHAO Sidecar Dashboard</title>
    <style>
        body { font-family: system-ui; max-width: 1200px; margin: 0 auto; padding: 20px; }
        .stats { display: flex; gap: 20px; margin-bottom: 30px; }
        .stat-card {
            background: #f5f5f5;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            flex: 1;
        }
        .stat-value { font-size: 2em; font-weight: bold; }
        .stat-label { color: #666; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        .vote-yes { color: green; }
        .vote-no { color: red; }
        .vote-abstain { color: orange; }
        .vote-veto { color: darkred; }
        .confidence {
            background: linear-gradient(90deg, #4CAF50 var(--conf), #eee var(--conf));
            padding: 4px 8px;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <h1>DAHAO Sidecar Dashboard</h1>

    <div class="stats">
        <div class="stat-card">
            <div class="stat-value" id="total-votes">-</div>
            <div class="stat-label">Total Votes</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="avg-confidence">-</div>
            <div class="stat-label">Avg Confidence</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="yes-percent">-</div>
            <div class="stat-label">YES Rate</div>
        </div>
    </div>

    <h2>Recent Decisions</h2>
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Proposal</th>
                <th>Vote</th>
                <th>Confidence</th>
                <th>Time</th>
            </tr>
        </thead>
        <tbody id="decisions-table">
            <tr><td colspan="5">Loading...</td></tr>
        </tbody>
    </table>

    <script>
        async function loadStats() {
            const resp = await fetch('/api/stats');
            const data = await resp.json();

            document.getElementById('total-votes').textContent = data.total_votes;
            document.getElementById('avg-confidence').textContent =
                (data.avg_confidence * 100).toFixed(0) + '%';

            const total = data.total_votes || 1;
            const yesRate = ((data.vote_distribution.YES || 0) / total * 100).toFixed(0);
            document.getElementById('yes-percent').textContent = yesRate + '%';
        }

        async function loadDecisions() {
            const resp = await fetch('/api/decisions?limit=10');
            const data = await resp.json();

            const tbody = document.getElementById('decisions-table');
            tbody.innerHTML = data.decisions.map(d => `
                <tr>
                    <td>#${d.proposal_id}</td>
                    <td>${d.proposal_title}</td>
                    <td class="vote-${d.vote.toLowerCase()}">${d.vote}</td>
                    <td>
                        <span class="confidence" style="--conf: ${d.confidence * 100}%">
                            ${(d.confidence * 100).toFixed(0)}%
                        </span>
                    </td>
                    <td>${new Date(d.timestamp).toLocaleString()}</td>
                </tr>
            `).join('');
        }

        loadStats();
        loadDecisions();

        // Auto-refresh every 30 seconds
        setInterval(() => {
            loadStats();
            loadDecisions();
        }, 30000);
    </script>
</body>
</html>
```

---

## Run Command

```bash
# Add to pyproject.toml or install manually
uv add flask flask-cors

# Run the UI
uv run python run_ui.py

# Or with custom port
uv run python run_ui.py --port 8080
```

```python
# run_ui.py
import argparse
from ui.app import create_app

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)
```

---

## Features Summary

### Must Have (Phase 1)
- [ ] Dashboard with stats
- [ ] Recent decisions table
- [ ] Decision detail view with full reasoning
- [ ] Fork configuration display
- [ ] Basic system status

### Nice to Have (Phase 2)
- [ ] Real-time updates via WebSocket
- [ ] Vote distribution charts (Chart.js)
- [ ] Confidence histogram
- [ ] Search/filter decisions
- [ ] Export to CSV

### Future (Phase 3)
- [ ] Manual vote trigger
- [ ] Fork editor
- [ ] Multi-agent swarm view
- [ ] Proposal comparison
- [ ] Decision replay/audit

---

## Tech Stack Options

### Option A: Pure Flask (Recommended for simplicity)
```
Flask + Jinja2 templates + vanilla JS
```
- Pros: Simple, no build step, Python-only
- Cons: Less interactive

### Option B: Flask + HTMX
```
Flask + Jinja2 + HTMX
```
- Pros: Interactive without complex JS, partial page updates
- Cons: HTMX learning curve

### Option C: Flask API + React/Vue Frontend
```
Flask API backend + Vite + React/Vue
```
- Pros: Most interactive, modern UX
- Cons: More complex, separate build step

### Option D: Streamlit (Quickest)
```
Streamlit dashboard
```
- Pros: Fastest to build, auto-refresh, charts built-in
- Cons: Less customizable, Streamlit-specific patterns

---

## Quick Start with Streamlit (Alternative)

If you want the fastest path to a working UI:

```python
# streamlit_app.py
import streamlit as st
import json
from pathlib import Path
import pandas as pd

st.set_page_config(page_title="DAHAO Sidecar", layout="wide")
st.title("DAHAO Sidecar Dashboard")

# Load decisions
@st.cache_data(ttl=10)
def load_decisions():
    path = Path("decisions.log")
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except:
                    pass
    return entries

decisions = load_decisions()

# Stats
col1, col2, col3 = st.columns(3)
col1.metric("Total Votes", len(decisions))
col2.metric("Avg Confidence", f"{sum(d['confidence'] for d in decisions)/len(decisions)*100:.0f}%" if decisions else "N/A")
col3.metric("YES Rate", f"{sum(1 for d in decisions if d['vote']=='YES')/len(decisions)*100:.0f}%" if decisions else "N/A")

# Recent decisions
st.subheader("Recent Decisions")
if decisions:
    df = pd.DataFrame(decisions[-10:][::-1])
    st.dataframe(df[['timestamp', 'proposal_id', 'proposal_title', 'vote', 'confidence']])

# Vote distribution
st.subheader("Vote Distribution")
if decisions:
    votes = pd.Series([d['vote'] for d in decisions]).value_counts()
    st.bar_chart(votes)
```

```bash
uv add streamlit pandas
uv run streamlit run streamlit_app.py
```

---

## Recommendation

Start with **Option A (Pure Flask)** for:
1. Integration with existing Python codebase
2. No additional build complexity
3. Sufficient for monitoring purposes

Move to **Option C (Flask + React)** later if:
1. You need complex interactivity
2. Multiple users will access the dashboard
3. You want real-time WebSocket updates

Or use **Streamlit** for:
1. Quick prototype
2. Internal/personal use only
3. Built-in charting needs
