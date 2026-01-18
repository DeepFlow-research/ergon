"""Inngest client configuration."""

import inngest
import os

from h_arcane.core.settings import settings

# Get Inngest API base URL from environment or settings
# In Docker, this should be set to http://inngest-dev:8288
# On host, use http://localhost:8289
inngest_base_url = os.getenv("INNGEST_API_BASE_URL", settings.inngest_api_base_url)

# Create Inngest client
# Note: event_api_base_url is used for sending events, api_base_url is for function registration
inngest_client = inngest.Inngest(
    app_id="h-arcane",
    event_key=settings.inngest_event_key or "local-dev",
    is_production=not settings.inngest_dev,
    api_base_url=inngest_base_url,
    event_api_base_url=inngest_base_url,  # Use same URL for events
    serializer=inngest.PydanticSerializer(),
)
