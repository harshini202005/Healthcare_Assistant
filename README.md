# 🏥 Healthcare Assistant - AI-Powered Health Management System

A modern healthcare management system with AI-powered chat interface, diet planning, and appointment booking capabilities.

## 🚀 Quick Start

### Option 1: Simple One-Command Start (Recommended)
```bash
./start.sh
```

### Option 2: Using Python
```bash
# Activate virtual environment first
source .venv/bin/activate

# Run the application
python main.py
```

### Option 3: Manual Start
```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Install dependencies (first time only)
pip install -r requirements.txt

# 3. Start the server
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## 📱 Access the Application

1. **Backend API**: http://localhost:8000
2. **Frontend**: Open `frontend/index.html` in your browser
3. **API Docs**: http://localhost:8000/docs

## 🔑 Demo Accounts

The app ships with a Doctor Dashboard + patient portal. To try it without creating your own account, seed the demo data first (`python seed_database.py` — needs `SUPABASE_URL`/`SUPABASE_KEY` set, see `SUPABASE_SETUP.md`), then sign in with any of these on the login page (also shown there under "Try a demo account"):

| Role | Name | Email | Password |
|---|---|---|---|
| Patient | Harshini | `harshini.demo@healthcare-demo.com` | `Patient@123` |
| Patient | Rohan | `rohan.demo@healthcare-demo.com` | `Patient@123` |
| Doctor | Dr. Priya (Dermatology) | `priya.derm@healthcare-demo.com` | `Doctor@123` |
| Doctor | Dr. Rahul (Cardiology) | `rahul.cardio@healthcare-demo.com` | `Doctor@123` |
| Doctor | Dr. Ananya (Nutrition) | `ananya.nutrition@healthcare-demo.com` | `Doctor@123` |

These are seeded demo/test accounts only — no real patient data.

## ✨ Features

### 💬 Smart Chat Interface
- Natural language understanding
- Automatically detects your intent (health query, diet plan, or appointment)
- No need to select tools manually!

### 🥗 Diet Plan Generator
Just ask naturally:
- "Generate a vegetarian diet plan for 2000 calories"
- "Give me a keto meal plan"
- "Create a diabetic-friendly diet"

### 📅 Appointment Booking
Book appointments conversationally:
- "Book an appointment for PAT001 tomorrow at 10 AM for general checkup"
- "Schedule a cardiology visit for PAT123 at 2 PM"

### 💊 General Health Assistant
Ask any health question:
- "What are the benefits of drinking water?"
- "How much sleep do I need?"
- "Tips for staying healthy"

## 🛠️ Setup (First Time)

```bash
# 1. Create virtual environment
python3 -m venv .venv

# 2. Activate it
source .venv/bin/activate  # On Mac/Linux
# or
.venv\Scripts\activate  # On Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python main.py
```

## 📦 Project Structure

```
Healthcare/
├── backend/
│   ├── main.py          # FastAPI application
│   ├── mcp.py           # MCP server implementation
│   └── tools/           # Tool implementations
│       ├── general.py   # Health Q&A
│       ├── diet.py      # Diet plan generator
│       └── booking.py   # Appointment booking
├── frontend/
│   └── index.html       # Chat interface
├── main.py              # Application launcher
├── start.sh             # Quick start script
├── requirements.txt     # Python dependencies
└── supabase_schema.sql  # Database schema (doctors, appointments, etc. — see SUPABASE_SETUP.md)
```

## 🎯 Example Queries

Try these in the chat interface:

**Health Questions:**
- "What are the benefits of meditation?"
- "How to improve my immune system?"
- "Best exercises for weight loss"

**Diet Plans:**
- "Create a 1800 calorie vegetarian diet plan"
- "Generate a high-protein meal plan for muscle building"
- "Keto diet plan with no dairy"

**Appointments:**
- "Book appointment for PAT001 tomorrow at 3 PM for checkup"
- "Schedule cardiology consultation for PAT456 next Monday at 10 AM"

## 🔧 Troubleshooting

### Server won't start?
```bash
# Make sure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt

# Try running directly
python main.py
```

### Port 8000 already in use?
```bash
# Find and kill the process
lsof -ti:8000 | xargs kill -9

# Or use a different port
uvicorn backend.main:app --reload --port 8001
```

### Frontend not connecting?
- Make sure backend is running on http://localhost:8000
- Check browser console for errors
- Try opening frontend/index.html directly in browser

## 📝 API Endpoints

- `GET /` - API information
- `GET /mcp/tools` - List available tools
- `POST /mcp/call` - Call a specific tool
- `GET /docs` - Interactive API documentation

## 🤝 Contributing

Feel free to enhance the system with:
- More health tools
- Better NLP for query understanding
- Additional features like medication tracking
- Integration with real healthcare APIs

## 📄 License

This project is for educational and demonstration purposes.



cd C:\Users\Admin\Desktop\Healthcare
.venv\Scripts\activate
python main.py