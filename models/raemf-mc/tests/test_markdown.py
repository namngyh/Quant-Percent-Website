from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _local_images(markdown: str) -> list[str]:
    images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", markdown)
    return [image for image in images if not image.startswith(("http://", "https://"))]


def _assert_markdown_structure(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert len(lines) > 20, f"{path} appears collapsed into too few lines"
    fences = [line for line in lines if line.strip().startswith("```")]
    assert len(fences) % 2 == 0, f"Unclosed code fence in {path}"
    for index, line in enumerate(lines[:-1]):
        if line.startswith("| ") and (index == 0 or not lines[index - 1].startswith("| ")):
            assert re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", lines[index + 1]), f"Malformed Markdown table near line {index + 1}"


def test_readme_markdown_mermaid_tables_and_images_are_valid():
    path = ROOT / "README.md"
    content = path.read_text(encoding="utf-8")
    _assert_markdown_structure(path)
    assert "```mermaid\nflowchart LR\n" in content
    assert content.count("<!-- RESULTS_START -->") == 1
    assert content.count("<!-- RESULTS_END -->") == 1
    assert "\\(" not in content and "\\)" not in content, "Use GitHub-compatible $...$ for inline math"
    assert "CPU downside experiment" not in content
    assert "RAEMF_VB_MC_REPORT.md" in content
    images = _local_images(content)
    assert len(images) >= 4
    for image in images:
        assert (ROOT / image).exists(), f"Broken README image path: {image}"


def test_root_vb_report_has_train_validation_test_and_risk_sections():
    path = ROOT / "RAEMF_VB_MC_REPORT.md"
    _assert_markdown_structure(path)
    content = path.read_text(encoding="utf-8")
    for section in ["TRAIN", "VALID", "TEST", "Xác suất bốn regime", "Quản trị rủi ro"]:
        assert section in content
    for image in _local_images(content):
        assert (ROOT / image).exists(), f"Broken VB report image path: {image}"


def test_report_references_every_figure_and_comments_after_each_image():
    path = ROOT / "outputs/latest/report.md"
    content = path.read_text(encoding="utf-8")
    _assert_markdown_structure(path)
    referenced = set(_local_images(content))
    actual = {f"figures/{path.name}" for path in (ROOT / "outputs/latest/figures").glob("*.png")}
    assert actual
    assert actual <= referenced
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("!["):
            window = "\n".join(lines[index + 1 : index + 10])
            assert "**Nhận xét định lượng:**" in window, f"Missing figure interpretation after: {line}"


def test_current_monitor_report_and_readme_images_are_valid():
    report = ROOT / "outputs/current_monitor/report_for_nonspecialists.md"
    if not report.exists():
        return
    _assert_markdown_structure(report)
    content = report.read_text(encoding="utf-8")
    images = _local_images(content)
    assert len(images) == 4
    for image in images:
        assert (report.parent / image).exists(), f"Broken current-monitor report image: {image}"


def test_oos_distribution_report_references_generated_figures_and_comments():
    path = ROOT / "docs" / "distribution_oos_benchmark.md"
    content = path.read_text(encoding="utf-8")
    _assert_markdown_structure(path)
    images = _local_images(content)
    actual = {
        f"../outputs/distribution_oos_laptop/figures/{figure.name}"
        for figure in (ROOT / "outputs" / "distribution_oos_laptop" / "figures").glob("*.png")
    }
    assert len(actual) == 9
    assert set(images) == actual
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("!["):
            window = "\n".join(lines[index + 1 : index + 7])
            assert "**Nhận xét định lượng:**" in window, f"Missing OOS figure interpretation after: {line}"
