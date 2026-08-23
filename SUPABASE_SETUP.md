# Supabase Setup Guide for Healthcare MCP Server

This guide explains how to connect your Healthcare MCP Server to Supabase for persistent storage of doctors, schedules, and appointments.

## Quick Start

### 1. Create Supabase Project

1. Go to [https://supabase.com](https://supabase.com) and sign up/login
2. Click "New Project"
3. Enter project name: `healthcare-mcp`
4. Set a secure database password (save this!)
5. Choose region closest to your users
6. Wait for project provisioning (~2 minutes)

### 2. Get API Credentials

Once project is ready:

1. Go to **Project Settings** → **API**
2. Copy these values:
   - **URL**: `https://xxxxxx.supabase.co` → Set as `SUPABASE_URL`
   - **anon public**: `eyJhbG...` → Set as `SUPABASE_KEY`

   ![API Settings Location](https://i.imgur.com/example.png)

### 3. Create Database Tables

1. Go to **SQL Editor** → **New query**
2. Copy entire contents of `supabase_schema.sql` from this project
3. Paste into SQL Editor
4. Click **Run**
5. You should see: "Success. No rows returned"

### 4. Configure Environment

Update your `.env` file:

```bash
# Mistral AI API Configuration
MISTRAL_API_KEY=your-mistral-key

# Supabase Configuration
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...your-anon-key
```

### 5. Seed Database

Run the seeder to populate initial doctor data:

```bash
python seed_database.py
```

Expected output:
```
🔌 Testing database connection...
   ✅ Connection successful!

📋 Step 1: Seeding doctors...
   ✅ Seeded 8 doctors

📅 Step 2: Seeding doctor schedules...
   ✅ Seeded 40 schedules

✨ Database seeding complete!
```

### 6. Start Server

```bash
./start.sh
# or
python -m uvicorn backend.main:app --reload --port 8000
```

### 7. Test API

Open browser to: `http://localhost:8000/mcp/tools`

You should see 7 tools listed including:
- `get_doctors`
- `get_available_slots`
- `book_appointment`
- `get_appointment`
- `cancel_appointment`

---

## Testing the Flow

### 1. Get Doctors

```bash
curl -X POST http://localhost:8000/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_doctors",
    "args": {"specialty": "cardiology"}
  }'
```

### 2. Check Available Slots

```bash
curl -X POST http://localhost:8000/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_available_slots",
    "args": {
      "specialty": "cardiology",
      "date": "2026-01-27"
    }
  }'
```

### 3. Book Appointment

```bash
curl -X POST http://localhost:8000/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "book_appointment",
    "args": {
      "user_id": "patient_001",
      "date": "2026-01-27",
      "time": "10:00",
      "specialty": "cardiology",
      "reason": "Annual heart checkup"
    }
  }'
```

---

## Database Schema Overview

```
┌─────────────┐       ┌──────────────────┐       ┌─────────────────┐
│   doctors   │◄──────┤ doctor_schedules │       │   appointments  │
├─────────────┤       ├──────────────────┤       ├─────────────────┤
│ id          │       │ id               │       │ id              │
│ name        │       │ doctor_id        │──────►│ patient_id      │
│ specialty   │       │ day_of_week      │       │ doctor_id       │
│ email       │       │ start_time       │       │ appointment_date│
│ years_exp   │       │ end_time         │       │ appointment_time│
└─────────────┘       └──────────────────┘       │ specialty       │
                                                  │ status          │
┌─────────────────┐                               └─────────────────┘
│ doctor_avail    │
│ (overrides)     │
├─────────────────┤
│ doctor_id       │
│ date            │
│ is_available    │
│ reason          │
└─────────────────┘
```

---

## Troubleshooting

| Error | Solution |
|-------|----------|
| `SUPABASE_URL not set` | Check `.env` file has both URL and KEY |
| `relation "doctors" does not exist` | Run `supabase_schema.sql` in SQL Editor |
| `403: Permission denied` | Check RLS policies are enabled in schema |
| `Connection refused` | Verify Supabase project is active |
| `seed_database.py fails` | Ensure `pip install supabase` |

---

## Security Notes

- **anon key** is safe for client-side use (has limited permissions)
- For admin operations, use **service_role key** (keep secret!)
- Row Level Security (RLS) is enabled on all tables
- Never commit `.env` to git

---

## Next Steps

- [ ] Add real-time subscriptions for live availability
- [ ] Implement patient authentication
- [ ] Add appointment reminders
- [ ] Create admin dashboard