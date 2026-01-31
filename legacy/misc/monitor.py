"""
DAHAO Hive Mind Monitor - Real-time Cognitive Stream Interface

A "Mind Reading Interface" that shows not just WHAT agents decided,
but WHY they decided it, and WHERE they conflict.

Run with: uv run streamlit run monitor.py
"""

import streamlit as st
import pandas as pd
import json
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import yaml
import re

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="DAHAO: Hive Mind Monitor",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- AGENT CONFIGURATION ---
AGENTS = {
    "Alice": {
        "color": "#4CAF50",
        "emoji": "🌿",
        "title": "Nature Mother",
        "worldview": "Biocentric, eco-focused",
    },
    "Bob": {
        "color": "#FFD700",
        "emoji": "💰",
        "title": "Capitalist",
        "worldview": "Profit-driven, growth-focused",
    },
    "Charlie": {
        "color": "#FF5252",
        "emoji": "✊",
        "title": "Anarchist",
        "worldview": "Decentralization maximalist",
    },
    "Dave": {
        "color": "#2196F3",
        "emoji": "🏛️",
        "title": "Conformist",
        "worldview": "Status quo defender",
    },
    "Eve": {
        "color": "#9C27B0",
        "emoji": "🔐",
        "title": "Hacker",
        "worldview": "Security researcher",
    }
}


# --- DATA LOADERS ---
def load_decisions(log_file: str = "decisions.log") -> list[dict]:
    """Load all decisions from the log file."""
    path = Path(log_file)
    if not path.exists():
        return []

    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                if line.strip():
                    data.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return data


def extract_agent_name(decision: dict | str) -> str:
    """Extract the agent name from a decision entry or fork_name string.

    Args:
        decision: Either a decision dict (with agent_name/fork_name) or a string.

    Returns:
        The agent name for display.
    """
    # If it's a dict, check for agent_name first (from --name CLI arg)
    if isinstance(decision, dict):
        agent_name = decision.get('agent_name')
        if agent_name:
            return agent_name
        fork_name = decision.get('fork_name', '')
    else:
        fork_name = decision

    # fork_name might be "Alice" or "Alice - Nature Mother" or "Deep Ecologist Node"
    if not fork_name:
        return "Unknown"

    # Check if it starts with a known agent name
    for name in AGENTS.keys():
        if fork_name.startswith(name):
            return name

    # Return first word as fallback
    return fork_name.split()[0] if fork_name else "Unknown"


def group_by_proposal(decisions: list[dict]) -> dict[int, list[dict]]:
    """Group decisions by proposal ID."""
    grouped = defaultdict(list)
    for d in decisions:
        pid = d.get('proposal_id', 0)
        grouped[pid].append(d)
    return dict(grouped)


def get_agent_info(name: str) -> dict:
    """Get agent display info, with fallback for unknown agents."""
    # Try to extract base name
    base_name = extract_agent_name(name)

    return AGENTS.get(base_name, {
        "color": "#888888",
        "emoji": "🤖",
        "title": "Unknown",
        "worldview": "Unknown worldview",
    })


def get_vote_color(vote: str) -> str:
    """Get color for vote badge."""
    return {
        "YES": "#4CAF50",
        "NO": "#FF5252",
        "ABSTAIN": "#FFC107",
        "NO_WITH_VETO": "#9C27B0"
    }.get(vote, "#888888")


