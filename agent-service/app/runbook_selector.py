"""Runbook Selector: decides which runbooks the SQL generator needs.

Pipeline step: R. It updates the state after step 1 and after step 2.
It loads the full runbook text only when step 5 needs it, to keep the LLM context small.
"""

from app.models import PipelineState


def update_runbooks(state: PipelineState, candidates: list[str]) -> None:
    """Add runbook candidates to the state. Set needs_runbook and relevant_runbooks.

    What it must do:
        Keep only names of runbooks that exist. Remove duplicates. Keep the order.

    Example:
        update_runbooks(state, ["active_customer"])
        state.needs_runbook == True; state.relevant_runbooks == ["active_customer"]
    """
    raise NotImplementedError(
        "The Runbook Selector (step R) is not implemented yet. See the roadmap in README.md."
    )


def load_runbook_texts(state: PipelineState) -> list[str]:
    """Return the full text of each relevant runbook. Call it only right before step 5."""
    raise NotImplementedError(
        "The Runbook Selector (step R) is not implemented yet. See the roadmap in README.md."
    )
