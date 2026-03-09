from pydantic import BaseModel
from typing import Optional

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class TeamCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(BaseModel):
    team_id: int
    code: str
    title: str
    xml_standard: str
