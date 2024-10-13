import os
import re
import base64
import requests
import time
from django.db.models import Avg
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Router
from ninja.responses import Response
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

from backend.core.models import Flashcard, FlashcardStudy, StudySession

api = NinjaAPI(title="JIT Learning")

v1 = Router()

api.add_router("/v1", v1)


class FlashCard(BaseModel):
    question: str
    answer: str


class FlashCards(BaseModel):
    cards: List[FlashCard]


class GenerateFlashcardsInput(BaseModel):
    raw_data: Optional[str] = None
    pdf_base64: Optional[str] = None


class StudySessionCreate(BaseModel):
    raw_data: Optional[str] = None
    pdf_base64: Optional[str] = None


class FlashcardStudyInput(BaseModel):
    flashcard_id: str
    knowledge_level: int = Field(..., ge=1, le=3)

    @field_validator("knowledge_level")
    @classmethod
    def validate_knowledge_level(cls, v):
        if v < 1 or v > 3:
            raise ValueError("Knowledge level must be between 1 and 3")
        return v


class FlashcardResponse(BaseModel):
    id: str
    question: str
    answer: str


# New response models
class StudySessionResponse(BaseModel):
    session_id: str = Field(..., description="The ID of the created study session")


class FlashcardStudyResponse(BaseModel):
    message: str = Field(..., description="A success message")


class EndStudySessionResponse(BaseModel):
    message: str = Field(..., description="A success message")


def extract_content_from_pdf(pdf_base64):
    llama_api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    upload_url = "https://api.cloud.llamaindex.ai/api/parsing/upload"

    # Decode base64 string to bytes
    pdf_bytes = base64.b64decode(pdf_base64)

    # Upload file and start parsing
    files = {"file": ("document.pdf", pdf_bytes, "application/pdf")}
    headers = {"Authorization": f"Bearer {llama_api_key}", "accept": "application/json"}

    response = requests.post(upload_url, headers=headers, files=files)
    response.raise_for_status()
    job_id = response.json()["job_id"]

    # Check job status until complete
    status_url = f"https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}"
    while True:
        status_response = requests.get(status_url, headers=headers)
        status_response.raise_for_status()
        status = status_response.json()["status"]
        if status == "COMPLETED":
            break
        elif status in ["FAILED", "CANCELLED"]:
            raise Exception(f"PDF parsing failed with status: {status}")
        time.sleep(3)  # Wait before checking again

    # Get results in Text
    result_url = f"https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}/result/text"
    result_response = requests.get(result_url, headers=headers)
    result_response.raise_for_status()

    return result_response.text


@v1.post("/create-study-session", response=StudySessionResponse)
def create_study_session(
    request, session_input: StudySessionCreate
) -> StudySessionResponse:
    # Create a new study session
    study_session = StudySession.objects.create()

    # Generate flashcards using the existing generate_flashcards function
    flashcards_data = generate_flashcards(
        request,
        GenerateFlashcardsInput(
            raw_data=session_input.raw_data, pdf_base64=session_input.pdf_base64
        ),
    )

    # Create Flashcard objects and associate them with the study session
    for card in flashcards_data.cards:
        Flashcard.objects.create(
            study_session=study_session, question=card.question, answer=card.answer
        )

    return StudySessionResponse(session_id=str(study_session.id))


@v1.get(
    "/get-next-flashcard/{session_id}", response={200: FlashcardResponse, 404: dict}
)
def get_next_flashcard(request, session_id: str) -> Response:
    study_session = get_object_or_404(StudySession, id=session_id)

    # Simple algorithm to get the next flashcard
    # Prioritize cards with higher average knowledge level (less known)
    next_flashcard = (
        Flashcard.objects.filter(study_session=study_session)
        .annotate(avg_knowledge=Avg("studies__knowledge_level"))
        .order_by("-avg_knowledge", "?")
        .first()
    )

    if next_flashcard:
        return 200, FlashcardResponse(
            id=str(next_flashcard.id),
            question=next_flashcard.question,
            answer=next_flashcard.answer,
        )
    else:
        return 404, {"message": "No more flashcards in this session"}


@v1.post("/study-flashcard/{session_id}", response=FlashcardStudyResponse)
def study_flashcard(
    request, session_id: str, study_input: FlashcardStudyInput
) -> FlashcardStudyResponse:
    study_session = get_object_or_404(StudySession, id=session_id)
    flashcard = get_object_or_404(
        Flashcard, id=study_input.flashcard_id, study_session=study_session
    )

    FlashcardStudy.objects.create(
        flashcard=flashcard,
        study_session=study_session,
        knowledge_level=study_input.knowledge_level,
    )

    return FlashcardStudyResponse(message="Flashcard study recorded successfully")
