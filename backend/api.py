from ninja import NinjaAPI, Router
from promptic import llm
from pydantic import BaseModel

api = NinjaAPI(
    title="JIT Learning"
)

v1 = Router()

api.add_router("/v1", v1)

class FlashCard(BaseModel):
    question: str
    answer: str

class FlashCards(BaseModel):
    cards: list[FlashCard]


@v1.post("/generate-flashcards")
def generate_flashcards(request, raw_data: str, model="gemini/gemini-1.5-pro-latest"):
    @llm(model=model)
    def generate(raw_data: str) -> FlashCards:
        """
        You are an AI assistant tasked with generating flashcards from raw data. Your goal is to create informative and engaging flashcards that capture the essential information from the provided data. Follow these instructions carefully to produce high-quality flashcards in the required format.

        Here is the raw data you will be working with:

        <raw_data>
        {raw_data}
        </raw_data>

        Analyze the raw data carefully. Identify key concepts, facts, definitions, and relationships within the information provided. Look for important terms, dates, events, or any other significant details that would be suitable for flashcards.

        Generate flashcards based on the analyzed data. Each flashcard should consist of a question (front of the card) and an answer (back of the card). Ensure that the questions are clear and concise, and the answers are accurate and informative.

        Follow these guidelines when creating the flashcards:
        1. Ensure diversity in the types of questions (e.g., definitions, comparisons, cause-and-effect, etc.)
        2. Make the questions challenging but not overly complex
        3. Keep the answers concise but informative
        4. Avoid repetition of information across flashcards
        5. Ensure that all information in the flashcards is directly derived from the provided raw data

        Once you have generated the flashcards, review them for accuracy, clarity, and relevance. Make any necessary adjustments to improve their quality.

        Output your final set of flashcards in the specified JSON format, enclosed within <flashcards> tags. Ensure that the JSON is properly formatted and valid.

        Begin your task now. Analyze the raw data, generate the flashcards, and provide the output as instructed.
        """
    
    return generate(raw_data)
