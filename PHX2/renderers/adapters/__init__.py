"""Output adapters that consume :class:`PHX2.renderers.rendered_alert.RenderedAlert`.

8A shipped :class:`PHX2.renderers.adapters.plain_text.PlainTextAdapter`. 8C
adds :class:`PHX2.renderers.adapters.discord.DiscordEmbedAdapter` alongside
it, again without modifying the renderer or :class:`RenderedAlert`.
"""

from PHX2.renderers.adapters.discord import DiscordEmbedAdapter
from PHX2.renderers.adapters.plain_text import PlainTextAdapter

__all__ = ["DiscordEmbedAdapter", "PlainTextAdapter"]
