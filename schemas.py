from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    message_template: str
    gmail_app_password: str
    mail_interval: str

class CompanyCreate(BaseModel):
    hr_name: str
    email: EmailStr
    company_name: str
