from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    """Generic message response."""
    message: str