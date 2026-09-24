from __future__ import annotations

import json
from typing import Any, Literal, TypedDict, TypeVar, cast

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from incident_commander.models import IncidentInput, IncidentReport, Severity


class InvestigationState(TypedDict, total=False):
    incident: dict[str, Any]
    severity: Severity
    triage_rationale: str
    evidence: list[str]
    recommendations: list[str]
    timeline: list[str]
    agents_run: list[str]
    probable_root_cause: str
    confidence: float
    summary: str


class TriageDecision(BaseModel):
    severity: Severity
    rationale: str


class RootCauseDecision(BaseModel):
    probable_root_cause: str
    confidence: float = Field(ge=0, le=1)


class CommanderDecision(BaseModel):
    summary: str
    recommendations: list[str]


DecisionT = TypeVar("DecisionT", bound=BaseModel)


class AgentReasoner:
    def __init__(self, mode: str, model: str) -> None:
        if mode not in {"deterministic", "openai"}:
            raise ValueError("LLM_MODE must be 'deterministic' or 'openai'")
        self.mode = mode
        self.model = model
        self._llm = ChatOpenAI(model=model, temperature=0) if mode == "openai" else None

    def structured(self, schema: type[DecisionT], role: str, payload: dict[str, Any]) -> DecisionT:
        if self._llm is None:
            raise RuntimeError("structured reasoning is available only in openai mode")
        prompt = (
            f"You are the {role} in a read-only cloud incident investigation. "
            "Use only supplied evidence. Do not claim remediation was executed. "
            "Return the requested structured output.\n\n" + json.dumps(payload, default=str)
        )
        result = self._llm.with_structured_output(schema).invoke(prompt)
        return cast(DecisionT, result)


class IncidentWorkflow:
    def __init__(self, graph: Any) -> None:
        self.graph = graph

    def analyze(self, incident: IncidentInput) -> IncidentReport:
        state: InvestigationState = {
            "incident": incident.model_dump(mode="json"),
            "evidence": [],
            "recommendations": [],
            "timeline": [],
            "agents_run": [],
        }
        result = self.graph.invoke(state)
        return IncidentReport(
            incident_id=incident.incident_id,
            service=incident.service,
            status="completed",
            severity=result["severity"],
            summary=result["summary"],
            probable_root_cause=result["probable_root_cause"],
            confidence=result["confidence"],
            evidence=result["evidence"],
            recommendations=result["recommendations"],
            timeline=result["timeline"],
            agents_run=result["agents_run"],
            requires_human_approval=True,
        )


def _append(
    state: InvestigationState,
    key: Literal["evidence", "recommendations", "timeline", "agents_run"],
    value: str,
) -> list[str]:
    return [*state.get(key, []), value]


def _deterministic_severity(incident: dict[str, Any]) -> tuple[Severity, str]:
    metrics = incident.get("metrics", {})
    error_rate = float(metrics.get("error_rate", 0))
    saturation = max(
        float(metrics.get("memory_percent", 0)),
        float(metrics.get("cpu_percent", 0)),
        float(metrics.get("db_connections_percent", 0)),
    )
    if error_rate >= 0.2 or saturation >= 95:
        return "critical", "User impact or resource saturation crossed a critical threshold."
    if error_rate >= 0.1 or saturation >= 85:
        return "high", "Signals indicate substantial degradation."
    if error_rate >= 0.03 or saturation >= 75:
        return "medium", "Signals indicate measurable but contained degradation."
    return "low", "Available signals indicate limited impact."


