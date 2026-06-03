from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB Connection - Now using .env (SECURE!)
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)

# Database
db = client["student_portal"]

# Collections
student = db["student"]
admins = db["admins"]
otps = db["otps"]