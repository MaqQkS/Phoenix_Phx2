"""Stage 20 pytest configuration.

IMPORTANT -- Windows ACL workaround (mirrors Stage 16A/16B/17/18/19):

Every Stage 20 test run MUST be invoked with a fresh ``--basetemp``
path, e.g.::

    py -3 -m pytest -q --basetemp=./.pytest_basetmp_stage20_p1a \\
        PHX2/tests/stage20/

The default pytest tmp directory under
``%LOCALAPPDATA%\\Temp\\pytest-of-<user>`` accumulates restrictive
ACLs that even ``Remove-Item -Force`` cannot always clear. Each
sub-phase uses a distinct ``--basetemp`` so the run starts on a
clean slate.

Stage 20.1 scope:
  * Reads Stage 18 + Stage 19 run directories (read-only).
  * Writes no artifacts; tests use synthetic fixtures.
  * Forbidden from importing PHX2.stage17, PHX2.stage18,
    PHX2.stage19. Fixture modules independently duplicate the
    upstream column tuples and label vocabulary.
"""

from __future__ import annotations
