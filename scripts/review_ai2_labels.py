"""Launch with python -m streamlit run scripts/review_ai2_labels.py."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from conversation.labeling.ui import main

if __name__ == "__main__":
    main()
