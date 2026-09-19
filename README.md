# 📌 Geo-Location Based Smart Attendance System with Analytics & Prediction

## 📖 Project Description

The Geo-Location Based Smart Attendance System is an advanced, full-stack web application designed to solve proxy attendance and provide deep academic insights. It leverages browser-based **geo-location validation (geo-fencing)** to ensure students are physically present within a defined radius (e.g., a college campus or classroom) before they can mark their attendance.

Beyond basic tracking, the system features robust **role-based authentication** (for Admins and Students), a complete **subject management system**, and an **advanced analytics and prediction engine**. By analyzing past behavior, the system calculates current attendance trends, alerts students to attendance risks, and forecasts future attendance percentages.

---

## 🚀 Features

### 1. Authentication System
- **Role-Based Access Control:** Distinct portals and permissions secure the platform for both 'Admin' and 'Student' roles.
- **Secure Login:** Session-based authentication using hashed passwords protects student and administrative data securely.

### 2. Student Profile System
- **Mandatory Onboarding:** Upon their first login, students must fill out their complete academic details (Degree, Branch, Specialization, Year, Section) before accessing the tracking portal.

### 3. Geo-location Based Attendance
- **Browser Geolocation API:** Uses native HTML5 APIs to pinpoint the student's exact coordinates.
- **Geo-Fencing:** Verifies if the user is within an allowed physical radius (e.g., 100 meters) of the campus coordinates.
- **Anti-Spoofing:** Actively prevents attendance from being marked outside the designated physical location.

### 4. Subject Management (Admin)
- **Course Setup:** Admins can add subjects and define the total hours required for each.
- **Student Assignment:** Admins can assign specific subjects to individual students or efficiently use a "Select All" bulk assignment feature.

### 5. Attendance Tracking
- **Subject-Wise Tracking:** Students mark attendance accurately categorized by their assigned subjects.
- **Late Arrival Tracking:** Timestamps are recorded, allowing for the calculation of late arrivals dynamically.

### 6. Analytics Dashboard
- **Comprehensive Overviews:** Displays absolute total present days, absent days, and overall attendance percentage.
- **Subject-Wise Performance:** Highlights strong subjects (>85%) and weak subjects (<75%).
- **Trend Analysis:** Analyzes the last 7–10 attendance records to determine if attendance is improving, declining, or stable.
- **Attendance Streaks:** Calculates current consecutive present days and longest all-time streak.

### 7. Prediction System
- **Future Forecasting:** Predicts future attendance percentages by extrapolating current behavior.
- **Risk Assessment:** Calculates the risk of falling below a mandatory threshold (e.g., 75%) and displays warning flags.
- **Recovery Strategy:** Suggests the exact number of consecutive classes required to recover to a safe attendance level.

---

## 🧠 Analytics & Dataset Explanation

This system is completely self-contained and **no external dataset is used**. All data is generated dynamically from real user interactions.

### Data Generation & Storage
- Data is aggregated directly from attendance records stored securely in the PostgreSQL relational database.
- The working dataset includes:
  - Daily attendance logs (Present/Absent).
  - Subject-wise timestamps.
  - Calculated late flags.

### Prediction Logic
The Predictive Model evaluates historical attendance data using the following logic:
1. It converts attendance history into a binary sequence (`1 = present`, `0 = absent`).
2. It calculates the current attendance rate over the total elapsed days.
3. It forecasts future attendance assuming the student maintains the exact same trend over a specified future period.

**Formula Used:**
```text
predicted_attendance = (current_present + (rate * future_days)) / (total_days + future_days)
```

---

## 📍 Geo-Location System Explanation

The geo-location validation heavily relies on frontend-to-backend coordinate syncing.

- **Frontend Collection:** Uses the native browser API (`navigator.geolocation.getCurrentPosition()`) to retrieve exact Latitude and Longitude variables from the student's device.
- **Backend Validation:** The Flask backend utilizes the Python `geopy` library (or equivalent Haversine mathematics).
- **Purpose:** Calculates the precise geodesic distance between the student's reported location and the fixed, admin-defined attendance 'hotspot'.
- **Geo-Fencing Logic:**
  - If calculated distance `≤ 100 meters` → **Allow** attendance marking.
  - If calculated distance `> 100 meters` → **Reject** transaction.