def analyze_conflict(decisions: list[dict]) -> dict:
    """Analyze conflicts between agent decisions on the same proposal."""
    if len(decisions) < 2:
        return {"has_conflict": False, "details": []}

    votes = {}
    for d in decisions:
        agent = extract_agent_name(d)
        vote = d.get('vote', 'ABSTAIN')
        votes[agent] = {
            "vote": vote,
            "confidence": d.get('confidence', 0),
            "principles": d.get('principles_aligned', []),
            "reasoning": d.get('llm_reasoning', '')
        }

    yes_agents = [a for a, v in votes.items() if v['vote'] == 'YES']
    no_agents = [a for a, v in votes.items() if v['vote'] in ('NO', 'NO_WITH_VETO')]

    has_conflict = len(yes_agents) > 0 and len(no_agents) > 0

    conflicts = []
    if has_conflict:
        for yes_a in yes_agents:
            for no_a in no_agents:
                conflicts.append({
                    "agent_yes": yes_a,
                    "agent_no": no_a,
                    "yes_principles": votes[yes_a]['principles'],
                    "no_principles": votes[no_a]['principles'],
                    "yes_reasoning": votes[yes_a]['reasoning'],
                    "no_reasoning": votes[no_a]['reasoning']
                })

    return {
        "has_conflict": has_conflict,
        "yes_agents": yes_agents,
        "no_agents": no_agents,
        "details": conflicts,
        "votes": votes
    }


def predict_outcome(decisions: list[dict]) -> dict:
    """Predict proposal outcome based on current votes."""
    if not decisions:
        return {"prediction": "UNKNOWN", "confidence": 0}

    yes_count = sum(1 for d in decisions if d.get('vote') == 'YES')
    no_count = sum(1 for d in decisions if d.get('vote') in ('NO', 'NO_WITH_VETO'))
    veto_count = sum(1 for d in decisions if d.get('vote') == 'NO_WITH_VETO')
    total = len(decisions)

    if yes_count > no_count:
        prediction = "PASS"
        confidence = yes_count / total
    elif no_count > yes_count:
        prediction = "REJECT"
        confidence = no_count / total
    else:
        prediction = "TIE"
        confidence = 0.5

    if total > 0 and veto_count / total > 0.33:
        prediction = "VETOED"
        confidence = veto_count / total

    return {
        "prediction": prediction,
        "confidence": confidence,
        "yes": yes_count,
        "no": no_count,
        "veto": veto_count,
        "total": total
    }


def format_time_ago(timestamp_str: str) -> str:
    """Format timestamp as relative time."""
    try:
        ts = timestamp_str.replace('Z', '')
        if '+' in ts:
            ts = ts.split('+')[0]
        dt = datetime.fromisoformat(ts)
        now = datetime.now()
        diff = now - dt

        seconds = diff.total_seconds()
        if seconds < 0:
            return "just now"
        elif seconds < 60:
            return f"{int(seconds)}s ago"
        elif seconds < 3600:
            return f"{int(seconds/60)}m ago"
        elif seconds < 86400:
            return f"{int(seconds/3600)}h ago"
        else:
            return f"{int(seconds/86400)}d ago"
    except:
        return timestamp_str[:16] if timestamp_str else "Unknown"


def truncate_principles(principles: list, max_items: int = 3, max_len: int = 40) -> str:
    """Truncate principle list for display."""
    if not principles:
        return "None detected"

    result = []
    for p in principles[:max_items]:
        if isinstance(p, str):
            if len(p) > max_len:
                result.append(p[:max_len] + "...")
            else:
                result.append(p)

    if len(principles) > max_items:
        result.append(f"+{len(principles) - max_items} more")

    return ", ".join(result)


