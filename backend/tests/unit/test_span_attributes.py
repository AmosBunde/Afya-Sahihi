"""Tests for the canonical span attribute constants."""

from __future__ import annotations

import re

from app.observability.attributes import AfyaAttr, AfyaResource

_SNAKE_DOT = re.compile(r"^[a-z][a-z0-9_.]*[a-z0-9]$")


def test_all_afya_attrs_follow_snake_dot_naming() -> None:
    """Every AfyaAttr value is lowercase, dot-delimited, starts with a letter."""
    for name, value in vars(AfyaAttr).items():
        if name.startswith("_"):
            continue
        assert isinstance(value, str)
        assert _SNAKE_DOT.match(value), f"{name}={value!r} is not snake_dot"


def test_all_afya_attrs_are_unique() -> None:
    values = [v for k, v in vars(AfyaAttr).items() if not k.startswith("_")]
    assert len(values) == len(set(values)), "duplicate AfyaAttr value"


def test_resource_constants_are_valid() -> None:
    # OTel semantic conventions for resource attributes are lowercase
    # dot-delimited; SERVICE_NAME === 'service.name'.
    assert AfyaResource.SERVICE_NAME == "service.name"
    assert AfyaResource.SERVICE_VERSION == "service.version"
    assert AfyaResource.DEPLOYMENT_ENV == "deployment.environment"
    assert AfyaResource.GIT_SHA.startswith("afya_sahihi.")
