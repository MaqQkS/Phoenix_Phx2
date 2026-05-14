"""Stage 19 pytest configuration.

IMPORTANT -- Windows ACL workaround (mirrors Stage 16A/16B/17/18):

Every Stage 19 test run MUST be invoked with a fresh ``--basetemp``
path, e.g.::

    py -3 -m pytest -q --basetemp=./.pytest_basetmp_stage19_p1_redo \\
        PHX2/tests/stage19/

The default pytest tmp directory under
``%LOCALAPPDATA%\\Temp\\pytest-of-<user>`` accumulates restrictive
ACLs that even ``Remove-Item -Force`` cannot always clear. Each
phase uses a distinct ``--basetemp`` so the run starts on a clean
slate.

Stage 18 input contract:

  * Stage 19 reads a completed Stage 18 output directory plus an
    operator-supplied input CSV (``operator_review_input.csv``).
  * For Phase 19.1 redo no fixtures are exercised: the constants,
    errors, and import-boundary tests are pure module-level
    inspections. Fixtures live in
    ``PHX2.tests.stage19.fixtures.stage18_outputs`` and
    ``PHX2.tests.stage19.fixtures.operator_inputs`` and will be
    wired into shared pytest fixtures in later phases as the
    readers / validators / ledger come online.
  * Fixture modules MUST NOT import ``PHX2.stage17`` or
    ``PHX2.stage18`` (independence from upstream stages).
    Imports of ``PHX2.stage19.*`` are permitted -- Phase 19.2+
    tests legitimately exercise Stage 19's own modules against
    fixture data. The fixture modules in this phase still
    duplicate the upstream contract values locally.
"""

from __future__ import annotations
