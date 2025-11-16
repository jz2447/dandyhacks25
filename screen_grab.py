import mss
import mss.tools
from google import genai
from PIL import Image
import os
from dotenv import load_dotenv

load_dotenv()

def capture_screen(path="screen.png"):
    with mss.mss() as sct:
        screenshot = sct.shot(output=path)
        return screenshot

capture_screen()




image = Image.open("screen.png")
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

response = client.models.generate_content(
    model="gemini-2.5-flash", contents=["Analyze this screenshot and tell me what tasks I should do next:", image]
)

print(response.text)