def build_workflow(
    llm_mode: str = "deterministic", openai_model: str = "gpt-4o-mini"
) -> IncidentWorkflow:
    reasoner = AgentReasoner(llm_mode, openai_model)

    def triage(state: InvestigationState) -> InvestigationState:
        incident = state["incident"]
        if reasoner.mode == "openai":
            decision = reasoner.structured(TriageDecision, "triage agent", incident)
            assert isinstance(decision, TriageDecision)
            severity, rationale = decision.severity, decision.rationale
        else:
            severity, rationale = _deterministic_severity(incident)
        return {
            "severity": severity,
            "triage_rationale": rationale,
            "agents_run": _append(state, "agents_run", "triage"),
            "timeline": _append(state, "timeline", f"Triage classified impact as {severity}."),
        }

    def metrics(state: InvestigationState) -> InvestigationState:
        evidence = list(state.get("evidence", []))
        for name, value in state["incident"].get("metrics", {}).items():
            evidence.append(f"metric {name}={value:g}")
        return {
            "evidence": evidence,
            "agents_run": _append(state, "agents_run", "metrics"),
            "timeline": _append(state, "timeline", "Metrics agent inspected supplied telemetry."),
        }

    def logs(state: InvestigationState) -> InvestigationState:
        evidence = [*state.get("evidence", []), *state["incident"].get("logs", [])]
        return {
            "evidence": evidence,
            "agents_run": _append(state, "agents_run", "logs"),
            "timeline": _append(state, "timeline", "Logs agent extracted relevant events."),
        }

    def root_cause(state: InvestigationState) -> InvestigationState:
        payload = {"incident": state["incident"], "evidence": state.get("evidence", [])}
        if reasoner.mode == "openai":
            decision = reasoner.structured(RootCauseDecision, "root-cause agent", payload)
            assert isinstance(decision, RootCauseDecision)
            cause, confidence = decision.probable_root_cause, decision.confidence
        else:
            text = json.dumps(payload).lower()
            if "oomkilled" in text or "memory" in text:
                cause, confidence = "A memory leak exhausted the container memory limit.", 0.92
            elif "release" in text or "version=" in text or "deployment" in text:
                cause, confidence = "A recent application deployment introduced the errors.", 0.88
            elif "connection pool" in text or "db_connections" in text:
                cause, confidence = "Database connection pool saturation blocked new work.", 0.9
            elif "latency" in text or "timeout" in text:
                cause, confidence = (
                    "An upstream dependency or capacity constraint increased latency.",
                    0.65,
                )
            else:
                cause, confidence = (
                    "The supplied evidence is insufficient for a specific root cause.",
                    0.35,
                )
        return {
            "probable_root_cause": cause,
            "confidence": confidence,
            "agents_run": _append(state, "agents_run", "root_cause"),
            "timeline": _append(
                state, "timeline", "Root-cause agent ranked an evidence-based hypothesis."
            ),
        }

    def runbook(state: InvestigationState) -> InvestigationState:
        cause = state["probable_root_cause"].lower()
        if "memory" in cause:
            actions = [
                "Review heap and allocation telemetry for the affected version.",
                "Request approval to roll back or increase limits while the leak is fixed.",
            ]
        elif "deployment" in cause:
            actions = [
                "Compare the failing release with the last known-good version.",
                "Request approval for a controlled rollback after validating blast radius.",
            ]
        elif "connection" in cause:
            actions = [
                "Inspect slow queries and connection checkout duration.",
                "Request approval before changing pool or database capacity.",
            ]
        else:
            actions = [
                "Collect dependency traces and compare them with the healthy baseline.",
                "Request human review before making any production change.",
            ]
        return {
            "recommendations": actions,
            "agents_run": _append(state, "agents_run", "runbook"),
            "timeline": _append(
                state, "timeline", "Runbook agent prepared approval-gated next steps."
            ),
        }

    def commander(state: InvestigationState) -> InvestigationState:
        payload = {
            "severity": state["severity"],
            "root_cause": state["probable_root_cause"],
            "confidence": state["confidence"],
            "evidence": state["evidence"],
            "recommendations": state["recommendations"],
        }
        if reasoner.mode == "openai":
            decision = reasoner.structured(CommanderDecision, "incident commander agent", payload)
            assert isinstance(decision, CommanderDecision)
            summary = decision.summary
            recommendations = decision.recommendations
        else:
            summary = (
                f"{state['severity'].title()} incident: {state['probable_root_cause']} "
                f"Confidence {state['confidence']:.0%}."
            )
            recommendations = state["recommendations"]
        return {
            "summary": summary,
            "recommendations": recommendations,
            "agents_run": _append(state, "agents_run", "commander"),
            "timeline": _append(
                state, "timeline", "Incident commander assembled the final report."
            ),
        }

    def route_after_triage(state: InvestigationState) -> Literal["metrics", "logs"]:
        return "metrics" if state["severity"] in {"critical", "high"} else "logs"

    def route_after_first_signal(
        state: InvestigationState,
    ) -> Literal["metrics", "logs", "root_cause"]:
        agents = state["agents_run"]
        if agents[-1] == "metrics" and "logs" not in agents:
            return "logs"
        if agents[-1] == "logs" and "metrics" not in agents:
            return "metrics"
        return "root_cause"

    graph = StateGraph(InvestigationState)
    graph.add_node("triage", triage)
    graph.add_node("metrics", metrics)
    graph.add_node("logs", logs)
    graph.add_node("root_cause", root_cause)
    graph.add_node("runbook", runbook)
    graph.add_node("commander", commander)
    graph.add_edge(START, "triage")
    graph.add_conditional_edges("triage", route_after_triage)
    graph.add_conditional_edges("metrics", route_after_first_signal)
    graph.add_conditional_edges("logs", route_after_first_signal)
    graph.add_edge("root_cause", "runbook")
    graph.add_edge("runbook", "commander")
    graph.add_edge("commander", END)
    return IncidentWorkflow(graph.compile())
