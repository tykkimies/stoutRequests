from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    plex_id: Optional[int] = Field(default=None, unique=True, index=True)
    username: str = Field(index=True, unique=True)
    email: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_admin: bool = Field(default=False)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    # Local authentication fields
    password_hash: Optional[str] = Field(default=None)
    is_local_user: bool = Field(default=False)
    
    def is_plex_user(self) -> bool:
        """Check if this is a Plex-authenticated user"""
        return self.plex_id is not None and not self.is_local_user
    
    def has_password(self) -> bool:
        """Check if user has a local password set"""
        return self.password_hash is not None