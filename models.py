from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    resume_path = Column(String(255), nullable=False)
    message_template = Column(Text, nullable=False)
    gmail_app_password = Column(String(255), nullable=False)
    mail_interval = Column(String(50), nullable=False)
    companies = relationship("Company", back_populates="user")

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    hr_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    company_name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))  # link to user table

    user = relationship("User", back_populates="companies")
    
class SentMailLog(Base):
    __tablename__ = "sent_mail_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    timestamp = Column(String, nullable=False)
    status = Column(Boolean, nullable=False)

    user = relationship("User")
    company = relationship("Company")