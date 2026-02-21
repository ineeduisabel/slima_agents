"""Shared test fixtures."""

from __future__ import annotations

import pytest

from slima_agents.agents.context import WorldContext


@pytest.fixture
def world_context():
    return WorldContext()
