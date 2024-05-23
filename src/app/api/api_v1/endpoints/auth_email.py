from fastapi import Depends, Request, APIRouter, status, HTTPException
from fastapi import APIRouter, Depends
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from app.schemas.email_user import EmailUserCreate, LoginRequest
from app.services.common.utils import process_request
from app.services.crud.email_user import create_new_user, login, verify_email
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.crud.user import get_user_by_email
from app.sql_app.database import get_db


router = APIRouter()


@router.post("/users")
async def email_register(user: EmailUserCreate, db: AsyncSession = Depends(get_db)):

    async def _create_new_user():
            return await create_new_user(user, db)
    
    return await process_request(_create_new_user)
    

@router.post("/token")
async def email_login(request: Request, login_request: LoginRequest, db: AsyncSession = Depends(get_db)):

    async def _email_login():
        return await login(request ,login_request, db)
    
    return await process_request(_email_login)


@router.get("/verify")
async def email_verify(token: str, db: AsyncSession = Depends(get_db)):
    
    async def _verify_email():
        return await verify_email(token, db)
    
    return await process_request(_verify_email)