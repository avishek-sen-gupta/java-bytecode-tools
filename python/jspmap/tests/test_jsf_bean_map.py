"""Tests for JsfBeanResolver."""

import textwrap

import pytest

from jspmap.jsf_bean_map import JsfBeanResolver
from jspmap.protocols import BeanInfo

FACES_CONFIG_BASIC = textwrap.dedent("""\
    <?xml version="1.0"?>
    <faces-config>
      <managed-bean>
        <managed-bean-name>orderAction</managed-bean-name>
        <managed-bean-class>com.example.web.OrderAction</managed-bean-class>
        <managed-bean-scope>session</managed-bean-scope>
      </managed-bean>
      <managed-bean>
        <managed-bean-name>userBean</managed-bean-name>
        <managed-bean-class>com.example.web.UserBean</managed-bean-class>
        <managed-bean-scope>request</managed-bean-scope>
      </managed-bean>
    </faces-config>
""")

FACES_CONFIG_MISSING_CLASS = textwrap.dedent("""\
    <?xml version="1.0"?>
    <faces-config>
      <managed-bean>
        <managed-bean-name>broken</managed-bean-name>
        <managed-bean-class></managed-bean-class>
        <managed-bean-scope>request</managed-bean-scope>
      </managed-bean>
      <managed-bean>
        <managed-bean-name>orderAction</managed-bean-name>
        <managed-bean-class>com.example.web.OrderAction</managed-bean-class>
        <managed-bean-scope>session</managed-bean-scope>
      </managed-bean>
    </faces-config>
""")

FACES_CONFIG_NAMESPACED = textwrap.dedent("""\
    <?xml version="1.0"?>
    <faces-config xmlns="http://java.sun.com/xml/ns/javaee">
      <managed-bean>
        <managed-bean-name>orderAction</managed-bean-name>
        <managed-bean-class>com.example.web.OrderAction</managed-bean-class>
        <managed-bean-scope>session</managed-bean-scope>
      </managed-bean>
    </faces-config>
""")


@pytest.fixture()
def resolver():
    return JsfBeanResolver()


class TestJsfBeanResolverBasic:
    def test_parses_two_beans(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_BASIC)
        result = resolver.resolve(config)
        assert set(result.keys()) == {"orderAction", "userBean"}

    def test_bean_name_correct(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_BASIC)
        bean = resolver.resolve(config)["orderAction"]
        assert bean.name == "orderAction"

    def test_bean_fqcn_correct(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_BASIC)
        bean = resolver.resolve(config)["orderAction"]
        assert bean.fqcn == "com.example.web.OrderAction"

    def test_bean_scope_correct(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_BASIC)
        bean = resolver.resolve(config)["orderAction"]
        assert bean.scope == "session"

    def test_returns_frozen_bean_info(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_BASIC)
        bean = resolver.resolve(config)["orderAction"]
        assert isinstance(bean, BeanInfo)

    def test_skips_bean_with_empty_class(self, resolver, tmp_path, capsys):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_MISSING_CLASS)
        result = resolver.resolve(config)
        assert "broken" not in result
        assert "orderAction" in result
        captured = capsys.readouterr()
        assert "broken" in captured.err

    def test_parses_namespaced_xml(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_NAMESPACED)
        result = resolver.resolve(config)
        assert "orderAction" in result
        assert result["orderAction"].fqcn == "com.example.web.OrderAction"
