# sync_to_atlas.py
from pymongo import MongoClient

# Local connection
local_client = MongoClient("mongodb://localhost:27017")
local_db = local_client["student_portal"]

# Atlas connection with correct credentials
atlas_client = MongoClient(
    "mongodb+srv://dhartichodvadiya_db_user:DhaRTI9706@cluster0.rs9mdgp.mongodb.net/",
    tlsAllowInvalidCertificates=True,
    tlsAllowInvalidHostnames=True
)

atlas_db = atlas_client["student_portal"]
atlas_db = atlas_client["student_portal"]

# Collections to sync
collections = ['student', 'admins', 'otps', 'attendance', 'marks', 'subjects','courses','enrollments','db','announcement','forum_questions','forum_replies','course_materials','important_materials','quizzes','quiz_attempts','chat_messages','chat_rooms','video_lectures','fee_structures','fee_payments','fee_settings','fee_reminders']

for col_name in collections:
    print(f"Syncing {col_name}...")
    try:
        local_data = list(local_db[col_name].find({}, {"_id": 0}))
        if local_data:
            atlas_db[col_name].delete_many({})
            atlas_db[col_name].insert_many(local_data)
            print(f"  ✅ Synced {len(local_data)} documents")
        else:
            print(f"  ⏭️ No data in {col_name}")
    except Exception as e:
        print(f"  ❌ Error syncing {col_name}: {str(e)}")

print("\n✅ Sync completed!")