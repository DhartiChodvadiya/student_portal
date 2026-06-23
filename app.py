from flask import Flask, request, jsonify, render_template, session
from flask_mail import Mail, Message, Attachment
from database import (
    student,
    admins,
    attendance,
    marks,
    subjects,
    courses,
    enrollments,
    db,
    announcement,
    forum_questions,
    forum_replies,
    course_materials,
    important_materials,
    quizzes,
    quiz_attempts,
    chat_messages,
    chat_rooms,
    video_lectures,
    fee_structures,
    fee_payments,
    fee_settings,
    fee_reminders,
)
import jwt
import re
import urllib.request
import json
import requests
import datetime
from functools import wraps
import hashlib
import random
from flask_cors import CORS
from dotenv import load_dotenv
import os
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename

# Load environment variables FIRST
load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# SECRET KEY
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "your_secret_key_123")
app.config["SESSION_COOKIE_SECURE"] = True

# Razorpay configuration (Add your keys)
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "Put_your_razorpay_keyidhere")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "Put_your_razorpay_keysecret_here")

# Email Configuration
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 465
app.config["MAIL_USE_TLS"] = False
app.config["MAIL_USE_SSL"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "your_email_id@gmail.com")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "your_mail_password")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv(
    "MAIL_DEFAULT_SENDER", "your_email_id@gmail.com"
)

# Configuration for file uploads
UPLOAD_FOLDER = "static/uploads/materials"
ALLOWED_EXTENSIONS = {"pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Ensure upload folders exist
UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "uploads"
)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, "chat_images"), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, "materials"), exist_ok=True)

mail = Mail(app)


# Grade Calculator Function
def calculate_grade(percentage):
    if percentage >= 90:
        return "A+"
    elif percentage >= 80:
        return "A"
    elif percentage >= 70:
        return "B+"
    elif percentage >= 60:
        return "B"
    elif percentage >= 50:
        return "C"
    elif percentage >= 40:
        return "D"
    else:
        return "F"


# JWT FUNCTIONS
def generate_token(user_id, role):
    exp_time = datetime.datetime.now() + datetime.timedelta(hours=2)
    token = jwt.encode(
        {
            "user_id": user_id,
            "role": role,
            "exp": exp_time,
        },
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    return token


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("token")
        if not token:
            return jsonify({"message": "Token is missing"}), 401
        try:
            data = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            current_user = data
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token Expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"message": "Invalid Token"}), 401
        return f(current_user, *args, **kwargs)

    return decorated


# ============ FEE MANAGEMENT ============

# Course fee structure
COURSE_FEES = {
    "BCA": {"base_fee": 15000, "semester_increment": 5000},
    "MCA": {"base_fee": 45000, "semester_increment": 5000},
    "BSC": {"base_fee": 325000, "semester_increment": 5000},
    "MSC": {"base_fee": 50000, "semester_increment": 5000},
    "CA": {"base_fee": 30000, "semester_increment": 5000},
    "BBA": {"base_fee": 11000, "semester_increment": 5000},
    "Cloud Computing": {"base_fee": 35000, "semester_increment": 5000},
}


def calculate_fee(course, semester):
    """Calculate fee based on course and semester"""
    course = course.strip()
    semester_num = int(semester.split()[1]) if semester else 1

    if course in COURSE_FEES:
        base = COURSE_FEES[course]["base_fee"]
        increment = COURSE_FEES[course]["semester_increment"]
        # Fee = base + (semester - 1) * increment
        return base + (semester_num - 1) * increment
    return 0


# ========== ADMIN FEE ENDPOINTS ==========