---

## 🛠️ Tech Stack & Libraries

### Backend
- **Python:** Core programming language.
- **Flask:** Lightweight web framework for handling routing, APIs, templating, and session state.

### Database
- **PostgreSQL:** Powerful relational database used for storing users, credentials, attendance records, profiles, and subjects.
- **psycopg2:** The PostgreSQL database adapter for Python allowing secure SQL execution.

### Frontend
- **HTML5:** Semantic structure.
- **CSS3:** Custom styling representing a modern, dynamic, 'glassmorphism' aesthetic.
- **JavaScript:** Dynamic behavior, mapping, asynchronous fetch requests, and geolocation handling.

### External Libraries
- `geopy` (or `math`): Distance calculations for accurate geo-fencing.
- `datetime`: Strict temporal tracking for streaks and predictions.
- *(Optional)* `scikit-learn`: Planned for advanced Machine Learning prediction models in future implementations.

---

## 🗄️ Database Design

The relational schema is built on core linked tables ensuring strong data integrity:
- `users`: Stores login credentials, roles (admin/student), and hashed passwords.
- `attendance`: Stores timestamped attendance logs with coordinate data.
- `subjects`: Master table of subject information and total required hours.
- `student_subjects`: Joining table mapping individual students to their respective subjects.
- `student_profiles`: Detailed academic onboarding records (Degree, Branch, Year).

---

## 🔐 Security Features

- **Session-Based Authentication:** Employs secure, encrypted Flask sessions mapped to user IDs.
- **Role-Based Access Control (RBAC):** Distinct route guarding to ensure Students cannot access Admin functionality.
- **Parameterized SQL Queries:** Implemented natively via `psycopg2` to completely prevent SQL injection attacks.
- **Password Hashing:** Passwords are cryptographically hashed using SHA-256 before insertion into the database.

---

## 📊 How the System Works

1. **Account Creation:** The Admin creates basic student accounts (Username/Password).
2. **Subject Assignment:** Admin configures campus location boundaries and assigns subjects to students.
3. **Student Login:** Student logs in using their credentials.
4. **Onboarding:** First-time students completely fill out their academic profile.
5. **Physical Arrival:** The student must physically travel to the allowed campus location.
6. **Location Validation:** The system pings the browser API and verifies geographical boundaries.
7. **Attendance Marking:** If within radius, the student selects a subject and successfully marks attendance.
8. **Real-Time Analytics:** The system instantaneously updates predictive models, streaks, and risk assessments.

---

## 📈 Future Improvements

- **Biometric Integration:** Implement fingerprint authentication using native hardware APIs.
- **Face Recognition:** Add a lightweight OpenCV camera module for visual identity verification.
- **Mobile Application:** Port the frontend to a native React Native or Flutter application.
- **Advanced Machine Learning:** Integrate advanced predictive models incorporating weather patterns, test scores, or historical semester data.

---

## ⚙️ Setup Instructions

Follow these steps to deploy the application locally.

1. **Install Dependencies:**
   Ensure Python is installed, then run the following in your terminal:
   ```bash
   pip install flask psycopg2-binary geopy
   ```

2. **Setup PostgreSQL Database:**
   - Create a database in your local PostgreSQL instance named `attendance_system`.
   - Update the connection credentials (User and Password) within the `db.py` file to match your local setup.

3. **Run the Application:**
   Execute the core Python script to start the Flask development server:
   ```bash
   python app.py
   ```

4. **Access the Portal:**
   Open your preferred modern web browser and navigate to:
   ```text
   http://127.0.0.1:5000
   ```

---

## 📌 Conclusion

The Geo-Location Based Smart Attendance System is a robust demonstration of **Full-Stack Development** bridging physical constraints with digital logic. It effectively solves a real-world problem (attendance spoofing) through smart **Geo-Location Integration** and elevates the user experience by delivering immediate, actionable **Data Analytics and Prediction**.
