from fastapi import (
    FastAPI,
    Form,
    UploadFile,
    File,
    Request,
    Depends,
    HTTPException,
    status,
    BackgroundTasks
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from database import Base, engine, get_db, send_email_background
from sqlalchemy.orm import Session
from models import SentMailLog, User, Company
import shutil
import os
import shutil
from datetime import timedelta
from auth_middleware import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    SECRET_KEY,
    ALGORITHM,
)
from jose import JWTError, jwt
from math import ceil
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


templates = Jinja2Templates(directory="templates")

Base.metadata.create_all(bind=engine)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, success: bool = False, email: str = ""):
    """Render login page with optional success message and prefilled email"""
    return templates.TemplateResponse(
        "user_login.html", {"request": request, "success": success, "email": email}
    )


@app.get("/user_registration", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("user_registration.html", {"request": request})


@app.post("/register")
async def register_user(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    resume: UploadFile = File(...),
    message_template: str = Form(...),
    gmail_app_password: str = Form(...),
    mail_interval: str = Form(...),
    db: Session = Depends(get_db),
):
    """Handle registration form submission."""
    print(password)

    hashed_password = get_password_hash(password)

    # Ensure upload folder exists
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, resume.filename)

    # Save the uploaded resume
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(resume.file, buffer)

    # Create the user record
    user = User(
        name=name,
        email=email,
        password=hashed_password,
        resume_path=file_path,
        message_template=message_template,
        gmail_app_password=gmail_app_password,
        mail_interval=mail_interval,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return RedirectResponse(url=f"/?success=true&email={email}", status_code=303)


@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    # ✅ create JWT token with user_id
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"user_id": user.id}, expires_delta=access_token_expires
    )

    # store token in cookie
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/", status_code=303)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise JWTError
    except JWTError:
        return RedirectResponse(url="/", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user_name": user.name}
    )


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")  # 👈 clear JWT cookie
    return response


@app.get("/company_registration", response_class=HTMLResponse)
async def company_registration(request: Request):
    return templates.TemplateResponse("registration.html", {"request": request})


