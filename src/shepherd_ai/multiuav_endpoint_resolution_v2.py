"""Resolve concrete MultiUAV command URLs for a separate post-hoc diagnostic."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from shepherd_ai.multiuav_context import validate_agent_visible_context
from shepherd_ai.multiuav_grounding_validator import ENDPOINT_SPECS
from shepherd_ai.multiuav_plan_contract import ApiCall, StrictModelOutput


_CONCRETE_COMMAND = re.compile(
    r"/drones/([A-Za-z0-9_-]+)/command/([a-z_]+)\Z"
)


@dataclass(frozen=True)
class ResolvedOutput:
    output: StrictModelOutput
    resolved_calls: int


def resolve_concrete_endpoints(
    output: StrictModelOutput,
    context: Mapping[str, Any],
) -> ResolvedOutput:
    """Map a visible drone URL to its catalog template without changing intent."""

    validate_agent_visible_context(context)
    visible_ids = {str(drone["id"]) for drone in context["drones"]}
    resolved: list[ApiCall] = []
    resolved_count = 0
    for call in output.api_plan:
        match = _CONCRETE_COMMAND.fullmatch(call.endpoint)
        if match is None:
            resolved.append(call)
            continue
        drone_id, command = match.groups()
        template = f"/drones/{{id}}/command/{command}"
        parameter_id = call.parameters.get("id")
        if (
            template not in ENDPOINT_SPECS
            or drone_id not in visible_ids
            or (parameter_id is not None and parameter_id != drone_id)
        ):
            resolved.append(call)
            continue
        parameters = dict(call.parameters)
        parameters.setdefault("id", drone_id)
        resolved.append(ApiCall(endpoint=template, parameters=parameters))
        resolved_count += 1
    return ResolvedOutput(
        output=StrictModelOutput(
            decision=output.decision,
            reason=output.reason,
            clarification_question=output.clarification_question,
            api_plan=tuple(resolved),
        ),
        resolved_calls=resolved_count,
    )
