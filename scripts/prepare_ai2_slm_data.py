"""Generate, label, validate and queue; stop before human review and export."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from conversation.labeling.cli import main

if __name__ == "__main__":
    raise SystemExit(main("prepare"))
