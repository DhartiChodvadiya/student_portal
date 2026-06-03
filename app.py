from flask import Flask, request, jsonify, render_template, session
from flask_mail import Mail, Message
from database import student, admins, otps
import jwt
import datetime
from functools import wraps
import hashlib
import random
from flask_cors import CORS
from dotenv import load_dotenv
import os

# Load environment variables FIRST
load_dotenv()

app = Flask(__name__)
CORS(app)

# SECRET KEY - Load from .env or use default
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "your_secret_key_123")
# print(f"SECRET_KEY loaded: {app.config['SECRET_KEY']}")  # Removed for security
app.config["SESSION_COOKIE_SECURE"] = True

# Email Configuration
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 465
app.config["MAIL_USE_TLS"] = False
app.config["MAIL_USE_SSL"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "abcd1276@gmail.com")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "erwerhytujiokmni")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", "abcd1276@gmail.com")

mail = Mail(app)

# JWT FUNCTIONS
def generate_token(user_id, role):
    token = jwt.encode(
        {
            "user_id": user_id,
            "role": role,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=2),
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

# HOME
@app.route("/")
def home():
    return jsonify({"message": "Student Portal Backend Running"})

@app.route('/student')
def student_portal():
    return render_template('student.html')

@app.route('/admin')
def admin_portal():
    return render_template('admin.html')

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
    student.insert_one(
        {
            "student_id": data["student_id"],
            "name": data["name"],
            "email": data["email"],
            "password": hashed_password,
            "course": data["course"],
            "phoneno": data["phoneno"],
            "gender": data["gender"],
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

# FORGOT PASSWORD - Step 1: Request OTP
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
        {
            "email": email,
            "otp": otp,
            "created_at": datetime.datetime.utcnow(),
        }
    )

    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                .container {{
                    font-family: Arial, sans-serif;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f4f4f4;
                }}
                .header {{
                    background-color: #2563eb;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 10px 10px 0 0;
                }}
                .content {{
                    background-color: white;
                    padding: 30px;
                    border-radius: 0 0 10px 10px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }}
                .otp-code {{
                    font-size: 32px;
                    font-weight: bold;
                    color: #2563eb;
                    text-align: center;
                    padding: 20px;
                    background-color: #f0f0f0;
                    border-radius: 5px;
                    letter-spacing: 5px;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 20px;
                    color: #666;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Password Reset Request</h2>
                </div>
                <div class="content">
                    <p>Hello <strong>{student_data['name']}</strong>,</p>
                    <p>We received a request to reset your password.</p>
                    <p>Your OTP for password reset is:</p>
                    <div class="otp-code">{otp}</div>
                    <p>This OTP is valid for <strong>10 minutes</strong>.</p>
                    <p>If you didn't request this, please ignore this email.</p>
                    <hr>
                    <p style="color: #666; font-size: 14px;">Never share this OTP with anyone.</p>
                </div>
                <div class="footer">
                    <p>Student Portal Team</p>
                </div>
            </div>
        </body>
        </html>
        """

        msg = Message(
            subject="Password Reset OTP - Student Portal",
            recipients=[email],
            html=html_content,
        )
        mail.send(msg)
        return jsonify({"message": f"OTP sent to {email}. Check your inbox."}), 200
    except Exception as e:
        print(f"Email error: {str(e)}")
        return jsonify({"message": f"Test OTP: {otp} (Email not configured)", "otp": otp}), 200

# VERIFY OTP
@app.route("/student/verify_otp", methods=["POST"])
def verify_otp():
    data = request.json
    email = data.get("email")
    otp = data.get("otp")

    otp_data = otps.find_one({"email": email, "otp": otp})

    if not otp_data:
        return jsonify({"message": "Invalid OTP"}), 400

    created_at = otp_data.get("created_at")
    if created_at and (datetime.datetime.utcnow() - created_at).seconds > 600:
        otps.delete_many({"email": email})
        return jsonify({"message": "OTP has expired. Please request a new one."}), 400

    return jsonify({"message": "OTP verified successfully"}), 200

# RESET PASSWORD
@app.route("/student/reset_password", methods=["POST"])
def reset_password():
    data = request.json
    email = data.get("email")
    otp = data.get("otp")
    new_password = data.get("new_password")

    otp_data = otps.find_one({"email": email, "otp": otp})
    if not otp_data:
        return jsonify({"message": "Invalid OTP. Please request a new one."}), 400

    created_at = otp_data.get("created_at")
    if created_at and (datetime.datetime.utcnow() - created_at).seconds > 600:
        otps.delete_many({"email": email})
        return jsonify({"message": "OTP has expired. Please request a new one."}), 400

    if len(new_password) < 6:
        return jsonify({"message": "Password must be at least 6 characters long"}), 400

    hashed_password = hashlib.sha256(new_password.encode()).hexdigest()
    result = student.update_one(
        {"email": email}, {"$set": {"password": hashed_password}}
    )

    otps.delete_many({"email": email})

    if result.modified_count > 0:
        return jsonify({"message": "Password reset successful! You can now login."}), 200

    return jsonify({"message": "Student not found"}), 404

# CHANGE PASSWORD
@app.route("/student/change_password", methods=["POST"])
@token_required
def change_password(current_user):
    data = request.json
    old_password = data.get("old_password")
    new_password = data.get("new_password")

    student_data = student.find_one({"student_id": current_user["user_id"]})
    if not student_data:
        return jsonify({"message": "Student not found"}), 404

    hashed_old = hashlib.sha256(old_password.encode()).hexdigest()
    if student_data["password"] != hashed_old:
        return jsonify({"message": "Current password is incorrect"}), 401

    if len(new_password) < 6:
        return jsonify({"message": "New password must be at least 6 characters long"}), 400

    hashed_new = hashlib.sha256(new_password.encode()).hexdigest()
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
            {"$set": {"password": hashlib.sha256(data["password"].encode()).hexdigest()}}
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
    update_data = {
        "name": data["name"],
        "email": data["email"],
    }
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

# RUN APP
if __name__ == "__main__":
    app.run(debug=True)