# --- MAIN UI ---
def main():
    # Header
    st.title("🧠 DAHAO Hive Mind Monitor")
    st.caption("Real-time cognitive stream from autonomous governance agents")

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Controls")

        auto_refresh = st.checkbox("🔄 Auto-Refresh", value=True)
        refresh_interval = st.slider("Refresh Interval (sec)", 1, 10, 3) if auto_refresh else 3

        st.divider()

        st.header("🔍 Filters")
        agent_options = ["All Agents"] + list(AGENTS.keys())
        selected_agent = st.selectbox("Filter by Agent", agent_options)

        vote_options = ["All Votes", "YES", "NO", "ABSTAIN", "NO_WITH_VETO"]
        selected_vote = st.selectbox("Filter by Vote", vote_options)

        min_confidence = st.slider("Min Confidence", 0.0, 1.0, 0.0, 0.1)

        st.divider()

        st.header("📊 Agent Legend")
        for name, info in AGENTS.items():
            st.markdown(f"{info['emoji']} **{name}** - {info['title']}")

    # Load data
    decisions = load_decisions()

    # Apply filters
    filtered = decisions.copy()
    if selected_agent != "All Agents":
        filtered = [d for d in filtered if extract_agent_name(d) == selected_agent]
    if selected_vote != "All Votes":
        filtered = [d for d in filtered if d.get('vote') == selected_vote]
    filtered = [d for d in filtered if d.get('confidence', 0) >= min_confidence]

    # Metrics Row
    if decisions:
        col1, col2, col3, col4, col5 = st.columns(5)

        total = len(decisions)
        yes_votes = sum(1 for d in decisions if d.get('vote') == 'YES')
        no_votes = sum(1 for d in decisions if d.get('vote') in ('NO', 'NO_WITH_VETO'))
        abstain_votes = sum(1 for d in decisions if d.get('vote') == 'ABSTAIN')
        avg_conf = sum(d.get('confidence', 0) for d in decisions) / total if total > 0 else 0

        col1.metric("🗳️ Total Decisions", total)
        col2.metric("✅ Approval Rate", f"{(yes_votes/total)*100:.0f}%")
        col3.metric("❌ Rejection Rate", f"{(no_votes/total)*100:.0f}%")
        col4.metric("⚖️ Abstain Rate", f"{(abstain_votes/total)*100:.0f}%")
        col5.metric("🎯 Avg Confidence", f"{avg_conf*100:.0f}%")
    else:
        st.info("No decisions recorded yet. Start the sidecar swarm to see data.")

    st.divider()

    # Main Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📡 Live Thought Stream",
        "🎯 Proposal Comparison",
        "⚔️ Conflict Analysis",
        "📈 Analytics"
    ])

    # --- TAB 1: LIVE THOUGHT STREAM ---
    with tab1:
        st.subheader("📡 Live Cognitive Feed")
        st.caption("Watch agents think in real-time as they process governance proposals")

        if not filtered:
            st.info("🔮 Waiting for incoming thoughts from the swarm...")
        else:
            # Show most recent first
            for d in reversed(filtered[-20:]):
                agent_name = extract_agent_name(d)
                agent_info = get_agent_info(agent_name)
                vote = d.get('vote', 'UNKNOWN')
                confidence = d.get('confidence', 0.0)
                proposal_title = d.get('proposal_title', 'Unknown Proposal')
                proposal_id = d.get('proposal_id', 0)
                reasoning = d.get('llm_reasoning', 'No reasoning provided.')
                timestamp = d.get('timestamp', '')
                principles = d.get('principles_aligned', [])
                terms = d.get('terms_referenced', [])
                reasoning_hash = d.get('reasoning_hash', '')[:16]

                time_ago = format_time_ago(timestamp)
                vote_color = get_vote_color(vote)

                # Card container
                with st.container():
                    # Header row
                    header_col1, header_col2, header_col3 = st.columns([3, 4, 2])

                    with header_col1:
                        st.markdown(f"### {agent_info['emoji']} {agent_name}")
                        st.caption(f"{agent_info['title']} • {agent_info['worldview']}")

                    with header_col2:
                        st.markdown(f"**Proposal #{proposal_id}:** {proposal_title}")

                    with header_col3:
                        st.markdown(f":{vote.lower().replace('_', '')}[**{vote}**]" if vote in ["YES", "NO"] else f"**{vote}**")
                        st.caption(time_ago)

                    # Confidence bar
                    conf_col1, conf_col2 = st.columns([1, 4])
                    with conf_col1:
                        st.caption("Confidence")
                    with conf_col2:
                        st.progress(confidence, text=f"{confidence*100:.0f}%")

                    # Reasoning
                    with st.expander("💭 View Reasoning", expanded=False):
                        st.markdown(f"> {reasoning}")

                        meta_col1, meta_col2, meta_col3 = st.columns(3)
                        with meta_col1:
                            st.caption(f"**Principles:** {truncate_principles(principles)}")
                        with meta_col2:
                            st.caption(f"**Terms:** {', '.join(terms) if terms else 'None'}")
                        with meta_col3:
                            st.caption(f"**Hash:** `{reasoning_hash}...`")

                    st.divider()

    # --- TAB 2: PROPOSAL COMPARISON ---
    with tab2:
        st.subheader("🎯 Proposal-Centric View")
        st.caption("See how different agents voted on the same proposal")

        grouped = group_by_proposal(decisions)

        if not grouped:
            st.info("No proposals to compare yet...")
        else:
            for pid in sorted(grouped.keys(), reverse=True):
                prop_decisions = grouped[pid]
                first = prop_decisions[0]
                proposal_title = first.get('proposal_title', f'Proposal #{pid}')

                conflict = analyze_conflict(prop_decisions)
                prediction = predict_outcome(prop_decisions)

                with st.expander(f"**Proposal #{pid}:** {proposal_title}", expanded=(pid == max(grouped.keys()))):

                    # Prediction row
                    pred_col, conflict_col = st.columns(2)

                    with pred_col:
                        pred_emoji = {"PASS": "✅", "REJECT": "❌", "VETOED": "🚫", "TIE": "⚖️"}.get(prediction['prediction'], "❓")
                        st.markdown(f"**Predicted Outcome:** {pred_emoji} **{prediction['prediction']}** ({prediction['yes']} YES / {prediction['no']} NO)")

                    with conflict_col:
                        if conflict['has_conflict']:
                            st.warning(f"⚔️ **CONFLICT:** {', '.join(conflict['yes_agents'])} vs {', '.join(conflict['no_agents'])}")
                        else:
                            st.success("✓ Consensus Reached")

                    st.markdown("---")

                    # Agent votes grid
                    num_agents = len(prop_decisions)
                    cols = st.columns(min(num_agents, 5))

                    for idx, d in enumerate(prop_decisions):
                        agent_name = extract_agent_name(d)
                        agent_info = get_agent_info(agent_name)
                        vote = d.get('vote', 'UNKNOWN')
                        confidence = d.get('confidence', 0)
                        vote_color = get_vote_color(vote)

                        with cols[idx % 5]:
                            st.markdown(f"### {agent_info['emoji']}")
                            st.markdown(f"**{agent_name}**")
                            st.markdown(f":{vote.lower().replace('_','')}[{vote}]" if vote in ["YES","NO"] else vote)
                            st.progress(confidence, text=f"{confidence*100:.0f}%")

                    # Reasoning comparison for conflicts
                    if conflict['has_conflict'] and conflict['votes']:
                        st.markdown("---")
                        st.markdown("**💭 All Reasoning:**")

                        # Show YES coalition reasoning
                        if conflict['yes_agents']:
                            st.markdown("##### ✅ YES Coalition")
                            for agent in conflict['yes_agents']:
                                vote_data = conflict['votes'].get(agent, {})
                                agent_info = get_agent_info(agent)
                                reasoning = vote_data.get('reasoning', 'No reasoning provided.')
                                principles = vote_data.get('principles', [])
                                confidence = vote_data.get('confidence', 0)

                                with st.expander(f"{agent_info['emoji']} **{agent}** - {confidence*100:.0f}% confidence", expanded=False):
                                    if principles:
                                        st.caption(f"**Principles:** {', '.join(principles)}")
                                    st.markdown(reasoning)

                        # Show NO coalition reasoning
                        if conflict['no_agents']:
                            st.markdown("##### ❌ NO Coalition")
                            for agent in conflict['no_agents']:
                                vote_data = conflict['votes'].get(agent, {})
                                agent_info = get_agent_info(agent)
                                reasoning = vote_data.get('reasoning', 'No reasoning provided.')
                                principles = vote_data.get('principles', [])
                                confidence = vote_data.get('confidence', 0)
                                vote_type = vote_data.get('vote', 'NO')

                                label = f"{agent_info['emoji']} **{agent}** - {confidence*100:.0f}% confidence"
                                if vote_type == 'NO_WITH_VETO':
                                    label += " ⚠️ VETO"

                                with st.expander(label, expanded=False):
                                    if principles:
                                        st.caption(f"**Principles:** {', '.join(principles)}")
                                    st.markdown(reasoning)

    # --- TAB 3: CONFLICT ANALYSIS ---
    with tab3:
        st.subheader("⚔️ Principle Clash Analysis")
        st.caption("Deep dive into why agents disagree")

        grouped = group_by_proposal(decisions)

        all_conflicts = []
        for pid, prop_decisions in grouped.items():
            conflict = analyze_conflict(prop_decisions)
            if conflict['has_conflict']:
                all_conflicts.append({
                    "proposal_id": pid,
                    "proposal_title": prop_decisions[0].get('proposal_title', f'Proposal #{pid}'),
                    "conflict": conflict
                })

        if not all_conflicts:
            st.success("🕊️ No conflicts detected! All agents are in harmony.")
        else:
            st.warning(f"⚠️ Found **{len(all_conflicts)}** proposal(s) with conflicting votes")

            for item in all_conflicts:
                pid = item['proposal_id']
                title = item['proposal_title']
                conflict = item['conflict']

                st.markdown(f"### ⚔️ Proposal #{pid}: {title}")

                col1, col2 = st.columns(2)
                with col1:
                    st.success(f"**✅ YES Coalition:** {', '.join(conflict['yes_agents'])}")
                with col2:
                    st.error(f"**❌ NO Coalition:** {', '.join(conflict['no_agents'])}")

                # Show all YES agents
                with st.expander(f"✅ YES Coalition ({len(conflict['yes_agents'])} agents)", expanded=True):
                    for agent in conflict['yes_agents']:
                        vote_data = conflict['votes'].get(agent, {})
                        agent_info = get_agent_info(agent)
                        reasoning = vote_data.get('reasoning', 'No reasoning provided.')
                        principles = vote_data.get('principles', [])
                        confidence = vote_data.get('confidence', 0)

                        st.markdown(f"### {agent_info['emoji']} {agent}")
                        st.caption(f"**Worldview:** {agent_info['worldview']} | **Confidence:** {confidence*100:.0f}%")
                        if principles:
                            st.caption(f"**Triggered Principles:** {', '.join(principles)}")
                        st.success(reasoning)
                        st.markdown("---")

                # Show all NO agents
                with st.expander(f"❌ NO Coalition ({len(conflict['no_agents'])} agents)", expanded=True):
                    for agent in conflict['no_agents']:
                        vote_data = conflict['votes'].get(agent, {})
                        agent_info = get_agent_info(agent)
                        reasoning = vote_data.get('reasoning', 'No reasoning provided.')
                        principles = vote_data.get('principles', [])
                        confidence = vote_data.get('confidence', 0)
                        vote_type = vote_data.get('vote', 'NO')

                        veto_badge = " ⚠️ **VETO**" if vote_type == 'NO_WITH_VETO' else ""
                        st.markdown(f"### {agent_info['emoji']} {agent}{veto_badge}")
                        st.caption(f"**Worldview:** {agent_info['worldview']} | **Confidence:** {confidence*100:.0f}%")
                        if principles:
                            st.caption(f"**Triggered Principles:** {', '.join(principles)}")
                        st.error(reasoning)
                        st.markdown("---")

                st.divider()

    # --- TAB 4: ANALYTICS ---
    with tab4:
        st.subheader("📈 Swarm Analytics")

        if not decisions:
            st.info("Not enough data for analytics yet...")
        else:
            # Vote distribution by agent
            st.markdown("### 🗳️ Vote Distribution by Agent")

            agent_votes = defaultdict(lambda: {"YES": 0, "NO": 0, "ABSTAIN": 0, "NO_WITH_VETO": 0})
            for d in decisions:
                agent = extract_agent_name(d)
                vote = d.get('vote', 'ABSTAIN')
                agent_votes[agent][vote] += 1

            if agent_votes:
                df_votes = pd.DataFrame(agent_votes).T
                st.bar_chart(df_votes)

            # Confidence by agent
            st.markdown("### 🎯 Average Confidence by Agent")

            agent_conf = defaultdict(list)
            for d in decisions:
                agent = extract_agent_name(d)
                agent_conf[agent].append(d.get('confidence', 0))

            avg_conf_data = {agent: sum(confs)/len(confs)*100 for agent, confs in agent_conf.items() if confs}
            if avg_conf_data:
                df_conf = pd.DataFrame.from_dict(avg_conf_data, orient='index', columns=['Avg Confidence %'])
                st.bar_chart(df_conf)

            # Agent agreement matrix
            st.markdown("### 🤝 Agent Agreement Matrix")
            st.caption("How often do agents vote the same way? (percentage)")

            grouped = group_by_proposal(decisions)
            agreement_matrix = defaultdict(lambda: defaultdict(int))
            total_comparisons = defaultdict(lambda: defaultdict(int))

            for pid, prop_decisions in grouped.items():
                votes_by_agent = {extract_agent_name(d): d.get('vote') for d in prop_decisions}
                agents = list(votes_by_agent.keys())

                for i, a1 in enumerate(agents):
                    for a2 in agents[i+1:]:
                        total_comparisons[a1][a2] += 1
                        total_comparisons[a2][a1] += 1
                        if votes_by_agent[a1] == votes_by_agent[a2]:
                            agreement_matrix[a1][a2] += 1
                            agreement_matrix[a2][a1] += 1

            agent_names = list(AGENTS.keys())
            matrix_data = []
            for a1 in agent_names:
                row = []
                for a2 in agent_names:
                    if a1 == a2:
                        row.append(100)
                    elif total_comparisons[a1][a2] > 0:
                        pct = (agreement_matrix[a1][a2] / total_comparisons[a1][a2]) * 100
                        row.append(int(pct))
                    else:
                        row.append(0)
                matrix_data.append(row)

            df_matrix = pd.DataFrame(matrix_data, index=agent_names, columns=agent_names)

            def color_agreement(val):
                if val >= 80:
                    return 'background-color: #4CAF50; color: white'
                elif val >= 60:
                    return 'background-color: #8BC34A; color: black'
                elif val >= 40:
                    return 'background-color: #FFC107; color: black'
                elif val >= 20:
                    return 'background-color: #FF9800; color: black'
                else:
                    return 'background-color: #FF5252; color: white'

            st.dataframe(df_matrix.style.map(color_agreement))

            # Timeline
            st.markdown("### 📅 Recent Decision Timeline")

            timeline_data = []
            for d in decisions[-30:]:
                timeline_data.append({
                    "Time": format_time_ago(d.get('timestamp', '')),
                    "Agent": extract_agent_name(d),
                    "Proposal": f"#{d.get('proposal_id', 0)}",
                    "Vote": d.get('vote', 'UNKNOWN'),
                    "Confidence": f"{d.get('confidence', 0)*100:.0f}%"
                })

            if timeline_data:
                df_timeline = pd.DataFrame(reversed(timeline_data))
                st.dataframe(df_timeline, width="stretch", hide_index=True)

    # Auto-refresh
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
