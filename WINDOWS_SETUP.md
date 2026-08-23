# Healthcare Chatbot - Windows Setup Guide

Complete setup instructions for running the Healthcare MCP Chatbot on Windows.

## Prerequisites

- Windows 10/11
- Python 3.10 or higher
- Git (optional, for cloning)
- Supabase account (free tier works)

## Step 1: Install Python

1. Download Python from [python.org](https://www.python.org/downloads/)
2. Run installer and **CHECK "Add Python to PATH"**
3. Verify installation:
   ```cmd
   python --version
   pip --version
   ```

## Step 2: Get the Project

### Option A: Download ZIP
1. Download project as ZIP
2. Extract to `C:\Healthcare` (or your preferred location)
3. Open Command Prompt:
   ```cmd
   cd C:\Healthcare
   ```

### Option B: Clone with Git
```cmd
git clone <repository-url> C:\Healthcare
cd C:\Healthcare
```

## Step 3: Create Virtual Environment

```cmd
python -m venv venv
venv\Scripts\activate
```

You should see `(venv)` in your prompt.

## Step 4: Install Dependencies

```cmd
pip install -r requirements.txt
```

If you get SSL errors:
```cmd
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
```

## Step 5: Set Up Supabase Database

### 5.1 Create Supabase Account
1. Go to [supabase.com](https://supabase.com)
2. Sign up with GitHub/Google
3. Create new project
4. Wait for database to be ready (~2 minutes)

### 5.2 Get API Keys
1. Go to Project Settings → API
2. Copy `Project URL` → this is your `SUPABASE_URL`
3. Copy `anon public` key → this is your `SUPABASE_KEY`
4. Copy `service_role secret` key → this is your `SUPABASE_SERVICE_KEY`

### 5.3 Configure Environment
1. Copy `.env.example` to `.env`:
   ```cmd
   copy .env.example .env
   ```

2. Edit `.env` with Notepad:
   ```cmd
   notepad .env
   ```

3. Replace placeholders:
   ```
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-anon-key-here
   SUPABASE_SERVICE_KEY=your-service-role-key-here
   MISTRAL_API_KEY=your-mistral-api-key-or-leave-blank
   ```

### 5.4 Create Database Tables
1. In Supabase Dashboard, go to SQL Editor
2. Copy contents of `supabase_schema.sql`
3. Paste and Run

### 5.5 Seed Sample Data
```cmd
python seed_database.py
```

## Step 6: Run the Application

### Start Backend Server
```cmd
python main.py
```

Or with custom port:
```cmd
python main.py --port 8080
```

You should see:
```
🚀 Starting Healthcare MCP Server
📡 API: http://localhost:8000
🌐 Web UI: http://localhost:8000
```

### Access the Application
- Open browser: `http://localhost:8000`
- Or click the link shown in terminal

## Troubleshooting

### Port Already in Use
```cmd
python main.py --port 8080
```

### Supabase Connection Failed
- Check `.env` file values
- Verify Supabase project is active
- Try creating new project if RLS issues persist

### Module Not Found Errors
```cmd
pip install -r requirements.txt --force-reinstall
```

### Permission Denied
Run Command Prompt as Administrator

### Database Not Seeded
If `seed_database.py` fails:
1. Check Supabase credentials
2. Ensure tables exist (run SQL schema)
3. Try individual commands in Supabase SQL Editor

## Features Available

Once running, you can:

| Feature | How to Access |
|---------|--------------|
| 💬 Chat | Type natural questions in the chat box |
| 📅 Book Appointment | Click "📅 Book Appointment" button |
| 🥗 Diet Plan | Click "🥗 Diet Plan" button |
| ⚡ Quick Tools | Click lightning bolt ⚡ near input |
| 👨‍⚕️ Find Doctors | Type "Show me cardiologists" |
| 📋 Check Schedule | Type "What is Dr. Priya Patel's schedule?" |
| 📅 Check Slots | Type "Available slots for dermatology tomorrow" |

## Stopping the Server

Press `Ctrl+C` in the terminal window.

## Project Structure

```
C:\Healthcare\
├── .env                  # Environment variables (create from .env.example)
├── requirements.txt      # Python dependencies
├── main.py              # Entry point
├── backend/
│   ├── main.py          # FastAPI server
│   ├── mcp.py           # MCP tool registry
│   ├── database.py      # Database operations
│   └── tools/
│       ├── doctors.py   # Doctor tools
│       ├── booking.py   # Appointment tools
│       ├── diet.py      # Diet plan tools
│       └── general.py   # Health Q&A tools
├── frontend/
│   └── index.html       # Chat UI
└── supabase_schema.sql  # Database setup
```

## Updating

To update to latest version:
```cmd
cd C:\Healthcare
git pull  # If using git
pip install -r requirements.txt --upgrade
```

## Need Help?

- Check logs in terminal for errors
- Verify all `.env` values are correct
- Ensure Python 3.10+ is installed
- Try restarting the server