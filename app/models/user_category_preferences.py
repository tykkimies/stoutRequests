from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class UserCategoryPreferences(SQLModel, table=True):
    """User-specific category customization preferences"""
    __tablename__ = "user_category_preferences"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    category_id: str = Field(index=True)  # matches the category ID from default categories
    is_visible: bool = Field(default=True)  # whether the category is shown to the user
    display_order: int = Field(default=0)  # custom order for this user
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    class Config:
        # Ensure each user can only have one preference per category
        table_args = {"sqlite_on_conflict_unique": "REPLACE"}