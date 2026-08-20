"""Google ADK discovery module.

Run with ``adk web src`` or import ``realitydiff.agent:app`` from an ADK host.
"""

from .adk_agent import build_adk_app, build_adk_agent
from .cloud import build_state_backend
from .config import settings
from .repository import WorldRepository


repository = WorldRepository(
    settings.fixture_path,
    settings.state_path,
    cloud_state=build_state_backend(settings),
)
root_agent = build_adk_agent(repository)
app = build_adk_app(repository, root_agent)
