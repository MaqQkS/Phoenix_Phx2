"""PreviewPipeline orchestrator.

Wires together the three Stage 8A/8B collaborators:

  alert_decision -> assembler -> rendering context -> renderer -> rendered alert -> dispatcher

The pipeline accepts an :class:`AlertDecision` because it is the orchestrator;
nothing downstream of it does. The pipeline does not catch exceptions from its
collaborators (the engine integration call site catches), and it does not read
the wall clock (callers supply ``as_of_time``).
"""

from datetime import datetime

from PHX2.dispatch.dispatcher import Dispatcher
from PHX2.models import AlertDecision
from PHX2.renderers.alert_renderer import AlertRenderer
from PHX2.renderers.context import RenderingContextAssembler


class PreviewPipeline:
    """Run assemble → render → dispatch for one ``AlertDecision``."""

    def __init__(
        self,
        assembler: RenderingContextAssembler,
        renderer: AlertRenderer,
        dispatcher: Dispatcher,
    ) -> None:
        self._assembler = assembler
        self._renderer = renderer
        self._dispatcher = dispatcher

    def handle(
        self,
        alert_decision: AlertDecision,
        as_of_time: datetime,
        alert_decision_id: int,
    ) -> None:
        """Render and dispatch one decision.

        ``alert_decision_id`` is supplied by the caller (the engine, which
        captures the integer primary key from the just-completed insert). The
        spec keeps :class:`AlertDecision` immutable, so the id is passed
        alongside rather than derived from the dataclass.
        """

        context = self._assembler.assemble(
            alert_decision, as_of_time, alert_decision_id
        )
        rendered = self._renderer.render(context)
        self._dispatcher.dispatch(rendered, alert_decision_id)
