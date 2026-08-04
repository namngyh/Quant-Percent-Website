"""Update only the generated README results region."""

from __future__ import annotations

import argparse

from raemf_mc.reporting.report_builder import update_readme_results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", default="outputs/latest")
    parser.add_argument("--readme", default="README.md")
    args = parser.parse_args()
    update_readme_results(args.readme, args.run_dir)


if __name__ == "__main__":
    main()
