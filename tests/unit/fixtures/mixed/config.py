"""Named so the analyser reads it as configuration, which is the point of it here.

A configuration module importing another module produces a CONFIGURES edge beside the
IMPORTS one. That derivation shares a loop with the TESTS derivation, and TESTS is covered
by three fixtures while CONFIGURES was covered by none.
"""

from pkg.adapter import BATCH_SIZE
from pkg.ports import Feed

DEFAULT_BATCH = BATCH_SIZE
FEED: Feed | None = None
