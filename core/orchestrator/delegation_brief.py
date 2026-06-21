"""
Delegation Brief Generator.
Produces a structured XML handoff document acting as the "Office Meeting" 
where the Orchestrator details the specs for sub-agents to follow.
"""

DELEGATION_BRIEF_TEMPLATE = """
<project_brief>

  <meeting_summary>
    <task_original>{original_user_request}</task_original>
    <decomposition_rationale>
      {rationale}
    </decomposition_rationale>
    <delivery_strategy>
      {strategy}
    </delivery_strategy>
  </meeting_summary>

  <project_context>
    <tech_stack>
      {tech_stack}
    </tech_stack>
    <existing_codebase>
      {codebase_context}
    </existing_codebase>
    <design_system>
      {design_system}
    </design_system>
    <conventions>
      {conventions}
    </conventions>
  </project_context>

  <agent_assignments>
    {assignments_xml}
  </agent_assignments>

  <coordination_rules>
    All agents write status to AGENTS.md after every completed subtask.
    If an agent requires API contracts, they must read the ## Exposes section of AGENTS.md.
    If any agent is BLOCKED, they must report back so the Chief Orchestrator can re-evaluate.
  </coordination_rules>

  <delivery_definition>
    {delivery_criteria}
  </delivery_definition>

</project_brief>
"""

def generate_delegation_brief(
    original_user_request: str,
    rationale: str,
    strategy: str,
    tech_stack: str,
    codebase_context: str,
    design_system: str,
    conventions: str,
    assignments_xml: str,
    delivery_criteria: str
) -> str:
    """Fills out the project delegation brief for downstream agents."""
    return DELEGATION_BRIEF_TEMPLATE.format(
        original_user_request=original_user_request,
        rationale=rationale,
        strategy=strategy,
        tech_stack=tech_stack,
        codebase_context=codebase_context,
        design_system=design_system,
        conventions=conventions,
        assignments_xml=assignments_xml,
        delivery_criteria=delivery_criteria
    )
