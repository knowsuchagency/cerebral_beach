from ninja import NinjaAPI, Router
from pydantic import BaseModel
import os
import requests
import json
import re

api = NinjaAPI(title="JIT Learning")

v1 = Router()

api.add_router("/v1", v1)


class FlashCard(BaseModel):
    question: str
    answer: str


class FlashCards(BaseModel):
    cards: list[FlashCard]

class GenerateFlashcardsInput(BaseModel):
    raw_data: str


@v1.post("/generate-flashcards")
def generate_flashcards(request, flashcards_input: GenerateFlashcardsInput, model="azure/gpt-4o"):
    api_key = os.getenv("KINDO_API_KEY")
    url = "https://llm.kindo.ai/v1/chat/completions"

    headers = {
        "api-key": api_key,
        "content-type": "application/json"
    }

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

    user_message = f"Here is the raw data to generate flashcards from:\n\n{flashcards_input.raw_data}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()  # This will raise an exception for HTTP errors

    # Parse the JSON response
    response_data = response.json()
    flashcards_content = response_data['choices'][0]['message']['content']

    # Try to parse the content as JSON directly
    try:
        flashcards = FlashCards.model_validate_json(flashcards_content)
    except ValueError:
        # If direct parsing fails, try to extract JSON from markdown code blocks
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', flashcards_content)
        if json_match:
            flashcards_json = json_match.group(1)
            flashcards = FlashCards.model_validate_json(flashcards_json)
        else:
            raise ValueError("Unable to parse flashcards from the response")

    return flashcards
