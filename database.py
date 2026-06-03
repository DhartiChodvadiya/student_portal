from pymongo import MongoClient

# MongoDB Connection
client = MongoClient("mongodb+srv://dhartichodvadiya_db_user:dharti%40123@cluster0.rs9mdgp.mongodb.net/")

# Database
db = client["student_portal"]

# Collections
student = db["student"]
admins = db["admins"]
otps = db["otps"]
# mohwexvxsrxncfko