# Get all fee structures (admin)
@app.route("/api/fee/admin/structures", methods=["GET"])
@token_required
def admin_get_fee_structures(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin access required"}), 403

    try:
        structures = []
        for fee in fee_structures.find().sort("created_at", -1):
            student_data = student.find_one({"student_id": fee["student_id"]})
            structures.append(
                {
                    "id": str(fee["_id"]),
                    "student_id": fee["student_id"],
                    "student_name": student_data["name"] if student_data else "Unknown",
                    "course": student_data["course"] if student_data else "Unknown",
                    "semester": fee.get("semester", ""),
                    "fee_type": fee.get("fee_type", "Tuition Fee"),
                    "total_fee": fee.get("total_fee", 0),
                    "paid_amount": fee.get("paid_amount", 0),
                    "pending_amount": fee.get(
                        "pending_amount", fee.get("total_fee", 0)
                    ),
                    "status": fee.get("status", "Unpaid"),
                    "due_date": fee.get("due_date", ""),
                    "created_at": fee.get("created_at", ""),
                }
            )
        return jsonify(structures), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Generate fee for all students (admin)
@app.route("/api/fee/admin/generate", methods=["POST"])
@token_required
def generate_fees(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin access required"}), 403
    
    try:
        data = request.json
        semester = data.get("semester", "Semester 1")
        
        # Get all students
        all_students = list(student.find({}))
        generated_count = 0
        skipped_count = 0
        skipped_students = []
        
        for stu in all_students:
            course = stu.get("course", "")
            if not course:
                skipped_count += 1
                skipped_students.append(f"{stu.get('name', 'Unknown')} - No course")
                continue
                
            # Calculate fee
            total_fee = calculate_fee(course, semester)
            if total_fee == 0:
                skipped_count += 1
                skipped_students.append(f"{stu.get('name', 'Unknown')} - Fee calculation returned 0")
                continue
            
            # Check if fee already exists for this semester
            existing = fee_structures.find_one({
                "student_id": stu["student_id"],
                "semester": semester
            })
            
            if existing:
                skipped_count += 1
                skipped_students.append(f"{stu.get('name', 'Unknown')} - Fee already exists for {semester}")
                continue
            
            # Create fee structure
            fee = {
                "student_id": stu["student_id"],
                "semester": semester,
                "fee_type": "Tuition Fee",
                "total_fee": total_fee,
                "paid_amount": 0,
                "pending_amount": total_fee,
                "status": "Unpaid",
                "due_date": data.get("due_date", ""),
                "created_at": datetime.datetime.now().isoformat(),
                "created_by": current_user["user_id"]
            }
            
            fee_structures.insert_one(fee)
            generated_count += 1
            
            # Create reminder for student
            create_fee_reminder(stu["student_id"], f"Fee for {semester} is due. Amount: ₹{total_fee:,.2f}")
            
            # Send email notification
            try:
                send_fee_reminder_email(
                    stu["email"],
                    stu["name"],
                    semester,
                    total_fee,
                    data.get("due_date", "")
                )
            except Exception as e:
                print(f"Email notification failed for {stu['email']}: {e}")
        
        # Print detailed summary
        print(f"📊 Fee Generation Summary:")
        print(f"   ✅ Generated: {generated_count} students")
        print(f"   ⏭️ Skipped: {skipped_count} students")
        if skipped_students:
            print(f"   📋 Skipped details:")
            for s in skipped_students[:5]:  # Show first 5
                print(f"      - {s}")
        
        return jsonify({
            "message": f"Generated fees for {generated_count} students, skipped {skipped_count} students",
            "generated_count": generated_count,
            "skipped_count": skipped_count,
            "skipped_students": skipped_students[:10]  # Send first 10 for debugging
        }), 200
        
    except Exception as e:
        print(f"❌ Error generating fees: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": str(e)}), 500

# ============ FEE PAYMENT NOTICE / ANNOUNCEMENT ============
# Admin sends fee payment notice to specific semester
@app.route("/api/fee/announcement", methods=["POST"])
@token_required
def create_fee_announcement(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin access required"}), 403
    
    try:
        data = request.json
        semester = data.get("semester")
        title = data.get("title")
        content = data.get("content")
        due_date = data.get("due_date")
        
        if not semester or not title or not content:
            return jsonify({"message": "Semester, title and content are required"}), 400
        
        # Get all students in this semester
        students_in_semester = list(student.find({"current_semester": semester}))
        
        if not students_in_semester:
            return jsonify({"message": f"No students found in {semester}"}), 404
        
        # Create announcement with type "fee_notice"
        announcement_data = {
            "title": f"{title}",
            "content": f"{content}\n\n📌 Semester: {semester}\n📅 Due Date: {due_date if due_date else 'Not specified'}",
            "priority": "high",
            "date": datetime.datetime.now().isoformat(),
            "semester": semester,
            "type": "fee_notice",  # This identifies it as a fee notice
            "expiry": due_date if due_date else None,
            "created_by": current_user["user_id"]
        }
        
        result = announcement.insert_one(announcement_data)
        
        # Create fee reminders for each student
        reminder_count = 0
        for stu in students_in_semester:
            # Check if fee exists
            existing_fee = fee_structures.find_one({
                "student_id": stu["student_id"],
                "semester": semester
            })
            
            if existing_fee:
                # Create reminder
                create_fee_reminder(
                    stu["student_id"],
                    f" Fee Payment Notice: {title}\nSemester: {semester}\nAmount: ₹{existing_fee.get('total_fee', 0):,.2f}\nDue Date: {due_date if due_date else 'Not specified'}"
                )
                reminder_count += 1
        
        return jsonify({
            "message": f" Fee notice sent to {len(students_in_semester)} students in {semester}",
            "students_count": len(students_in_semester),
            "reminders_created": reminder_count
        }), 200
        
    except Exception as e:
        print(f" Error: {e}")
        return jsonify({"message": str(e)}), 500

# Get unread fee notices for a student
@app.route("/api/fee/notices/<int:student_id>", methods=["GET"])
@token_required
def get_fee_notices(current_user, student_id):
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        return jsonify({"message": "Access Denied"}), 403
    
    try:
        # Get student's semester
        student_data = student.find_one({"student_id": student_id})
        if not student_data:
            return jsonify({"message": "Student not found"}), 404
        
        student_semester = student_data.get("current_semester", "Semester 1")
        
        # Get fee notices for this semester
        notices = []
        for ann in announcement.find({
            "semester": student_semester,
            "type": "fee_notice"
        }).sort("date", -1):
            notices.append({
                "_id": str(ann["_id"]),
                "title": ann.get("title", ""),
                "content": ann.get("content", ""),
                "date": ann.get("date", ""),
                "semester": ann.get("semester", ""),
                "expiry": ann.get("expiry", None)
            })
        
        # Check if student has any unread notices
        read_notices = json.loads(localStorage.getItem('readFeeNotices') or '[]')
        
        return jsonify({
            "notices": notices,
            "count": len(notices),
            "unread_count": len([n for n in notices if n["_id"] not in read_notices])
        }), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

# Mark a fee notice as read
@app.route("/api/fee/notice/read/<notice_id>", methods=["POST"])
@token_required
def mark_fee_notice_read(current_user, notice_id):
    try:
        # This is just a marker, we use localStorage on frontend
        return jsonify({"message": "Notice marked as read"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
# Get fee announcements for a student (only their semester)
@app.route("/api/fee/announcements/<int:student_id>", methods=["GET"])
@token_required
def get_fee_announcements(current_user, student_id):
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        return jsonify({"message": "Access Denied"}), 403

    try:
        # Get student's semester
        student_data = student.find_one({"student_id": student_id})
        if not student_data:
            return jsonify({"message": "Student not found"}), 404

        student_semester = student_data.get("current_semester", "Semester 1")

        # Get announcements for this semester
        announcements_list = []
        for ann in announcement.find({"semester": student_semester}).sort("date", -1):
            announcements_list.append(
                {
                    "_id": str(ann["_id"]),
                    "title": ann.get("title", ""),
                    "content": ann.get("content", ""),
                    "priority": ann.get("priority", "normal"),
                    "date": ann.get("date", ""),
                    "expiry": ann.get("expiry", None),
                    "semester": ann.get("semester", ""),
                }
            )

        return (
            jsonify(
                {
                    "semester": student_semester,
                    "announcements": announcements_list,
                    "count": len(announcements_list),
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Add fee structure (admin) - Manual add if needed
@app.route("/api/fee/admin/add", methods=["POST"])
@token_required
def admin_add_fee_structure(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin access required"}), 403

    try:
        data = request.json
        student_id = data.get("student_id")

        # Check if student exists
        student_data = student.find_one({"student_id": student_id})
        if not student_data:
            return jsonify({"message": f"Student with ID {student_id} not found"}), 404

        semester = data.get("semester", "Semester 1")
        course = student_data.get("course", "")

        # Calculate fee automatically
        total_fee = calculate_fee(course, semester)
        if total_fee == 0:
            return (
                jsonify({"message": f"Could not calculate fee for course: {course}"}),
                400,
            )

        # Check if fee structure already exists for this semester
        existing = fee_structures.find_one(
            {"student_id": student_id, "semester": semester}
        )

        if existing:
            return (
                jsonify({"message": "Fee structure for this semester already exists"}),
                400,
            )

        fee = {
            "student_id": student_id,
            "semester": semester,
            "fee_type": "Tuition Fee",
            "total_fee": total_fee,
            "paid_amount": 0,
            "pending_amount": total_fee,
            "status": "Unpaid",
            "due_date": data.get("due_date", ""),
            "created_at": datetime.datetime.now().isoformat(),
            "created_by": current_user["user_id"],
        }

        result = fee_structures.insert_one(fee)

        # Create reminder for student
        create_fee_reminder(
            student_id, f"Fee for {semester} is due. Amount: ₹{total_fee:,.2f}"
        )

        # Send email notification
        try:
            send_fee_reminder_email(
                student_data["email"],
                student_data["name"],
                semester,
                total_fee,
                data.get("due_date", ""),
            )
        except Exception as e:
            print(f"Email notification failed: {e}")

        return (
            jsonify(
                {
                    "message": "Fee structure added successfully",
                    "id": str(result.inserted_id),
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Update fee structure (admin)
@app.route("/api/fee/admin/update/<fee_id>", methods=["PUT"])
@token_required
def admin_update_fee_structure(current_user, fee_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin access required"}), 403

    try:
        data = request.json
        update_data = {}

        if "total_fee" in data:
            total_fee = data["total_fee"]
            fee = fee_structures.find_one({"_id": ObjectId(fee_id)})
            paid_amount = fee.get("paid_amount", 0) if fee else 0
            update_data["total_fee"] = total_fee
            update_data["pending_amount"] = total_fee - paid_amount

        if "status" in data:
            update_data["status"] = data["status"]
        if "due_date" in data:
            update_data["due_date"] = data["due_date"]
        if "semester" in data:
            update_data["semester"] = data["semester"]

        if update_data:
            result = fee_structures.update_one(
                {"_id": ObjectId(fee_id)}, {"$set": update_data}
            )
            if result.modified_count > 0:
                return jsonify({"message": "Fee structure updated successfully"}), 200

        return jsonify({"message": "No changes made"}), 200

    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Delete fee structure (admin)
@app.route("/api/fee/admin/delete/<fee_id>", methods=["DELETE"])
@token_required
def admin_delete_fee_structure(current_user, fee_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin access required"}), 403

    try:
        result = fee_structures.delete_one({"_id": ObjectId(fee_id)})
        if result.deleted_count > 0:
            return jsonify({"message": "Fee structure deleted successfully"}), 200
        return jsonify({"message": "Fee structure not found"}), 404
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# ========== STUDENT FEE ENDPOINTS ==========


# Get student fee structure
@app.route("/api/fee/student/<int:student_id>", methods=["GET"])
@token_required
def get_student_fee(current_user, student_id):
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        return jsonify({"message": "Access Denied"}), 403

    try:
        fees = []
        for fee in fee_structures.find({"student_id": student_id}).sort(
            "created_at", -1
        ):
            fees.append(
                {
                    "id": str(fee["_id"]),
                    "semester": fee.get("semester", ""),
                    "fee_type": fee.get("fee_type", "Tuition Fee"),
                    "total_fee": fee.get("total_fee", 0),
                    "paid_amount": fee.get("paid_amount", 0),
                    "pending_amount": fee.get(
                        "pending_amount", fee.get("total_fee", 0)
                    ),
                    "status": fee.get("status", "Unpaid"),
                    "due_date": fee.get("due_date", ""),
                }
            )

        # Calculate totals
        total_fee = sum(f["total_fee"] for f in fees)
        total_paid = sum(f["paid_amount"] for f in fees)
        total_pending = total_fee - total_paid

        # Check if student has any pending fees for reminder
        has_pending = any(f["pending_amount"] > 0 for f in fees)

        return (
            jsonify(
                {
                    "fees": fees,
                    "summary": {
                        "total_fee": total_fee,
                        "total_paid": total_paid,
                        "total_pending": total_pending,
                        "has_pending": has_pending,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Get student fee summary (for dashboard)
@app.route("/api/fee/summary/<int:student_id>", methods=["GET"])
@token_required
def get_fee_summary(current_user, student_id):
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        return jsonify({"message": "Access Denied"}), 403

    try:
        fees = list(fee_structures.find({"student_id": student_id}))

        total_fee = sum(f.get("total_fee", 0) for f in fees)
        total_paid = sum(f.get("paid_amount", 0) for f in fees)
        total_pending = total_fee - total_paid
        has_pending = any(f.get("pending_amount", 0) > 0 for f in fees)

        # Get recent payments
        payments = list(
            fee_payments.find({"student_id": student_id})
            .sort("payment_date", -1)
            .limit(3)
        )
        recent_payments = []
        for p in payments:
            recent_payments.append(
                {
                    "amount": p.get("amount", 0),
                    "payment_date": p.get("payment_date", ""),
                    "receipt_number": p.get("receipt_number", ""),
                }
            )

        return (
            jsonify(
                {
                    "total_fee": total_fee,
                    "total_paid": total_paid,
                    "total_pending": total_pending,
                    "total_pending_formatted": f"₹{total_pending:,.2f}",
                    "total_fee_formatted": f"₹{total_fee:,.2f}",
                    "total_paid_formatted": f"₹{total_paid:,.2f}",
                    "has_pending": has_pending,
                    "recent_payments": recent_payments,
                    "total_payments": fee_payments.count_documents(
                        {"student_id": student_id}
                    ),
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Record payment (student)
@app.route("/api/fee/pay", methods=["POST"])
@token_required
def record_fee_payment(current_user):
    data = request.json
    student_id = data.get("student_id")

    # If student is paying, use their own ID
    if current_user["role"] == "student":
        student_id = current_user["user_id"]

    # Verify student exists
    student_data = student.find_one({"student_id": student_id})
    if not student_data:
        return jsonify({"message": "Student not found"}), 404

    amount = data.get("amount", 0)
    fee_structure_id = data.get("fee_structure_id")
    payment_method = data.get("payment_method", "Razorpay")
    transaction_id = data.get("transaction_id", "")

    # Generate receipt number
    receipt_number = f"REC-{datetime.datetime.now().strftime('%Y%m%d')}-{student_id}-{int(time.time()) % 10000}"

    payment = {
        "student_id": student_id,
        "fee_structure_id": fee_structure_id,
        "amount": amount,
        "payment_method": payment_method,
        "status": "Success",
        "payment_date": datetime.datetime.now().isoformat(),
        "receipt_number": receipt_number,
        "transaction_id": transaction_id,
        "created_at": datetime.datetime.now().isoformat(),
    }

    result = fee_payments.insert_one(payment)

    # Update fee structure paid amount
    if fee_structure_id:
        fee = fee_structures.find_one({"_id": ObjectId(fee_structure_id)})
        if fee:
            new_paid = fee.get("paid_amount", 0) + amount
            new_pending = fee.get("total_fee", 0) - new_paid
            status = "Paid" if new_pending <= 0 else "Unpaid"

            fee_structures.update_one(
                {"_id": ObjectId(fee_structure_id)},
                {
                    "$set": {
                        "paid_amount": new_paid,
                        "pending_amount": new_pending,
                        "status": status,
                    }
                },
            )

            # If fully paid, remove reminder
            if status == "Paid":
                fee_reminders.update_one(
                    {"student_id": student_id, "fee_structure_id": fee_structure_id},
                    {
                        "$set": {
                            "resolved": True,
                            "resolved_at": datetime.datetime.now().isoformat(),
                        }
                    },
                )

    # Send payment confirmation email
    try:
        send_payment_confirmation_email(
            student_data["email"],
            student_data["name"],
            amount,
            receipt_number,
            payment_method,
        )
    except Exception as e:
        print(f"Email notification failed: {e}")

    return (
        jsonify(
            {
                "message": "Payment recorded successfully",
                "receipt_number": receipt_number,
                "id": str(result.inserted_id),
            }
        ),
        200,
    )


# ========== FEE REMINDERS ==========


def create_fee_reminder(student_id, message):
    """Create a fee reminder for a student"""
    fee_reminders.insert_one(
        {
            "student_id": student_id,
            "message": message,
            "created_at": datetime.datetime.now().isoformat(),
            "read": False,
            "resolved": False,
            "resolved_at": None,
        }
    )


# Get fee reminders for student
@app.route("/api/fee/reminders/<int:student_id>", methods=["GET"])
@token_required
def get_fee_reminders(current_user, student_id):
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        return jsonify({"message": "Access Denied"}), 403

    try:
        reminders = []
        for r in fee_reminders.find({"student_id": student_id, "resolved": False}).sort(
            "created_at", -1
        ):
            reminders.append(
                {
                    "id": str(r["_id"]),
                    "message": r.get("message", ""),
                    "created_at": r.get("created_at", ""),
                    "read": r.get("read", False),
                }
            )
        return jsonify(reminders), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Mark reminder as read
@app.route("/api/fee/reminders/read/<reminder_id>", methods=["PUT"])
@token_required
def mark_reminder_read(current_user, reminder_id):
    try:
        result = fee_reminders.update_one(
            {"_id": ObjectId(reminder_id)}, {"$set": {"read": True}}
        )
        if result.modified_count > 0:
            return jsonify({"message": "Reminder marked as read"}), 200
        return jsonify({"message": "Reminder not found"}), 404
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Mark all reminders as read
@app.route("/api/fee/reminders/read/all/<int:student_id>", methods=["PUT"])
@token_required
def mark_all_reminders_read(current_user, student_id):
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        return jsonify({"message": "Access Denied"}), 403

    try:
        result = fee_reminders.update_many(
            {"student_id": student_id, "resolved": False}, {"$set": {"read": True}}
        )
        return (
            jsonify({"message": f"Marked {result.modified_count} reminders as read"}),
            200,
        )
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# ========== PAYMENT HISTORY ==========


# Get student payment history
@app.route("/api/fee/payments/<int:student_id>", methods=["GET"])
@token_required
def get_student_payments(current_user, student_id):
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        return jsonify({"message": "Access Denied"}), 403

    try:
        payments = []
        for p in fee_payments.find({"student_id": student_id}).sort("payment_date", -1):
            # Get semester info from fee structure
            fee = None
            if p.get("fee_structure_id"):
                fee = fee_structures.find_one({"_id": ObjectId(p["fee_structure_id"])})

            payments.append(
                {
                    "id": str(p["_id"]),
                    "amount": p.get("amount", 0),
                    "payment_method": p.get("payment_method", ""),
                    "payment_date": p.get("payment_date", ""),
                    "receipt_number": p.get("receipt_number", ""),
                    "transaction_id": p.get("transaction_id", ""),
                    "semester": fee.get("semester", "") if fee else "",
                    "status": p.get("status", "Success"),
                }
            )
        return jsonify({"payments": payments}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Get single payment by receipt number
@app.route("/api/fee/payment/<receipt_number>", methods=["GET"])
@token_required
def get_payment_by_receipt(current_user, receipt_number):
    try:
        print(f"🔍 Looking for payment with receipt: {receipt_number}")

        payment = fee_payments.find_one({"receipt_number": receipt_number})
        if not payment:
            print(f"❌ Payment not found: {receipt_number}")
            return jsonify({"message": "Payment not found"}), 404

        print(f"✅ Payment found: {payment}")

        # Check if user has access
        if (
            current_user["role"] == "student"
            and payment["student_id"] != current_user["user_id"]
        ):
            return jsonify({"message": "Access Denied"}), 403

        # Get student data for course
        student_data = student.find_one({"student_id": payment["student_id"]})
        course = student_data.get("course", "N/A") if student_data else "N/A"
        student_name = (
            student_data.get("name", "Student") if student_data else "Student"
        )

        # Get semester info
        semester = "N/A"
        if payment.get("fee_structure_id"):
            try:
                fee = fee_structures.find_one(
                    {"_id": ObjectId(payment["fee_structure_id"])}
                )
                if fee:
                    semester = fee.get("semester", "N/A")
            except Exception as e:
                print(f"Error getting fee: {e}")

        return (
            jsonify(
                {
                    "receipt_number": payment.get("receipt_number"),
                    "payment_date": payment.get("payment_date"),
                    "amount": payment.get("amount"),
                    "payment_method": payment.get("payment_method"),
                    "transaction_id": payment.get("transaction_id"),
                    "status": payment.get("status"),
                    "semester": semester,
                    "course": course,
                    "student_name": student_name,
                }
            ),
            200,
        )
    except Exception as e:
        print(f"❌ Error fetching payment: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"message": str(e)}), 500


# Check fee reminders on student login
@app.route("/api/fee/check-reminders/<int:student_id>", methods=["GET"])
@token_required
def check_fee_reminders(current_user, student_id):
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        return jsonify({"message": "Access Denied"}), 403

    try:
        # Get all pending fee structures
        pending_fees = list(
            fee_structures.find({"student_id": student_id, "status": "Unpaid"})
        )

        reminders = []
        for fee in pending_fees:
            if fee.get("pending_amount", 0) > 0:
                reminders.append(
                    {
                        "fee_id": str(fee["_id"]),
                        "semester": fee.get("semester", ""),
                        "pending_amount": fee.get("pending_amount", 0),
                        "due_date": fee.get("due_date", ""),
                        "status": fee.get("status", "Unpaid"),
                    }
                )

        return (
            jsonify(
                {
                    "has_pending": len(reminders) > 0,
                    "reminders": reminders,
                    "total_pending": sum(r["pending_amount"] for r in reminders),
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# ========== EMAIL NOTIFICATIONS ==========


def send_fee_reminder_email(student_email, student_name, semester, amount, due_date):
    """Send fee reminder email to student"""
    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                .container {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .fee-details {{ background: white; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
                .btn {{ display: inline-block; background: #667eea; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>💰 Fee Payment Reminder</h2>
                </div>
                <div class="content">
                    <p>Dear <strong>{student_name}</strong>,</p>
                    <p>A new fee structure has been added to your account.</p>
                    <div class="fee-details">
                        <p><strong>Semester:</strong> {semester}</p>
                        <p><strong>Total Amount:</strong> ₹{amount:,.2f}</p>
                        <p><strong>Due Date:</strong> {due_date if due_date else 'Not specified'}</p>
                    </div>
                    <p style="text-align:center;">
                        <a href="http://localhost:5000/fee" class="btn">Pay Now</a>
                    </p>
                    <p>Best regards,<br><strong>Student Portal Team</strong></p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg = Message(
            subject=f"💰 Fee Payment Reminder - {semester}",
            recipients=[student_email],
            html=html_content,
        )
        mail.send(msg)
        print(f"Fee reminder email sent to {student_email}")
        return True
    except Exception as e:
        print(f"Failed to send fee reminder email: {e}")
        return False


def send_payment_confirmation_email(
    student_email, student_name, amount, receipt_number, method
):
    """Send payment confirmation email"""
    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                .container {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .payment-details {{ background: white; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: center; }}
                .amount {{ font-size: 36px; font-weight: bold; color: #10b981; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>✅ Payment Confirmation</h2>
                </div>
                <div class="content">
                    <p>Dear <strong>{student_name}</strong>,</p>
                    <p>Your payment has been successfully processed.</p>
                    <div class="payment-details">
                        <p><strong>Amount:</strong></p>
                        <div class="amount">₹{amount:,.2f}</div>
                        <p><strong>Receipt Number:</strong> {receipt_number}</p>
                        <p><strong>Payment Method:</strong> {method}</p>
                    </div>
                    <p>You can view and download your receipt from the student portal.</p>
                    <p>Best regards,<br><strong>Student Portal Team</strong></p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg = Message(
            subject=f"✅ Payment Confirmation - {receipt_number}",
            recipients=[student_email],
            html=html_content,
        )
        mail.send(msg)
        print(f"Payment confirmation email sent to {student_email}")
        return True
    except Exception as e:
        print(f"Failed to send payment confirmation email: {e}")
        return False

    def send_fee_announcement_email(
        student_email, student_name, semester, title, content, amount, due_date
    ):
        """Send fee announcement email to student"""

    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                .container {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .fee-details {{ background: white; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .amount {{ font-size: 32px; font-weight: bold; color: #667eea; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
                .btn {{ display: inline-block; background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; }}
                .highlight {{ background: #fef3c7; padding: 10px; border-radius: 5px; border-left: 4px solid #f59e0b; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>💰 Fee Payment Notice</h2>
                </div>
                <div class="content">
                    <p>Dear <strong>{student_name}</strong>,</p>
                    <div class="highlight">
                        <p><strong>📢 {title}</strong></p>
                        <p>{content}</p>
                    </div>
                    <div class="fee-details">
                        <p><strong>📌 Semester:</strong> {semester}</p>
                        <p><strong>💰 Amount:</strong> <span class="amount">₹{amount:,.2f}</span></p>
                        <p><strong>📅 Due Date:</strong> {due_date if due_date else 'Not specified'}</p>
                    </div>
                    <p style="text-align:center; margin-top: 20px;">
                        <a href="http://localhost:5000/fee" class="btn">Pay Now</a>
                    </p>
                    <p style="margin-top: 20px;">Best regards,<br><strong>Student Portal Team</strong></p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg = Message(
            subject=f"💰 Fee Payment Notice - {semester}",
            recipients=[student_email],
            html=html_content,
        )
        mail.send(msg)
        print(f"Fee announcement email sent to {student_email}")
        return True
    except Exception as e:
        print(f"Failed to send fee announcement email: {e}")
        return False


# HOME
@app.route("/")
def home():
    return jsonify({"message": "Student Portal Backend Running"})


@app.route("/student")
def student_portal():
    return render_template("student.html")


@app.route("/admin")
def admin_portal():
    return render_template("admin.html")


@app.route("/quiz.html")
def quiz_page():
    return render_template("quiz.html")


@app.route("/fee")
def fee_page():
    return render_template("fee.html")

@app.route('/test')
def test():
    return "✅ Server is working! App is LIVE!"


# STUDENT REGISTER
@app.route("/student/register", methods=["POST"])
def student_register():
    data = request.json
    existing_student = student.find_one({"student_id": data["student_id"]})
    existing_email = student.find_one({"email": data["email"]})
    if existing_student:
        return jsonify({"message": "Student ID already exists"}), 400
    if existing_email:
        return jsonify({"message": "Email already exists"}), 400
    hashed_password = hashlib.sha256(data["password"].encode()).hexdigest()
    
    # Get semester from registration data
    current_semester = data.get("current_semester", "Semester 1")
    
    student.insert_one(
        {
            "student_id": data["student_id"],
            "name": data["name"],
            "email": data["email"],
            "password": hashed_password,
            "course": data["course"],
            "phoneno": data["phoneno"],
            "gender": data["gender"],
            "current_semester": current_semester,  # ✅ This saves the semester
            "created_at": datetime.datetime.now().isoformat()
        }
    )
    token = generate_token(data["student_id"], "student")
    return jsonify({"message": "Student Registered Successfully", "token": token})

# STUDENT LOGIN
@app.route("/student/login", methods=["POST"])
def student_login():
    data = request.json
    student_data = student.find_one({"email": data["email"]})
    if not student_data:
        return jsonify({"message": "Student Not Found"}), 404
    hashed_password = hashlib.sha256(data["password"].encode()).hexdigest()
    if student_data["password"] != hashed_password:
        return jsonify({"message": "Invalid Password"}), 401
    token = generate_token(student_data["student_id"], "student")
    return jsonify(
        {
            "message": "Student Login Successful",
            "token": token,
            "student_id": student_data["student_id"],
            "name": student_data["name"],
            "email": student_data["email"],
            "course": student_data["course"],
            "phoneno": student_data["phoneno"],
            "gender": student_data["gender"],
        }
    )


# FORGOT PASSWORD
@app.route("/student/forgot_password", methods=["POST"])
def forgot_password():
    data = request.json
    email = data.get("email")
    student_data = student.find_one({"email": email})
    if not student_data:
        return jsonify({"message": "No account found with this email address"}), 404
    otp = str(random.randint(100000, 999999))
    otps.delete_many({"email": email})
    otps.insert_one(
        {"email": email, "otp": otp, "created_at": datetime.datetime.utcnow()}
    )
    try:
        msg = Message(
            subject="Password Reset OTP - Student Portal",
            recipients=[email],
            html=f"<h2>Your OTP is: {otp}</h2><p>Valid for 5 minutes.</p>",  # Changed from 10 to 5
        )
        mail.send(msg)
        return jsonify({"message": f"OTP sent to {email}. Check your inbox."}), 200
    except Exception as e:
        return jsonify({"message": f"Test OTP: {otp}", "otp": otp}), 200


# VERIFY OTP
@app.route("/student/verify_otp", methods=["POST"])
def verify_otp():
    data = request.json
    otp_data = otps.find_one({"email": data["email"], "otp": data["otp"]})
    if not otp_data:
        return jsonify({"message": "Invalid OTP"}), 400
    created_at = otp_data.get("created_at")
    # CHANGE FROM 600 TO 300 (5 minutes)
    if created_at and (datetime.datetime.utcnow() - created_at).seconds > 300:
        otps.delete_many({"email": data["email"]})
        return jsonify({"message": "OTP has expired"}), 400
    return jsonify({"message": "OTP verified successfully"}), 200


# RESET PASSWORD
@app.route("/student/reset_password", methods=["POST"])
def reset_password():
    data = request.json
    otp_data = otps.find_one({"email": data["email"], "otp": data["otp"]})
    if not otp_data:
        return jsonify({"message": "Invalid OTP"}), 400
    created_at = otp_data.get("created_at")
    # CHANGE FROM 600 TO 300 (5 minutes)
    if created_at and (datetime.datetime.utcnow() - created_at).seconds > 300:
        otps.delete_many({"email": data["email"]})
        return jsonify({"message": "OTP has expired"}), 400
    if len(data["new_password"]) < 6:
        return jsonify({"message": "Password must be at least 6 characters"}), 400
    hashed_password = hashlib.sha256(data["new_password"].encode()).hexdigest()
    student.update_one(
        {"email": data["email"]}, {"$set": {"password": hashed_password}}
    )
    otps.delete_many({"email": data["email"]})
    return jsonify({"message": "Password reset successful!"}), 200


# CHANGE PASSWORD
@app.route("/student/change_password", methods=["POST"])
@token_required
def change_password(current_user):
    data = request.json
    student_data = student.find_one({"student_id": current_user["user_id"]})
    if not student_data:
        return jsonify({"message": "Student not found"}), 404
    hashed_old = hashlib.sha256(data["old_password"].encode()).hexdigest()
    if student_data["password"] != hashed_old:
        return jsonify({"message": "Current password is incorrect"}), 401
    if len(data["new_password"]) < 6:
        return jsonify({"message": "Password must be at least 6 characters"}), 400
    hashed_new = hashlib.sha256(data["new_password"].encode()).hexdigest()
    student.update_one(
        {"student_id": current_user["user_id"]}, {"$set": {"password": hashed_new}}
    )
    return jsonify({"message": "Password changed successfully!"}), 200


# GET ALL STUDENTS
@app.route("/students", methods=["GET"])
@token_required
def get_students(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    all_students = []
    for stu in student.find({}, {"_id": 0}):
        all_students.append(stu)
    return jsonify(all_students)


# GET STUDENT BY ID
@app.route("/student/<int:student_id>", methods=["GET"])
@token_required
def get_student(current_user, student_id):
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        return jsonify({"message": "Access Denied"}), 403
    student_data = student.find_one({"student_id": student_id}, {"_id": 0})
    if student_data:
        # Make sure current_semester is included
        if "current_semester" not in student_data:
            student_data["current_semester"] = "Semester 1"
        return jsonify(student_data)
    return jsonify({"message": "Student Not Found"})

# UPDATE STUDENT
@app.route("/student/update/<int:student_id>", methods=["PUT"])
@token_required
def update_student(current_user, student_id):
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        return jsonify({"message": "Access Denied"}), 403
    data = request.json
    existing_email = student.find_one(
        {"email": data["email"], "student_id": {"$ne": student_id}}
    )
    if existing_email:
        return jsonify({"message": "Email already exists"}), 400
    result = student.update_one(
        {"student_id": student_id},
        {
            "$set": {
                "name": data["name"],
                "email": data["email"],
                "course": data["course"],
                "phoneno": data["phoneno"],
                "gender": data["gender"],
            }
        },
    )
    if data.get("password") and data["password"] != "":
        student.update_one(
            {"student_id": student_id},
            {
                "$set": {
                    "password": hashlib.sha256(data["password"].encode()).hexdigest()
                }
            },
        )
    if result.modified_count > 0:
        return jsonify({"message": "Student Updated Successfully"})
    return jsonify({"message": "Student Not Found"})


# DELETE STUDENT
@app.route("/student/delete/<int:student_id>", methods=["DELETE"])
@token_required
def delete_student(current_user, student_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    result = student.delete_one({"student_id": student_id})
    if result.deleted_count > 0:
        return jsonify({"message": "Student Deleted Successfully"})
    return jsonify({"message": "Student Not Found"})


# ========== EMAIL NOTIFICATION FUNCTIONS ==========


def send_enrollment_email(student_email, student_name, course_name):
    """Send email when student enrolls in a course"""
    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                .container {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .course-name {{ font-size: 24px; color: #667eea; font-weight: bold; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🎓 Course Enrollment Confirmation</h2>
                </div>
                <div class="content">
                    <p>Dear <strong>{student_name}</strong>,</p>
                    <p>You have successfully enrolled in:</p>
                    <div style="text-align: center; margin: 20px 0;">
                        <div class="course-name">{course_name}</div>
                    </div>
                    <p>You can now access all course materials and track your progress in the student portal.</p>
                    <p>Best of luck with your learning journey!</p>
                </div>
                <div class="footer">
                    <p>Student Portal Team</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg = Message(
            subject=f"✅ Course Enrollment Confirmation - {course_name}",
            recipients=[student_email],
            html=html_content,
        )
        mail.send(msg)
        print(f"Enrollment email sent to {student_email}")
        return True
    except Exception as e:
        print(f"Failed to send enrollment email: {e}")
        return False


def send_marks_published_email(
    student_email,
    student_name,
    subject_name,
    marks_obtained,
    total_marks,
    percentage,
    grade,
    exam_type,
):
    """Send email when marks are published"""
    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                .container {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .marks-card {{ background: white; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .percentage {{ font-size: 36px; font-weight: bold; color: #667eea; }}
                .grade {{ font-size: 24px; font-weight: bold; color: {'#10b981' if grade[0] in ['A','B'] else '#f59e0b' if grade[0] == 'C' else '#ef4444'}; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>📊 Results Published</h2>
                </div>
                <div class="content">
                    <p>Dear <strong>{student_name}</strong>,</p>
                    <p>Your marks for <strong>{exam_type}</strong> examination have been published.</p>
                    <div class="marks-card">
                        <h3>{subject_name}</h3>
                        <p>Marks: {marks_obtained} / {total_marks}</p>
                        <div class="percentage">{percentage}%</div>
                        <div class="grade">Grade: {grade}</div>
                    </div>
                    <p>Login to the student portal to view your complete results.</p>
                </div>
                <div class="footer">
                    <p>Student Portal Team</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg = Message(
            subject=f"📊 Results Published - {subject_name} ({exam_type})",
            recipients=[student_email],
            html=html_content,
        )
        mail.send(msg)
        print(f"Marks email sent to {student_email}")
        return True
    except Exception as e:
        print(f"Failed to send marks email: {e}")
        return False


def send_low_attendance_alert(student_email, student_name, attendance_percentage):
    """Send alert when attendance falls below 75%"""
    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                .container {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #ef4444, #dc2626); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .warning {{ background: #fee2e2; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: center; border-left: 4px solid #ef4444; }}
                .percentage {{ font-size: 48px; font-weight: bold; color: #ef4444; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>⚠️ Low Attendance Alert</h2>
                </div>
                <div class="content">
                    <p>Dear <strong>{student_name}</strong>,</p>
                    <div class="warning">
                        <p>Your attendance has fallen below the required 75%!</p>
                        <div class="percentage">{attendance_percentage}%</div>
                        <p>Current Attendance: <strong>{attendance_percentage}%</strong></p>
                    </div>
                    <p>Please ensure regular attendance to avoid academic consequences.</p>
                    <p>Contact your class teacher if you have any concerns.</p>
                </div>
                <div class="footer">
                    <p>Student Portal Team</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg = Message(
            subject=f"⚠️ Low Attendance Alert - {attendance_percentage}%",
            recipients=[student_email],
            html=html_content,
        )
        mail.send(msg)
        print(f"Low attendance alert sent to {student_email}")
        return True
    except Exception as e:
        print(f"Failed to send attendance alert: {e}")
        return False


def check_attendance_and_alert(student_id):
    """Check if student attendance is below 75% and send alert"""
    student_data = student.find_one({"student_id": student_id})
    if not student_data:
        return

    attendances = list(attendance.find({"student_id": student_id}))
    if not attendances:
        return

    total = len(attendances)
    present = sum(1 for a in attendances if a["status"] == "Present")
    late = sum(1 for a in attendances if a["status"] == "Late")
    effective_present = present + (late * 0.5)
    percentage = (effective_present / total * 100) if total > 0 else 0

    if percentage < 75:
        send_low_attendance_alert(
            student_data["email"], student_data["name"], round(percentage, 2)
        )


# ========== SEND RESULTS AS PDF VIA EMAIL ==========
def send_results_pdf_email(student_email, student_name, student_id, course, pdf_base64):
    """Send results as PDF attachment via email"""
    try:
        import base64

        # Decode base64 PDF data
        if "," in pdf_base64:
            pdf_data = base64.b64decode(pdf_base64.split(",")[1])
        else:
            pdf_data = base64.b64decode(pdf_base64)

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                .container {{ font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .info-box {{ background: white; padding: 15px; border-radius: 8px; margin: 20px 0; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
                .button {{ display: inline-block; background: #667eea; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>📄 Your Results Are Ready!</h2>
                </div>
                <div class="content">
                    <p>Dear <strong>{student_name}</strong>,</p>
                    <p>Your academic results have been published. Please find attached your results PDF.</p>
                    
                    <div class="info-box">
                        <p><strong>📋 Student Information</strong></p>
                        <p>Student ID: <strong>{student_id}</strong><br>
                        Course: <strong>{course}</strong><br>
                        Date: <strong>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</strong></p>
                    </div>
                    
                    <p>The PDF attachment contains your complete results including subject-wise marks, percentage, and overall grade.</p>
                    
                    <p>You can also log in to the student portal anytime to view your results online.</p>
                    
                    <p>Best regards,<br><strong>Student Portal Team</strong></p>
                </div>
                <div class="footer">
                    <p>This is an automatically generated email. Please do not reply.</p>
                    <p>Student Portal | Your Academic Journey Companion</p>
                </div>
            </div>
        </body>
        </html>
        """

        msg = Message(
            subject=f"📄 Your Results PDF - {student_name} (ID: {student_id})",
            recipients=[student_email],
            html=html_content,
        )

        # Attach PDF
        from email.mime.base import MIMEBase
        from email import encoders
        import io

        mime_part = MIMEBase("application", "pdf")
        mime_part.set_payload(pdf_data)
        encoders.encode_base64(mime_part)
        mime_part.add_header(
            "Content-Disposition",
            f'attachment; filename="Results_{student_name.replace(" ", "_")}.pdf"',
        )
        msg.attach(mime_part)

        mail.send(msg)
        print(f"Results PDF email sent to {student_email}")
        return True
    except Exception as e:
        print(f"Failed to send results PDF email: {e}")
        return False


def get_youtube_duration(video_url):
    """Extract YouTube video duration using urllib (no extra dependencies)"""
    try:
        # Extract video ID
        video_id = None
        patterns = [
            r"(?:youtube\.com\/watch\?v=)([^&]+)",
            r"(?:youtu\.be\/)([^?]+)",
            r"(?:youtube\.com\/embed\/)([^?]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, video_url)
            if match:
                video_id = match.group(1)
                break

        if not video_id:
            print(f"⚠️ Could not extract video ID from: {video_url}")
            return "N/A"

        # Use YouTube API with urllib
        api_url = f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={video_id}&key=AIzaSyB4kFbKhF7yIuLQ3n2q8OqFz3w8GX3Q4M"

        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get("items") and len(data["items"]) > 0:
                duration_iso = data["items"][0]["contentDetails"]["duration"]
                formatted = format_duration(duration_iso)
                print(f"✅ Found duration: {formatted} for video ID: {video_id}")
                return formatted

        print(f"⚠️ No duration found for video ID: {video_id}")
        return "N/A"
    except Exception as e:
        print(f"❌ Error fetching duration: {e}")
        return "N/A"


def format_duration(duration_iso):
    """Convert ISO 8601 duration to HH:MM:SS or MM:SS"""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_iso)
    if not match:
        return "N/A"

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"


# API endpoint to send results as PDF
@app.route("/send_results_pdf", methods=["POST", "OPTIONS"])
def send_results_pdf():
    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
        return "", 200

    try:
        print("=" * 50)
        print("POST request received at /send_results_pdf")

        # Get request data
        request_data = request.json
        if not request_data:
            return jsonify({"success": False, "message": "No data received"}), 400

        student_id = request_data.get("student_id")
        pdf_base64 = request_data.get("pdf_base64")

        print(f"Student ID: {student_id}")
        print(f"PDF Base64 length: {len(pdf_base64) if pdf_base64 else 0}")

        if not pdf_base64:
            return jsonify({"success": False, "message": "PDF data is missing"}), 400

        # Get student details
        student_data = student.find_one({"student_id": student_id})
        if not student_data:
            return jsonify({"success": False, "message": "Student not found"}), 404

        print(f"Student found: {student_data['name']} - {student_data['email']}")

        # Decode PDF
        import base64

        if "base64," in pdf_base64:
            pdf_data = base64.b64decode(pdf_base64.split("base64,")[1])
        elif "," in pdf_base64:
            pdf_data = base64.b64decode(pdf_base64.split(",")[1])
        else:
            pdf_data = base64.b64decode(pdf_base64)

        print(f"PDF data size: {len(pdf_data)} bytes")

        # Create email
        msg = Message(
            subject=f"Your Results PDF - {student_data['name']}",
            recipients=[student_data["email"]],
            html=f"""
            <html>
            <body>
                <h2>Your Results Are Ready!</h2>
                <p>Dear {student_data['name']},</p>
                <p>Your academic results have been published. Please find attached your results PDF.</p>
                <p><strong>Student ID:</strong> {student_id}<br>
                <strong>Course:</strong> {student_data.get('course', 'Not enrolled')}<br>
                <strong>Date:</strong> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Best regards,<br>Student Portal Team</p>
            </body>
            </html>
            """,
        )

        # Attach PDF
        from flask_mail import Attachment

        attachment = Attachment(
            filename=f"Results_{student_data['name'].replace(' ', '_')}.pdf",
            content_type="application/pdf",
            data=pdf_data,
            disposition="attachment",
        )
        msg.attachments.append(attachment)

        print("Sending email...")
        mail.send(msg)
        print("Email sent successfully!")
        print("=" * 50)

        return jsonify(
            {"success": True, "message": f"Results PDF sent to {student_data['email']}"}
        )

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ADMIN REGISTER
@app.route("/admin/register", methods=["POST"])
def admin_register():
    data = request.json
    existing_admin = admins.find_one({"admin_id": data["admin_id"]})
    hashed_password = hashlib.sha256(data["password"].encode()).hexdigest()
    if existing_admin:
        return jsonify({"message": "Admin ID already exists"}), 400
    existing_admin_email = admins.find_one({"email": data["email"]})
    if existing_admin_email:
        return jsonify({"message": "Email already exists"}), 400
    admins.insert_one(
        {
            "admin_id": data["admin_id"],
            "name": data["name"],
            "email": data["email"],
            "password": hashed_password,
            "role": "admin",
        }
    )
    token = generate_token(data["admin_id"], "admin")
    return jsonify({"message": "Admin Registered Successfully", "token": token})


# ADMIN LOGIN
@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.json
    admin_data = admins.find_one({"email": data["email"]})
    if not admin_data:
        return jsonify({"message": "Admin Not Found"}), 404
    hashed_password = hashlib.sha256(data["password"].encode()).hexdigest()
    if admin_data["password"] != hashed_password:
        return jsonify({"message": "Invalid Password"}), 401
    token = generate_token(admin_data["admin_id"], "admin")
    return jsonify(
        {
            "message": "Admin Login Successful",
            "token": token,
            "admin_id": admin_data["admin_id"],
            "name": admin_data["name"],
            "email": admin_data["email"],
            "role": admin_data["role"],
        }
    )


# GET ALL ADMINS
@app.route("/admins", methods=["GET"])
@token_required
def get_admins(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    all_admins = []
    for admin in admins.find({}, {"_id": 0}):
        all_admins.append(admin)
    return jsonify(all_admins)


# GET ADMIN BY ID
@app.route("/admin/<int:admin_id>", methods=["GET"])
@token_required
def get_admin(current_user, admin_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    admin_data = admins.find_one({"admin_id": admin_id}, {"_id": 0})
    if admin_data:
        return jsonify(admin_data)
    return jsonify({"message": "Admin Not Found"})


# UPDATE ADMIN
@app.route("/admin/update/<int:admin_id>", methods=["PUT"])
@token_required
def update_admin(current_user, admin_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    if current_user["user_id"] != admin_id:
        return jsonify({"message": "Access Denied"}), 403
    data = request.json
    existing_admin_email = admins.find_one(
        {"email": data["email"], "admin_id": {"$ne": admin_id}}
    )
    if existing_admin_email:
        return jsonify({"message": "Email already exists"}), 400
    update_data = {"name": data["name"], "email": data["email"]}
    if data.get("password") and data["password"] != "":
        update_data["password"] = hashlib.sha256(data["password"].encode()).hexdigest()
    result = admins.update_one({"admin_id": admin_id}, {"$set": update_data})
    if result.modified_count > 0:
        return jsonify({"message": "Admin Updated Successfully"})
    return jsonify({"message": "Admin Not Found"})


# DELETE ADMIN
@app.route("/admin/delete/<int:admin_id>", methods=["DELETE"])
@token_required
def delete_admin(current_user, admin_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    if current_user["user_id"] == admin_id:
        return jsonify({"message": "You cannot delete your own admin account"}), 403
    result = admins.delete_one({"admin_id": admin_id})
    if result.deleted_count > 0:
        return jsonify({"message": "Admin Deleted Successfully"})
    return jsonify({"message": "Admin Not Found"})


# ========== SUBJECT MANAGEMENT ==========
@app.route("/subjects", methods=["GET"])
@token_required
def get_subjects(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    all_subjects = []
    for sub in subjects.find({}):
        all_subjects.append(
            {
                "subject_id": sub["subject_id"],
                "subject_name": sub["subject_name"],
                "course": sub.get("course", ""),
                "_id": str(sub["_id"]),
            }
        )
    return jsonify(all_subjects)


@app.route("/subject/add", methods=["POST"])
@token_required
def add_subject(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    data = request.json
    existing = subjects.find_one({"subject_id": data["subject_id"]})
    if existing:
        return jsonify({"message": "Subject ID already exists"}), 400
    subjects.insert_one(
        {
            "subject_id": data["subject_id"],
            "subject_name": data["subject_name"],
            "course": data.get("course", ""),
        }
    )
    return jsonify({"message": "Subject added successfully"}), 200


@app.route("/subject/update/<subject_id>", methods=["PUT"])
@token_required
def update_subject(current_user, subject_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    data = request.json
    result = subjects.update_one(
        {"subject_id": subject_id},
        {
            "$set": {
                "subject_name": data["subject_name"],
                "course": data.get("course", ""),
            }
        },
    )
    if result.modified_count > 0:
        return jsonify({"message": "Subject updated successfully"}), 200
    return jsonify({"message": "Subject not found"}), 404


@app.route("/subject/delete/<subject_id>", methods=["DELETE"])
@token_required
def delete_subject(current_user, subject_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    result = subjects.delete_one({"subject_id": subject_id})
    if result.deleted_count > 0:
        return jsonify({"message": "Subject deleted successfully"}), 200
    return jsonify({"message": "Subject not found"}), 404


# ========== ATTENDANCE MANAGEMENT ==========
@app.route("/attendance/mark", methods=["POST"])
@token_required
def mark_attendance(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403

    data = request.json
    student_id = data.get("student_id")
    date = data.get("date")
    status = data.get("status")

    existing = attendance.find_one({"student_id": student_id, "date": date})
    if existing:
        attendance.update_one(
            {"student_id": student_id, "date": date},
            {"$set": {"status": status, "marked_by": current_user["user_id"]}},
        )
        message = "Attendance updated successfully"
    else:
        attendance.insert_one(
            {
                "student_id": student_id,
                "date": date,
                "status": status,
                "marked_by": current_user["user_id"],
                "created_at": datetime.datetime.utcnow(),
            }
        )
        message = "Attendance marked successfully"

    # Check attendance percentage and send alert if below 75%
    check_attendance_and_alert(student_id)

    return jsonify({"message": message}), 200


@app.route("/attendance/all", methods=["GET"])
@token_required
def get_all_attendance(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    all_attendance = []
    for att in attendance.find({}):
        student_data = student.find_one({"student_id": att["student_id"]}, {"name": 1})
        all_attendance.append(
            {
                "_id": str(att["_id"]),
                "student_id": att["student_id"],
                "student_name": student_data["name"] if student_data else "Unknown",
                "date": att["date"],
                "status": att["status"],
            }
        )
    return jsonify(all_attendance)


@app.route("/attendance/update/<attendance_id>", methods=["PUT"])
@token_required
def update_attendance(current_user, attendance_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    data = request.json
    result = attendance.update_one(
        {"_id": ObjectId(attendance_id)}, {"$set": {"status": data["status"]}}
    )
    if result.modified_count > 0:
        return jsonify({"message": "Attendance updated successfully"}), 200
    return jsonify({"message": "Attendance record not found"}), 404


@app.route("/attendance/delete/<attendance_id>", methods=["DELETE"])
@token_required
def delete_attendance(current_user, attendance_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    result = attendance.delete_one({"_id": ObjectId(attendance_id)})
    if result.deleted_count > 0:
        return jsonify({"message": "Attendance record deleted successfully"}), 200
    return jsonify({"message": "Attendance record not found"}), 404


@app.route("/attendance/student/<int:student_id>", methods=["GET"])
@token_required
def get_student_attendance(current_user, student_id):
    # This should return attendance records with dates and statuses
    attendances = []
    for att in attendance.find({"student_id": student_id}):
        attendances.append({"date": att["date"], "status": att["status"]})

    total = len(attendances)
    present = sum(1 for a in attendances if a["status"] == "Present")
    absent = sum(1 for a in attendances if a["status"] == "Absent")
    late = sum(1 for a in attendances if a["status"] == "Late")
    percentage = (present / total * 100) if total > 0 else 0

    return (
        jsonify(
            {
                "attendance_records": attendances,
                "summary": {
                    "total_days": total,
                    "present": present,
                    "absent": absent,
                    "late": late,
                    "percentage": round(percentage, 2),
                },
            }
        ),
        200,
    )


# ========== COURSE ENROLLMENT ==========
@app.route("/enroll/student", methods=["POST"])
@token_required
def enroll_student(current_user):
    data = request.json
    student_id = data.get("student_id")
    course_id = data.get("course_id")

    if current_user["role"] == "admin" and student_id:
        target_student_id = student_id
    else:
        target_student_id = current_user["user_id"]

    student_data = student.find_one({"student_id": target_student_id})
    if not student_data:
        return jsonify({"message": "Student not found"}), 404

    course_data = courses.find_one({"course_id": course_id})
    if not course_data:
        return jsonify({"message": "Course not found"}), 404

    existing = enrollments.find_one(
        {"student_id": target_student_id, "course_id": course_id}
    )
    if existing:
        return jsonify({"message": "Student already enrolled in this course"}), 400

    enrollments.insert_one(
        {
            "student_id": target_student_id,
            "student_name": student_data["name"],
            "course_id": course_id,
            "course_name": course_data["course_name"],
            "enrolled_at": datetime.datetime.utcnow(),
            "status": "Active",
        }
    )

    # Send enrollment email notification
    send_enrollment_email(
        student_data["email"], student_data["name"], course_data["course_name"]
    )

    return (
        jsonify(
            {
                "message": f"{student_data['name']} enrolled in {course_data['course_name']} successfully. Email notification sent!"
            }
        ),
        200,
    )


# ========== MARKS MANAGEMENT ==========
@app.route("/marks/add", methods=["POST"])
@token_required
def add_marks(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403

    data = request.json
    student_id = data.get("student_id")
    subject_id = data.get("subject_id")
    marks_obtained = data.get("marks_obtained")
    total_marks = data.get("total_marks", 100)
    exam_type = data.get("exam_type", "Internal")

    subject_data = subjects.find_one({"subject_id": subject_id})
    if not subject_data:
        return jsonify({"message": "Subject not found. Please add subject first."}), 404

    student_data = student.find_one({"student_id": student_id})
    if not student_data:
        return jsonify({"message": "Student not found"}), 404

    percentage = (marks_obtained / total_marks) * 100
    grade = calculate_grade(percentage)

    existing = marks.find_one(
        {"student_id": student_id, "subject_id": subject_id, "exam_type": exam_type}
    )

    is_new = False
    if existing:
        marks.update_one(
            {
                "student_id": student_id,
                "subject_id": subject_id,
                "exam_type": exam_type,
            },
            {
                "$set": {
                    "marks_obtained": marks_obtained,
                    "total_marks": total_marks,
                    "percentage": percentage,
                    "grade": grade,
                }
            },
        )
        message = "Marks updated successfully"
    else:
        marks.insert_one(
            {
                "student_id": student_id,
                "subject_id": subject_id,
                "subject_name": subject_data["subject_name"],
                "marks_obtained": marks_obtained,
                "total_marks": total_marks,
                "percentage": percentage,
                "grade": grade,
                "exam_type": exam_type,
                "created_at": datetime.datetime.utcnow(),
            }
        )
        is_new = True
        message = "Marks added successfully"

    # Send email notification for marks published
    if is_new or exam_type == "Final":
        send_marks_published_email(
            student_data["email"],
            student_data["name"],
            subject_data["subject_name"],
            marks_obtained,
            total_marks,
            round(percentage, 2),
            grade,
            exam_type,
        )

    return jsonify({"message": message}), 200


@app.route("/marks/all", methods=["GET"])
@token_required
def get_all_marks(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    all_marks = []
    for m in marks.find({}):
        student_data = student.find_one({"student_id": m["student_id"]}, {"name": 1})
        all_marks.append(
            {
                "_id": str(m["_id"]),
                "student_id": m["student_id"],
                "student_name": student_data["name"] if student_data else "Unknown",
                "subject_id": m["subject_id"],
                "subject_name": m["subject_name"],
                "marks_obtained": m["marks_obtained"],
                "total_marks": m["total_marks"],
                "percentage": m["percentage"],
                "grade": m["grade"],
                "exam_type": m["exam_type"],
            }
        )
    return jsonify(all_marks)


@app.route("/marks/update/<marks_id>", methods=["PUT"])
@token_required
def update_marks(current_user, marks_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    data = request.json

    marks_obtained = data.get("marks_obtained")
    total_marks = data.get("total_marks", 100)
    percentage = (marks_obtained / total_marks) * 100
    grade = calculate_grade(percentage)

    result = marks.update_one(
        {"_id": ObjectId(marks_id)},
        {
            "$set": {
                "marks_obtained": marks_obtained,
                "total_marks": total_marks,
                "percentage": percentage,
                "grade": grade,
                "exam_type": data.get("exam_type"),
            }
        },
    )
    if result.modified_count > 0:
        return jsonify({"message": "Marks updated successfully"}), 200
    return jsonify({"message": "Marks record not found"}), 404


@app.route("/marks/delete/<marks_id>", methods=["DELETE"])
@token_required
def delete_marks(current_user, marks_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin Access Required"}), 403
    result = marks.delete_one({"_id": ObjectId(marks_id)})
    if result.deleted_count > 0:
        return jsonify({"message": "Marks record deleted successfully"}), 200
    return jsonify({"message": "Marks record not found"}), 404


@app.route("/marks/student/<int:student_id>", methods=["GET"])
@token_required
def get_student_marks(current_user, student_id):
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        return jsonify({"message": "Access Denied"}), 403

    all_marks = []
    for m in marks.find({"student_id": student_id}):
        all_marks.append(
            {
                "subject_name": m.get("subject_name", "Unknown"),
                "marks_obtained": m.get("marks_obtained", 0),
                "total_marks": m.get("total_marks", 100),
                "percentage": m.get("percentage", 0),
                "grade": m.get("grade", "F"),
                "exam_type": m.get("exam_type", "Unknown"),
            }
        )

    total_percentage = sum(m["percentage"] for m in all_marks) if all_marks else 0
    avg_percentage = total_percentage / len(all_marks) if all_marks else 0
    overall_grade = calculate_grade(avg_percentage)

    return jsonify(
        {
            "marks": all_marks,
            "summary": {
                "total_subjects": len(all_marks),
                "average_percentage": round(avg_percentage, 2),
                "overall_grade": overall_grade,
            },
        }
    )


# Test email route
@app.route("/test_email")
def test_email():
    try:
        msg = Message(
            subject="Test Email",
            recipients=[os.getenv("MAIL_USERNAME")],
            body="This is a test email from your Student Portal",
        )
        mail.send(msg)
        return "✅ Email sent successfully! Check your inbox."
    except Exception as e:
        return f"❌ Error: {str(e)}"


# Frontend Portal Route
@app.route("/portal")
def portal():
    return render_template("index.html")


# ========== ACTIVITY LOGS ==========
activity_logs = db["activity_logs"]


@app.route("/activity/log", methods=["POST"])
@token_required
def log_activity(current_user):
    data = request.json
    activity_logs.insert_one(
        {
            "user_id": current_user["user_id"],
            "role": current_user["role"],
            "action": data.get("action"),
            "timestamp": datetime.datetime.utcnow(),
            "ip": request.remote_addr,
        }
    )
    return jsonify({"message": "Logged"}), 200


@app.route("/activity/logs", methods=["GET"])
@token_required
def get_activity_logs(current_user):
    all_logs = []
    for log in (
        activity_logs.find({"user_id": current_user["user_id"]})
        .sort("timestamp", -1)
        .limit(20)
    ):
        all_logs.append(
            {
                "action": log["action"],
                "timestamp": log["timestamp"],
                "ip": log.get("ip", "-"),
            }
        )
    return jsonify(all_logs), 200


# ============ ANNOUNCEMENTS ==========


# Get all announcements (for students and admin)
@app.route("/announcements", methods=["GET"])
@token_required
def get_announcements(current_user):
    try:
        all_announcements = []
        for ann in announcement.find({}).sort("date", -1):
            all_announcements.append(
                {
                    "_id": str(ann["_id"]),
                    "title": ann.get("title", ""),
                    "content": ann.get("content", ""),
                    "priority": ann.get("priority", "normal"),
                    "date": ann.get("date", ""),
                    "expiry": ann.get("expiry", None),
                }
            )
        return jsonify(all_announcements), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Add new announcement (admin only)
@app.route("/announcements/add", methods=["POST"])
@token_required
def add_announcement(current_user):
    try:
        data = request.get_json()

        new_announcement = {
            "title": data.get("title"),
            "content": data.get("content"),
            "priority": data.get("priority", "normal"),
            "date": datetime.datetime.now().isoformat(),
            "expiry": data.get("expiry"),
        }

        result = announcement.insert_one(new_announcement)
        new_announcement["_id"] = str(result.inserted_id)

        return jsonify({"message": "Announcement posted successfully!"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Update announcement
@app.route("/announcements/update/<announcement_id>", methods=["PUT"])
@token_required
def update_announcement(current_user, announcement_id):
    try:
        data = request.get_json()
        update_data = {}

        if "title" in data:
            update_data["title"] = data["title"]
        if "content" in data:
            update_data["content"] = data["content"]
        if "priority" in data:
            update_data["priority"] = data["priority"]
        if "expiry" in data:
            update_data["expiry"] = data["expiry"]

        announcement.update_one(
            {"_id": ObjectId(announcement_id)}, {"$set": update_data}
        )

        return jsonify({"message": "Announcement updated successfully!"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Delete announcement
@app.route("/announcements/delete/<announcement_id>", methods=["DELETE"])
@token_required
def delete_announcement(current_user, announcement_id):
    try:
        result = announcement.delete_one({"_id": ObjectId(announcement_id)})

        if result.deleted_count == 0:
            return jsonify({"message": "Announcement not found"}), 404

        return jsonify({"message": "Announcement deleted successfully!"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# Keep old /notices endpoint for backward compatibility
@app.route("/notices", methods=["GET"])
@token_required
def get_notices(current_user):
    return get_announcements(current_user)


# ============ RANKING ==========
@app.route("/ranking/student/<int:student_id>", methods=["GET"])
@token_required
def get_student_rank(current_user, student_id):
    # Get all students' average percentages
    all_students = []
    for stu in student.find({}):
        student_marks = list(marks.find({"student_id": stu["student_id"]}))
        if student_marks:
            total_percentage = sum(m["percentage"] for m in student_marks)
            avg_percentage = total_percentage / len(student_marks)
            all_students.append(
                {
                    "student_id": stu["student_id"],
                    "name": stu["name"],
                    "avg_percentage": avg_percentage,
                }
            )

    # Sort by percentage descending
    all_students.sort(key=lambda x: x["avg_percentage"], reverse=True)

    # Find rank
    rank = 1
    student_percentage = 0
    for i, stu in enumerate(all_students):
        if stu["student_id"] == student_id:
            rank = i + 1
            student_percentage = stu["avg_percentage"]
            break

    # Calculate averages
    all_percentages = [s["avg_percentage"] for s in all_students]
    average_percentage = (
        sum(all_percentages) / len(all_percentages) if all_percentages else 0
    )
    top_percentage = max(all_percentages) if all_percentages else 0

    return (
        jsonify(
            {
                "rank": rank,
                "total_students": len(all_students),
                "student_percentage": round(student_percentage, 2),
                "average_percentage": round(average_percentage, 2),
                "top_percentage": round(top_percentage, 2),
                "class_average": round(average_percentage, 2),
            }
        ),
        200,
    )


# ============ LEADERBOARD ==========
@app.route("/leaderboard", methods=["GET"])
@token_required
def get_leaderboard(current_user):
    period = request.args.get("period", "weekly")

    # Calculate points for all students based on attendance and marks
    all_students = []
    for stu in student.find({}):
        points = 0

        # Points from attendance (5 per present, 2 per late)
        attendances = attendance.find({"student_id": stu["student_id"]})
        for att in attendances:
            if att["status"] == "Present":
                points += 5
            elif att["status"] == "Late":
                points += 2

        # Points from marks (percentage / 10)
        student_marks = marks.find({"student_id": stu["student_id"]})
        for m in student_marks:
            points += int(m.get("percentage", 0) / 10)

        all_students.append(
            {"name": stu["name"], "points": points, "student_id": stu["student_id"]}
        )

    # Sort by points
    all_students.sort(key=lambda x: x["points"], reverse=True)

    # Add rank
    result = []
    for i, stu in enumerate(all_students[:50]):
        result.append({"rank": i + 1, "name": stu["name"], "points": stu["points"]})

    return jsonify(result), 200


# ============ DISCUSSION FORUM ============


# Get all questions
@app.route("/forum/questions", methods=["GET"])
@token_required
def get_questions(current_user):
    questions = forum_questions.find().sort("created_at", -1)
    result = []
    for q in questions:
        q["_id"] = str(q["_id"])
        # Get reply count
        reply_count = forum_replies.count_documents({"question_id": q["_id"]})
        q["reply_count"] = reply_count
        # Make sure student_name exists
        if "student_name" not in q:
            # If missing, try to get from student collection
            student_data = student.find_one({"student_id": q["student_id"]})
            q["student_name"] = (
                student_data["name"] if student_data else "Unknown Student"
            )
        result.append(q)
    return jsonify(result)


# Post a question
@app.route("/forum/question", methods=["POST"])
@token_required
def post_question(current_user):
    data = request.json

    # Get student details from database
    student_data = student.find_one({"student_id": current_user["user_id"]})
    student_name = (
        student_data["name"] if student_data else current_user.get("name", "Student")
    )

    question = {
        "student_id": current_user["user_id"],
        "student_name": student_name,  # Use actual name from database
        "title": data["title"],
        "content": data["content"],
        "subject": data.get("subject", "General"),
        "created_at": datetime.datetime.now().isoformat(),
        "upvotes": 0,
        "views": 0,
    }
    result = forum_questions.insert_one(question)
    return jsonify({"message": "Question posted!", "_id": str(result.inserted_id)})


# Get replies for a question
@app.route("/forum/replies/<question_id>", methods=["GET"])
@token_required
def get_replies(current_user, question_id):
    replies = forum_replies.find({"question_id": question_id}).sort("created_at", 1)
    result = []
    for r in replies:
        r["_id"] = str(r["_id"])
        # Make sure student_name exists
        if "student_name" not in r:
            student_data = student.find_one({"student_id": r["student_id"]})
            r["student_name"] = (
                student_data["name"] if student_data else "Unknown Student"
            )
        result.append(r)
    return jsonify(result)


# Post a reply
@app.route("/forum/reply", methods=["POST"])
@token_required
def post_reply(current_user):
    data = request.json

    # Get student details from database
    student_data = student.find_one({"student_id": current_user["user_id"]})
    student_name = (
        student_data["name"] if student_data else current_user.get("name", "Student")
    )

    reply = {
        "question_id": data["question_id"],
        "student_id": current_user["user_id"],
        "student_name": student_name,  # Use actual name from database
        "content": data["content"],
        "created_at": datetime.datetime.now().isoformat(),
        "upvotes": 0,
    }
    result = forum_replies.insert_one(reply)
    return jsonify({"message": "Reply posted!", "_id": str(result.inserted_id)})


# Upvote a question or reply
@app.route("/forum/upvote/<type>/<id>", methods=["POST"])
@token_required
def upvote(current_user, type, id):
    collection = forum_questions if type == "question" else forum_replies
    collection.update_one({"_id": ObjectId(id)}, {"$inc": {"upvotes": 1}})
    return jsonify({"message": "Upvoted!"})


# ============ LIVE CHAT ============
# Create or get a chat room
@app.route("/chat/room", methods=["POST"])
@token_required
def create_or_get_chat_room(current_user):
    data = request.json
    room_name = data.get("room_name", f"Room_{datetime.datetime.now().timestamp()}")
    room_type = data.get("room_type", "public")  # public, private, course

    # Check if room exists
    existing_room = chat_rooms.find_one({"room_name": room_name})
    if existing_room:
        return (
            jsonify(
                {
                    "room_id": str(existing_room["_id"]),
                    "room_name": existing_room["room_name"],
                    "room_type": existing_room["room_type"],
                    "created_by": existing_room["created_by"],
                }
            ),
            200,
        )

    # Create new room
    room = {
        "room_name": room_name,
        "room_type": room_type,
        "created_by": current_user["user_id"],
        "created_at": datetime.datetime.now().isoformat(),
        "participants": [current_user["user_id"]],
        "is_active": True,
    }
    result = chat_rooms.insert_one(room)

    return (
        jsonify(
            {
                "room_id": str(result.inserted_id),
                "room_name": room_name,
                "room_type": room_type,
                "created_by": current_user["user_id"],
            }
        ),
        200,
    )


# Get all chat rooms
@app.route("/chat/rooms", methods=["GET"])
@token_required
def get_chat_rooms(current_user):
    rooms = chat_rooms.find({"is_active": True}).sort("created_at", -1)
    result = []
    for room in rooms:
        # Get last message
        last_msg = chat_messages.find_one(
            {"room_id": str(room["_id"])}, sort=[("timestamp", -1)]
        )
        result.append(
            {
                "_id": str(room["_id"]),
                "room_name": room["room_name"],
                "room_type": room["room_type"],
                "created_by": room["created_by"],
                "created_at": room["created_at"],
                "participant_count": len(room.get("participants", [])),
                "last_message": last_msg["message"] if last_msg else "No messages yet",
                "last_message_time": last_msg["timestamp"] if last_msg else None,
            }
        )
    return jsonify(result), 200


# Send message
@app.route("/chat/message", methods=["POST"])
@token_required
def send_chat_message(current_user):
    data = request.json
    room_id = data.get("room_id")
    message = data.get("message")

    # Get user details
    student_data = student.find_one({"student_id": current_user["user_id"]})
    user_name = student_data["name"] if student_data else "User"

    # Add message to chat
    chat_msg = {
        "room_id": room_id,
        "sender_id": current_user["user_id"],
        "sender_name": user_name,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat(),
        "is_read": False,
    }
    result = chat_messages.insert_one(chat_msg)

    # Update room's last activity
    chat_rooms.update_one(
        {"_id": ObjectId(room_id)},
        {"$set": {"last_activity": datetime.datetime.now().isoformat()}},
    )

    return (
        jsonify(
            {
                "message_id": str(result.inserted_id),
                "sender_name": user_name,
                "message": message,
                "timestamp": chat_msg["timestamp"],
            }
        ),
        200,
    )


# Get messages for a room - FIXED
@app.route("/chat/messages/<room_id>", methods=["GET"])
@token_required
def get_chat_messages(current_user, room_id):
    try:
        # Check if user is in room
        room = chat_rooms.find_one({"_id": ObjectId(room_id)})
        if not room:
            return jsonify({"message": "Room not found"}), 404

        messages = chat_messages.find({"room_id": room_id}).sort("timestamp", 1)
        result = []
        for msg in messages:
            result.append(
                {
                    "_id": str(msg["_id"]),
                    "sender_id": msg["sender_id"],
                    "sender_name": msg["sender_name"],
                    "message": msg["message"],
                    "timestamp": msg["timestamp"],
                    "is_image": msg.get("is_image", False),
                    "image_url": msg.get("image_url", ""),
                    "edited": msg.get("edited", False),
                    "edited_at": msg.get("edited_at", ""),
                }
            )
        return jsonify(result), 200
    except Exception as e:
        print(f"❌ Error in get_chat_messages: {e}")
        return jsonify({"message": str(e)}), 500


# Join a chat room
@app.route("/chat/join/<room_id>", methods=["POST"])
@token_required
def join_chat_room(current_user, room_id):
    result = chat_rooms.update_one(
        {"_id": ObjectId(room_id)},
        {"$addToSet": {"participants": current_user["user_id"]}},
    )
    if result.modified_count > 0:
        return jsonify({"message": "Joined room successfully"}), 200
    return jsonify({"message": "Already in room or room not found"}), 200


# ============ LIVE CHAT - ENHANCED ============


# Edit a message
@app.route("/chat/message/<message_id>", methods=["PUT"])
@token_required
def edit_chat_message(current_user, message_id):
    data = request.json
    new_message = data.get("message")

    if not new_message:
        return jsonify({"message": "Message cannot be empty"}), 400

    # Find the message
    msg = chat_messages.find_one({"_id": ObjectId(message_id)})
    if not msg:
        return jsonify({"message": "Message not found"}), 404

    # Check if user is the sender
    if msg["sender_id"] != current_user["user_id"]:
        return jsonify({"message": "You can only edit your own messages"}), 403

    # Update the message
    chat_messages.update_one(
        {"_id": ObjectId(message_id)},
        {
            "$set": {
                "message": new_message,
                "edited": True,
                "edited_at": datetime.datetime.now().isoformat(),
            }
        },
    )

    return (
        jsonify(
            {
                "message": "Message updated successfully",
                "edited": True,
                "edited_at": datetime.datetime.now().isoformat(),
            }
        ),
        200,
    )


# Delete a message
@app.route("/chat/message/<message_id>", methods=["DELETE"])
@token_required
def delete_chat_message(current_user, message_id):
    # Find the message
    msg = chat_messages.find_one({"_id": ObjectId(message_id)})
    if not msg:
        return jsonify({"message": "Message not found"}), 404

    # Check if user is the sender
    if msg["sender_id"] != current_user["user_id"]:
        return jsonify({"message": "You can only delete your own messages"}), 403

    # Delete the message
    chat_messages.delete_one({"_id": ObjectId(message_id)})

    return jsonify({"message": "Message deleted successfully"}), 200


@app.route("/chat/upload", methods=["POST"])
@token_required
def upload_chat_image(current_user):
    import os
    from werkzeug.utils import secure_filename
    from datetime import datetime

    print("=" * 60)
    print("📷 UPLOAD ENDPOINT CALLED")

    if "image" not in request.files:
        print("❌ No image in request")
        return jsonify({"message": "No image uploaded"}), 400

    file = request.files["image"]
    print(f"📁 File name: {file.filename}")
    print(f"📁 Content type: {file.content_type}")

    if file.filename == "":
        print("❌ Empty filename")
        return jsonify({"message": "No file selected"}), 400

    # Check file type
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        print(f"❌ Invalid file type: {file.content_type}")
        return jsonify({"message": "Only image files are allowed"}), 400

    # Check file size (max 5MB)
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    print(f"📊 File size: {file_size} bytes")

    if file_size > 5 * 1024 * 1024:
        print("❌ File too large")
        return jsonify({"message": "File size must be less than 5MB"}), 400

    # Create unique filename
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_filename = f"{timestamp}_{filename}"
    print(f"📝 Unique filename: {unique_filename}")

    # Create the folder path
    upload_folder = os.path.join(os.getcwd(), "static", "uploads", "chat_images")
    print(f"📁 Upload folder: {upload_folder}")

    # Create folder if it doesn't exist
    os.makedirs(upload_folder, exist_ok=True)
    print(f"📁 Folder exists: {os.path.exists(upload_folder)}")

    # Save the file
    filepath = os.path.join(upload_folder, unique_filename)
    print(f"📁 Full filepath: {filepath}")

    try:
        file.save(filepath)
        print(f"✅ File saved successfully!")
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        return jsonify({"message": f"Error saving file: {str(e)}"}), 500

    # Verify file was saved
    if os.path.exists(filepath):
        print(f"✅ File exists: True")
        print(f"✅ File size: {os.path.getsize(filepath)} bytes")
    else:
        print(f"❌ File does NOT exist after save!")
        return jsonify({"message": "File was not saved"}), 500

    # Return the URL
    image_url = f"/static/uploads/chat_images/{unique_filename}"
    print(f"📁 Image URL: {image_url}")
    print("=" * 60)

    return (
        jsonify(
            {
                "message": "Image uploaded successfully",
                "image_url": image_url,
                "is_image": True,
            }
        ),
        200,
    )


# Get message with image support
@app.route("/chat/messages_with_images/<room_id>", methods=["GET"])
@token_required
def get_chat_messages_with_images(current_user, room_id):
    # Check if user is in room
    room = chat_rooms.find_one({"_id": ObjectId(room_id)})
    if not room:
        return jsonify({"message": "Room not found"}), 404

    messages = chat_messages.find({"room_id": room_id}).sort("timestamp", 1)
    result = []
    for msg in messages:
        result.append(
            {
                "_id": str(msg["_id"]),
                "sender_id": msg["sender_id"],
                "sender_name": msg["sender_name"],
                "message": msg["message"],
                "timestamp": msg["timestamp"],
                "is_image": msg.get("is_image", False),
                "image_url": msg.get("image_url", ""),
                "edited": msg.get("edited", False),
                "edited_at": msg.get("edited_at", ""),
            }
        )
    return jsonify(result), 200


# Send message with image support
@app.route("/chat/message_with_image", methods=["POST"])
@token_required
def send_chat_message_with_image(current_user):
    data = request.json
    room_id = data.get("room_id")
    message = data.get("message", "")
    is_image = data.get("is_image", False)
    image_url = data.get("image_url", "")

    # Get user details
    student_data = student.find_one({"student_id": current_user["user_id"]})
    user_name = student_data["name"] if student_data else "User"

    # Add message to chat
    chat_msg = {
        "room_id": room_id,
        "sender_id": current_user["user_id"],
        "sender_name": user_name,
        "message": message if message else "📷 Image",
        "timestamp": datetime.datetime.now().isoformat(),
        "is_read": False,
        "is_image": is_image,
        "image_url": image_url,
        "edited": False,
        "edited_at": "",
    }
    result = chat_messages.insert_one(chat_msg)

    # Update room's last activity
    chat_rooms.update_one(
        {"_id": ObjectId(room_id)},
        {"$set": {"last_activity": datetime.datetime.now().isoformat()}},
    )

    return (
        jsonify(
            {
                "message_id": str(result.inserted_id),
                "sender_name": user_name,
                "message": message,
                "timestamp": chat_msg["timestamp"],
                "is_image": is_image,
                "image_url": image_url,
            }
        ),
        200,
    )


# ============ STUDENT VIDEO ENDPOINTS ============


# Get all video lectures (for students)
@app.route("/videos", methods=["GET"])
@token_required
def get_videos(current_user):
    print(f"🔍 Videos endpoint called by student: {current_user['user_id']}")
    subject = request.args.get("subject")
    query = {}
    if subject:
        query["subject"] = subject
    videos = video_lectures.find(query).sort("uploaded_at", -1)
    result = []
    for v in videos:
        v["_id"] = str(v["_id"])
        result.append(v)
    print(f"📦 Found {len(result)} videos")
    return jsonify(result), 200


# Get video by ID (for students)
@app.route("/videos/<video_id>", methods=["GET"])
@token_required
def get_video(current_user, video_id):
    print(
        f"🎬 Video endpoint called by student: {current_user['user_id']} for video: {video_id}"
    )

    try:
        video = video_lectures.find_one({"_id": ObjectId(video_id)})
        if not video:
            print(f"❌ Video not found: {video_id}")
            return jsonify({"message": "Video not found"}), 404

        video["_id"] = str(video["_id"])
        # Increment views
        video_lectures.update_one({"_id": ObjectId(video_id)}, {"$inc": {"views": 1}})
        print(f"✅ Video found: {video['title']}")
        return jsonify(video), 200
    except Exception as e:
        print(f"❌ Error fetching video: {e}")
        return jsonify({"message": "Invalid video ID"}), 400


# Like a video
@app.route("/videos/like/<video_id>", methods=["POST"])
@token_required
def like_video(current_user, video_id):
    try:
        result = video_lectures.update_one(
            {"_id": ObjectId(video_id)}, {"$inc": {"likes": 1}}
        )
        if result.modified_count > 0:
            return jsonify({"message": "Video liked!"}), 200
        return jsonify({"message": "Video not found"}), 404
    except Exception as e:
        return jsonify({"message": str(e)}), 400


# ============ ADMIN VIDEO MANAGEMENT ============


# Get all videos for admin
@app.route("/admin/videos", methods=["GET"])
@token_required
def admin_get_videos(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin access required"}), 403

    videos = video_lectures.find().sort("uploaded_at", -1)
    result = []
    for v in videos:
        v["_id"] = str(v["_id"])
        result.append(v)
    return jsonify(result), 200


# Add video (admin only) - AUTO DURATION
@app.route("/video/add", methods=["POST"])
@token_required
def add_video(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin access required"}), 403

    data = request.json
    video_url = data.get("video_url")

    # Auto-fetch duration if not provided
    duration = data.get("duration", "")
    if not duration or duration == "" or duration == "N/A":
        duration = get_youtube_duration(video_url)

    # Auto-fetch thumbnail if not provided
    thumbnail = data.get("thumbnail", "")
    if not thumbnail or thumbnail == "":
        video_id = None
        patterns = [
            r"(?:youtube\.com\/watch\?v=)([^&]+)",
            r"(?:youtu\.be\/)([^?]+)",
            r"(?:youtube\.com\/embed\/)([^?]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, video_url)
            if match:
                video_id = match.group(1)
                break
        if video_id:
            thumbnail = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

    video = {
        "title": data.get("title"),
        "description": data.get("description", ""),
        "subject": data.get("subject"),
        "video_url": video_url,
        "duration": duration,
        "thumbnail": thumbnail,
        "uploaded_by": current_user["user_id"],
        "uploaded_at": datetime.datetime.now().isoformat(),
        "views": 0,
        "likes": 0,
    }
    result = video_lectures.insert_one(video)
    return (
        jsonify(
            {
                "message": f"Video added successfully! Duration: {duration}",
                "_id": str(result.inserted_id),
            }
        ),
        200,
    )


# Update video (admin only)
@app.route("/admin/video/update/<video_id>", methods=["PUT"])
@token_required
def admin_update_video(current_user, video_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin access required"}), 403

    data = request.json
    update_data = {}
    fields = ["title", "description", "subject", "video_url", "duration", "thumbnail"]
    for field in fields:
        if field in data:
            update_data[field] = data[field]

    if update_data:
        result = video_lectures.update_one(
            {"_id": ObjectId(video_id)}, {"$set": update_data}
        )
        if result.modified_count > 0:
            return jsonify({"message": "Video updated successfully"}), 200

    return jsonify({"message": "No changes made or video not found"}), 404


def get_youtube_duration(video_url):
    """Extract YouTube video duration with fallback methods"""
    try:
        # Extract video ID
        video_id = None
        patterns = [
            r"(?:youtube\.com\/watch\?v=)([^&]+)",
            r"(?:youtu\.be\/)([^?]+)",
            r"(?:youtube\.com\/embed\/)([^?]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, video_url)
            if match:
                video_id = match.group(1)
                break

        if not video_id:
            print(f"⚠️ Could not extract video ID from: {video_url}")
            return "N/A"

        # Try multiple API keys (free public keys)
        api_keys = [
            "AIzaSyB4kFbKhF7yIuLQ3n2q8OqFz3w8GX3Q4M",
            "AIzaSyCv-HM9P8jEFXKkR1wXyZ6kP2XxYzZqQ8",
            "AIzaSyD7Qp9ZqZxYwXvYzQpQkZxYwXvYzQpQk",
        ]

        for api_key in api_keys:
            try:
                api_url = f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={video_id}&key={api_key}"
                req = urllib.request.Request(
                    api_url, headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=3) as response:
                    data = json.loads(response.read().decode())
                    if data.get("items") and len(data["items"]) > 0:
                        duration_iso = data["items"][0]["contentDetails"]["duration"]
                        formatted = format_duration(duration_iso)
                        print(
                            f"✅ Found duration: {formatted} for video ID: {video_id}"
                        )
                        return formatted
            except Exception as e:
                print(f"⚠️ API key failed: {e}")
                continue

        # If all API keys fail, use a default duration
        print(f"⚠️ No duration found for video ID: {video_id}, using default")
        return "45:00"
    except Exception as e:
        print(f"❌ Error fetching duration: {e}")
        return "45:00"  # Return default duration instead of "N/A"


def format_duration(duration_iso):
    """Convert ISO 8601 duration to HH:MM:SS or MM:SS"""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_iso)
    if not match:
        return "N/A"

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"


# Fix missing durations for existing videos
@app.route("/admin/videos/fix-durations", methods=["POST"])
@token_required
def fix_video_durations(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin access required"}), 403

    fixed_count = 0
    videos = video_lectures.find(
        {
            "$or": [
                {"duration": "N/A"},
                {"duration": ""},
                {"duration": None},
                {"duration": {"$exists": False}},
            ]
        }
    )

    for video in videos:
        try:
            duration = get_youtube_duration(video.get("video_url", ""))
            if duration != "N/A":
                video_lectures.update_one(
                    {"_id": video["_id"]}, {"$set": {"duration": duration}}
                )
                fixed_count += 1
                print(
                    f"✅ Fixed duration for: {video.get('title', 'Unknown')} -> {duration}"
                )
        except Exception as e:
            print(f"❌ Failed to fix {video.get('title', 'Unknown')}: {e}")

    return (
        jsonify(
            {
                "message": f"Fixed durations for {fixed_count} videos",
                "fixed_count": fixed_count,
            }
        ),
        200,
    )


# Delete video (admin only)
@app.route("/admin/video/delete/<video_id>", methods=["DELETE"])
@token_required
def admin_delete_video(current_user, video_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Admin access required"}), 403

    try:
        result = video_lectures.delete_one({"_id": ObjectId(video_id)})
        if result.deleted_count > 0:
            return jsonify({"message": "Video deleted successfully"}), 200
        return jsonify({"message": "Video not found"}), 404
    except Exception as e:
        return jsonify({"message": str(e)}), 400


# ============ COURSE MATERIALS ============


# Get all materials
@app.route("/materials", methods=["GET"])
@token_required
def get_materials(current_user):
    subject = request.args.get("subject")
    query = {}
    if subject:
        query["subject"] = subject
    materials = course_materials.find(query).sort("created_at", -1)
    result = []
    for m in materials:
        m["_id"] = str(m["_id"])
        result.append(m)
    return jsonify(result)


# Add material (admin only) - with file upload
@app.route("/materials/add", methods=["POST"])
@token_required
def add_material(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Unauthorized"}), 403

    # Check if file is present
    if "file" not in request.files:
        return jsonify({"message": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"message": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"message": "Only PDF files are allowed"}), 400

    # Get form data
    title = request.form.get("title")
    description = request.form.get("description")
    subject = request.form.get("subject")

    if not title or not subject:
        return jsonify({"message": "Title and subject are required"}), 400

    # Secure filename and save
    filename = secure_filename(file.filename)
    # Add timestamp to avoid duplicate names
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_filename = f"{timestamp}_{filename}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
    file.save(filepath)

    # Get file size
    file_size = os.path.getsize(filepath)

    # Save to database
    material = {
        "title": title,
        "description": description,
        "subject": subject,
        "file_url": f"/static/uploads/materials/{unique_filename}",  # Store the URL path
        "file_name": filename,
        "file_size": file_size,
        "file_type": "pdf",
        "created_at": datetime.datetime.now().isoformat(),
        "downloads": 0,
        "uploaded_by": current_user["user_id"],
    }

    result = course_materials.insert_one(material)
    return (
        jsonify(
            {"message": "Material added successfully!", "_id": str(result.inserted_id)}
        ),
        200,
    )


# Update material (admin only)
@app.route("/materials/update/<material_id>", methods=["PUT"])
@token_required
def update_material(current_user, material_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Unauthorized"}), 403

    data = request.json
    update_data = {
        "title": data["title"],
        "description": data["description"],
        "subject": data["subject"],
    }

    result = course_materials.update_one(
        {"_id": ObjectId(material_id)}, {"$set": update_data}
    )

    if result.modified_count > 0:
        return jsonify({"message": "Material updated!"}), 200
    return jsonify({"message": "Material not found"}), 404


# Delete material (admin only)
@app.route("/materials/delete/<material_id>", methods=["DELETE"])
@token_required
def delete_material(current_user, material_id):
    if current_user["role"] != "admin":
        return jsonify({"message": "Unauthorized"}), 403
    result = course_materials.delete_one({"_id": ObjectId(material_id)})
    if result.deleted_count > 0:
        return jsonify({"message": "Material deleted!"}), 200
    return jsonify({"message": "Material not found"}), 404


# Increment download count
@app.route("/materials/download/<material_id>", methods=["POST"])
@token_required
def increment_download(current_user, material_id):
    course_materials.update_one(
        {"_id": ObjectId(material_id)}, {"$inc": {"downloads": 1}}
    )
    return jsonify({"message": "Download counted"})


# Mark material as important
@app.route("/materials/important/<material_id>", methods=["POST"])
@token_required
def mark_important(current_user, material_id):
    user_id = current_user["user_id"]
    important = important_materials.find_one(
        {"student_id": user_id, "material_id": material_id}
    )
    if important:
        important_materials.delete_one({"_id": important["_id"]})
        return jsonify({"message": "Removed from important"})
    else:
        important_materials.insert_one(
            {
                "student_id": user_id,
                "material_id": material_id,
                "created_at": datetime.datetime.now().isoformat(),
            }
        )
        return jsonify({"message": "Added to important"})


# Get student's important materials
@app.route("/materials/important", methods=["GET"])
@token_required
def get_important_materials(current_user):
    important = important_materials.find({"student_id": current_user["user_id"]})
    material_ids = [i["material_id"] for i in important]
    materials = course_materials.find(
        {"_id": {"$in": [ObjectId(id) for id in material_ids]}}
    )
    result = []
    for m in materials:
        m["_id"] = str(m["_id"])
        result.append(m)
    return jsonify(result)


# ============ QUIZ SYSTEM ============


# Get available quizzes
@app.route("/quizzes", methods=["GET"])
@token_required
def get_quizzes(current_user):
    all_quizzes = quizzes.find({"active": True}).sort("created_at", -1)
    result = []
    for q in all_quizzes:
        q["_id"] = str(q["_id"])
        # Check if student has taken quiz
        taken = quiz_attempts.find_one(
            {"student_id": current_user["user_id"], "quiz_id": q["_id"]}
        )
        q["taken"] = taken is not None
        if taken:
            q["score"] = taken["score"]
            q["percentage"] = taken["percentage"]
        result.append(q)
    return jsonify(result)


# Get quiz questions
@app.route("/quiz/<quiz_id>", methods=["GET"])
@token_required
def get_quiz(current_user, quiz_id):
    quiz = quizzes.find_one({"_id": ObjectId(quiz_id)})
    if not quiz:
        return jsonify({"message": "Quiz not found"}), 404
    quiz["_id"] = str(quiz["_id"])
    # Don't send answers for security
    for q in quiz["questions"]:
        del q["correct_answer"]
    return jsonify(quiz)


@app.route("/quiz/submit", methods=["POST"])
@token_required
def submit_quiz(current_user):
    data = request.json
    quiz_id = data.get("quiz_id")
    answers = data.get("answers", {})

    # Get student name
    student_data = student.find_one({"student_id": current_user["user_id"]})
    student_name = student_data["name"] if student_data else "Student"

    # Handle LearnSphere quiz (from quiz.html)
    if quiz_id == "learnsphere_quiz_001":
        # 🔥 USE THE GRADE FROM FRONTEND - DON'T RECALCULATE
        score = data.get("score", 0)
        total = data.get("total", 20)
        percentage = data.get("percentage", 0)
        grade = data.get("grade", "F")  # ✅ Use frontend's grade

        print(
            f"📊 Received from frontend - Score: {score}, Total: {total}, Percentage: {percentage}%, Grade: {grade}"
        )

        attempt = {
            "quiz_id": quiz_id,
            "quiz_title": "LearnSphere Assessment",
            "student_id": current_user["user_id"],
            "student_name": student_name,
            "score": score,
            "total": total,
            "percentage": percentage,
            "grade": grade,  # ✅ Use frontend's grade
            "answers": answers,
            "completed_at": datetime.datetime.now().isoformat(),
        }

        quiz_attempts.insert_one(attempt)

        return (
            jsonify(
                {
                    "message": "Quiz submitted successfully!",
                    "score": score,
                    "total": total,
                    "percentage": percentage,
                    "grade": grade,
                }
            ),
            200,
        )

    # Handle regular database quizzes
    try:
        quiz = quizzes.find_one({"_id": ObjectId(quiz_id)})
        if not quiz:
            return jsonify({"message": "Quiz not found"}), 404

        score = 0
        total = len(quiz["questions"])
        for i, q in enumerate(quiz["questions"]):
            if str(answers.get(str(i))) == str(q["correct_answer"]):
                score += 1

        percentage = (score / total) * 100

        # Calculate grade for regular quizzes
        if percentage >= 90:
            grade = "A+"
        elif percentage >= 80:
            grade = "A"
        elif percentage >= 70:
            grade = "B+"
        elif percentage >= 60:
            grade = "B"
        elif percentage >= 50:
            grade = "C"
        else:
            grade = "F"

        attempt = {
            "quiz_id": quiz_id,
            "quiz_title": quiz["title"],
            "student_id": current_user["user_id"],
            "student_name": student_name,
            "score": score,
            "total": total,
            "percentage": percentage,
            "grade": grade,
            "answers": answers,
            "completed_at": datetime.datetime.now().isoformat(),
        }

        quiz_attempts.insert_one(attempt)

        return (
            jsonify(
                {
                    "message": "Quiz submitted!",
                    "score": score,
                    "total": total,
                    "percentage": percentage,
                    "grade": grade,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"message": str(e)}), 400


@app.route("/quiz/history", methods=["GET"])
@token_required
def get_quiz_history(current_user):
    # Get quiz attempts for the current student
    results = list(
        quiz_attempts.find({"student_id": current_user["user_id"]}, {"_id": 0}).sort(
            "completed_at", -1
        )
    )

    return jsonify(results), 200


# Add quiz (admin only)
@app.route("/quiz/add", methods=["POST"])
@token_required
def add_quiz(current_user):
    if current_user["role"] != "admin":
        return jsonify({"message": "Unauthorized"}), 403
    data = request.json
    quiz = {
        "title": data["title"],
        "subject": data["subject"],
        "duration": data["duration"],  # in minutes
        "questions": data["questions"],
        "active": True,
        "created_at": datetime.datetime.now().isoformat(),
    }
    result = quizzes.insert_one(quiz)
    return jsonify({"message": "Quiz created!", "_id": str(result.inserted_id)})


# ============ RAZORPAY PAYMENT INTEGRATION ============

# Initialize Razorpay client
try:
    import razorpay
    from bson import ObjectId
    import time

    # Use your actual Razorpay test keys
    RAZORPAY_KEY_ID = "rzp_test_T2zJ8dNx0Nchzu"
    RAZORPAY_KEY_SECRET = "hzbeamTVRd0G06j4WCEGIHrZ"  # Replace with your actual secret
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    print("✅ Razorpay initialized successfully")
except ImportError:
    print("⚠️ Razorpay library not installed. Run: pip install razorpay")
    razorpay_client = None
except Exception as e:
    print(f"⚠️ Razorpay initialization error: {e}")
    razorpay_client = None


# Create Razorpay order
@app.route("/api/fee/razorpay/order", methods=["POST"])
@token_required
def create_razorpay_order(current_user):
    if not razorpay_client:
        return jsonify({"message": "Razorpay not configured"}), 500

    try:
        data = request.json
        amount = data.get("amount")
        student_id = data.get("student_id")
        fee_structure_id = data.get("fee_structure_id")

        print(f"📝 Creating order - Amount: {amount}")

        if not amount or amount <= 0:
            return jsonify({"message": "Invalid amount"}), 400

        # 🔥 Check if amount exceeds limit
        if amount > 100000:
            return (
                jsonify(
                    {
                        "message": f"Amount ₹{amount:,.2f} exceeds maximum limit of ₹100,000. Please pay in installments.",
                        "max_allowed": 100000,
                    }
                ),
                400,
            )

        # Get fee for description
        fee = None
        semester = "Semester"
        if fee_structure_id:
            try:
                fee = fee_structures.find_one({"_id": ObjectId(fee_structure_id)})
                if fee:
                    semester = fee.get("semester", "Semester")
            except:
                pass

        # Create order
        order_data = {
            "amount": int(amount * 100),  # Amount in paise
            "currency": "INR",
            "receipt": f"receipt_{student_id}_{int(time.time())}",
            "notes": {
                "student_id": str(student_id),
                "fee_structure_id": str(fee_structure_id) if fee_structure_id else "",
                "semester": semester,
            },
        }

        order = razorpay_client.order.create(data=order_data)
        print(f"✅ Order created: {order['id']}")

        return (
            jsonify(
                {
                    "order_id": order["id"],
                    "amount": order["amount"],
                    "currency": order["currency"],
                    "semester": semester,
                    "razorpay_key_id": RAZORPAY_KEY_ID,
                }
            ),
            200,
        )

    except Exception as e:
        print(f"❌ Order creation error: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"message": str(e)}), 500


# Verify Razorpay payment
@app.route("/api/fee/razorpay/verify", methods=["POST"])
@token_required
def verify_razorpay_payment(current_user):
    if not razorpay_client:
        return jsonify({"message": "Razorpay not configured"}), 500

    try:
        data = request.json
        order_id = data.get("razorpay_order_id")
        payment_id = data.get("razorpay_payment_id")
        signature = data.get("razorpay_signature")
        student_id = data.get("student_id")
        fee_structure_id = data.get("fee_structure_id")
        amount = data.get("amount")

        print(f"📝 Verifying payment - Order: {order_id}, Payment: {payment_id}")

        # Verify signature
        params_dict = {
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        }

        razorpay_client.utility.verify_payment_signature(params_dict)
        print("✅ Signature verified")

        # Get student data
        student_data = student.find_one({"student_id": student_id})
        if not student_data:
            return jsonify({"message": "Student not found"}), 404

        student_name = student_data.get("name", "Student")
        student_email = student_data.get("email", "")

        # Generate receipt number
        receipt_number = f"REC-{datetime.datetime.now().strftime('%Y%m%d')}-{student_id}-{int(time.time()) % 10000}"

        # Check if payment already exists
        existing_payment = fee_payments.find_one({"transaction_id": payment_id})
        if existing_payment:
            print(f"⚠️ Payment already recorded: {payment_id}")
            return (
                jsonify(
                    {
                        "message": "Payment already recorded",
                        "receipt_number": existing_payment.get("receipt_number"),
                    }
                ),
                200,
            )

        # Record payment
        payment = {
            "student_id": student_id,
            "fee_structure_id": fee_structure_id,
            "amount": amount,
            "payment_method": "Razorpay",
            "transaction_id": payment_id,
            "status": "Success",
            "payment_date": datetime.datetime.now().isoformat(),
            "receipt_number": receipt_number,
            "created_at": datetime.datetime.now().isoformat(),
        }

        fee_payments.insert_one(payment)
        print(f"✅ Payment recorded: {receipt_number}")

        # Update fee structure
        if fee_structure_id:
            try:
                fee = fee_structures.find_one({"_id": ObjectId(fee_structure_id)})
                if fee:
                    new_paid = fee.get("paid_amount", 0) + amount
                    new_pending = fee.get("total_fee", 0) - new_paid
                    status = "Paid" if new_pending <= 0 else "Unpaid"

                    fee_structures.update_one(
                        {"_id": ObjectId(fee_structure_id)},
                        {
                            "$set": {
                                "paid_amount": new_paid,
                                "pending_amount": new_pending,
                                "status": status,
                            }
                        },
                    )
                    print(f"✅ Fee structure updated: {status}")

                    # If fully paid, remove reminder
                    if status == "Paid":
                        fee_reminders.update_one(
                            {
                                "student_id": student_id,
                                "fee_structure_id": fee_structure_id,
                            },
                            {
                                "$set": {
                                    "resolved": True,
                                    "resolved_at": datetime.datetime.now().isoformat(),
                                }
                            },
                        )
            except Exception as e:
                print(f"⚠️ Error updating fee structure: {e}")

        # Send confirmation email
        try:
            if student_email:
                send_payment_confirmation_email(
                    student_email, student_name, amount, receipt_number, "Razorpay"
                )
        except Exception as e:
            print(f"Email notification failed: {e}")

        return (
            jsonify(
                {
                    "message": "Payment verified and recorded",
                    "receipt_number": receipt_number,
                }
            ),
            200,
        )

    except razorpay.errors.SignatureVerificationError as e:
        print(f"❌ Signature verification failed: {e}")
        return jsonify({"message": "Invalid signature"}), 400
    except Exception as e:
        print(f"❌ Payment verification error: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"message": str(e)}), 400


# RUN APP
if __name__ == "__main__":
    app.run(debug=True)
