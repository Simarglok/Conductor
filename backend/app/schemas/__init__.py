from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    """Generic message response."""
    message: str


class HealthResponse(BaseModel):
    """Health check response with DB and Redis status."""
    message: str
    database: str
    redis: str