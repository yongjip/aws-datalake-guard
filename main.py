"""Compatibility entry point for local CLI execution.

The primary installed command is ``lfguard``.
"""

from lakeformation_guard.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
