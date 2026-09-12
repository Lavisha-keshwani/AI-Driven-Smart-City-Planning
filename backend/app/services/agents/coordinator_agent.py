"""
Coordinator Agent.

Receives outputs from all other agents, weighs conflicting priorities, and
produces the final recommendation. Right now this is a simple severity-vote:
alert from any agent pulls the decision toward restriction; caution pulls
toward conditional approval; all-clear allows normal approval.

This is the natural place to later plug in the NSGA-II / multi-objective
optimizer described in the project spec — right now it's a transparent,
inspectable rule so the rest of the system can be built and tested first.
"""

TONE_SEVERITY = {"alert": 3, "caution": 2, "neutral": 1, "positive": 0}


def run(city_name: str, agent_outputs: list[dict]) -> dict:
    alert_agents = [a["agent"] for a in agent_outputs if a["tone"] == "alert"]
    caution_agents = [a["agent"] for a in agent_outputs if a["tone"] == "caution"]

    if alert_agents:
        text = (
            f"{', '.join(alert_agents)} flagged critical concerns for {city_name}. "
            f"Recommend pausing new approvals in the affected areas and prioritizing "
            f"a targeted review before any expansion proceeds."
        )
    elif caution_agents:
        text = (
            f"{', '.join(caution_agents)} raised concerns worth addressing. Recommend "
            f"conditional approval — proceed with mitigations (rainwater harvesting, "
            f"water recycling, or buffer zones as flagged) rather than blocking outright."
        )
    else:
        text = (
            f"No agent raised significant concern for {city_name} at current growth "
            f"trajectories. Recommend standard approval with routine monitoring."
        )

    return {"agent": "Coordinator", "tone": "decision", "text": text}
