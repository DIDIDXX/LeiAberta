"""Queue a bounded batch of Senate catalog entries for full-text capture."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.jobs import queue_senado_text_batch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100, help="Máximo de normas para enfileirar (até 500).")
    args = parser.parse_args()
    print(json.dumps(queue_senado_text_batch(limit=args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
