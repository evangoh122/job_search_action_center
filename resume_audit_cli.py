from __future__ import annotations

import argparse
import json

from apply.ats_resume_audit import audit_docx


def main() -> None:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Audit a DOCX resume for deterministic ATS parsing risks."
    )
    parser.add_argument("resume", help="Path to the DOCX resume")
    parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Required keyword to check; repeat for multiple keywords",
    )
    args = parser.parse_args()
    print(json.dumps(audit_docx(args.resume, args.keyword).model_dump(), indent=2))


if __name__ == "__main__":
    main()
