#!/usr/bin/env python3
"""
Script to auto-generate llms.txt from RST documentation files.

This script reads all RST files in the docs directory and concatenates them
into a single llms.txt file for LLM consumption.
"""

from pathlib import Path


def generate_llms_txt(docs_dir: Path, output_file: Path) -> None:
    """
    Generate llms.txt from all RST files in the docs directory.

    Args:
        docs_dir: Path to the docs directory
        output_file: Path where llms.txt should be written
    """
    # Find all RST files, excluding _build directory
    rst_files = []
    for rst_file in docs_dir.rglob("*.rst"):
        # Skip files in _build directory
        if "_build" in rst_file.parts:
            continue
        rst_files.append(rst_file)

    # Sort files for consistent ordering
    # Put index.rst first, then user-guide/index.rst, then alphabetically
    def sort_key(path: Path) -> tuple:
        parts = path.relative_to(docs_dir).parts
        if parts == ("index.rst",):
            return (0, "")
        elif parts == ("user-guide", "index.rst"):
            return (1, "")
        else:
            return (2, str(path))

    rst_files.sort(key=sort_key)

    # Generate the llms.txt content
    output_parts = []
    output_parts.append("# EOS - Experiment Orchestration System Documentation\n\n")

    for rst_file in rst_files:
        # Read the RST file
        try:
            content = rst_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Warning: Could not read {rst_file}: {e}")
            continue

        # Add section header with file path
        relative_path = rst_file.relative_to(docs_dir)
        output_parts.append(f"# File: {relative_path}\n")
        output_parts.append("=" * 80 + "\n\n")

        # Add the RST content as-is
        output_parts.append(content)
        output_parts.append("\n")

    # Write the output file
    output_content = "".join(output_parts)
    output_file.write_text(output_content, encoding="utf-8")
    print(f"Generated {output_file} ({len(output_content):,} bytes)")
    print(f"Processed {len(rst_files)} RST files")


def main():
    """Main entry point for the script."""
    # Determine paths relative to this script
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    docs_dir = project_root / "docs"
    output_file = docs_dir / "_build" / "llms.txt"

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Generate llms.txt
    generate_llms_txt(docs_dir, output_file)


if __name__ == "__main__":
    main()
