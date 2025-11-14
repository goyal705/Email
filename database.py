from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

load_dotenv()
db_pass = os.environ.get("DATABASE_PASSWORD")
DATABASE_URL = os.environ.get("DATABASE_URL").format(db_pass)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
def send_email_background(sender_email, app_password, recipient_email, subject, body, resume_path, user_id, company_id):
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Attach the resume
    with open(resume_path, "rb") as file:
        part = MIMEApplication(file.read(), Name=os.path.basename(resume_path))
    part["Content-Disposition"] = f'attachment; filename="{os.path.basename(resume_path)}"'
    msg.attach(part)

    try:
        timestamp = datetime.utcnow().isoformat()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.send_message(msg)
        print(f"Email sent successfully to {recipient_email}")
        log_sent_email(db=SessionLocal(), user_id=user_id, company_id=company_id, timestamp=timestamp, status=True)
    except Exception as e:
        print(f"Error sending mail to {recipient_email}: {e}")
        log_sent_email(db=SessionLocal(), user_id=user_id, company_id=company_id, timestamp=timestamp, status=False)

def log_sent_email(db, user_id, company_id, timestamp , status):
    from models import SentMailLog
    log_entry = SentMailLog(user_id=user_id, company_id=company_id, timestamp=timestamp, status=status)
    db.add(log_entry)
    db.commit()