# 🎓 Student Dashboard & Learning Management System

## 📌 Overview
A comprehensive student portal with real-time features including attendance tracking, academic performance analytics, interactive learning tools, and gamification elements.

## ✨ Features

### 🔐 Authentication
- JWT-based authentication
- OTP password reset
- Remember me functionality
- Role-based access (Student/Admin)

### 📊 Academic Tracking
- Interactive attendance charts
- Subject performance visualization
- Automated GPA calculation
- Class ranking system

### 💬 Collaboration
- Real-time chat with image sharing
- Discussion forum with replies
- Upvoting system

### 📚 Content Management
- Course materials repository
- Video lectures with YouTube integration
- Important materials bookmarking

### 🎮 Gamification
- Points system (5 pts/Present, 2 pts/Late)
- Achievement badges
- Leaderboard (Weekly/Monthly/All-time)

### 📱 Features
- Dark/Light mode
- PDF report generation
- Email result delivery
- Responsive design

## 🛠️ Tech Stack

### Backend
- Python 3.9+
- Flask 2.3+
- MongoDB
- JWT Authentication
- bcrypt password hashing

### Frontend
- HTML5, CSS3, JavaScript
- Chart.js
- html2canvas + jsPDF
- Font Awesome

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- MongoDB
- Git

### Installation
```bash
# Clone repository
git clone https://github.com/yourusername/student-portal.git

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
# Edit .env with your credentials

# Run application
python app.py
