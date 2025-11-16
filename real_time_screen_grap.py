import time

while True:
    capture_screen("latest.png")
    # send to Gemini
    analyze("latest.png")
    time.sleep(5)  # every 5 seconds
