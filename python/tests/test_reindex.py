"""Tests for reindex encoding support."""

import textwrap
from pathlib import Path
from unittest.mock import patch, call
import pytest

from reindex import (
    parse_config_file,
    build_config,
    compile_sources,
    index_sources,
    ReindexConfig,
)

# --- parse_config_file ---


def test_config_file_parses_encoding(tmp_path: Path) -> None:
    conf = tmp_path / "reindex.conf"
    conf.write_text(textwrap.dedent("""\
        src=/some/src
        classes=/some/classes
        output=/some/index.scip
        encoding=windows-874
        """))
    result = parse_config_file(conf)
    assert result["encoding"] == ["windows-874"]


def test_config_file_encoding_absent_gives_empty_list(tmp_path: Path) -> None:
    conf = tmp_path / "reindex.conf"
    conf.write_text("src=/s\nclasses=/c\noutput=/o\n")
    result = parse_config_file(conf)
    assert result["encoding"] == []


# --- compile_sources ---


def _config(encoding: str = "") -> ReindexConfig:
    return ReindexConfig(
        srcs=(Path("/src"),),
        classes=(Path("/cls"),),
        output=Path("/out/index.scip"),
        encoding=encoding,
    )


def test_encoding_flag_included_in_compile_when_set(tmp_path: Path) -> None:
    config = _config(encoding="windows-874")
    java_files = [tmp_path / "Foo.java"]
    java_files[0].touch()

    with patch("reindex.run") as mock_run, patch("reindex.Path.mkdir"):
        compile_sources(config, java_files)

    args = mock_run.call_args[0][0]
    assert "-encoding" in args
    idx = args.index("-encoding")
    assert args[idx + 1] == "windows-874"


def test_encoding_flag_omitted_from_compile_when_empty(tmp_path: Path) -> None:
    config = _config(encoding="")
    java_files = [tmp_path / "Foo.java"]
    java_files[0].touch()

    with patch("reindex.run") as mock_run, patch("reindex.Path.mkdir"):
        compile_sources(config, java_files)

    args = mock_run.call_args[0][0]
    assert "-encoding" not in args


# --- index_sources ---


def test_encoding_flag_included_in_index_when_set(tmp_path: Path) -> None:
    config = _config(encoding="windows-874")

    with patch("reindex.run") as mock_run:
        index_sources(config, [])

    args = mock_run.call_args[0][0]
    assert "-encoding" in args
    idx = args.index("-encoding")
    assert args[idx + 1] == "windows-874"


def test_encoding_flag_omitted_from_index_when_empty(tmp_path: Path) -> None:
    config = _config(encoding="")

    with patch("reindex.run") as mock_run:
        index_sources(config, [])

    args = mock_run.call_args[0][0]
    assert "-encoding" not in args
