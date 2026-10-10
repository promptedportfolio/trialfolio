"""Trial Folio: plan, record, and compare Portfolio123 strategy evidence."""

import logging

# Core functions log, and never print. Without this, Python's last-resort handler would write
# their warnings to stderr whenever the caller configures no logging, as another interface
# running the core may not (R03-AC13). The CLI gives the logger its own handlers.
logging.getLogger(__name__).addHandler(logging.NullHandler())
