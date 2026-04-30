"""Tests for reindex encoding, lib_dir, and add_exports support."""

import textwrap
from pathlib import Path
from unittest.mock import patch

from reindex import (
    parse_config_file,
    compile_sources,
    index_sources,
    lib_dir_jars,
    deduplicate_java_files,
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


def _config(encoding: str = "", lib_dirs: tuple[Path, ...] = ()) -> ReindexConfig:
    return ReindexConfig(
        srcs=(Path("/src"),),
        classes=(Path("/cls"),),
        output=Path("/out/index.scip"),
        encoding=encoding,
        lib_dirs=lib_dirs,
        add_exports=(),
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


# --- lib_dir_jars ---


def test_lib_dir_jars_returns_jars_from_directory(tmp_path: Path) -> None:
    (tmp_path / "a.jar").touch()
    (tmp_path / "b.jar").touch()
    (tmp_path / "readme.txt").touch()

    result = lib_dir_jars((tmp_path,))

    jar_names = [p.name for p in result]
    assert "a.jar" in jar_names
    assert "b.jar" in jar_names
    assert "readme.txt" not in jar_names


def test_lib_dir_jars_empty_when_no_lib_dirs() -> None:
    assert lib_dir_jars(()) == []


def test_lib_dir_jars_combines_multiple_directories(tmp_path: Path) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "x.jar").touch()
    (dir_b / "y.jar").touch()

    result = lib_dir_jars((dir_a, dir_b))

    jar_names = [p.name for p in result]
    assert "x.jar" in jar_names
    assert "y.jar" in jar_names


# --- lib_dir JARs appear on -cp in compile and index ---


def test_lib_dir_jars_appear_on_classpath_in_compile(tmp_path: Path) -> None:
    jar = tmp_path / "dep.jar"
    jar.touch()
    config = _config(lib_dirs=(tmp_path,))

    with patch("reindex.run") as mock_run, patch("reindex.Path.mkdir"):
        compile_sources(config, [])

    cp_arg = mock_run.call_args[0][0]
    cp_idx = cp_arg.index("-cp")
    assert str(jar) in cp_arg[cp_idx + 1]


def test_lib_dir_jars_appear_on_classpath_in_index(tmp_path: Path) -> None:
    jar = tmp_path / "dep.jar"
    jar.touch()
    config = _config(lib_dirs=(tmp_path,))

    with patch("reindex.run") as mock_run:
        index_sources(config, [])

    cp_arg = mock_run.call_args[0][0]
    cp_idx = cp_arg.index("-cp")
    assert str(jar) in cp_arg[cp_idx + 1]


# --- config file parses lib_dir ---


def test_config_file_parses_lib_dir(tmp_path: Path) -> None:
    conf = tmp_path / "reindex.conf"
    conf.write_text(textwrap.dedent("""\
        src=/s
        classes=/c
        output=/o
        lib_dir=/some/lib
        lib_dir=/other/lib
        """))
    result = parse_config_file(conf)
    assert result["lib_dir"] == ["/some/lib", "/other/lib"]


# --- deduplicate_java_files ---


def test_unique_files_are_kept(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "com/example").mkdir(parents=True)
    a = src / "com/example/A.java"
    b = src / "com/example/B.java"
    a.touch()
    b.touch()

    result = deduplicate_java_files((src,), [a, b])

    assert result == [a, b]


def test_duplicate_fqcn_across_src_roots_keeps_first(tmp_path: Path) -> None:
    src1 = tmp_path / "mod1/src"
    src2 = tmp_path / "mod2/src"
    (src1 / "com/example").mkdir(parents=True)
    (src2 / "com/example").mkdir(parents=True)
    f1 = src1 / "com/example/Svc.java"
    f2 = src2 / "com/example/Svc.java"
    f1.touch()
    f2.touch()

    result = deduplicate_java_files((src1, src2), [f1, f2])

    assert result == [f1]
    assert f2 not in result


def test_files_from_different_packages_are_both_kept(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "com/a").mkdir(parents=True)
    (src / "com/b").mkdir(parents=True)
    f1 = src / "com/a/Svc.java"
    f2 = src / "com/b/Svc.java"
    f1.touch()
    f2.touch()

    result = deduplicate_java_files((src,), [f1, f2])

    assert f1 in result
    assert f2 in result


# --- add_exports ---

_EXPORT = "java.xml/com.sun.org.apache.xerces.internal.impl.dv.util=ALL-UNNAMED"
_EXPORT2 = "java.base/sun.net.www.protocol.https=ALL-UNNAMED"


def test_config_file_parses_add_exports(tmp_path: Path) -> None:
    conf = tmp_path / "reindex.conf"
    conf.write_text(textwrap.dedent(f"""\
        src=/s
        classes=/c
        output=/o
        add_exports={_EXPORT}
        add_exports={_EXPORT2}
        """))
    result = parse_config_file(conf)
    assert result["add_exports"] == [_EXPORT, _EXPORT2]


def test_config_file_add_exports_absent_gives_empty_list(tmp_path: Path) -> None:
    conf = tmp_path / "reindex.conf"
    conf.write_text("src=/s\nclasses=/c\noutput=/o\n")
    result = parse_config_file(conf)
    assert result["add_exports"] == []


def _config_with_exports(
    add_exports: tuple[str, ...] = (),
) -> ReindexConfig:
    return ReindexConfig(
        srcs=(Path("/src"),),
        classes=(Path("/cls"),),
        output=Path("/out/index.scip"),
        encoding="",
        lib_dirs=(),
        add_exports=add_exports,
    )


def test_add_exports_flags_included_in_compile_when_set(tmp_path: Path) -> None:
    config = _config_with_exports(add_exports=(_EXPORT, _EXPORT2))
    java_files = [tmp_path / "Foo.java"]
    java_files[0].touch()

    with patch("reindex.run") as mock_run, patch("reindex.Path.mkdir"):
        compile_sources(config, java_files)

    args = mock_run.call_args[0][0]
    assert "--add-exports" in args
    exports_in_args = [args[i + 1] for i, a in enumerate(args) if a == "--add-exports"]
    assert _EXPORT in exports_in_args
    assert _EXPORT2 in exports_in_args


def test_add_exports_flags_omitted_from_compile_when_empty(tmp_path: Path) -> None:
    config = _config_with_exports()
    java_files = [tmp_path / "Foo.java"]
    java_files[0].touch()

    with patch("reindex.run") as mock_run, patch("reindex.Path.mkdir"):
        compile_sources(config, java_files)

    args = mock_run.call_args[0][0]
    assert "--add-exports" not in args


def test_add_exports_flags_included_in_index_when_set() -> None:
    config = _config_with_exports(add_exports=(_EXPORT,))

    with patch("reindex.run") as mock_run:
        index_sources(config, [])

    args = mock_run.call_args[0][0]
    assert "--add-exports" in args
    idx = args.index("--add-exports")
    assert args[idx + 1] == _EXPORT


def test_add_exports_flags_omitted_from_index_when_empty() -> None:
    config = _config_with_exports()

    with patch("reindex.run") as mock_run:
        index_sources(config, [])

    args = mock_run.call_args[0][0]
    assert "--add-exports" not in args
