import sys

if sys.version_info < (3, 10):
    sys.exit("Tandem requires Python 3.10 or newer; run -m tandem_bridge with an absolute Python 3.10+ interpreter path.")

from .tandem import cli

if __name__ == "__main__":
    cli()
