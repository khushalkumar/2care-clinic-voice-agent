import argparse
from pathlib import Path

from app.evaluation.report import load_measurements, render_markdown_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Render a redacted, per-language voice evaluation report from JSONL measurements."
        )
    )
    parser.add_argument("input", type=Path, help="JSONL measurements with no PII or recordings")
    parser.add_argument("--output", type=Path, required=True, help="Markdown report output path")
    args = parser.parse_args()
    args.output.write_text(render_markdown_report(load_measurements(args.input)), encoding="utf-8")


if __name__ == "__main__":
    main()
