# Interview_agent
So I buit agent that can take initial screening test of candidates . It would ask relevant questions and can also manipulate them in accordance with the candidates answers.
### Requirements

Python 3.11

Deepgram and Gemini

### Steps to run

Open .env file and setup your Deepgram and Gemini keys

Create a virtualenv and install depends from requirements.txt using below command

pip install -r requirements.txt

pip install google-generativeai

if error of no module named requests come, then give command 

pip install requests

Run the app using below command

python app.py
