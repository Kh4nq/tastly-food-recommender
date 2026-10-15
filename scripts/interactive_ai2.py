"""Run from any working directory: python scripts/interactive_ai2.py."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation.interactive.cli import main


if __name__ == "__main__":
    main()
