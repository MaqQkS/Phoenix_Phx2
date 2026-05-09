"""AlertDispatcher placeholder."""

from PHX2.config.settings import DispatchMode


class AlertDispatcher:
    """Future dispatch boundary.

    Stage 2 does not send Telegram or Discord messages.
    """

    default_mode = DispatchMode.DISABLED
