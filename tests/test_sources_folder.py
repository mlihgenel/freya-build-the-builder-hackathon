from fbb.ingest.sources import BIG_CHARS, expand, read_sources


def test_big_data_file_with_text_twin_is_shortened(tmp_path):
    (tmp_path / "BRIEF.md").write_text("brief")
    data = tmp_path / "data"
    data.mkdir()
    (data / "rows.json").write_text('{"x": "' + "a" * (BIG_CHARS * 3) + '"}')
    (data / "rows.md").write_text("| x |\n|---|\n| a |")
    text = read_sources([tmp_path])
    assert len(text) < BIG_CHARS
    assert "the same content is in rows.md" in text


def test_big_file_without_twin_is_cut_with_a_note(tmp_path):
    (tmp_path / "notes.txt").write_text("b" * (BIG_CHARS * 2))
    text = read_sources([tmp_path])
    assert "only the first" in text and len(text) < BIG_CHARS + 1000


def test_top_level_brief_and_readme_come_first(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "README.md").write_text("sub readme")
    (tmp_path / "README.md").write_text("readme")
    (tmp_path / "BRIEF.md").write_text("brief")
    (tmp_path / "a.md").write_text("a")
    order = [str(p.relative_to(tmp_path)) for p in expand([tmp_path])]
    assert order[:2] == ["BRIEF.md", "README.md"]
