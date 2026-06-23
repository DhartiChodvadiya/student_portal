from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)

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
# ============ LIVE CHAT ============
chat_messages = db["chat_messages"]
chat_rooms = db["chat_rooms"]     
video_lectures = db["video_lectures"]
fee_structures = db["fee_structures"]
fee_payments = db["fee_payments"]
fee_settings = db["fee_settings"]
fee_reminders = db["fee_reminders"]



