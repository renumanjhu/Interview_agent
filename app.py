import requests
import re
import os
import threading
import time
import tempfile
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions, Microphone
import pygame
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Initialize API keys
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Initialize clients
dg_client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# Deepgram TTS configuration
DEEPGRAM_TTS_URL = 'https://api.deepgram.com/v1/speak?model=aura-helios-en'
headers = {
    "Authorization": f"Token {DEEPGRAM_API_KEY}",
    "Content-Type": "application/json"
}

# Global variables
conversation_memory = []  # Stores the conversation history
asked_questions = set()   # Tracks questions already asked
mute_microphone = threading.Event()  # Controls microphone muting during playback

# Updated prompt with instructions to avoid repetition
PROMPT = """## Objective
You are a voice AI agent conducting an initial screening interview with the user. 
You will respond based on your given instructions and the provided transcript and be as human-like as possible.

## Role
Personality: Your name is Charles, and you are the hiring manager at XYZ Company. Maintain a professional yet approachable demeanor throughout the interview to ensure the candidate feels comfortable and can showcase their skills effectively.

## Instructions
1. Carefully review conversation history to avoid repetition.
2. Never repeat questions already asked: {asked_questions}.
3. If the candidate answers a question, ask follow-ups on the same topic.
4. If unsure about repetition, ask a new question from the job profile.
5. End with a closing statement after 5-6 quality questions.

## Job Profiles and Commonly Asked Questions
[Your job profiles and questions here...]

## Interview Flow
- Start with: "Hello, this is Charles from XYZ Company. How are you today?"
- Transition to: "I’ll be conducting your initial screening interview today. Let’s get started."
- Ask screening questions based on the job role.
- Adapt follow-ups based on the candidate’s responses.
- Close with: "Thank you for your time. We’ll review your responses and get back to you soon."
"""

# Helper functions
def segment_text_by_sentence(text):
    """Split text into sentences for natural-sounding TTS."""
    sentence_boundaries = re.finditer(r'(?<=[.!?])\s+', text)
    boundaries_indices = [boundary.start() for boundary in sentence_boundaries]  # Fixed variable name
    segments = []
    start = 0
    for boundary_index in boundaries_indices:
        segments.append(text[start:boundary_index + 1].strip())
        start = boundary_index + 1
    segments.append(text[start:].strip())
    return segments

def synthesize_audio(text):
    """Convert text to speech using Deepgram TTS."""
    payload = {"text": text}
    with requests.post(DEEPGRAM_TTS_URL, stream=True, headers=headers, json=payload) as r:
        return r.content

def play_audio(file_path):
    """Play audio using pygame."""
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
    pygame.mixer.music.stop()
    pygame.mixer.quit()
    mute_microphone.clear()

def extract_questions(text):
    """Extract questions from a text."""
    return [q.strip() for q in re.findall(r'([^.!?]+\?)', text)]

def is_duplicate_question(new_text, existing_questions):
    """Check if a question has already been asked."""
    new_questions = extract_questions(new_text)
    return any(q.lower() in (eq.lower() for eq in existing_questions) for q in new_questions)

def get_ai_response():
    """Generate a response from Gemini AI."""
    current_prompt = PROMPT.format(
        asked_questions=", ".join(asked_questions),
        original_prompt=PROMPT
    )
    
    messages = [{"role": "user", "parts": [current_prompt]}]
    messages += [{"role": msg["role"], "parts": [msg["content"]]} for msg in conversation_memory[-6:]]
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(messages)
    return response.text.strip()

def process_and_play_audio(text):
    """Process text into audio and play it."""
    text_segments = segment_text_by_sentence(text)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tf:
        for segment in text_segments:
            audio_data = synthesize_audio(segment)
            tf.write(audio_data)
        temp_path = tf.name
    
    mute_microphone.set()
    play_audio(temp_path)
    os.remove(temp_path)
    mute_microphone.clear()

# Main function
def main():
    try:
        deepgram = DeepgramClient(DEEPGRAM_API_KEY)
        dg_connection = deepgram.listen.live.v("1")
        is_finals = []
        has_introduced = False  # Flag to track if the assistant has introduced itself

        def on_message(self, result, **kwargs):
            nonlocal is_finals, has_introduced

            if mute_microphone.is_set():
                return

            sentence = result.channel.alternatives[0].transcript
            if len(sentence) == 0:
                return

            if result.is_final:
                is_finals.append(sentence)
                if result.speech_final:
                    utterance = " ".join(is_finals)
                    print(f"Speech Final: {utterance}")
                    is_finals = []
                    conversation_memory.append({"role": "user", "content": sentence.strip()})

                    # Generate AI response
                    ai_response = get_ai_response()

                    # Prevent introduction repetition
                    if not has_introduced:
                        ai_response = "Hello, this is Charles from XYZ Company. How are you today? " + \
                                    "I'll be conducting your initial screening interview. Let's begin.\n" + ai_response
                        has_introduced = True

                    # Check for duplicates and retry if necessary
                    retry_count = 0
                    while is_duplicate_question(ai_response, asked_questions) and retry_count < 3:
                        ai_response = get_ai_response()
                        retry_count += 1

                    # Add new questions to tracking
                    new_questions = extract_questions(ai_response)
                    asked_questions.update(new_questions)

                    # Ensure closing statement
                    if len(asked_questions) >= 5 and "closing" not in ai_response.lower():
                        ai_response += "\nThank you for your time. We'll review your responses and get back to you soon."

                    # Add AI response to conversation memory
                    conversation_memory.append({"role": "assistant", "content": ai_response})

                    # Process and play the AI response
                    process_and_play_audio(ai_response)

            else:
                print(f"Interim Results: {sentence}")

        # Set up Deepgram connection
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        options = LiveOptions(
            model="nova-2",
            language="en-US",
            smart_format=True,
            encoding="linear16",
            channels=1,
            sample_rate=16000,
            interim_results=True,
            utterance_end_ms="1000",
            vad_events=True,
            endpointing=500,
        )

        print("\n\nPress Enter to stop recording...\n\n")
        if not dg_connection.start(options):
            print("Failed to connect to Deepgram")
            return

        # Start microphone
        microphone = Microphone(dg_connection.send)
        microphone.start()
        input("")
        microphone.finish()
        dg_connection.finish()
        print("Finished")

    except Exception as e:
        print(f"Could not open socket: {e}")

# Entry point
if __name__ == "__main__":
    main()