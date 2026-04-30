#!/usr/bin/env python3
"""Regenerate a SCIP index from one or more Java source trees.

Run whenever source files change.

Config file format (key=value, keys may repeat for arrays):
    src=module-a/src/main/java
    src=module-b/src/main/java
    classes=module-a/target/classes
    classes=module-b/target/classes
    output=target/index.scip

CLI flags override the config file on a per-key basis.
First --classes dir is the javac -d output; all are joined as -cp.
"""

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReindexConfig:
    srcs: tuple[Path, ...]
    classes: tuple[Path, ...]
    output: Path


def parse_config_file(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"src": [], "classes": [], "output": []}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        if key in result:
            result[key].append(value)
    return result


def build_config(args: argparse.Namespace) -> ReindexConfig:
    if args.config:
        cfg = parse_config_file(Path(args.config))
        srcs = [Path(p) for p in cfg["src"]]
        classes = [Path(p) for p in cfg["classes"]]
        output_str = cfg["output"][0] if cfg["output"] else ""
    else:
        srcs = [Path(p) for p in args.src]
        classes = [Path(p) for p in args.classes]
        output_str = args.output or ""

    if not srcs or not classes or not output_str:
        print(
            "error: --src, --classes, and --output are all required (via CLI or config)",
            file=sys.stderr,
        )
        sys.exit(1)

    return ReindexConfig(
        srcs=tuple(srcs),
        classes=tuple(classes),
        output=Path(output_str),
    )


def collect_java_files(srcs: tuple[Path, ...]) -> list[Path]:
    return [f for src in srcs for f in sorted(src.rglob("*.java"))]


def sourcepath(srcs: tuple[Path, ...]) -> str:
    return ":".join(str(s) for s in srcs)


def classpath(classes: tuple[Path, ...]) -> str:
    return ":".join(str(c) for c in classes)


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def compile_sources(config: ReindexConfig, java_files: list[Path]) -> None:
    out_dir = config.classes[0]
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Compiling sources ({len(java_files)} files, output -> {out_dir})...")
    run(
        [
            "javac",
            "-g",
            "-sourcepath",
            sourcepath(config.srcs),
            "-cp",
            classpath(config.classes),
            "-d",
            str(out_dir),
            *[str(f) for f in java_files],
        ]
    )


def index_sources(config: ReindexConfig, java_files: list[Path]) -> None:
    out_dir = config.classes[0]
    print("Indexing with scip-java...")
    run(
        [
            "scip-java",
            "index",
            "--build-tool=javac",
            f"--output={config.output}",
            "--",
            "javac",
            "-g",
            "-sourcepath",
            sourcepath(config.srcs),
            "-cp",
            classpath(config.classes),
            "-d",
            str(out_dir),
            *[str(f) for f in java_files],
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--config",
        metavar="FILE",
        help="config file (mutually exclusive with --src/--classes/--output)",
    )
    mode.add_argument(
        "--src",
        metavar="DIR",
        action="append",
        dest="src",
        default=None,
        help="source root (repeatable)",
    )
    parser.add_argument(
        "--classes",
        metavar="DIR",
        action="append",
        default=[],
        help="classes dir (repeatable); required with --src",
    )
    parser.add_argument(
        "--output", metavar="FILE", help="output index.scip path; required with --src"
    )

    args = parser.parse_args()
    if args.src is not None and (not args.classes or not args.output):
        parser.error("--classes and --output are required when using --src")

    config = build_config(args)
    java_files = collect_java_files(config.srcs)

    compile_sources(config, java_files)
    index_sources(config, java_files)
    print(f"Done: {config.output}")


if __name__ == "__main__":
    main()
