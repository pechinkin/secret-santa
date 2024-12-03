from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime
import pytz
import random

# Database configuration
SQLALCHEMY_DATABASE_URL = "postgresql://myuser:mypassword@localhost/mydatabase"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# User model
class User(Base):
    __tablename__ = "users"
    nickname = Column(String(50), primary_key=True, index=True)
    password = Column(String(100), nullable=False)
    contact_info = Column(String(255))
    wishes = Column(Text)
    gifting_to = Column(String(1000))

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic models for request validation
class UserCreate(BaseModel):
    nickname: str
    password: str

class UserLogin(BaseModel):
    nickname: str
    password: str

class SaveWishes(BaseModel):
    nickname: str
    wishes: str

class SaveContactInfo(BaseModel):
    nickname: str
    contact_info: str

# Dependency to get the user from the token
def get_user_from_token(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("secret_santa_user_token")
    if not token:
        raise HTTPException(status_code=401, detail="Token not found")

    nickname, password = token.split(":")
    user = db.query(User).filter(User.nickname == nickname, User.password == password).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    return user

# Routes
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/home", response_class=HTMLResponse)
async def read_home(request: Request, user: User = Depends(get_user_from_token)):
    return templates.TemplateResponse("home.html", {"request": request, "user": user})

@app.post("/register")
async def register_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.nickname == user.nickname).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Nickname already registered")
    db_user = User(nickname=user.nickname, password=user.password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    response = JSONResponse(content={"message": "User registered successfully"})
    response.set_cookie(key="secret_santa_user_token", value=f"{user.nickname}:{user.password}", httponly=True)
    return response

@app.post("/login")
async def login_user(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.nickname == user.nickname).first()
    if not db_user or db_user.password != user.password:
        raise HTTPException(status_code=400, detail="Invalid nickname or password")

    response = JSONResponse(content={"message": "Login successful", "nickname": db_user.nickname})
    response.set_cookie(key="secret_santa_user_token", value=f"{user.nickname}:{user.password}", httponly=True)
    return response

@app.post("/logout")
async def logout_user(response: Response):
    response = JSONResponse(content={"message": "Logout successful"})
    response.delete_cookie(key="secret_santa_user_token")
    return response

@app.post("/save-wishes")
async def save_wishes(wishes: SaveWishes, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.nickname == wishes.nickname).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.wishes = wishes.wishes
    db.commit()
    db.refresh(user)
    return {"message": "Wishes saved successfully"}

@app.post("/save-contact-info")
async def save_contact_info(contact_info: SaveContactInfo, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.nickname == contact_info.nickname).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.contact_info = contact_info.contact_info
    db.commit()
    db.refresh(user)
    return {"message": "Contact info saved successfully"}

scheduler = BackgroundScheduler()

@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)

    scheduler = BackgroundScheduler()

    def assign_gifting_to(db: Session):
        users = db.query(User).all()
        nicknames = [user.nickname for user in users]
        random.shuffle(nicknames)
        for i in range(len(nicknames)):
            user = db.query(User).filter(User.nickname == nicknames[i]).first()
            gifting_to_user = db.query(User).filter(User.nickname == nicknames[(i + 1) % len(nicknames)]).first()
            user.gifting_to = (
                f"Nickname: {gifting_to_user.nickname}\n"
                f"Contact Info: {gifting_to_user.contact_info}\n"
                f"Wishes: {gifting_to_user.wishes}"
            )
            db.commit()

    moscow_timezone = pytz.timezone('Europe/Moscow')
    run_date = moscow_timezone.localize(datetime(2024, 12, 18, 0, 0))
    trigger = DateTrigger(run_date=run_date)
    scheduler.add_job(assign_gifting_to, trigger, args=[SessionLocal()])

    scheduler.start()

@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()
