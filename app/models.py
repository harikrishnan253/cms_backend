from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base
import enum

class WorkflowStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    XML_GENERATED = "XML_GENERATED"
    PUBLISHED = "PUBLISHED"

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String)
    users = relationship("User", secondary="user_roles", back_populates="roles")

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    users = relationship("User", back_populates="team")
    projects = relationship("Project", back_populates="team")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    is_active = Column(Boolean, default=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    
    team = relationship("Team", back_populates="users")
    roles = relationship("Role", secondary="user_roles", back_populates="users")

class UserRole(Base):
    __tablename__ = "user_roles"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    code = Column(String, unique=True, index=True)
    client_name = Column(String, nullable=True)  # Client/Publisher name
    xml_standard = Column(String)
    status = Column(String, default="RECEIVED")
    team_id = Column(Integer, ForeignKey("teams.id"))
    
    team = relationship("Team", back_populates="projects")
    files = relationship("File", back_populates="project")
    chapters = relationship("Chapter", back_populates="project", cascade="all, delete-orphan")

class Chapter(Base):
    __tablename__ = "chapters"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    number = Column(String, index=True)
    title = Column(String)
    
    project = relationship("Project", back_populates="chapters")
    files = relationship("File", back_populates="chapter")

class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=True)
    filename = Column(String, index=True)
    file_type = Column(String)
    category = Column(String, default="Manuscript") # Art, Manuscript, InDesign, Proof, XML
    path = Column(String)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    version = Column(Integer, default=1)
    
    project = relationship("Project", back_populates="files")
    chapter = relationship("Chapter", back_populates="files")
    
    # Checkout Logic
    is_checked_out = Column(Boolean, default=False)
    checked_out_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    checked_out_at = Column(DateTime, nullable=True)
    
    checked_out_by = relationship("User", foreign_keys=[checked_out_by_id])
    versions = relationship("FileVersion", back_populates="original_file", cascade="all, delete-orphan")

class FileVersion(Base):
    __tablename__ = "file_versions"
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    version_num = Column(Integer)
    path = Column(String)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    original_file = relationship("File", back_populates="versions")
    uploaded_by = relationship("User")