@app.post("/register_company")
async def register_company(
    request: Request,
    hr_name: str = Form(...),
    email: str = Form(...),
    company_name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    company = db.query(Company).filter(Company.email == email).first()
    if company:
        raise HTTPException(
            status_code=400, detail="Company with this email already exists."
        )

    new_company = Company(
        hr_name=hr_name,
        email=email,
        company_name=company_name,
        user_id=current_user["id"],
    )

    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/my_companies", response_class=HTMLResponse)
async def my_companies(
    request: Request,
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    per_page = 5
    skip = (page - 1) * per_page

    total = db.query(Company).filter(Company.user_id == current_user["id"]).count()
    total_pages = ceil(total / per_page)

    companies = (
        db.query(Company)
        .filter(Company.user_id == current_user["id"])
        .order_by(Company.id)
        .offset(skip)
        .limit(per_page)
        .all()
    )

    if not companies:
        return HTMLResponse(
            "<tr><td colspan='6' style='text-align:center;'>No companies found.</td></tr>"
        )

    # Table rows
    rows_html = ""
    for c in companies:
        mail_sent = db.query(SentMailLog).filter(SentMailLog.company_id == c.id, SentMailLog.status == True).count()
        
        rows_html += f"""
        <tr>
            <td style='text-align:center;'>{c.id}</td>
            <td style='text-align:center;'>{c.hr_name}</td>
            <td style='text-align:center;'>{c.email}</td>
            <td style='text-align:center;'>{c.company_name}</td>
            <td style='text-align:center;'>{mail_sent}</td>
            <td style='text-align:center;'>{c.user.name}</td>
            <td style='text-align:center;'>
                <a href="/company_details/{c.id}">
                    <i class="fa fa-eye" style="font-size:20px;color:blue;"></i>
                </a>
                <button onclick="window.location.href='/edit_company/{c.id}'" 
                        style='background:#2196F3;color:white;border:none;padding:5px 8px;border-radius:3px;cursor:pointer;'>
                    Edit
                </button>
                <button onclick="deleteCompany({c.id})" 
                        style='background:#f44336;color:white;border:none;padding:5px 8px;border-radius:3px;cursor:pointer;'>
                    Delete
                </button>
                <button onclick="sendMail({c.id})" 
                        style='background:#34E80C;color:white;border:none;padding:5px 8px;border-radius:3px;cursor:pointer;'>
                    Send Mail
                </button>
            </td>
        </tr>
        """

    # Pagination controls
    pagination_html = "<div style='text-align:center;margin-top:10px;margin-bottom:10px;'>"
    if page > 1:
        pagination_html += (
            f"<button onclick='loadCompanies({page - 1})'>Previous</button> "
        )
    if page < total_pages:
        pagination_html += f"<button onclick='loadCompanies({page + 1})'>Next</button>"
    pagination_html += "</div>"

    return HTMLResponse(rows_html + pagination_html)

@app.post("/delete_company/{company_id}")
async def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    company = (
        db.query(Company)
        .filter(Company.id == company_id, Company.user_id == current_user["id"])
        .first()
    )
    if not company:
        return JSONResponse({"error": "Company not found"}, status_code=404)
    db.delete(company)
    db.commit()
    return JSONResponse({"message": "Company deleted successfully"})


@app.get("/edit_company/{company_id}", response_class=HTMLResponse)
async def edit_company_page(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    company = (
        db.query(Company)
        .filter(Company.id == company_id, Company.user_id == current_user["id"])
        .first()
    )

    if not company:
        return HTMLResponse(
            "<p>Company not found or you are not authorized.</p>", status_code=404
        )

    html = f"""
    <html>
    <head>
        <title>Edit Company</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background-color: #f4f4f4;
                margin: 40px;
            }}
            form {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                max-width: 500px;
                margin: auto;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }}
            input {{
                width: 100%;
                padding: 10px;
                margin: 8px 0;
                box-sizing: border-box;
            }}
            button {{
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 15px;
                cursor: pointer;
                border-radius: 4px;
            }}
            button:hover {{
                background-color: #45A049;
            }}
        </style>
    </head>
    <body>
        <h2 style="text-align:center;">Edit Company</h2>
        <form action="/update_company/{company_id}" method="post">
            <label>HR Name:</label>
            <input type="text" name="hr_name" value="{company.hr_name}" required>

            <label>Email:</label>
            <input type="email" name="email" value="{company.email}" required>

            <label>Company Name:</label>
            <input type="text" name="company_name" value="{company.company_name}" required>

            <button type="submit">Update Company</button>
        </form>
    </body>
    </html>
    """
    return HTMLResponse(html)


@app.post("/update_company/{company_id}")
async def update_company(
    company_id: int,
    hr_name: str = Form(...),
    email: str = Form(...),
    company_name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    company = (
        db.query(Company)
        .filter(Company.id == company_id, Company.user_id == current_user["id"])
        .first()
    )

    if not company:
        return HTMLResponse(
            "<p>Company not found or you are not authorized.</p>", status_code=404
        )

    company.hr_name = hr_name
    company.email = email
    company.company_name = company_name
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/updateprofile", response_class=HTMLResponse)
async def user_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Fetch user from DB
    user = db.query(User).filter(User.id == current_user["id"]).first()

    if not user:
        return HTMLResponse("<p>User not found</p>", status_code=404)

    # Template context
    context = {
        "request": request,
        "name": user.name,
        "email": user.email,
        "resume_url": user.resume_path if user.resume_path else "#",
        "message_template": user.message_template or "",
        "gmail_app_password": user.gmail_app_password or "",
        "mail_interval": user.mail_interval or "daily",
    }

    return templates.TemplateResponse("updateprofile.html", context)

@app.post("/updateprofile")
async def update_profile(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    message_template: str = Form(...),
    gmail_app_password: str = Form(...),
    mail_interval: str = Form(...),
    update_resume: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        return HTMLResponse("<p>User not found.</p>", status_code=404)

    user.name = name
    user.email = email
    user.message_template = message_template
    user.gmail_app_password = gmail_app_password
    user.mail_interval = mail_interval

    if update_resume.filename:
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)

        if user.resume_path:
            old_path = user.resume_path.lstrip("/")
            if os.path.exists(old_path):
                os.remove(old_path)

        resume_filename = f"{user.id}_{update_resume.filename}"
        resume_path = os.path.join(upload_dir, resume_filename)

        with open(resume_path, "wb") as buffer:
            shutil.copyfileobj(update_resume.file, buffer)

        user.resume_path = f"uploads\{resume_filename}"

    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/send_mail/{company_id}")
async def send_mail_to_company(
    background_tasks: BackgroundTasks,
    company_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    company = (
        db.query(Company)
        .filter(Company.id == company_id, Company.user_id == current_user["id"])
        .first()
    )
    if not company:
        return JSONResponse({"error": "Company not found"}, status_code=404)
    # Fetch user profile
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        return JSONResponse(status_code=404, content={"error": f"User not found"})
    if not user.gmail_app_password or not user.email:
        return JSONResponse(status_code=400, content={"error": "Missing Gmail credentials"})
    if not user.resume_path:
        return JSONResponse(status_code=400, content={"error": "Resume not found"})
    sender_email = user.email
    app_password = user.gmail_app_password
    body = user.message_template if user.message_template else "Hello, please find my resume attached."

    resume_path = user.resume_path.lstrip("/")
    if not os.path.exists(resume_path):
        return JSONResponse(status_code=404, content={"error": f"Resume file not found on server"})

    # Launch background task
    background_tasks.add_task(
        send_email_background,
        sender_email,
        app_password,
        company.email,
        "Application for Job",
        body,
        resume_path,
        user.id,
        company.id
    )

    return {"message": f"Email to {company.email} is being sent in background."}
