"""Exploratory, agent-visible safety screen and plan release for the follow-up."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from shepherd_ai.multiuav_context import validate_agent_visible_context
from shepherd_ai.multiuav_endpoint_resolution_v2 import resolve_concrete_endpoints
from shepherd_ai.multiuav_grounding_validator import validate_grounded_plan
from shepherd_ai.multiuav_plan_contract import StrictModelOutput
from shepherd_ai.multiuav_plan_contract import parse_strict_model_output
from shepherd_ai.multiuav_prompts import PromptRequest, build_first_call_request
from shepherd_ai.multiuav_runner import GenerationResult, ModelBackend
from shepherd_ai.multiuav_recoverability import (
    assess_resource_conflict,
    extract_explicit_drone_references,
)


_ASSIGNED_UAV = re.compile(r"\bassigned UAV ([A-Z])\b", re.IGNORECASE)
_THRESHOLD_PLACEHOLDERS = re.compile(
    r"\b(?:the required portion of the target area|"
    r"the required level of area coverage|the required threshold)\b",
    re.IGNORECASE,
)
_RESTORED_PERCENTAGE = re.compile(r"\s*\(\s*\d+(?:\.\d+)?\s*%\s*\)")
_DRONE_COUNT = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)"
    r"[\s-]+drones?\b",
    re.IGNORECASE,
)
_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


@dataclass(frozen=True)
class CandidateReport:
    decision: str
    reason_code: str
    release_authorized: bool
    resolved_calls: int
    postplan_stage: str | None


@dataclass(frozen=True)
class CandidateRun:
    """One exploratory model attempt, retaining the raw generation for audit."""

    report: CandidateReport
    request: PromptRequest | None
    generation: GenerationResult | None
    parse_status: str | None
    parse_error_code: str | None


def run_candidate(
    context: Mapping[str, Any], backend: ModelBackend,
) -> CandidateRun:
    """Screen visible evidence, then try one plan without changing M1--M4."""

    decision, reason = screen_visible_request(context)
    if decision != "EXECUTE":
        return CandidateRun(
            CandidateReport(decision, reason, False, 0, None),
            None, None, None, None,
        )

    request = build_first_call_request("M1_monolithic", context)
    try:
        generation = backend.generate(request)
    except Exception as error:
        generation = GenerationResult(
            raw_output="", generation_status="BACKEND_ERROR",
            error_type=type(error).__name__, error_message=str(error),
        )
    if not isinstance(generation, GenerationResult):
        generation = GenerationResult(
            raw_output="", generation_status="BACKEND_PROTOCOL_ERROR",
            error_type="TypeError",
            error_message="backend.generate must return GenerationResult",
        )
    if not isinstance(generation.raw_output, str):
        generation = GenerationResult(
            raw_output="", generation_status="BACKEND_PROTOCOL_ERROR",
            error_type="TypeError",
            error_message="generation raw_output must be text",
        )
    if generation.generation_status != "GENERATED":
        return CandidateRun(
            CandidateReport("BLOCK", "generation_failed", False, 0, None),
            request, generation, None, None,
        )

    parsed = parse_strict_model_output(generation.raw_output)
    if parsed.parsed is None:
        report = CandidateReport("BLOCK", "model_output_parse_error", False, 0, None)
    else:
        report = evaluate_candidate(parsed.parsed, context)
    return CandidateRun(
        report, request, generation, parsed.parse_status, parsed.error_code,
    )


def screen_visible_request(context: Mapping[str, Any]) -> tuple[str, str]:
    """Conservatively screen known unresolved references without private labels."""

    validate_agent_visible_context(context)
    instruction = str(context["instruction"])
    references = extract_explicit_drone_references(instruction)
    counts = [
        _COUNT_WORDS.get(match.group(1).lower()) or int(match.group(1))
        for match in _DRONE_COUNT.finditer(instruction)
    ]
    conflict = assess_resource_conflict(
        context,
        required_drone_references=references,
        required_count=max(counts, default=0) or (None if references else 1),
    )
    if conflict.block_allowed:
        return "BLOCK", "visible_fleet_conflict"

    for match in _ASSIGNED_UAV.finditer(instruction):
        mapping = re.compile(
            rf"\bassigned UAV {re.escape(match.group(1))}\s*"
            r"\(\s*Drone\s+\d+\s*\)",
            re.IGNORECASE,
        )
        if mapping.search(instruction) is None:
            return "CLARIFY", "unresolved_assigned_uav"
    for match in _THRESHOLD_PLACEHOLDERS.finditer(instruction):
        if _RESTORED_PERCENTAGE.match(instruction, match.end()) is None:
            return "CLARIFY", "unresolved_threshold_reference"
    return "EXECUTE", "visible_request_ready"


def evaluate_candidate(
    output: StrictModelOutput,
    context: Mapping[str, Any],
) -> CandidateReport:
    """Release only a screened, nonempty, grounded plan; do not change M1-M4."""

    decision, reason = screen_visible_request(context)
    if decision != "EXECUTE":
        return CandidateReport(decision, reason, False, 0, None)
    if output.decision != "EXECUTE":
        return CandidateReport(output.decision, "model_nonexecution", False, 0, None)
    if not output.api_plan:
        return CandidateReport("BLOCK", "empty_plan", False, 0, None)
    resolved = resolve_concrete_endpoints(output, context)
    report = validate_grounded_plan(resolved.output, context)
    if not report.valid:
        return CandidateReport(
            "BLOCK", "postplan_rejected", False,
            resolved.resolved_calls, report.containment_stage,
        )
    return CandidateReport(
        "EXECUTE", "grounded_plan", True,
        resolved.resolved_calls, report.containment_stage,
    )
