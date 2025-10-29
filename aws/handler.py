from mangum import Mangum

# Reuse the existing FastAPI app from the project
# This keeps behavior identical to the local/dev and Docker versions
from app.main import app

# Lambda handler entrypoint
handler = Mangum(app)