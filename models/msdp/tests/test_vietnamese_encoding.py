from pathlib import Path


def test_vietnamese_documents_are_valid_utf8_without_mojibake():
    files = [
        Path("README.md"),
        Path("README_VI.md"),
        Path("scripts/update_readme_results.py"),
    ]
    broken_markers = ("\ufffd", "Ã", "Â", "áº", "á»", "Ä‘")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in broken_markers), path
        assert any(word in text for word in ("dự báo", "tiếng Việt", "thực tế")), path
