from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    print("❌ MONGO_URI environment variable is not set!")
    raise ValueError("MONGO_URI environment variable is required")

# ✅ FIX: Connect with SSL options
try:
    client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsAllowInvalidCertificates=True,
        serverSelectionTimeoutMS=30000,
        socketTimeoutMS=30000
    )
    # Test connection
    client.admin.command('ping')
    print("✅ MongoDB connection successful!")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    raise

# Database
db = client["student_portal"]

# Collections
student = db["student"]
admins = db["admins"]
otps = db["otps"]
attendance = db["attendance"]
marks = db["marks"]
subjects = db["subjects"]
courses = db["courses"]
enrollments = db["enrollments"]
activity_logs = db["activity_logs"]
announcement = db["announcement"]
forum_questions = db["forum_questions"]
forum_replies = db["forum_replies"]
course_materials = db["course_materials"]
important_materials = db["important_materials"]
quizzes = db["quizzes"]
quiz_attempts = db["quiz_attempts"]
chat_messages = db["chat_messages"]
chat_rooms = db["chat_rooms"]
video_lectures = db["video_lectures"]
fee_structures = db["fee_structures"]
fee_payments = db["fee_payments"]
fee_settings = db["fee_settings"]
fee_reminders = db["fee_reminders"]
