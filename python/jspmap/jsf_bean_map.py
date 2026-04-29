"""JsfBeanResolver — parses faces-config.xml into a managed-bean registry."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from jspmap.protocols import BeanInfo


def _local(tag: str) -> str:
    """Strip XML namespace from a tag name."""
    return tag.split("}")[-1] if "}" in tag else tag


class JsfBeanResolver:
    """Implements BeanResolver for JSF faces-config.xml managed-bean registration."""

    def resolve(self, config_path: Path) -> dict[str, BeanInfo]:
        root = ET.parse(config_path).getroot()
        return dict(
            filter(
                None,
                (
                    _parse_bean(elem)
                    for elem in root.iter()
                    if _local(elem.tag) == "managed-bean"
                ),
            )
        )


def _child_text(elem: ET.Element, local_name: str) -> str:
    return next(
        (
            (child.text or "").strip()
            for child in elem
            if _local(child.tag) == local_name
        ),
        "",
    )


def _parse_bean(elem: ET.Element) -> tuple[str, BeanInfo] | None:
    name = _child_text(elem, "managed-bean-name")
    fqcn = _child_text(elem, "managed-bean-class")
    scope = _child_text(elem, "managed-bean-scope")
    if not fqcn:
        print(f"Warning: bean '{name}' has no class element, skipping", file=sys.stderr)
        return None
    return name, BeanInfo(name=name, fqcn=fqcn, scope=scope)
