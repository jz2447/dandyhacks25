import json
import re
from flask import Flask, Response, render_template, request, jsonify, send_file
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
import threading

from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface
from typing import IO
from io import BytesIO
from elevenlabs import VoiceSettings
from playsound3 import playsound # <<< Use playsound3
from elevenlabs.play import play

from fpdf import FPDF

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
    agent_id = os.getenv("AGENT_ID")
    return render_template("index.html", agent_id=agent_id)

@app.route("/component/prevSession")
def prevSession():
    return render_template("prevSession.html")

@app.route("/component/studyMetrics")
def studyMetrics():
    return render_template("studyMetrics.html")

@app.route("/component/studyStats")
def studyStats():
    return render_template("studyStats.html")

@app.route("/component/reinforcedLearning")
def reinforcedLearning():
    return render_template("reinforcedLearning.html")

# --- Download Endpoint ---
@app.route("/download/notes-pdf", methods=["POST"])
def download_session_notes():
    with open('study_summary.txt', 'r') as file:
        content = file.read()
        print(content)
    final_sum = gemini_session.send_message(
            
            "Analyze this list of topics and return a report that goes into detail on these topics in nice html: " + content
            
        )
    
    file = open("study_summary.txt", "w")
    file.write(final_sum.text)
    file.close()
    text = final_sum.text

    cleaned = re.sub(r"```(?:html)?", "", text).strip()
    cleaned = cleaned.replace("```", "").strip()

    return cleaned

def handle_music_playback(user_text, music_prompt):
    """Generates and plays the music track in a separate thread."""
    try:
        track = elevenLabs.music.compose(
            prompt=f"Create me a study track for this study goal: {user_text} with these vibes: {music_prompt}",
            music_length_ms=300000,
        )
        print("playing music")
        # IMPORTANT: Ensure 'play' itself is non-blocking or handles its own thread/process
        play(track) 
    except Exception as e:
        print(f"Error during music playback: {e}")

# --- Example HTMX endpoint ---
@app.route("/api/ask", methods=["POST"])
def ask_gemini():
    user_text = request.form.get("goal")
    music = request.form.get("music")
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

    if music:
        music_thread = threading.Thread(
            target=handle_music_playback,
            args=(user_text, music)
        )
        music_thread.start()

    # update the agent
    # conversation.send_contextual_update(f"The user's goal is to {user_text}")

    duration = request.form.get("duration")
    print("duration: " + duration)
    check_focus(int(duration))
    
    response = Response("New Session Started")
    # 'clearForm' is a custom event name you choose
    response.headers["HX-Trigger"] = "clearForm" 
    
    return response

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
                "Analyze this screen grab and return ONLY valid JSON with this format:\n\n"
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

            generate_report(image)

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

    print("Study session over")
    
    

def convert_To_PDF():
    pdf = FPDF()

    pdf.add_page()
    pdf.set_font("Courier", size=10)
    pdf.cell(200, 10, txt="Session Notes Report", ln=1, align="C")
    global GOAL
    pdf.cell(200, 10, txt=f"Study Goal: {GOAL}", ln=1)
    pdf.ln(5) # New line space
    input_file_path = "study_summary.txt"
    try:
        # Use 'with open' for safe file handling and specify encoding (UTF-8 recommended)
        with open(input_file_path, "r", encoding="utf-8") as f:
            # Use multi_cell to handle line wrapping automatically
            # w=0 makes the cell extend to the right margin
            # h=5 is the line height in the current unit (mm by default)
            # txt=f.read() reads the entire file content as a single string
            pdf.multi_cell(w=0, h=5, txt=f.read())

    except FileNotFoundError:
        print(f"Error: Input file '{input_file_path}' not found.")
        return
    except Exception as e:
        print(f"An error occurred: {e}")
        return

    # output_file_path = "study_summary.pdf"
    # pdf.output(output_file_path)
    # print(f"Successfully converted '{input_file_path}' to '{output_file_path}'")
    # Use BytesIO to capture the output in memory instead of saving to disk
    pdf_output = pdf.output(dest='S') # 'S' means return as a string
    return BytesIO(pdf_output)

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

def generate_report(image):
    response = gemini_session.send_message(
            [
                "Analyze this screen grab and return a list of the main topics being researched",

                image
            ]
        )
    
    with open("study_summary.txt", "a") as file:
        file.write(response.text)
    



if __name__ == "__main__":
    app.run(debug=True)
