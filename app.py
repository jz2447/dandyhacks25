import json
import re
from flask import Flask, render_template, request, jsonify
import os
import httpx
from dotenv import load_dotenv
import mss
import mss.tools
from google import genai
from PIL import Image
import os
from dotenv import load_dotenv
import time
import os
import signal

from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface
from typing import IO
from io import BytesIO
from elevenlabs import VoiceSettings
from playsound3 import playsound # <<< Use playsound3


load_dotenv()

app = Flask(__name__)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
# Create the session once when the app starts
gemini_session = client.chats.create(
    model="gemini-2.5-flash",
    # system_instruction="""
    # Your goal: analyze user screens for productivity blockers without responding 
    # unless asked. Track patterns like clutter, repeated tasks, and automation opportunities.
    # """
)

agent_id = os.getenv("AGENT_ID")
api_key = os.getenv("ELEVENLABS_API_KEY")

# Setup callbacks
def on_agent_response(text):
    print(f"Agent: {text}")

def on_user_transcript(text):
    print(f"You: {text}")

def on_latency(ms):
    print(f"Latency: {ms}ms")

elevenLabs = ElevenLabs(api_key=api_key)

conversation = Conversation(
    elevenLabs,
    agent_id=os.getenv("AGENT_ID"),
    requires_auth=False,
    audio_interface=DefaultAudioInterface()
)
# conversation.start_session()


GOAL = ""


# --- Home Page ---
@app.route("/")
def home():
    return render_template("index.html")

# --- Example HTMX endpoint ---
@app.route("/api/ask", methods=["POST"])
def ask_gemini():
    user_text = request.form.get("text")
    global GOAL
    GOAL = user_text

    # response_text = client.models.generate_content(
    #     model="gemini-2.5-flash", contents=f"This is my study goal: {user_text}"
    # )
    # Inject the new goal into the *existing* session
    response = gemini_session.send_message(
        message=f"""
        Update your understanding. The user's current study goal is:
        "{user_text}".
        Do NOT respond.
        """
    )
    '''
        response = gemini_session.send_message(
        [
            "Analyze this screenshot and return JSON.",
            image  # PIL.Image.Image
        ]
    )
    '''

    print(response.text)

    # update the agent
    # conversation.send_contextual_update(f"The user's goal is to {user_text}")

    duration = 3
    check_focus(duration)
    

    return "New Session Started" #jsonify({"reply": response_text.text})


def capture_screen(path="screen.png"):

    time.sleep(10)
    with mss.mss() as sct:
        screenshot = sct.shot(output=path)
        print("new screenshot taken")
        return screenshot

def check_focus(duration):
    t_end = time.time() + 60 * duration
    while time.time() < t_end: 
        capture_screen()
        image = Image.open("screen.png")
        response = gemini_session.send_message(
            [
                "Analyze this screenshot and return ONLY valid JSON with this format:\n\n"
                "{\n"
                "  \"on_topic\": true/false,\n"
                "  \"reason\": \"short explanation\",\n"
                "  \"tips\": [\"tip1\", \"tip2\", \"tip3\"]\n"
                "}\n\n"
                "Determine if the screenshot matches the my current study goal. "
                "If it does NOT match, include tips for regaining focus.",

                image
            ]
        )

        print(response.text)

        try:
            result = extract_json(response.text)
        except Exception:
            print("Gemini returned malformed JSON:", response.text)
            continue

        # If user is off-topic → encourage with ElevenLabs
        if not result["on_topic"]:
            print("off topic")
            message = (
                "Hey, it looks like you're getting a bit distracted. "
                f"{result['reason']} "
                "Here are a few quick tips to refocus:\n"
                + "\n".join(["• " + t for t in result["tips"]])
                + "get back to work!!"
            )

            # ElevenLabs TTS
            audio = elevenLabs.text_to_speech.convert(
                text=message,
                voice_id="pNInz6obpgDQGcFmaJgB",
                model_id="eleven_flash_v2",
                output_format="mp3_22050_32",
                voice_settings=VoiceSettings(
                    stability=0.0,
                    similarity_boost=1.0,
                    style=0.0,
                    use_speaker_boost=True,
                    speed=1.0,
                ),
            )

        else:
            print("on topic")
            encouragement = gemini_session.send_message(f"give me a short encouraging message about my good work pursing my goal: {GOAL}")
            audio = elevenLabs.text_to_speech.convert(
                text=encouragement.text,
                voice_id="pNInz6obpgDQGcFmaJgB",
                model_id="eleven_flash_v2",
                output_format="mp3_22050_32",
                voice_settings=VoiceSettings(
                    stability=0.0,
                    similarity_boost=1.0,
                    style=0.0,
                    use_speaker_boost=True,
                    speed=1.0,
                ),
            )

        
        save_file_path = "output.mp3"
        # Writing the audio to a file
        with open(save_file_path, "wb") as f:
            for chunk in audio:
                if chunk:
                    f.write(chunk)   

        try:
            # 3. Play the Audio using playsound3
            print("Starting playback with playsound3...")
            # playsound3 can handle MP3 files on Windows natively via winmm.dll
            playsound(save_file_path) 
            print("Playback finished.")

        finally:
            # 4. Clean up the temporary file
            os.remove(save_file_path)
            print("Temporary file cleaned up.")

        # Wait a few seconds between checks
        time.sleep(5)

def extract_json(text):
    """
    Removes code fences and extracts the first valid JSON object.
    """
    if not text:
        raise ValueError("Empty response from model.")

    # Remove ```json or ``` code fences
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    cleaned = cleaned.replace("```", "").strip()

    # Extract first {...} block
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError("No JSON found in: " + text)

    return json.loads(match.group())


if __name__ == "__main__":
    app.run(debug=True)
