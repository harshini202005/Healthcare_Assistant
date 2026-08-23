# 🏥 Healthcare Assistant - Logging Guide

## 📋 How to View Logs

### **Option 1: Live Terminal Logs (Recommended for Development)**
Run the server in the foreground to see all logs in real-time:

```bash
./run.sh
```

Or manually:
```bash
source .venv/bin/activate
python main.py
```

You'll see output like:
```
================================================================================
🔧 TOOL CALL: generate_diet
📥 INPUT ARGS:
   • preferences: vegetarian
   • calories: 2000
--------------------------------------------------------------------------------
✅ SUCCESS
📤 OUTPUT:
   🥗 Diet: vegetarian
   📊 Calories: 2000
   📋 Meals: 4
================================================================================
```

### **Option 2: Background Server + View Logs**
If server is running in background, view logs with:

```bash
./logs.sh
```

Or manually:
```bash
tail -f server.log
```

### **Option 3: Check Recent Logs**
View last 50 lines of logs:

```bash
tail -50 server.log
```

Or all logs:
```bash
cat server.log
```

## 📊 What You'll See in Logs

### **When a tool is called:**
- 🔧 Tool name
- 📥 Input arguments
- ✅/❌ Success or error status
- 📤 Output details

### **For Diet Plans:**
```
🔧 TOOL CALL: generate_diet
📥 INPUT ARGS:
   • preferences: keto
   • calories: 1800
   • allergies: ['nuts', 'dairy']
✅ SUCCESS
📤 OUTPUT:
   🥗 Diet: keto
   📊 Calories: 1800
   📋 Meals: 4
```

### **For Appointments:**
```
🔧 TOOL CALL: book_appointment
📥 INPUT ARGS:
   • user_id: PAT001
   • time: 2026-01-16T10:00
   • specialty: cardiology
   • reason: checkup
✅ SUCCESS
📤 OUTPUT:
   🎫 Confirmation: BKG-20260115-PAT001
   👤 Patient: PAT001
   📅 Time: 2026-01-16 10:00
```

### **For Health Queries:**
```
🔧 TOOL CALL: general_query
📥 INPUT ARGS:
   • question: What are benefits of water?
✅ SUCCESS
📤 OUTPUT:
   💬 Answer: Drinking adequate water is essential for health. Benefits include...
```

## 🎯 Quick Commands Reference

```bash
# Start with live logs
./run.sh

# Start in background
./start.sh

# View live logs (if running in background)
./logs.sh

# Stop the server
lsof -ti:8000 | xargs kill -9

# Check if server is running
lsof -i:8000

# Clear old logs
> server.log
```

## 🔍 Debugging Tips

### See HTTP requests:
The logs show:
- Incoming HTTP requests
- Tool executions
- Response status

### Filter specific tool:
```bash
grep "generate_diet" server.log
grep "book_appointment" server.log
grep "general_query" server.log
```

### See only errors:
```bash
grep "ERROR" server.log
grep "❌" server.log
```

### See only successful calls:
```bash
grep "✅ SUCCESS" server.log
```

## 📝 Log Files

- `server.log` - Main server logs (created when running in background)
- Terminal output - Real-time logs (when running ./run.sh)

## 💡 Pro Tips

1. **Development**: Use `./run.sh` to see everything in real-time
2. **Production**: Use `./start.sh` to run in background
3. **Monitoring**: Keep `./logs.sh` open in another terminal
4. **Debugging**: Check `server.log` for historical data

## 🎨 Log Format

Each tool call shows:
```
================================================================================
🔧 TOOL CALL: [tool_name]
📥 INPUT ARGS:
   • arg1: value1
   • arg2: value2
--------------------------------------------------------------------------------
✅ SUCCESS / ❌ ERROR
📤 OUTPUT:
   [formatted output]
================================================================================
```

This makes it easy to:
- Track what tools are being called
- See input parameters
- Verify outputs
- Debug issues
- Monitor system activity
