"""Exam request schemas."""

from pydantic import BaseModel, Field


class ExamCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ExamQuestionAdd(BaseModel):
    questionId: str = Field(min_length=1)
