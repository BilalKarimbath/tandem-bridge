"""Plugin launcher: requires a project marker or explicit ledger."""
import sys

if sys.version_info < (3, 10):
    sys.exit("Tandem requires Python 3.10 or newer; run tandem.py with an absolute Python 3.10+ interpreter path.")

from pathlib import Path
from tandem_bridge.tandem import *  # Preserve existing import callers.
from tandem_bridge.tandem import cli

if __name__ == "__main__":
    cli()
