import google.generativeai as genai
from PIL import Image

genai.configure(api_key="YOUR_KEY")

image = Image.open("screen.png")
model = genai.GenerativeModel("gemini-2.0-flash")

response = model.generate_content(
    ["Analyze this screenshot and tell me what tasks I should do next:", image]
)

print(response.text)
