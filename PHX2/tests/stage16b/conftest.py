"""Stage 16B pytest configuration.

IMPORTANT -- Windows ACL workaround:

Every Stage 16B test run MUST be invoked with a fresh ``--basetemp`` path,
e.g.::

    py -3 -m pytest -q --basetemp=./.pytest_basetmp_stage16b_p1 PHX2/tests/stage16b/
    py -3 -m pytest -q --basetemp=./.pytest_basetmp_stage16b_p2 PHX2/tests/stage16b/

This mirrors the established Stage 16A workaround: pytest's default tmp
directory accumulates restrictive ACLs from prior runs that even
``Remove-Item -Force`` cannot always clear. Each Stage 16B phase uses a
distinct ``--basetemp`` path so the run starts on a clean slate.

This file deliberately does NOT register a session-level basetmp hook or
mutate pytest config -- a global hook risks bleeding into the rest of
the PHX2 suite. Manual ``--basetemp`` selection per-invocation is the
locked convention.
"""
