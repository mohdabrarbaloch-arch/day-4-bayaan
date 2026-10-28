"""Saved prompts — the small library that makes a playground usable day to day."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import SavedPrompt, User
from ..schemas import PromptCreate, PromptOut, PromptUpdate

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


def _owned(db: Session, user: User, prompt_id: str) -> SavedPrompt:
    """Fetch a prompt the caller owns, or 404 — never leak another user's ids."""
    prompt = db.scalar(
        select(SavedPrompt).where(SavedPrompt.id == prompt_id, SavedPrompt.user_id == user.id)
    )
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No saved prompt with that id."
        )
    return prompt


@router.get("", response_model=list[PromptOut])
def list_prompts(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[PromptOut]:
    rows = db.scalars(
        select(SavedPrompt)
        .where(SavedPrompt.user_id == user.id)
        .order_by(SavedPrompt.updated_at.desc())
    ).all()
    return [PromptOut.model_validate(r) for r in rows]


@router.post("", response_model=PromptOut, status_code=status.HTTP_201_CREATED)
def create_prompt(
    payload: PromptCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PromptOut:
    prompt = SavedPrompt(
        user_id=user.id,
        name=payload.name.strip(),
        system_prompt=payload.system_prompt,
        user_prompt=payload.user_prompt,
        notes=payload.notes,
    )
    db.add(prompt)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have a saved prompt called '{payload.name.strip()}'.",
        ) from exc
    db.refresh(prompt)
    return PromptOut.model_validate(prompt)


@router.get("/{prompt_id}", response_model=PromptOut)
def get_prompt(
    prompt_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> PromptOut:
    return PromptOut.model_validate(_owned(db, user, prompt_id))


@router.patch("/{prompt_id}", response_model=PromptOut)
def update_prompt(
    prompt_id: str,
    payload: PromptUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PromptOut:
    prompt = _owned(db, user, prompt_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(prompt, field, value.strip() if field == "name" else value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That name is already taken."
        ) from exc
    db.refresh(prompt)
    return PromptOut.model_validate(prompt)


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_prompt(
    prompt_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Response:
    prompt = _owned(db, user, prompt_id)
    db.delete(prompt)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
