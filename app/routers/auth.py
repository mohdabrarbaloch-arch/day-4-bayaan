"""Registration, login, and the current-user endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import client_ip, current_user
from ..models import User
from ..ratelimit import RateLimit
from ..schemas import TokenOut, UserCreate, UserLogin, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

register_limit = RateLimit(settings.rate_limit_auth, scope="auth:register")
login_limit = RateLimit(settings.rate_limit_auth, scope="auth:login")


@router.post(
    "/register",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(register_limit)],
)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> TokenOut:
    email = payload.email.lower().strip()

    exists = db.scalar(select(User).where(func.lower(User.email) == email))
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists. Try signing in instead.",
        )

    user = User(
        email=email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenOut(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenOut, dependencies=[Depends(login_limit)])
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenOut:
    email = payload.email.lower().strip()
    user = db.scalar(select(User).where(func.lower(User.email) == email))

    # Same message for "no such user" and "wrong password" — don't let the login
    # endpoint confirm which emails are registered.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    return TokenOut(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/whoami", include_in_schema=False)
def whoami(request: Request) -> dict:
    """Small diagnostic: shows how the server sees the caller's address."""
    return {"client": client_ip(request)}
