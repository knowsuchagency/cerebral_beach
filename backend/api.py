import os
import re
import base64
import requests
import time
from django.db.models import Avg
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Router
from pydantic import BaseModel

from backend.core.models import Flashcard, FlashcardStudy, StudySession

api = NinjaAPI(title="JIT Learning")

v1 = Router()

api.add_router("/v1", v1)


class FlashCard(BaseModel):
    question: str
    answer: str


class FlashCards(BaseModel):
    cards: list[FlashCard]


class GenerateFlashcardsInput(BaseModel):
    raw_data: str = None
    pdf_base64: str = None


class StudySessionCreate(BaseModel):
    raw_data: str = None
    pdf_base64: str = None


class FlashcardStudyInput(BaseModel):
    flashcard_id: str
    knowledge_level: int
    is_correct: bool


class FlashcardResponse(BaseModel):
    id: str
    question: str
    answer: str


def extract_content_from_pdf(pdf_base64):
    llama_api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    upload_url = "https://api.cloud.llamaindex.ai/api/parsing/upload"
    
    # Decode base64 string to bytes
    pdf_bytes = base64.b64decode(pdf_base64)
    
    # Upload file and start parsing
    files = {'file': ('document.pdf', pdf_bytes, 'application/pdf')}
    headers = {
        "Authorization": f"Bearer {llama_api_key}",
        "accept": "application/json"
    }
    
    response = requests.post(upload_url, headers=headers, files=files)
    response.raise_for_status()
    job_id = response.json()['job_id']
    
    # Check job status until complete
    status_url = f"https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}"
    while True:
        status_response = requests.get(status_url, headers=headers)
        status_response.raise_for_status()
        status = status_response.json()['status']
        if status == 'COMPLETED':
            break
        elif status in ['FAILED', 'CANCELLED']:
            raise Exception(f"PDF parsing failed with status: {status}")
        time.sleep(3)  # Wait before checking again
    
    # Get results in Text
    result_url = f"https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}/result/text"
    result_response = requests.get(result_url, headers=headers)
    result_response.raise_for_status()
    
    return result_response.text


@v1.post("/generate-flashcards")
def generate_flashcards(
    request,
    flashcards_input: GenerateFlashcardsInput,
    model="azure/gpt-4o",
):
    if flashcards_input.pdf_base64:
        raw_data = extract_content_from_pdf(flashcards_input.pdf_base64)
    else:
        raw_data = flashcards_input.raw_data

    api_key = os.getenv("KINDO_API_KEY")
    url = "https://llm.kindo.ai/v1/chat/completions"

    headers = {"api-key": api_key, "content-type": "application/json"}

    system_message = """
    You are an AI assistant tasked with generating flashcards from raw data. Your goal is to create informative and engaging flashcards that capture the essential information from the provided data. Follow these instructions carefully to produce high-quality flashcards in the required format.

    Analyze the raw data carefully. Identify key concepts, facts, definitions, and relationships within the information provided. Look for important terms, dates, events, or any other significant details that would be suitable for flashcards.

    Generate flashcards based on the analyzed data. Each flashcard should consist of a question (front of the card) and an answer (back of the card). Ensure that the questions are clear and concise, and the answers are accurate and informative.

    Follow these guidelines when creating the flashcards:
    1. Ensure diversity in the types of questions (e.g., definitions, comparisons, cause-and-effect, etc.)
    2. Make the questions challenging but not overly complex
    3. Keep the answers concise but informative
    4. Avoid repetition of information across flashcards
    5. Ensure that all information in the flashcards is directly derived from the provided raw data

    Once you have generated the flashcards, review them for accuracy, clarity, and relevance. Make any necessary adjustments to improve their quality.

    Output your final set of flashcards in JSON format. The JSON should be an object with a single key "cards", which contains an array of flashcard objects. Each flashcard object should have "question" and "answer" keys.
    """

    user_message = f"Here is the raw data to generate flashcards from:\n\n{raw_data}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()  # This will raise an exception for HTTP errors

    # Parse the JSON response
    response_data = response.json()
    flashcards_content = response_data["choices"][0]["message"]["content"]

    # Try to parse the content as JSON directly
    try:
        flashcards = FlashCards.model_validate_json(flashcards_content)
    except ValueError:
        # If direct parsing fails, try to extract JSON from markdown code blocks
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", flashcards_content)
        if json_match:
            flashcards_json = json_match.group(1)
            flashcards = FlashCards.model_validate_json(flashcards_json)
        else:
            raise ValueError("Unable to parse flashcards from the response")

    return flashcards


@v1.post("/create-study-session")
def create_study_session(request, session_input: StudySessionCreate):
    # Create a new study session
    study_session = StudySession.objects.create()

    # Generate flashcards using the existing generate_flashcards function
    flashcards_data = generate_flashcards(
        request, GenerateFlashcardsInput(raw_data=session_input.raw_data, pdf_base64=session_input.pdf_base64)
    )

    # Create Flashcard objects and associate them with the study session
    for card in flashcards_data.cards:
        Flashcard.objects.create(
            study_session=study_session, question=card.question, answer=card.answer
        )

    return {"session_id": str(study_session.id)}


@v1.get("/get-next-flashcard/{session_id}")
def get_next_flashcard(request, session_id: str):
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
        return FlashcardResponse(
            id=str(next_flashcard.id),
            question=next_flashcard.question,
            answer=next_flashcard.answer,
        )
    else:
        return {"message": "No more flashcards in this session"}


@v1.post("/study-flashcard/{session_id}")
def study_flashcard(request, session_id: str, study_input: FlashcardStudyInput):
    study_session = get_object_or_404(StudySession, id=session_id)
    flashcard = get_object_or_404(
        Flashcard, id=study_input.flashcard_id, study_session=study_session
    )

    knowledge_level = study_input.knowledge_level if study_input.is_correct else 3

    FlashcardStudy.objects.create(
        flashcard=flashcard,
        study_session=study_session,
        knowledge_level=knowledge_level,
    )

    return {"message": "Flashcard study recorded successfully"}


# @v1.post("/end-study-session/{session_id}")
# def end_study_session(request, session_id: str):
#     study_session = get_object_or_404(StudySession, id=session_id)
#     # You can add any cleanup or finalization logic here if needed
#     return {"message": "Study session ended successfully"}
