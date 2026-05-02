from enum import StrEnum

from node_types import NodeType


class TestNodeType:
    def test_is_str_enum(self):
        assert issubclass(NodeType, StrEnum)

    def test_java_method_value(self):
        assert NodeType.JAVA_METHOD == "java_method"

    def test_jsp_value(self):
        assert NodeType.JSP == "jsp"

    def test_el_expression_value(self):
        assert NodeType.EL_EXPRESSION == "el_expression"

    def test_usable_as_string(self):
        d = {"node_type": NodeType.JAVA_METHOD}
        assert d["node_type"] == "java_method"
