# Run this after uploading/cloning the ResQAI_app folder into Colab.
!pip install -q -r ResQAI_app/requirements.txt
!apt-get -qq update
!apt-get -qq install -y ffmpeg

import os, sys
sys.path.insert(0, "/content/ResQAI_app")

# Set your secret in Colab before running:
# os.environ["GROQ_API_KEY"] = "YOUR_GROQ_KEY"

from app import app

app.run(host="0.0.0.0", port=5000, debug=False)
