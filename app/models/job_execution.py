"""
Job execution tracking models
"""
from datetime import datetime
from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import DateTime


class JobExecution(SQLModel, table=True):
    """Track job execution history"""
    __tablename__ = "job_executions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    job_name: str = Field(index=True)
    started_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime))
    completed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    status: str = Field(default="running")  # running, success, failed
    result_data: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    error_message: Optional[str] = Field(default=None)
    triggered_by: str = Field(default="scheduler")  # scheduler, manual, api
    duration_seconds: Optional[float] = Field(default=None)
    
    def mark_completed(self, success: bool = True, result_data: Dict[str, Any] = None, error_message: str = None):
        """Mark job as completed"""
        self.completed_at = datetime.utcnow()
        self.status = "success" if success else "failed"
        if result_data:
            self.result_data = result_data
        if error_message:
            self.error_message = error_message
        
        # Calculate duration
        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()