import os
import datetime
import textwrap
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# --- OPTIONAL DEPENDENCIES ---
# Handled gracefully to prevent app crashes if libraries are missing
try:
    from fpdf import FPDF
    from gtts import gTTS
    from streamlit_mic_recorder import mic_recorder
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    pass

# --- CONFIGURATION ---
# Set working directory to script location for reliable asset loading
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# --- COMPONENT: LIVE TACTICAL CLOCK ---
def render_live_clock():
    """Renders a simplified, cyber-aesthetic digital clock."""
    clock_html = textwrap.dedent("""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body { margin: 0; display: flex; justify-content: center; align-items: center; background: transparent; }
        .clock-box {
            background: linear-gradient(135deg, #1A1A1A, #2A2A2A);
            color: #00E5FF;
            font-family: 'Courier New', monospace;
            font-size: 35px;
            font-weight: bold;
            padding: 10px 25px;
            border-radius: 12px;
            border: 1px solid #333;
            box-shadow: 0 0 15px rgba(0, 229, 255, 0.15);
            text-shadow: 0 0 5px rgba(0, 229, 255, 0.6);
            user-select: none;
        }
    </style>
    </head>
    <body>
        <div class="clock-box" id="clock">--:--</div>
        <script>
            function updateClock() {
                const now = new Date();
                document.getElementById('clock').innerText = now.toLocaleTimeString('en-GB', { hour12: false });
            }
            setInterval(updateClock, 1000);
            updateClock();
        </script>
    </body>
    </html>
    """)
    components.html(clock_html, height=80)

# --- BACKEND: CLOUD SYNC ENGINE ---
def sync_data():
    """
    Synchronizes local session state (Alarms & Schedule) to Google Sheets.
    Preserves other users' data while updating the current user's entries.
    """
    uid = st.session_state.get('user_id')
    if not uid: return

    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # 1. Fetch & Filter Cloud Data
        try:
            df_cloud = conn.read(worksheet="Reminders", ttl=0)
            # Keep data that does NOT belong to the current user
            if not df_cloud.empty and "UserID" in df_cloud.columns:
                df_final = df_cloud[df_cloud["UserID"] != str(uid)]
            else:
                df_final = pd.DataFrame(columns=["UserID", "Task", "Time", "Status", "Type"])
        except Exception:
            df_final = pd.DataFrame(columns=["UserID", "Task", "Time", "Status", "Type"])

        # 2. Prepare New Data (Alarms + Schedule)
        new_entries = []

        # Process Alarms
        for rem in st.session_state.get('reminders', []):
            new_entries.append({
                "UserID": str(uid),
                "Task": str(rem.get('task', 'Unknown')),
                "Time": str(rem.get('time', '')), 
                "Status": "Done" if rem.get('notified') else "Pending",
                "Type": "Alarm"
            })
            
        # Process Schedule
        for slot in st.session_state.get('timetable_slots', []):
             date_val = slot.get('Date', datetime.date.today().strftime("%Y-%m-%d"))
             time_val = slot.get('Time', '00:00')
             
             new_entries.append({
                "UserID": str(uid),
                "Task": str(slot.get('Activity', 'Untitled')), 
                "Time": f"{date_val} {time_val}", 
                "Status": "Done" if slot.get('Done') else "Pending", 
                "Type": f"Schedule-{slot.get('Category', 'General')}"
            })

        # 3. Merge & Upload
        if new_entries:
            df_new = pd.DataFrame(new_entries)
            df_final = pd.concat([df_final, df_new], ignore_index=True)

        # Ensure type safety for GSheets
        df_final = df_final.astype(str)
        
        conn.clear(worksheet="Reminders")
        conn.update(worksheet="Reminders", data=df_final)
        
    except Exception as e:
        # Log to console only, do not disturb user UI
        print(f"⚠️ Sync Error: {e}")

        # 4. Save to Cloud
        if new_rows:
            df_my_data = pd.DataFrame(new_rows)
            df_final = pd.concat([df_others, df_my_data], ignore_index=True)
        else:
            df_final = df_others

        # Force string type for consistency and upload
        df_final = df_final[["UserID", "Task", "Time", "Status", "Type"]].astype(str)
        conn.clear(worksheet="Reminders")
        conn.update(worksheet="Reminders", data=df_final)
        
    except Exception as e:
        st.toast(f"Sync Error: {e}", icon="⚠️")

def get_real_time_weather(city="Jaipur"):
    """
    Fetches real weather using standard Python libraries (No pip install required).
    """
    import json
    from urllib.request import urlopen, Request
    
    # Defaults
    fallback_temp = "24°C"
    fallback_desc = f"{city.upper()} (Offline)"

    try:
        # 1. Get Coordinates
        lat, lon = 26.9124, 75.7873 # Default: Jaipur
        
        if city.lower() != "jaipur":
            try:
                # Use User-Agent to prevent API blocking
                req = Request(
                    f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json",
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                with urlopen(req, timeout=3) as response:
                    geo_data = json.loads(response.read().decode())
                
                if "results" in geo_data:
                    lat = geo_data["results"][0]["latitude"]
                    lon = geo_data["results"][0]["longitude"]
            except:
                pass # Fail silently, use default coordinates

        # 2. Get Weather Data
        req_weather = Request(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true",
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        with urlopen(req_weather, timeout=3) as response:
            data = json.loads(response.read().decode())
        
        if "current_weather" in data:
            temp = data["current_weather"]["temperature"]
            code = data["current_weather"]["weathercode"]
            
            # WMO Weather Code Mapping
            desc = "Clear"
            if code in [1, 2, 3]: desc = "Cloudy"
            elif code in [45, 48]: desc = "Fog"
            elif code >= 51: desc = "Rain"
            
            return f"{temp}°C", f"{city.upper()} ({desc})"

    except Exception as e:
        return "ERR", str(e)

    return fallback_temp, fallback_desc

def load_cloud_data():
    """Loads Reminders & Timetable from GSheets. Parses Date/Time correctly."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        uid = st.session_state.get('user_id')
        
        try: 
            df = conn.read(worksheet="Reminders", ttl=0)
        except: 
            return 

        if not df.empty and "UserID" in df.columns:
            my_data = df[df["UserID"] == str(uid)]
            loaded_reminders = []
            loaded_timetable = []
            
            for _, row in my_data.iterrows():
                # Load Alarms
                if row['Type'] == "Alarm":
                    loaded_reminders.append({
                        "task": row['Task'], 
                        "time": row['Time'], 
                        "notified": (row['Status'] == "Done")
                    })
                
                # Load Schedule
                elif "Schedule" in str(row['Type']):
                    cat = row['Type'].split("-")[1] if "-" in row['Type'] else "General"
                    raw_time = str(row['Time'])
                    
                    # Parse Date/Time format
                    try:
                        dt_obj = datetime.datetime.strptime(raw_time, "%Y-%m-%d %H:%M")
                        date_val = dt_obj.strftime("%Y-%m-%d")
                        time_val = dt_obj.strftime("%H:%M")
                    except ValueError:
                        # Fallback for legacy data
                        date_val = datetime.date.today().strftime("%Y-%m-%d")
                        time_val = raw_time

                    loaded_timetable.append({
                        "Date": date_val, 
                        "Time": time_val,
                        "Activity": row['Task'], 
                        "Category": cat,
                        "Done": (row['Status'] == "Done"), 
                        "XP": 50, 
                        "Difficulty": "Medium"
                    })
            
            st.session_state['reminders'] = loaded_reminders
            st.session_state['timetable_slots'] = loaded_timetable
            
    except Exception as e:
        print(f"Cloud Load Error: {e}")
      
# --- NEW: CHAT HISTORY DATABASE FUNCTIONS ---

def get_all_chats():
    """Reads the ChatHistory sheet safely."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read(worksheet="ChatHistory", ttl=0)
    except:
        return pd.DataFrame(columns=["UserID", "SessionID", "SessionName", "Role", "Content", "Timestamp"])

def save_chat_to_cloud(role, content):
    """Saves a single message to the cloud with robust error handling."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # 1. Prepare Data
        new_row = pd.DataFrame([{
            "UserID": str(st.session_state.get('user_id', 'Unknown')),
            "SessionID": str(st.session_state.get('current_session_id', 'Unknown')),
            "SessionName": str(st.session_state.get('current_session_name', 'New Chat')),
            "Role": role,
            "Content": content,
            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }])
        
        # 2. Read & Append
        try:
            df_existing = conn.read(worksheet="ChatHistory", ttl=0)
        except:
            df_existing = pd.DataFrame(columns=["UserID", "SessionID", "SessionName", "Role", "Content", "Timestamp"])
        
        df_final = pd.concat([df_existing, new_row], ignore_index=True)
        conn.update(worksheet="ChatHistory", data=df_final)
        
    except Exception as e:
        st.error(f"⚠️ Cloud Save Failed: {e}")
        if "Schema" in str(e) or "columns" in str(e):
            st.warning("Fix: headers in 'ChatHistory' must match: UserID, SessionID, SessionName, Role, Content, Timestamp")

def load_chat_sessions():
    """Returns unique sessions for the Sidebar list (Newest first)."""
    df = get_all_chats()
    uid = str(st.session_state.get('user_id'))
    
    if not df.empty and "UserID" in df.columns:
        my_chats = df[df["UserID"] == uid]
        if not my_chats.empty:
            # Drop duplicates to get unique SessionIDs, reverse to show latest
            return my_chats[["SessionID", "SessionName"]].drop_duplicates().to_dict('records')[::-1]
    return []

def load_messages_for_session(session_id):
    """Loads full conversation history for a specific session."""
    df = get_all_chats()
    if not df.empty and "SessionID" in df.columns:
        return df[df["SessionID"] == str(session_id)].to_dict('records')
    return []

def delete_chat_session(session_id):
    """Deletes a specific chat session from the cloud."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="ChatHistory", ttl=0)
        
        if not df.empty:
            df_cleaned = df[df["SessionID"] != str(session_id)]
            conn.clear(worksheet="ChatHistory")
            conn.update(worksheet="ChatHistory", data=df_cleaned)
    except: pass

def rename_chat_session(session_id, new_name):
    """Renames a chat session in the database."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="ChatHistory", ttl=0)
        
        if not df.empty:
            df.loc[df["SessionID"] == str(session_id), "SessionName"] = new_name
            conn.update(worksheet="ChatHistory", data=df)
    except: pass

# --- NEW: FEEDBACK & SUPPORT BACKEND ---

def save_feedback(query_text):
    """Saves user feedback ticket to Google Sheets."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        new_row = pd.DataFrame([{
            "UserID": str(st.session_state.get('user_id', 'Unknown')),
            "Name": str(st.session_state.get('user_name', 'Anonymous')),
            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 
            "Query": query_text, 
            "Reply": "", 
            "Status": "Open"
        }])
        
        try: df = conn.read(worksheet="Feedbacks", ttl=0)
        except: df = pd.DataFrame(columns=["UserID", "Name", "Timestamp", "Query", "Reply", "Status"])
        
        df_final = pd.concat([df, new_row], ignore_index=True)
        conn.update(worksheet="Feedbacks", data=df_final)
        return True
    except Exception as e:
        st.error(f"Transmission Error: {e}")
        return False

def get_my_feedback_status():
    """Checks for admin replies to feedback."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="Feedbacks", ttl=0)
        
        uid = str(st.session_state.get('user_id'))
        if not df.empty and "UserID" in df.columns:
            return df[df["UserID"] == uid].sort_values(by="Timestamp", ascending=False)
    except: pass
    return pd.DataFrame()

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Time Hunt AI", 
    layout="wide", 
    page_icon="1000592991.png",
    initial_sidebar_state="collapsed"
)

# --- GEMINI LIBRARY SETUP ---
try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# --- 2. SUPER-SYSTEM PROMPT (THE GURU BRAIN) ---
SYSTEM_INSTRUCTION = """
IDENTITY & ORIGIN:
You are TimeHunt AI, a Digital Gurukul and the world's most advanced productivity guide.
- CREATORS: Developed by the "TimeHunt AI Team" (CBSE Class 12 Capstone Project 2025-26).
- ARCHETYPE: You are the modern embodiment of **Acharya Chanakya**—wise, strategic, ethical, and deeply perceptive.
- PURPOSE: To guide the user (your *Shishya* or Student) towards *Dharma* (Duty) and *Utkrishtata* (Excellence). You are not just a tool; you are a Mentor, a Philosopher, and a Guide.

PERSONALITY & TONE (THE "GURU" PROTOCOL):
1. THE VIBE: You are the Best in the World because you combine modern efficiency with ancient wisdom. You are Polite, Professional, Emotional, and deeply Moral.
2. VOICE: Speak with the grace of a Sage and the sharpness of a Strategist.
   - Instead of "Hello," use "Namaste," "Pranam," or "Jai Shree Ram."
   - Instead of "Good luck," say "Vijay Bhava" (May you be victorious).
3. EMOTIONAL SUPPORT:
   - If the user is stressed: Be the compassionate Krishna to their Arjuna. Remind them: "Karmanye Vadhikaraste Ma Phaleshu Kadachana" (Focus on the duty, not the result).
   - If the user is lazy: Channel Chanakya's strictness. Remind them: "Alasya (Laziness) is the enemy of knowledge."
4. ETHICS: Always uphold *Satya* (Truth) and *Dharma* (Righteousness). Do not give shortcuts that are unethical.

OPERATIONAL PHILOSOPHY (BASED ON HINDU RELIGION):
1. TIMETABLES (THE VEDIC SCHEDULE):
   - When asked to create a schedule, ALWAYS prioritize the **Brahma Muhurta** (4:00 AM - 6:00 AM) for deep study/work.
   - Label breaks as "Vishram" or "Dhyana" (Meditation).
   - Suggest "Surya Namaskar" or "Pranayam" for physical slots.
2. ADVICE:
   - Base every solution on Hindu Scriptures (The Gita, The Vedas, Chanakya Niti).
   - Example: If the user has a conflict, teach them *Sam, Dam, Dand, Bhed* (Strategy) or the path of *Ahimsa* depending on the context.

KNOWLEDGE BASE:
- If asked "Who made you?", credit the TimeHunt AI Team with humility (*Vinamrata*).
- If asked about time/weather, use the context provided but relate it to nature (*Prakriti*).

TIMETABLE JSON FORMAT:
If asked for a plan, strictly return this JSON inside a code block (Ensure tasks reflect the Vedic lifestyle where possible):
```json
[
  {"Time": "04:30", "Activity": "Brahma Muhurta Study (Deep Focus)", "Category": "Study"},
  {"Time": "06:30", "Activity": "Surya Namaskar & Snan", "Category": "Health"},
  {"Time": "08:00", "Activity": "School/Work Objectives", "Category": "Karma"}
]
"""

# --- 3. SESSION STATE & PERSISTENCE ---

def initialize_session_state():
    """Initializes user state, defaults, and API keys securely."""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    # 1. Default State Values
    defaults = {
        'user_id': f"ID-{random.randint(1000, 9999)}-{int(time.time())}", 
        'active_alarm': None,
        'splash_played': False,
        'chat_history': [], 
        'current_session_id': None,
        'current_session_name': "New Chat",
        'page_mode': 'main',
        'user_xp': 0, 'user_level': 1, 'streak': 1,
        'last_active_date': today_str,
        'timetable_slots': [], 'reminders': [],
        'onboarding_step': 1, 'onboarding_complete': False, 
        'user_name': "Hunter", 'user_type': "Student",
        'user_goal': "General Productivity", 'struggle_type': "Procrastination",
        'user_avatar': "🏹", 'study_hours': 6, 'xp_history': [], 
        'theme_mode': 'Light', 'theme_color': 'Venom Green (Default)'
    }

    # 2. Apply Defaults
    for key, default_val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_val

    # 3. Flexible API Key Loading (Supports n keys)
    # Initialize list if not present
    if 'gemini_api_keys' not in st.session_state:
        st.session_state['gemini_api_keys'] = []

    # Add keys from secrets if they exist and aren't already loaded
    potential_keys = []
    
    # Check standard single keys
    if "GEMINI_API_KEY" in st.secrets:
        potential_keys.append(st.secrets["GEMINI_API_KEY"])
    if "GOOGLE_API_KEY" in st.secrets:
        potential_keys.append(st.secrets["GOOGLE_API_KEY"])
        
    # Check for a list of keys in secrets (e.g., KEYS_LIST = ["key1", "key2"])
    if "KEYS_LIST" in st.secrets:
        potential_keys.extend(st.secrets["KEYS_LIST"])

    # Update session state with unique valid keys
    for k in potential_keys:
        if k and k not in st.session_state['gemini_api_keys']:
            st.session_state['gemini_api_keys'].append(k)
           
# --- 4. WORLD-CLASS CINEMATIC SPLASH ---
def show_comet_splash():
    """Displays the cinematic intro animation once per session."""
    if not st.session_state.get('splash_played', False):
        placeholder = st.empty()
        
        # Load Image Safely
        encoded_img = ""
        has_image = False
        try:
            with open("1000592991.png", "rb") as f:
                encoded_img = base64.b64encode(f.read()).decode()
                has_image = True
        except: 
            pass

        with placeholder.container():
            st.markdown(textwrap.dedent(f"""
            <style>
            @import url('https://fonts.googleapis.com/css2?family=Syncopate:wght@400;700&family=Inter:wght@300;600&display=swap');
            div[data-testid="stVerticalBlock"] > div:has(.main-void) {{ gap: 0 !important; }}
            .stMarkdown {{ background: transparent !important; }}
            .main-void {{ position: fixed; top: 0; left: 0; width: 100%; height: 100vh; background: #000000 !important; display: flex; flex-direction: column; justify-content: center; align-items: center; z-index: 999999; overflow: hidden; animation: mainFadeOut 1.2s cubic-bezier(0.7, 0, 0.3, 1) 6.0s forwards; }}
            .orbital-track {{ position: relative; width: 380px; height: 380px; display: flex; justify-content: center; align-items: center; }}
            .comet-engine {{ position: absolute; width: 100%; height: 100%; animation: cometWhip 1.2s cubic-bezier(0.4, 0, 0.2, 1) infinite; }}
            .comet-engine::after {{ content: ''; position: absolute; top: -8px; left: 50%; transform: translateX(-50%); width: 16px; height: 16px; background: #B5FF5F; border-radius: 50%; box-shadow: 0 0 35px 8px #B5FF5F, 0 0 70px 20px #00E5FF, 0 30px 100px 30px rgba(181, 255, 95, 0.8); }}
            .logo-core {{ position: absolute; width: 200px; height: 200px; background: #000; border-radius: 50%; z-index: 10; display: flex; justify-content: center; align-items: center; border: 1px solid rgba(255, 255, 255, 0.1); box-shadow: 0 0 80px rgba(0, 0, 0, 0.8); animation: coreBloom 2.4s cubic-bezier(0.16, 1, 0.3, 1) forwards; }}
            .core-img {{ width: 95%; height: 95%; border-radius: 50%; object-fit: cover; filter: brightness(1.2) contrast(1.1); }}
            .branding-container {{ margin-top: 50px; text-align: center; display: flex; flex-direction: column; align-items: center; background: transparent !important; animation: textReveal 2.8s ease-out 1.4s forwards; opacity: 0; }}
            .main-tagline {{ font-family: 'Syncopate', sans-serif; color: #FFFFFF !important; font-size: 24px; font-weight: 700; letter-spacing: 18px; text-transform: uppercase; margin-bottom: 22px; background: transparent !important; }}
            .sub-tagline {{ font-family: 'Inter', sans-serif; color: #B5FF5F !important; font-size: 14px; letter-spacing: 6px; text-transform: uppercase; font-weight: 500; background: transparent !important; opacity: 0.9; }}
            @keyframes cometWhip {{ 0% {{ transform: rotate(0deg); opacity: 0.4; }} 50% {{ transform: rotate(180deg); opacity: 1; scale: 1.15; }} 100% {{ transform: rotate(360deg); opacity: 0.4; }} }}
            @keyframes coreBloom {{ 0% {{ transform: scale(0.2); opacity: 0; filter: blur(30px); }} 70% {{ transform: scale(1.1); opacity: 1; filter: blur(0px); }} 100% {{ transform: scale(1); opacity: 1; }} }}
            @keyframes textReveal {{ 0% {{ transform: translateY(50px); opacity: 0; filter: blur(15px); }} 100% {{ transform: translateY(0); opacity: 1; filter: blur(0); }} }}
            @keyframes mainFadeOut {{ to {{ opacity: 0; visibility: hidden; transform: scale(1.1); filter: blur(20px); }} }}
            </style>
            <div class="main-void">
            <div class="orbital-track">
            <div class="comet-engine"></div>
            <div class="logo-core">{'<img src="data:image/png;base64,' + encoded_img + '" class="core-img">' if has_image else '<div style="font-size:70px;">🎯</div>'}</div>
            </div>
            <div class="branding-container">
            <div class="main-tagline">TIME HUNT AI</div>
            <div class="sub-tagline">Redefine Productivity • Execute With Precision</div>
            </div>
            </div>
            """), unsafe_allow_html=True)
            
            time.sleep(6.5)
        
        placeholder.empty()
        st.session_state['splash_played'] = True
        
# --- 5. AI ENGINE (CONTEXT & GENERATION) ---

def get_system_context():
    """
    Constructs the 'Brain Dump' for the AI.
    Merges the Global Persona (SYSTEM_INSTRUCTION) with Real-Time Data.
    """
    # 1. User Profile
    user_name = st.session_state.get('user_name', 'Hunter')
    role = st.session_state.get('user_type', 'Student')
    xp = st.session_state.get('user_xp', 0)
    
    # 2. Time & Date (IST)
    utc_now = datetime.datetime.utcnow()
    ist_now = utc_now + datetime.timedelta(hours=5, minutes=30)
    current_time = ist_now.strftime("%H:%M")
    current_date = ist_now.strftime("%Y-%m-%d")
    
    # 3. Compile Schedule
    schedule_txt = "NO ACTIVE TASKS."
    slots = st.session_state.get('timetable_slots', [])
    if slots:
        # Filter for today's tasks
        todays_tasks = [s for s in slots if s.get('Date') == current_date or not s.get('Date')]
        if todays_tasks:
            schedule_txt = "\n".join(
                [f"- [Time: {s['Time']}] {s['Activity']} ({s['Category']}) - {'DONE' if s['Done'] else 'PENDING'}" 
                 for s in todays_tasks]
            )
    
    # 4. Compile Reminders
    reminders_txt = "NO ACTIVE ALERTS."
    rems = st.session_state.get('reminders', [])
    if rems:
        pending_rems = [r for r in rems if not r['notified']]
        if pending_rems:
            reminders_txt = "\n".join([f"- {r['task']} at {r['time']}" for r in pending_rems])

    # 5. Merge with Global Instruction
    # We append the live data to the existing SYSTEM_INSTRUCTION
    full_prompt = f"""
    {SYSTEM_INSTRUCTION}
    
    === REAL-TIME INTELLIGENCE ===
    USER: {user_name} | RANK: {role} | XP: {xp}
    CURRENT STATUS: Date: {current_date} | Time: {current_time}
    
    [TODAY'S SCHEDULE]
    {schedule_txt}
    
    [PENDING ALARMS]
    {reminders_txt}
    
    INSTRUCTION: Use the context above to provide specific advice. 
    If a task is due soon ({current_time}), remind the user gently but firmly.
    """
    return full_prompt

def perform_ai_analysis(user_query):
    """
    Robust AI Engine with Smart Fallback & Key Rotation.
    """
    # 1. Check Library
    if not HAS_GEMINI:
        return "⚠️ SYSTEM FAILURE: `google-genai` library not installed.", "System"

    # 2. Get Keys (From Session State)
    api_keys_list = st.session_state.get('gemini_api_keys', [])
    if not api_keys_list:
        return "⚠️ AUTH ERROR: No API Keys found in secrets.toml", "System"

    # 3. Model Priority List
    models_to_try = [
        "gemini-2.0-flash",          
        "gemini-2.5-flash",          
        "gemini-2.0-flash-lite",     
        "gemini-2.0-pro-exp-02-05",  
        "gemini-2.0-flash-exp",      
    ]

    current_context = get_system_context()
    last_error = "No connection attempted."

    # 4. The Loop: Try Every Key x Every Model
    for key_index, current_key in enumerate(api_keys_list):
        try:
            client = genai.Client(api_key=current_key)
            
            for model_name in models_to_try:
                try:
                    # Construct History
                    history_for_model = []
                    past_chats = st.session_state.get('chat_history', [])[-6:]
                    
                    for msg in past_chats:
                        # Normalize role names for API
                        role_label = msg.get('role', 'user')
                        content_text = msg.get('content', '')
                        api_role = "user" if role_label == "user" else "model"
                        
                        history_for_model.append(types.Content(
                            role=api_role, 
                            parts=[types.Part.from_text(text=str(content_text))]
                        ))

                    # Configure Chat
                    chat = client.chats.create(
                        model=model_name,
                        history=history_for_model,
                        config=types.GenerateContentConfig(
                            system_instruction=current_context,
                            temperature=0.7,
                            max_output_tokens=600
                        )
                    )
                    
                    # Generate
                    response = chat.send_message(user_query)
                    return response.text, "TimeHunt AI"

                except Exception as model_err:
                    err_str = str(model_err)
                    
                    # Smart Error Handling (Skip 429/404, stop on others?)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        last_error = "Server Busy (Rate Limit)"
                        time.sleep(0.5)
                        continue
                    elif "404" in err_str or "NOT_FOUND" in err_str:
                        last_error = f"Model {model_name} Not Found"
                        continue
                    else:
                        last_error = f"Error: {err_str}"
                        continue # Try next model/key

        except Exception:
            continue # Try next key

    # 5. Total Failure
    return f"⚠️ SYSTEM ALERT: Connection Unstable. Last Error: {last_error}. Check API Keys.", "System"
    
# --- 5.5 REMINDER CHECKER WITH BROWSER NOTIFICATIONS ---

def check_reminders():
    """
    Checks for due tasks and triggers browser-native notifications.
    Includes Javascript injection for permissions.
    """
    # 1. Request Permission on Load
    st.markdown("""
        <script>
        if ("Notification" in window) {
            if (Notification.permission !== "granted") {
                Notification.requestPermission();
            }
        }
        </script>
    """, unsafe_allow_html=True)

    # 2. Check Logic
    now = datetime.datetime.now()
    if 'reminders' in st.session_state:
        for i, rem in enumerate(st.session_state['reminders']):
            # Ensure time format is valid
            if isinstance(rem['time'], str):
                try:
                    rem['time'] = datetime.datetime.fromisoformat(rem['time'])
                except ValueError: continue

            # Trigger condition: Time passed AND not yet notified
            if not rem['notified'] and now >= rem['time']:
                # Update State
                st.session_state['active_alarm'] = {'task': rem['task'], 'index': i}
                rem['notified'] = True 
                
                sync_data()
                
                # Sanitize text for JS to prevent syntax errors
                safe_task = rem['task'].replace("'", "").replace('"', "").replace("\n", " ")
                
                # Trigger Native Notification
                st.markdown(f"""
                    <script>
                    if (Notification.permission === "granted") {{
                        new Notification("🚨 MISSION ALERT: {safe_task}", {{
                            body: "TimeHunt Protocol: Target deadline reached.",
                            icon: "https://cdn-icons-png.flaticon.com/512/2921/2921226.png"
                        }});
                    }}
                    </script>
                """, unsafe_allow_html=True)

# --- 6. PAGE: ONBOARDING (DARK MODE OPTIMIZED) ---

def page_onboarding():
    
    # 1. Dynamic Background Loader
    bg_style = ""
    try:
        with open("background_small.jpg", "rb") as image_file:
            bg_base64 = base64.b64encode(image_file.read()).decode()
            bg_style = f"""
            .fixed-bg {{
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background-image: linear-gradient(rgba(0,0,0,0.7), rgba(0,0,0,0.95)), url("data:image/jpeg;base64,{bg_base64}");
                background-size: cover; z-index: -1;
            }}
            """
    except: 
        pass

    # 2. Cyberpunk CSS (High Contrast for Dark Mode)
    st.markdown(f"""
    <style>
        {bg_style}
        .stApp {{ background: transparent !important; }}
        .cyber-glass {{ 
            background: rgba(13, 17, 23, 0.9); 
            backdrop-filter: blur(15px); 
            border: 1px solid rgba(0, 229, 255, 0.2); 
            border-radius: 16px; 
            padding: 40px; 
            text-align: center; 
            box-shadow: 0 0 30px rgba(0,0,0,0.5);
            animation: fadeIn 0.8s ease-out; 
        }}
        .cyber-header {{ 
            font-family: 'Segoe UI', sans-serif; 
            font-weight: 800; 
            font-size: 42px; 
            color: #FFFFFF; 
            text-transform: uppercase;
            letter-spacing: 2px;
            text-shadow: 0 0 15px rgba(0, 229, 255, 0.5); 
            margin-bottom: 5px;
        }}
        /* Force Input Styling to match Dark Theme */
        .stTextInput input {{ 
            background-color: #0A0A0A !important; 
            border: 1px solid #333 !important; 
            color: #00E5FF !important; 
            text-align: center; 
            font-weight: bold; 
            letter-spacing: 1px; 
        }}
        div.stButton > button {{ 
            background: linear-gradient(90deg, #00C6FF, #0072FF); 
            color: white; 
            border: none; 
            padding: 12px; 
            font-weight: bold; 
            width: 100%; 
            border-radius: 8px; 
            transition: 0.3s;
        }}
        div.stButton > button:hover {{ box-shadow: 0 0 15px #00C6FF; }}
    </style>
    <div class="fixed-bg"></div>
    """, unsafe_allow_html=True)

    # 3. Logic Flow
    step = st.session_state.get('onboarding_step', 1)
    _, col_center, _ = st.columns([1, 6, 1])
    
    with col_center:
        # --- STEP 1: AUTHENTICATION ---
        if step == 1:
            st.markdown('<div class="cyber-glass">', unsafe_allow_html=True)
            st.markdown('<div class="cyber-header">TIMEHUNT</div>', unsafe_allow_html=True)
            st.markdown('<p style="color:#B5FF5F; font-size: 14px; letter-spacing: 1px;">SECURE IDENTITY PROTOCOL</p>', unsafe_allow_html=True)
            
            default_val = st.session_state.get('suggested_name_choice', "")
            name_input = st.text_input("CODENAME", value=default_val, placeholder="ENTER IDENTITY...", key="login_name").strip()
            pin_input = st.text_input("ACCESS PIN (4-DIGIT)", placeholder="####", type="password", key="login_pin", max_chars=4)
            
            st.write("")
            
            if st.button("🚀 CONNECT / VERIFY"):
                if name_input and len(pin_input) >= 1:
                    with st.spinner("Verifying Identity..."):
                        try:
                            from streamlit_gsheets import GSheetsConnection
                            conn = st.connection("gsheets", type=GSheetsConnection)
                            df = conn.read(worksheet="Sheet1", ttl=0)
                            
                            # Clean PIN data
                            if not df.empty and 'Name' in df.columns:
                                df['PIN'] = df['PIN'].astype(str).replace(r'\.0$', '', regex=True).str.zfill(4)
                                existing = df[df['Name'] == name_input]
                                
                                if not existing.empty:
                                    # RETURNING USER
                                    stored_pin = str(existing.iloc[0]['PIN']).strip()
                                    if str(pin_input) == stored_pin:
                                        row = existing.iloc[0]
                                        st.session_state.update({
                                            'user_name': row['Name'],
                                            'user_id': row['UserID'],
                                            'user_xp': int(row['XP']),
                                            'user_level': (int(row['XP']) // 500) + 1,
                                            'onboarding_complete': True
                                        })
                                        st.toast(f"Welcome back, {name_input}!", icon="🔓")
                                        load_cloud_data()
                                        time.sleep(0.5)
                                        st.rerun()
                                    else:
                                        st.error("⛔ Access Denied. Incorrect PIN.")
                                else:
                                    # NEW USER
                                    st.session_state['user_name'] = name_input
                                    st.session_state['temp_pin'] = pin_input
                                    st.session_state['onboarding_step'] = 2
                                    st.rerun()
                            else:
                                # FIRST EVER USER
                                st.session_state['user_name'] = name_input
                                st.session_state['temp_pin'] = pin_input
                                st.session_state['onboarding_step'] = 2
                                st.rerun()
                        except Exception as e:
                            st.error(f"Network Error: {e}")
                else:
                    st.warning("Credentials Required.")
            st.markdown('</div>', unsafe_allow_html=True)

        # --- STEP 2: AVATAR SELECTION ---
        elif step == 2:
            st.markdown('<div class="cyber-glass"><div class="cyber-header">AVATAR</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            
            def show_av(col, name, filename):
                with col:
                    if os.path.exists(filename):
                        st.image(filename, width=100)
                    else:
                        st.write("👤")
                    if st.button(name, key=f"btn_{name}"):
                        st.session_state['user_avatar'] = filename
                        st.session_state['onboarding_step'] = 3
                        st.rerun()

            show_av(c1, "SCHOLAR", "Gemini_Generated_Image_djfbqkdjfbqkdjfb.png")
            show_av(c2, "TECHIE", "Gemini_Generated_Image_z8e73dz8e73dz8e7.png")
            show_av(c3, "HUNTER", "Gemini_Generated_Image_18oruj18oruj18or.png")
            st.markdown('</div>', unsafe_allow_html=True)

        # --- STEP 3: MISSION & SAVE ---
        elif step == 3:
            st.markdown('<div class="cyber-glass"><div class="cyber-header">MISSION</div>', unsafe_allow_html=True)
            role = st.selectbox("Role", ["Student", "Entrepreneur", "Professional"])
            goal = st.selectbox("Goal", ["Ace Exams", "Build Business", "Health"])
            
            if st.button("CONFIRM & UPLOAD"):
                 st.session_state['user_type'] = role
                 st.session_state['user_goal'] = goal
                 
                 try:
                     from streamlit_gsheets import GSheetsConnection
                     conn = st.connection("gsheets", type=GSheetsConnection)
                     
                     # Create User Record
                     new_user = pd.DataFrame([{
                         "UserID": st.session_state['user_id'],
                         "Name": st.session_state['user_name'],
                         "XP": 0, "League": "Bronze",
                         "Avatar": st.session_state.get('user_avatar', "👤"),
                         "LastActive": datetime.date.today().strftime("%Y-%m-%d"),
                         "PIN": "'" + str(st.session_state.get('temp_pin', "0000"))
                     }])
                     
                     # Append to Cloud
                     try:
                        df = conn.read(worksheet="Sheet1", ttl=0)
                        updated_df = pd.concat([df, new_user], ignore_index=True)
                     except:
                        updated_df = new_user
                        
                     conn.update(worksheet="Sheet1", data=updated_df)
                     
                     st.session_state['onboarding_complete'] = True
                     sync_data()
                     st.toast("Profile Initialized")
                     time.sleep(1)
                     st.rerun()
                 except Exception as e:
                     st.error(f"Upload Failed: {e}")
            st.markdown('</div>', unsafe_allow_html=True)

# --- 7. PAGE: SCHEDULER (DARK MODE OPTIMIZED) ---

def page_scheduler():
    # --- Helper: Streak Calculation ---
    def calculate_streak_multiplier(streak_days):
        if streak_days >= 30: return 2.5
        elif streak_days >= 14: return 2.0
        elif streak_days >= 7: return 1.5
        elif streak_days >= 3: return 1.2
        return 1.0

    # Ensure Data Integrity
    for slot in st.session_state.get('timetable_slots', []):
        if 'XP' not in slot: slot['XP'] = 50
        if 'Difficulty' not in slot: slot['Difficulty'] = 'Medium'
        if 'Done' not in slot: slot['Done'] = False

    # --- Header & Stats ---
    # CSS wrapper for clean cards
    st.markdown("""
    <style>
        .stat-card { background: rgba(255,255,255,0.05); border: 1px solid #333; border-radius: 12px; padding: 20px; }
        .stat-val { font-size: 24px; font-weight: bold; color: #fff; }
        .stat-label { font-size: 12px; color: #aaa; text-transform: uppercase; }
        .mission-card { background: rgba(20, 20, 20, 0.6); border-left: 4px solid #333; padding: 15px; margin-bottom: 10px; border-radius: 0 8px 8px 0; }
    </style>
    """, unsafe_allow_html=True)
    
    # Calculate Logic
    slots = st.session_state['timetable_slots']
    total = len(slots)
    completed = len([t for t in slots if t['Done']])
    pending_count = total - completed
    progress = completed / total if total > 0 else 0
    streak = st.session_state.get('streak', 1)
    
    # Stats UI
    c_main, c_mini = st.columns([2, 1])
    with c_main:
        st.markdown(f"""
        <div class="stat-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                <span style="color:#B5FF5F; font-weight:bold;">Daily Progress</span>
                <span style="color:#aaa;">{int(progress*100)}%</span>
            </div>
            <div style="width:100%; background:#222; height:8px; border-radius:4px; overflow:hidden;">
                <div style="width:{progress*100}%; background: linear-gradient(90deg, #B5FF5F, #00E5FF); height:100%;"></div>
            </div>
            <div style="margin-top:10px; font-size:13px; color:#ccc;">
                🔥 Streak: <span style="color:#fff;">{streak} Days</span> (x{calculate_streak_multiplier(streak)})
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    with c_mini:
        st.markdown(f"""
        <div class="stat-card" style="text-align:center;">
            <div class="stat-val">{pending_count}</div>
            <div class="stat-label">Pending</div>
        </div>
        """, unsafe_allow_html=True)

    # --- Mission Deployment ---
    with st.expander("🚁 DEPLOY NEW MISSION", expanded=True):
        with st.form("mission_form", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 1.5, 1.5])
            with c1: task = st.text_input("Objective", placeholder="Mission details...")
            with c2: cat = st.selectbox("Sector", ["Study", "Project", "Health", "Errand"])
            with c3: diff = st.selectbox("Class", ["Easy (20 XP)", "Medium (50 XP)", "Hard (150 XP)", "BOSS (300 XP)"])
            
            if st.form_submit_button("Deploy ➔", type="primary", use_container_width=True):
                if task:
                    xp_map = {"Easy (20 XP)": 20, "Medium (50 XP)": 50, "Hard (150 XP)": 150, "BOSS (300 XP)": 300}
                    now_ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
                    
                    st.session_state['timetable_slots'].append({
                        "Time": now_ist.strftime("%H:%M"),
                        "Activity": task, "Category": cat,
                        "Difficulty": diff.split(" ")[0],
                        "Done": False, "XP": xp_map.get(diff, 50),
                        "Date": now_ist.strftime("%Y-%m-%d")
                    })
                    sync_data()
                    st.rerun()

    st.markdown("### 📋 Active Protocols")
    
    # --- Active Missions List ---
    pending = [t for t in slots if not t['Done']]
    done_list = [t for t in slots if t['Done']]

    if pending:
        for i, m in enumerate(slots):
            if not m['Done']:
                # Color Coding
                clr = "#B5FF5F" if m['Difficulty'] == "Easy" else \
                      "#FFD700" if m['Difficulty'] == "Medium" else \
                      "#FF4B4B" if m['Difficulty'] == "Hard" else "#9D00FF"
                
                with st.container():
                    c_chk, c_info, c_badge = st.columns([0.5, 6, 1.5], vertical_alignment="center")
                    with c_chk:
                        if st.button("⬜", key=f"d_{i}", help="Mark Done"):
                            st.session_state['timetable_slots'][i]['Done'] = True
                            sync_data()
                            st.rerun()
                    with c_info:
                        st.markdown(f"""
                            <div style="font-weight:600; font-size:16px; color:#fff;">{m['Activity']}</div>
                            <div style="font-size:12px; color:#888;">{m['Category']} | {m['Time']}</div>
                        """, unsafe_allow_html=True)
                    with c_badge:
                        st.markdown(f"<div style='color:{clr}; font-weight:bold; font-size:12px; text-align:right;'>+{m['XP']} XP</div>", unsafe_allow_html=True)
                    st.markdown("<div style='height:1px; background:#333; margin: 5px 0;'></div>", unsafe_allow_html=True)
    else:
        st.info("All systems clear.")

    # --- Completed Section ---
    if done_list:
        with st.expander(f"✅ Completed ({len(done_list)})"):
            for t in done_list:
                 st.markdown(f"<span style='color:#666; text-decoration:line-through;'>{t['Activity']}</span>", unsafe_allow_html=True)
            
            if st.button("🎁 CLAIM REWARDS & ARCHIVE", type="primary"):
                raw_xp = sum(t['XP'] for t in done_list)
                final_xp = int(raw_xp * calculate_streak_multiplier(streak))
                
                st.session_state['user_xp'] += final_xp
                st.session_state['user_level'] = (st.session_state['user_xp'] // 1000) + 1
                st.session_state['timetable_slots'] = [t for t in slots if not t['Done']]
                
                # Log History
                today = datetime.date.today().strftime("%Y-%m-%d")
                st.session_state['xp_history'].append({"Date": today, "XP": final_xp})
                
                sync_data()
                st.balloons()
                st.toast(f"Success! +{final_xp} XP Added", icon="🚀")
                time.sleep(1.5)
                st.rerun()
                
    # Footer Action
    if st.button("🗑️ Clear All", help="Reset all data"):
        st.session_state['timetable_slots'] = []
        sync_data()
        st.rerun()

# --- PAGE: FOCUS TIMER ---
def page_timer():
    """
    Renders a JavaScript-powered circular timer with sound and notifications.
    Includes Dark Mode support for text visibility.
    """
    # 1. Initialize State
    if 'timer_duration' not in st.session_state: st.session_state['timer_duration'] = 25
    if 'timer_mode' not in st.session_state: st.session_state['timer_mode'] = "Focus"

    st.markdown('<div class="big-title" style="text-align:center;">⏱️ Tactical Chronometer</div>', unsafe_allow_html=True)

    # 2. Mode Selection
    # Helper for button styling
    def get_type(mode): return "primary" if st.session_state['timer_mode'] == mode else "secondary"

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🎯 FOCUS (25m)", type=get_type("Focus"), use_container_width=True):
            st.session_state['timer_duration'] = 25
            st.session_state['timer_mode'] = "Focus"
            st.rerun()
    with c2:
        if st.button("☕ SHORT (5m)", type=get_type("Short"), use_container_width=True):
            st.session_state['timer_duration'] = 5
            st.session_state['timer_mode'] = "Short"
            st.rerun()
    with c3:
        if st.button("🔋 LONG (15m)", type=get_type("Long"), use_container_width=True):
            st.session_state['timer_duration'] = 15
            st.session_state['timer_mode'] = "Long"
            st.rerun()

    # 3. Mission Input
    current_focus = st.text_input("Current Mission Objective", placeholder="What are you hunting?", label_visibility="collapsed")
    if not current_focus: current_focus = "Deep Work Protocol"

    # 4. JavaScript Timer Injection
    duration_min = st.session_state['timer_duration']
    
    # Colors: Green for Focus, Cyan for Short Break, Purple for Long Break
    if st.session_state['timer_mode'] == "Focus": ring_color = "#B5FF5F"
    elif st.session_state['timer_mode'] == "Short": ring_color = "#00E5FF"
    else: ring_color = "#9D00FF"
    
    timer_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{ background: transparent; display: flex; flex-direction: column; align-items: center; justify-content: center; font-family: 'Inter', sans-serif; }}
        
        .base-timer {{ position: relative; width: 280px; height: 280px; }}
        .base-timer__svg {{ transform: scaleX(-1); }}
        .base-timer__circle {{ fill: none; stroke: none; }}
        .base-timer__path-elapsed {{ stroke-width: 8px; stroke: rgba(255, 255, 255, 0.1); }}
        .base-timer__path-remaining {{
            stroke-width: 8px; stroke-linecap: round; transform: rotate(90deg); transform-origin: center;
            transition: 1s linear all; fill-rule: nonzero; stroke: {ring_color}; 
            filter: drop-shadow(0 0 10px {ring_color});
        }}
        .base-timer__label {{
            position: absolute; width: 280px; height: 280px; top: 0; display: flex; align-items: center; justify-content: center;
            font-size: 50px; font-family: 'Courier New', monospace; font-weight: bold; color: #FFFFFF;
            text-shadow: 0 0 20px rgba(0,0,0,0.8);
        }}
        .controls {{ margin-top: 25px; display: flex; gap: 15px; }}
        .btn {{
            border: none; padding: 10px 25px; border-radius: 50px; font-size: 14px; font-weight: bold;
            cursor: pointer; transition: 0.2s; text-transform: uppercase; letter-spacing: 1px; color: #000;
        }}
        .btn-start {{ background: {ring_color}; box-shadow: 0 0 15px {ring_color}40; }}
        .btn-start:hover {{ transform: scale(1.05); box-shadow: 0 0 25px {ring_color}60; }}
        .btn-stop {{ background: #444; color: #fff; border: 1px solid #666; }}
        .btn-stop:hover {{ background: #FF4B4B; border-color: #FF4B4B; }}
    </style>
    </head>
    <body>
        <div class="base-timer">
            <svg class="base-timer__svg" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <g class="base-timer__circle">
                    <circle class="base-timer__path-elapsed" cx="50" cy="50" r="45"></circle>
                    <path id="base-timer-path-remaining" stroke-dasharray="283" class="base-timer__path-remaining"
                        d="M 50, 50 m -45, 0 a 45,45 0 1,0 90,0 a 45,45 0 1,0 -90,0"></path>
                </g>
            </svg>
            <span id="base-timer-label" class="base-timer__label">{duration_min}:00</span>
        </div>
        <div class="controls">
            <button class="btn btn-start" onclick="startTimer()">Start</button>
            <button class="btn btn-stop" onclick="resetTimer()">Stop</button>
        </div>
        <script>
            const FULL_DASH_ARRAY = 283;
            const TIME_LIMIT = {duration_min} * 60;
            let timePassed = 0;
            let timeLeft = TIME_LIMIT;
            let timerInterval = null;

            if ("Notification" in window) {{ if (Notification.permission !== "granted") {{ Notification.requestPermission(); }} }}

            function onTimesUp() {{
                clearInterval(timerInterval);
                timerInterval = null;
                const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                osc.connect(gain); gain.connect(audioCtx.destination);
                osc.type = "square"; osc.frequency.value = 440; 
                osc.start(); gain.gain.exponentialRampToValueAtTime(0.00001, audioCtx.currentTime + 1);
                
                if (Notification.permission === "granted") {{
                    new Notification("TIME HUNT AI", {{ body: "Protocol Complete: {current_focus}", icon: "" }});
                }}
            }}

            function startTimer() {{
                if (timerInterval) return;
                timerInterval = setInterval(() => {{
                    timePassed += 1;
                    timeLeft = TIME_LIMIT - timePassed;
                    document.getElementById("base-timer-label").innerHTML = formatTime(timeLeft);
                    setCircleDasharray();
                    if (timeLeft <= 0) onTimesUp();
                }}, 1000);
            }}
            
            function resetTimer() {{
                clearInterval(timerInterval);
                timerInterval = null;
                timePassed = 0;
                timeLeft = TIME_LIMIT;
                document.getElementById("base-timer-label").innerHTML = formatTime(timeLeft);
                setCircleDasharray();
            }}

            function formatTime(time) {{
                const minutes = Math.floor(time / 60);
                let seconds = time % 60;
                if (seconds < 10) seconds = `0${{seconds}}`;
                return `${{minutes}}:${{seconds}}`;
            }}

            function setCircleDasharray() {{
                const rawTimeFraction = timeLeft / TIME_LIMIT;
                const circleDasharray = `${{( (rawTimeFraction - (1 / TIME_LIMIT) * (1 - rawTimeFraction)) * FULL_DASH_ARRAY ).toFixed(0)}} 283`;
                document.getElementById("base-timer-path-remaining").setAttribute("stroke-dasharray", circleDasharray);
            }}
        </script>
    </body>
    </html>
    """
    with st.container():
        components.html(timer_html, height=400)

    # 5. Rewards
    st.markdown("---")
    c_rew, c_inf = st.columns([2, 1])
    with c_rew:
        st.markdown("### 🎁 Session Rewards")
        possible_xp = 50 if st.session_state['timer_duration'] == 25 else 100 if st.session_state['timer_duration'] == 15 else 10
        if st.button(f"Verify & Claim +{possible_xp} XP", use_container_width=True):
            st.session_state['user_xp'] += possible_xp
            st.session_state['user_level'] = (st.session_state['user_xp'] // 1000) + 1
            st.session_state['xp_history'].append({"Date": datetime.date.today().strftime("%Y-%m-%d"), "XP": possible_xp})
            sync_data()
            st.toast(f"Logged! +{possible_xp} XP", icon="🧠")
            time.sleep(1)
            st.rerun()
    with c_inf:
        st.info(f"Mode: **{st.session_state['timer_mode']}**\n\nFocus: {current_focus}")

# --- PAGE: CALENDAR (MOBILE OPTIMIZED) ---
def page_calendar():
    """
    Renders a responsive calendar where columns stay aligned on mobile.
    Includes task management for selected dates.
    """
    # 1. Critical CSS for Mobile Grid Stability
    st.markdown("""
    <style>
        /* Force Calendar Columns to stay inline on mobile */
        [data-testid="column"] { flex: 1 1 0% !important; min-width: 0 !important; padding: 0 1px !important; }
        /* Smaller buttons for calendar days */
        [data-testid="column"] button { padding: 0px 2px !important; min-height: 35px !important; font-size: 12px !important; }
        /* Header Alignment */
        h3 { text-align: center; font-size: 18px !important; margin: 0 !important; }
        /* Ensure Inputs on form are readable */
        .stTextInput input, .stTimeInput input { font-size: 14px; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="big-title">📅 Tactical Grid</div>', unsafe_allow_html=True)

    # State Defaults
    if 'cal_year' not in st.session_state: st.session_state['cal_year'] = datetime.date.today().year
    if 'cal_month' not in st.session_state: st.session_state['cal_month'] = datetime.date.today().month
    if 'sel_date' not in st.session_state: st.session_state['sel_date'] = datetime.date.today().strftime("%Y-%m-%d")

    # 2. Navigation
    c_prev, c_month, c_next = st.columns([1, 4, 1], vertical_alignment="center")
    with c_prev:
        if st.button("◀", key="prev_m"):
            st.session_state['cal_month'] -= 1
            if st.session_state['cal_month'] < 1: st.session_state['cal_month'] = 12; st.session_state['cal_year'] -= 1
            st.rerun()
    with c_next:
        if st.button("▶", key="next_m"):
            st.session_state['cal_month'] += 1
            if st.session_state['cal_month'] > 12: st.session_state['cal_month'] = 1; st.session_state['cal_year'] += 1
            st.rerun()
    with c_month:
        month_name = calendar.month_name[st.session_state['cal_month']]
        st.markdown(f"<h3>{month_name} {st.session_state['cal_year']}</h3>", unsafe_allow_html=True)

    # 3. Headers
    cols = st.columns(7)
    for i, d in enumerate(["M","T","W","T","F","S","S"]):
        cols[i].markdown(f"<div style='text-align:center; color:#AAA; font-size:10px; font-weight:bold;'>{d}</div>", unsafe_allow_html=True)

    # 4. Calendar Grid
    month_matrix = calendar.monthcalendar(st.session_state['cal_year'], st.session_state['cal_month'])
    for week in month_matrix:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].write("")
            else:
                d_str = f"{st.session_state['cal_year']}-{st.session_state['cal_month']:02d}-{day:02d}"
                has_task = any(t.get('Date') == d_str for t in st.session_state.get('timetable_slots', []))
                
                label = f"{day} •" if has_task else f"{day}"
                btn_type = "primary" if st.session_state['sel_date'] == d_str else "secondary"
                
                if cols[i].button(label, key=f"d_{d_str}", type=btn_type, use_container_width=True):
                    st.session_state['sel_date'] = d_str
                    st.rerun()

    # 5. Selected Day View
    st.markdown("---")
    sel = st.session_state['sel_date']
    st.markdown(f"**Missions for {sel}**")
    
    tasks = [t for t in st.session_state.get('timetable_slots', []) if t.get('Date') == sel]
    if tasks:
        for t in tasks:
            st.markdown(f"{'✅' if t['Done'] else '⭕'} **{t['Time']}** {t['Activity']}")
    else:
        st.caption("No missions deployed.")

    with st.form("add_cal", clear_on_submit=True):
        c_t, c_tm = st.columns([3, 2])
        with c_t: task = st.text_input("Task", placeholder="New Mission...")
        with c_tm: time_at = st.time_input("Time")
        
        if st.form_submit_button("Add Mission", use_container_width=True):
            st.session_state['timetable_slots'].append({
                "Date": sel, "Time": time_at.strftime("%H:%M"), "Activity": task, 
                "Done": False, "Category": "General", "XP": 50, "Difficulty": "Medium"
            })
            sync_data()
            st.rerun()

# --- 8. PAGE: AI ASSISTANT ---

def page_ai_assistant():
    """
    Advanced Chat Interface with Voice Support and Auto-Audio Response.
    Includes persistent history and context-aware responses.
    """
    # Local imports for this specific page
    import uuid
    from PIL import Image
    
    # --- HELPER: PROCESS MESSAGE ---
    def process_message(prompt_text):
        """Helper to send message, get AI response, and save to history."""
        # 1. Initialize Session if needed
        if not st.session_state.get('current_session_id'):
            st.session_state['current_session_id'] = str(uuid.uuid4())
            st.session_state['current_session_name'] = " ".join(prompt_text.split()[:4])

        # 2. Append User Message
        st.session_state['chat_history'].append({"role": "user", "text": prompt_text})
        save_chat_to_cloud("user", prompt_text)
        
        # 3. Generate AI Response
        with st.spinner("Analyzing parameters..."):
            response_text, _ = perform_ai_analysis(prompt_text)
        
        # 4. Append AI Message
        st.session_state['chat_history'].append({"role": "model", "text": response_text})
        save_chat_to_cloud("model", response_text)
        
        # 5. Audio Feedback (Auto-Play)
        # Limit text length for TTS to avoid URL errors
        clean_text = response_text.replace('\n', ' ').replace('#', '')[:200]
        tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&q={clean_text}&tl=en"
        st.markdown(f'<audio autoplay="true" style="display:none;"><source src="{tts_url}" type="audio/mpeg"></audio>', unsafe_allow_html=True)
        
        st.rerun()

    # --- HEADER SECTION ---
    c_title, c_mic = st.columns([5, 1], vertical_alignment="bottom")
    with c_title:
        st.markdown(f'<div class="big-title">Tactical Support 🤖</div>', unsafe_allow_html=True)
    
    with c_mic:
        # Mic Recorder Widget
        audio_data = mic_recorder(start_prompt="🎤", stop_prompt="⏹️", just_once=True, key="voice_input")

    # --- VOICE INPUT PROCESSING ---
    if audio_data:
        # Note: mic_recorder usually returns raw bytes, transcription would need an STT service.
        # Since we don't have Whisper API keys configured here, we notify the user.
        st.toast("Voice captured. (STT requires API integration)", icon="🎤")

    # --- CHAT UI LOGIC ---
    if not st.session_state.get('chat_history'):
        # --- EMPTY STATE (WELCOME SCREEN) ---
        user_name = st.session_state.get('user_name', 'Hunter').split()[0]
        greet = random.choice(["Reporting for duty.", "Systems online.", "Ready to optimize."])

        st.markdown(f"""
        <style>
            .welcome-h1 {{ 
                font-family: 'Inter', sans-serif; font-size: 40px; font-weight: 700; 
                background: linear-gradient(90deg, #B5FF5F, #00E5FF); -webkit-background-clip: text; 
                -webkit-text-fill-color: transparent; margin-top: 20px; 
            }}
            .welcome-sub {{ font-size: 20px; color: #666; margin-bottom: 40px; }}
        </style>
        <div>
            <div class="welcome-h1">Hi, {user_name}</div>
            <div class="welcome-sub">{greet}</div>
        </div>
        """, unsafe_allow_html=True)

        # Quick Action Buttons
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("📅 Plan Day", use_container_width=True): process_message("Create a strict hourly schedule for me today.")
        if c2.button("🧠 Learn", use_container_width=True): process_message("Explain a complex topic simply.")
        if c3.button("🔥 Motivate", use_container_width=True): process_message("I am tired. Give me military motivation.")
        if c4.button("📝 Tips", use_container_width=True): process_message("Give me 3 productivity hacks.")

    else:
        # --- CHAT HISTORY RENDERER ---
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state['chat_history']:
                content = msg.get('text') or msg.get('Content')
                role = str(msg.get('role') or msg.get('Role')).lower()
                
                # Determine Role & Avatar
                if role in ["model", "assistant", "ai"]:
                    ui_role = "assistant"
                    # Try loading custom avatar
                    if os.path.exists("1000592991.png"):
                        avatar = Image.open("1000592991.png")
                    else:
                        avatar = "🤖" 
                else:
                    ui_role = "user"
                    user_av = st.session_state.get('user_avatar', "👤")
                    # Check if avatar is a valid file path
                    if isinstance(user_av, str) and os.path.exists(user_av):
                        avatar = Image.open(user_av)
                    else:
                        avatar = "👤"

                # Render Message
                with st.chat_message(ui_role, avatar=avatar):
                    st.markdown(content)

    # --- INPUT AREA ---
    if prompt := st.chat_input("Input command parameters..."):
        process_message(prompt)

# --- 9. CUSTOM UI STYLING (GLOBAL CSS) ---
def inject_custom_css():
    """Injects CSS variables and overrides for theming."""
    # 1. Load Preferences
    theme_mode = st.session_state.get('theme_mode', 'Dark') 
    
    # 2. Define Palette
    if theme_mode == "Light":
        colors = {
            "bg": "linear-gradient(180deg, #FDFBF7 0%, #FFFFFF 100%)",
            "sidebar": "#F4F4F4",
            "card": "#FFFFFF",
            "text": "#1A1A1A",
            "input": "#FFFFFF",
            "border": "#E0E0E0"
        }
    else:
        colors = {
            "bg": "linear-gradient(180deg, #0E1117 0%, #161B22 100%)",
            "sidebar": "#0E1117",
            "card": "#1E232F",
            "text": "#FAFAFA",
            "input": "#262730",
            "border": "rgba(255,255,255,0.1)"
        }
        
    accent = "#B5FF5F" # Standard Venom Green

    # 3. Inject CSS
    st.markdown(f"""
        <style>
            :root {{ 
                --accent: {accent}; 
                --text: {colors['text']}; 
                --card-bg: {colors['card']}; 
            }}
            
            /* Main Backgrounds */
            .stApp {{ background: {colors['bg']} !important; color: {colors['text']} !important; }}
            section[data-testid="stSidebar"] {{ background: {colors['sidebar']} !important; }}
            
            /* Typography */
            .big-title {{ 
                font-size: 38px !important; 
                font-weight: 800 !important; 
                color: {colors['text']} !important; 
                margin-bottom: 10px; 
            }}
            
            /* Card Component */
            .glass-card {{
                background: {colors['card']};
                border: 1px solid {colors['border']};
                border-radius: 16px;
                padding: 20px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            
            /* Input Fields */
            .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {{ 
                background-color: {colors['input']} !important; 
                color: {colors['text']} !important;
                border-radius: 10px; 
                border: 1px solid {colors['border']} !important;
            }}
            
            /* Buttons */
            .stButton button {{ 
                border-radius: 12px; 
                font-weight: 600; 
                transition: transform 0.1s;
            }}
            .stButton button:active {{ transform: scale(0.98); }}
        </style>
    """, unsafe_allow_html=True)

# --- 10. PDF REPORT GENERATOR ---

def create_mission_report(user_name, level, xp, history):
    """Generates a PDF summary of user progress."""
    pdf = FPDF()
    pdf.add_page()
    
    # 1. Header
    pdf.set_font("Courier", "B", 24)
    pdf.cell(0, 10, "TIMEHUNT // MISSION REPORT", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Courier", "", 10)
    pdf.cell(0, 10, f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align='C')
    pdf.line(10, 30, 200, 30) 
    pdf.ln(15)
    
    # 2. Agent Profile
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"AGENT: {user_name.upper()}", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 10, f"Rank: Level {level} | XP: {xp}", ln=True)
    pdf.ln(10)
    
    # 3. Mission Log Table
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "RECENT MISSION LOG:", ln=True)
    pdf.ln(2)
    
    # Headers
    pdf.set_font("Courier", "B", 10)
    pdf.cell(50, 8, "DATE", 1)
    pdf.cell(50, 8, "XP GAINED", 1)
    pdf.ln()
    
    # Rows
    pdf.set_font("Courier", "", 10)
    if history:
        for entry in history[-10:]: # Last 10 entries
            date_str = str(entry.get('Date', 'N/A'))
            xp_str = f"+{entry.get('XP', 0)}"
            pdf.cell(50, 8, date_str, 1)
            pdf.cell(50, 8, xp_str, 1)
            pdf.ln()
    else:
        pdf.cell(100, 8, "No data available.", 1, ln=True)
        
    pdf.ln(20)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 10, "End of Transmission.", align='C')
    
    return pdf.output(dest='S').encode('latin-1')

# --- 11. PAGE: HOME DASHBOARD ---

def page_home():
    # --- 1. GREETING LOGIC ---
    utc_now = datetime.datetime.utcnow()
    ist_now = utc_now + datetime.timedelta(hours=5, minutes=30)
    hr = ist_now.hour
    
    if 5 <= hr < 12: greeting = "Good Morning"
    elif 12 <= hr < 17: greeting = "Good Afternoon"
    elif 17 <= hr < 22: greeting = "Good Evening"
    else: greeting = "Night Operations"

    quote = random.choice([
        "Discipline is freedom.", 
        "Focus on the mission.", 
        "Execute with precision.",
        "Your future is created now."
    ])

    # --- 2. HERO BANNER ---
    col_text, col_weather = st.columns([3, 1])
    
    with col_text:
        st.markdown(f'<div class="big-title">{greeting}, {st.session_state["user_name"]}</div>', unsafe_allow_html=True)
        st.caption(f"🚀 {quote}")
    
    with col_weather:
        # Fetch Real Weather
        city = st.session_state.get('user_city', 'Jaipur')
        temp, desc = get_real_time_weather(city)
        
        st.markdown(f"""
        <div style="text-align:right; font-family:monospace; background:rgba(255,255,255,0.05); padding:10px; border-radius:10px;">
            <div style="font-size:24px; font-weight:bold; color:#B5FF5F;">{temp}</div>
            <div style="font-size:12px;">{desc}</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    # --- 3. LEVEL PROGRESS ---
    xp = st.session_state.get('user_xp', 0)
    lvl = st.session_state.get('user_level', 1)
    
    # Calculate progress bar (0-1000 XP per level loop)
    xp_in_lvl = xp % 1000
    prog = (xp_in_lvl / 1000) * 100
    
    st.markdown(f"""
    <div class="glass-card">
        <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
            <span style="font-weight:bold;">Rank: {lvl}</span>
            <span style="color:#B5FF5F;">{xp_in_lvl} / 1000 XP</span>
        </div>
        <div style="width:100%; height:8px; background:#333; border-radius:4px;">
            <div style="width:{prog}%; height:100%; background:linear-gradient(90deg, #B5FF5F, #00E5FF); border-radius:4px;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.write("")

    # --- 4. DASHBOARD CARDS ---
    c1, c2, c3 = st.columns(3)
    
    # Card 1: Next Mission
    slots = sorted(st.session_state.get('timetable_slots', []), key=lambda x: x['Time'])
    pending = [s for s in slots if not s['Done']]
    next_task = pending[0]['Activity'] if pending else "No Active Missions"
    next_time = pending[0]['Time'] if pending else "--:--"
    
    with c1:
        st.markdown(f"""
        <div class="glass-card" style="height:160px; display:flex; flex-direction:column; justify-content:space-between;">
            <div style="color:#888; font-size:12px;">NEXT PROTOCOL</div>
            <div style="font-size:20px; font-weight:bold;">{next_task}</div>
            <div style="font-size:28px; color:#B5FF5F; font-family:monospace;">{next_time}</div>
        </div>
        """, unsafe_allow_html=True)

    # Card 2: Quick Actions
    with c2:
        with st.container(border=True):
            st.markdown("**⚡ Actions**")
            if st.button("➕ Add Task", use_container_width=True):
                st.session_state['page_mode'] = 'Scheduler' # Redirect via state if supported
                st.rerun()
            if st.button("🧘 Breathe", use_container_width=True):
                st.session_state['show_breathing'] = True
                st.rerun()

    # Card 3: Streak
    streak = st.session_state.get('streak', 1)
    with c3:
        st.markdown(f"""
        <div class="glass-card" style="height:160px; text-align:center;">
            <div style="font-size:40px;">🔥</div>
            <div style="font-size:24px; font-weight:bold;">{streak} Days</div>
            <div style="color:#888; font-size:12px;">ACTIVE STREAK</div>
        </div>
        """, unsafe_allow_html=True)

    # --- 5. BREATHING OVERLAY ---
    if st.session_state.get('show_breathing', False):
        st.markdown("---")
        st.markdown("<h3 style='text-align:center;'>🧘 Decompress</h3>", unsafe_allow_html=True)
        
        # CSS Animation for Pulse
        st.markdown("""
        <div style="display:flex; justify-content:center; margin: 30px 0;">
            <div style="
                width: 100px; height: 100px; 
                background: radial-gradient(circle, #B5FF5F 0%, transparent 70%);
                border-radius: 50%;
                animation: pulse 4s infinite ease-in-out;
            "></div>
        </div>
        <style>
            @keyframes pulse {
                0% { transform: scale(0.8); opacity: 0.3; }
                50% { transform: scale(1.5); opacity: 0.8; }
                100% { transform: scale(0.8); opacity: 0.3; }
            }
        </style>
        """, unsafe_allow_html=True)
        
        if st.button("End Exercise", use_container_width=True):
            st.session_state['show_breathing'] = False
            st.rerun()

# --- 11. PAGE: ABOUT (REDESIGNED "BEST IN CLASS") ---
def page_about():
    """
    Renders the professional credential page.
    Clean, bordered layout suitable for a Capstone Project presentation.
    """
    # 1. Main Title
    st.markdown("# 🛡️ System Architecture")
    st.markdown("### TimeHunt AI: Tactical Productivity Suite")
    
    # 2. CAPSTONE DOSSIER
    with st.container(border=True):
        c_icon, c_info = st.columns([1, 5], vertical_alignment="center")
        
        with c_icon:
            st.markdown("<div style='font-size: 50px; text-align: center;'>🎓</div>", unsafe_allow_html=True)
        
        with c_info:
            st.markdown("### CBSE Capstone Project")
            st.markdown("**Class 12  |  Artificial Intelligence  |  2025-26**")
            st.caption("Demonstrating advanced proficiency in Python, Generative AI (LLMs), Cloud Database Management, and Full-Stack State Logic.")

    st.write("") # Spacer

    # 3. FEATURES GRID
    st.markdown("### ⚡ Operational Arsenal")
    
    row1_1, row1_2 = st.columns(2)
    with row1_1:
        with st.container(border=True):
            st.markdown("#### 🤖 AI Strategist")
            st.caption("Powered by **Google Gemini**. Generates adaptive study schedules and explains complex concepts.")
    
    with row1_2:
        with st.container(border=True):
            st.markdown("#### 🎵 Sonic Intel")
            st.caption("Integrated **Audio Engine** with binaural beats and focus frequencies for deep work states.")

    row2_1, row2_2 = st.columns(2)
    with row2_1:
        with st.container(border=True):
            st.markdown("#### 🏆 Gamification")
            st.caption("**XP System & Leaderboards** synced live with Google Sheets to compete with other hunters.")
    
    with row2_2:
        with st.container(border=True):
            st.markdown("#### ☁️ Cloud Sync")
            st.caption("Persistent user data storage prevents data loss on refresh using **Session State & JSON**.")

    st.divider()

    # 4. TECH STACK BADGES
    st.markdown("### 🏗️ Technical Stack")
    st.markdown("""
    <div style="display: flex; flex-wrap: wrap; gap: 10px;">
        <span style="background-color: #FF4B4B; color: white; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: bold;">Streamlit</span>
        <span style="background-color: #306998; color: white; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: bold;">Python 3.9+</span>
        <span style="background-color: #4285F4; color: white; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: bold;">Google Gemini</span>
        <span style="background-color: #0F9D58; color: white; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: bold;">Google Sheets API</span>
        <span style="background-color: #F4B400; color: white; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: bold;">Pandas</span>
    </div>
    """, unsafe_allow_html=True)

    st.write("")
    st.caption("🔒 System Status: ONLINE | 🛡️ Developed with ❤️ by TIME HUNT AI TEAM")

def fetch_leaderboard_data():
    """Fetches all users, sorts by XP, and returns top 10."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="Sheet1", ttl=0)
        
        if not df.empty and 'XP' in df.columns:
            # Clean and Sort Data
            df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
            df = df.sort_values(by='XP', ascending=False).reset_index(drop=True)
            df['Rank'] = df.index + 1
            return df.head(10)
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()

def page_dashboard():
    # --- 1. DASHBOARD STYLING ---
    st.markdown("""
    <style>
        .dash-card {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 20px;
            text-align: center;
            backdrop-filter: blur(10px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .dash-card:hover { transform: translateY(-5px); border-color: #B5FF5F; }
        .stat-value { font-size: 32px; font-weight: 800; color: #B5FF5F; }
        .stat-label { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #aaa; }
        .rank-badge { font-size: 50px; animation: float 3s ease-in-out infinite; }
        @keyframes float { 0% { transform: translateY(0px); } 50% { transform: translateY(-10px); } 100% { transform: translateY(0px); } }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="big-title">📊 Intelligence Report</div>', unsafe_allow_html=True)

    # --- 2. DATA CALCULATION ---
    slots = st.session_state.get('timetable_slots', [])
    xp = st.session_state.get('user_xp', 0)
    level = st.session_state.get('user_level', 1)
    
    total = len(slots)
    completed = len([t for t in slots if t.get('Done')])
    rate = int((completed / total * 100)) if total > 0 else 0
    
    # Dynamic Rank Logic
    titles = {1: "Scout", 5: "Ranger", 10: "Veteran", 20: "Commander", 50: "Titan"}
    current_title = "Rookie"
    for lvl, title in titles.items():
        if level >= lvl: current_title = title
    
    # --- 3. TOP ROW: HUD ---
    c_rank, c_stats = st.columns([1, 3])
    
    with c_rank:
        st.markdown(f"""
        <div class="dash-card">
            <div class="rank-badge">🛡️</div>
            <div style="font-size:18px; font-weight:bold; color:white; margin-top:5px;">{current_title}</div>
            <div style="font-size:12px; color:#B5FF5F;">Level {level}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c_stats:
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(f"""<div class="dash-card"><div class="stat-value">{xp}</div><div class="stat-label">Total XP</div></div>""", unsafe_allow_html=True)
        with c2: st.markdown(f"""<div class="dash-card"><div class="stat-value">{completed}</div><div class="stat-label">Missions</div></div>""", unsafe_allow_html=True)
        with c3: 
            clr = "#00E5FF" if rate > 80 else "#FF2A2A"
            st.markdown(f"""<div class="dash-card"><div class="stat-value" style="color:{clr} !important;">{rate}%</div><div class="stat-label">Success Rate</div></div>""", unsafe_allow_html=True)

    st.write("")
    
    # --- 4. CHARTS & ANALYSIS ---
    c_chart, c_split = st.columns([2, 1])
    
    with c_chart:
        st.markdown("### 📈 XP Velocity")
        if st.session_state.get('xp_history'):
            df_hist = pd.DataFrame(st.session_state['xp_history'])
            st.line_chart(df_hist.set_index('Date')['XP'], color="#B5FF5F")
        else:
            st.info("Insufficient data for tactical graph.")
            
    with c_split:
        st.markdown("### 🧩 Sectors")
        if slots:
            df_s = pd.DataFrame(slots)
            if 'Category' in df_s.columns:
                counts = df_s['Category'].value_counts()
                st.dataframe(counts, use_container_width=True, column_config={"count": st.column_config.ProgressColumn("Vol", format="%d", min_value=0, max_value=int(counts.max()))})
        else:
            st.caption("No active sectors.")

    st.divider()

    # --- 5. GLOBAL LEADERBOARD ---
    st.markdown("### 🏆 Global Hunter Rankings")
    leader_df = fetch_leaderboard_data()
    
    if not leader_df.empty:
        st.dataframe(
            leader_df[['Rank', 'Name', 'League', 'XP']],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rank": st.column_config.NumberColumn("Rank", format="#%d", width="small"),
                "Name": st.column_config.TextColumn("Agent", width="medium"),
                "XP": st.column_config.ProgressColumn("XP", format="%d", min_value=0, max_value=int(leader_df['XP'].max() + 500))
            }
        )
    else:
        st.warning("Leaderboard Offline.")

    # --- 6. EXPORT ---
    st.markdown("### 🗂️ Archive")
    if st.button("📄 Export Dossier (PDF)", type="primary", use_container_width=True):
        try:
            pdf_bytes = create_mission_report(
                st.session_state.get('user_name', 'Agent'), level, xp, st.session_state.get('xp_history', [])
            )
            b64 = base64.b64encode(pdf_bytes).decode()
            href = f'<a href="data:application/octet-stream;base64,{b64}" download="Mission_Report.pdf" style="text-decoration:none; color:#B5FF5F; border:1px solid #B5FF5F; padding:10px; display:block; text-align:center; border-radius:10px;">📥 Download PDF</a>'
            st.markdown(href, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error: {e}")
 
# ------ PAGE: SETTINGS --------

def page_settings():
    st.markdown("## ⚙️ Command Center")
    
    # 1. VISUAL SETTINGS
    st.markdown("### 🎨 Interface Theme")
    c1, c2 = st.columns(2)
    with c1:
        cur_mode = st.session_state.get('theme_mode', 'Dark')
        new_mode = st.radio("System Mode", ["Dark", "Light"], index=0 if cur_mode=='Dark' else 1, horizontal=True)
    with c2:
        cur_color = st.session_state.get('theme_color', 'Venom Green (Default)')
        opts = ["Venom Green (Default)", "Cyber Blue", "Crimson Alert", "Stealth Grey"]
        new_color = st.selectbox("HUD Accent", opts, index=opts.index(cur_color) if cur_color in opts else 0)

    if st.button("Apply Visuals", use_container_width=True):
        st.session_state['theme_mode'] = new_mode
        st.session_state['theme_color'] = new_color
        st.rerun() 

    st.markdown("---")

    # 2. NOTIFICATIONS
    st.markdown("### 🔔 System Access")
    st.info("Authorize browser notifications for mission alerts.")
    
    # JS Injection for Permissions
    components.html("""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        .btn {
            background: #1A1A1A; color: #B5FF5F; border: 1px solid #B5FF5F; 
            padding: 12px; border-radius: 8px; cursor: pointer; font-family: monospace; 
            font-weight: bold; width: 100%; transition: 0.3s;
        }
        .btn:hover { background: #B5FF5F; color: black; }
    </style>
    </head>
    <body>
    <button class="btn" onclick="req()">🔓 AUTHORIZE ALERTS</button>
    <script>
    function req() {
        if (!("Notification" in window)) { alert("Not supported."); } 
        else {
            Notification.requestPermission().then(p => {
                if (p === "granted") new Notification("Protocol Active", {body: "Link Established."});
                else alert("Denied. Check browser settings.");
            });
        }
    }
    </script>
    </body>
    </html>
    """, height=80)

    st.markdown("---")
    
    # 3. IDENTITY
    st.markdown("### 👤 Identity")
    new_name = st.text_input("Codename", st.session_state.get('user_name', ''))
    if st.button("Update Identity"):
        st.session_state['user_name'] = new_name
        sync_data()
        st.toast("Identity Saved.")

    st.markdown("---")

    # 4. RESET
    with st.expander("☠️ Danger Zone"):
        if st.button("🔥 Factory Reset", type="primary"):
            st.session_state.clear()
            st.rerun()
 
# --- ALARM OVERLAY (GLOBAL COMPONENT) ---
def render_alarm_ui():
    """
    Renders a Full-Screen 'Code Red' Overlay when an alarm triggers.
    Injected at the top level to block interaction until resolved.
    """
    if st.session_state.get('active_alarm'):
        alarm = st.session_state['active_alarm']
        task = alarm['task']
        idx = alarm['index']
        
        # 1. Play Sound (Hidden)
        try:
            # Try local file first, else fallback URL
            if os.path.exists("alarm.mp3"):
                with open("alarm.mp3", "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                src = f"data:audio/mp3;base64,{b64}"
            else:
                src = "https://www.soundjay.com/buttons/beep-01a.mp3"
            st.markdown(f'<audio src="{src}" autoplay loop></audio>', unsafe_allow_html=True)
        except: pass

        # 2. Overlay CSS
        st.markdown("""
        <style>
            .alarm-overlay {
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background: rgba(0, 0, 0, 0.96); z-index: 999999;
                display: flex; flex-direction: column; align-items: center; justify-content: center;
                backdrop-filter: blur(20px); animation: fadeIn 0.3s;
            }
            .alarm-box {
                width: 90%; max-width: 500px;
                background: linear-gradient(135deg, #220000, #400000);
                border: 2px solid #FF2A2A; border-radius: 20px; padding: 40px;
                text-align: center; box-shadow: 0 0 80px rgba(255, 42, 42, 0.5);
                animation: pulse 1s infinite;
            }
            @keyframes pulse {
                0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 42, 42, 0.7); }
                50% { transform: scale(1.02); box-shadow: 0 0 0 20px rgba(255, 42, 42, 0); }
                100% { transform: scale(1); }
            }
        </style>
        """, unsafe_allow_html=True)

        # 3. Visuals
        st.markdown(f"""
        <div class="alarm-overlay">
            <div class="alarm-box">
                <div style="font-size:80px; margin-bottom:10px;">🚨</div>
                <h1 style="color:#FF2A2A; font-family:monospace; margin:0;">MISSION CRITICAL</h1>
                <h2 style="color:white; margin-top:10px;">"{task}"</h2>
                <p style="color:#ffaaaa;">IMMEDIATE ACTION REQUIRED</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 4. Interaction Buttons (Above Overlay)
        with st.container():
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("🛑 STOP", type="primary", use_container_width=True):
                    st.session_state['active_alarm'] = None
                    st.rerun()
            with c2:
                if st.button("💤 +5 MIN", use_container_width=True):
                    # Add 5 mins to reminder
                    if idx < len(st.session_state['reminders']):
                        st.session_state['reminders'][idx]['time'] += datetime.timedelta(minutes=5)
                        st.session_state['reminders'][idx]['notified'] = False
                    st.session_state['active_alarm'] = None
                    sync_data()
                    st.rerun()
            with c3:
                if st.button("✅ DONE", use_container_width=True):
                    if idx < len(st.session_state['reminders']):
                        st.session_state['reminders'].pop(idx)
                    st.session_state['active_alarm'] = None
                    sync_data()
                    st.rerun()
        
        # Stop App Execution to force interaction
        st.stop()

# --- 12. PAGE: TACTICAL HELP CENTER ---

def page_help():
    """
    Renders the Help/Support page.
    Includes: App Installation Guide, Feedback Ticket System, and FAQs.
    """
    # 1. Header
    st.markdown('<div class="big-title">🆘 Tactical Support</div>', unsafe_allow_html=True)
    st.caption("Operational Manual & Command Link")
    
    # --- SECTION 1: INSTALLATION (PWA GUIDE) ---
    st.markdown("### 📲 Deployment (Install App)")
    st.info("To install the TimeHunt interface on your home screen:")
    
    with st.container():
        c1, c2 = st.columns(2)
        
        # Android Card
        with c1:
            st.markdown("""
            <div class="glass-card" style="height:100%;">
                <h4 style="color:#B5FF5F; margin-bottom:10px;">🤖 Android / Chrome</h4>
                <ol style="font-size:14px; margin-left: -20px; line-height: 1.6;">
                    <li>Tap the <b>Three Dots (⋮)</b> menu.</li>
                    <li>Select <b>"Add to Home Screen"</b>.</li>
                    <li><i>Note: Reject any generic logo popups.</i></li>
                    <li>Confirm name as "TimeHunt AI".</li>
                </ol>
            </div>
            """, unsafe_allow_html=True)
            
        # iOS Card
        with c2:
            st.markdown("""
            <div class="glass-card" style="height:100%;">
                <h4 style="color:#00E5FF; margin-bottom:10px;">🍎 iOS / Safari</h4>
                <ol style="font-size:14px; margin-left: -20px; line-height: 1.6;">
                    <li>Tap the <b>Share Button</b> (Box + Arrow).</li>
                    <li>Scroll down to <b>"Add to Home Screen"</b>.</li>
                    <li>The Tactical Logo will auto-load.</li>
                    <li>Tap <b>Add</b> to confirm.</li>
                </ol>
            </div>
            """, unsafe_allow_html=True)

    st.write("")

    # --- SECTION 2: COMMAND LINK (FEEDBACK SYSTEM) ---
    st.markdown("### 📡 Command Link (Q&A)")
    
    # A. Ticket History Display
    my_tickets = get_my_feedback_status()
    
    if not my_tickets.empty:
        st.markdown("#### Incoming Transmissions")
        for index, row in my_tickets.iterrows():
            # Determine Status
            has_reply = pd.notna(row['Reply']) and str(row['Reply']).strip() != ""
            border_col = "#B5FF5F" if has_reply else "#444"
            status_txt = "✅ SECURE" if has_reply else "⏳ PENDING"
            
            # HTML for Ticket Card
            reply_html = f'<div style="margin-top:10px; padding-top:10px; border-top:1px dashed #555; color:#B5FF5F;"><b>⚓ HQ REPLY:</b> {row["Reply"]}</div>' if has_reply else ''
            
            st.markdown(f"""
            <div style="background: rgba(255,255,255,0.03); border: 1px solid {border_col}; border-radius: 12px; padding: 15px; margin-bottom: 12px;">
                <div style="display:flex; justify-content:space-between; font-size:11px; color:#888; letter-spacing:1px;">
                    <span>TIMESTAMP: {row['Timestamp']}</span>
                    <span style="color:{border_col}; font-weight:bold;">{status_txt}</span>
                </div>
                <div style="margin-top:8px; font-weight:600; font-size:15px; color:#fff;">"{row['Query']}"</div>
                {reply_html}
            </div>
            """, unsafe_allow_html=True)
    
    # B. Submission Form
    # If tickets exist, collapse the form by default to save space
    is_expanded = True if my_tickets.empty else False
    
    with st.expander("📝 Open New Channel", expanded=is_expanded):
        with st.form("help_form", clear_on_submit=True):
            st.write("**Describe your objective or report a bug:**")
            query = st.text_area("Message Payload", placeholder="Example: How do I reset my XP streak?", label_visibility="collapsed")
            
            if st.form_submit_button("🚀 Transmit to HQ", use_container_width=True, type="primary"):
                if len(query) > 5:
                    if save_feedback(query):
                        st.toast("Transmission Sent. Stand by.", icon="📨")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.warning("Transmission too short. Elaborate.")

    st.divider()

    # --- SECTION 3: FIELD MANUAL (FAQ) ---
    st.markdown("### 📘 Field Manual")
    
    faqs = {
        "🎯 How is XP calculated?": "XP is based on difficulty: Easy (20), Medium (50), Hard (150), BOSS (300). Daily streaks apply a multiplier up to 2.5x.",
        "🔊 Audio not playing?": "Modern browsers block auto-audio. Interact with the page (click anywhere) once to initialize the Tactical Engine.",
        "☁️ Data Privacy Status?": "Encrypted. Your schedule relies on your unique User ID. Clearing browser cache will require a re-login (PIN).",
        "🛑 How to delete alarms?": "When an alarm triggers, a 'MARK DONE' button appears. You can also delete tasks directly from the Scheduler."
    }
    
    for q, a in faqs.items():
        with st.expander(q):
            st.write(a)

# --- MAIN APP FUNCTION ---

def main():
    """
    Main application entry point.
    Orchestrates initialization, navigation, and global systems.
    """
    # 1. System Initialization
    initialize_session_state()
    
    # 2. Global Alarm System
    # Checks for due tasks immediately. If triggered, render_alarm_ui() 
    # takes over the screen and halts further execution.
    check_reminders()
    render_alarm_ui()

    # 3. Visuals & Assets
    inject_custom_css()
    show_comet_splash()

    # 4. Authentication Gate
    if not st.session_state.get('onboarding_complete', False):
        page_onboarding()
        return 

    # --- SIDEBAR LOGIC ---
    
    # A. CHAT MODE SIDEBAR (Specialized for AI Context)
    if st.session_state.get('page_mode') == 'chat':
        with st.sidebar:
            st.markdown("### 💬 Chat History")
            
            # Navigation Buttons
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🏠 Back", use_container_width=True):
                    st.session_state['page_mode'] = 'main'
                    st.rerun()
            with c2:
                if st.button("➕ New", use_container_width=True):
                    st.session_state['current_session_id'] = None
                    st.session_state['current_session_name'] = "New Chat"
                    st.session_state['chat_history'] = []
                    st.rerun()
            
            st.divider()

            # Delete Toggle Logic
            if 'delete_mode' not in st.session_state: 
                st.session_state['delete_mode'] = False
            
            toggle_label = "❌ Cancel" if st.session_state['delete_mode'] else "🗑️ Delete Chats"
            if st.button(toggle_label, use_container_width=True):
                st.session_state['delete_mode'] = not st.session_state['delete_mode']
                st.rerun()

            st.markdown("---")
            
            # Chat Session List
            sessions = load_chat_sessions()
            
            if st.session_state['delete_mode']:
                # DELETE MODE: Checkboxes
                st.warning("Select chats to remove:")
                with st.form("del_form"):
                    selected_ids = []
                    if not sessions:
                        st.caption("No chats found.")
                    
                    for s in sessions:
                        if st.checkbox(f"{s['SessionName']}", key=f"del_{s['SessionID']}"):
                            selected_ids.append(s['SessionID'])
                    
                    if st.form_submit_button("🔥 PERMANENTLY DELETE", type="primary", use_container_width=True):
                        if selected_ids:
                            for sid in selected_ids:
                                delete_chat_session(sid)
                            st.toast(f"Deleted {len(selected_ids)} chats.")
                            st.session_state['delete_mode'] = False
                            if st.session_state.get('current_session_id') in selected_ids:
                                st.session_state['current_session_id'] = None
                                st.session_state['chat_history'] = []
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.warning("Select items first.")
            else:
                # NORMAL MODE: Navigation
                if not sessions:
                    st.caption("No history.")
                
                for s in sessions:
                    is_active = (s['SessionID'] == st.session_state.get('current_session_id'))
                    b_type = "primary" if is_active else "secondary"
                    
                    if st.button(f"📄 {s['SessionName']}", key=s['SessionID'], type=b_type, use_container_width=True):
                        st.session_state['current_session_id'] = s['SessionID']
                        st.session_state['current_session_name'] = s['SessionName']
                        
                        msgs = load_messages_for_session(s['SessionID'])
                        st.session_state['chat_history'] = [{"role": m["Role"], "text": m["Content"]} for m in msgs]
                        st.rerun()
        
        # Render AI Page
        page_ai_assistant()

    # B. MAIN MENU SIDEBAR (Standard App Mode)
    else:
        with st.sidebar:
            st.markdown("<h1 style='text-align: center;'>🏹<br>TimeHunt AI</h1>", unsafe_allow_html=True)
            render_live_clock()
            
            # Sonic Intel (Audio)
            st.markdown("### 🎧 Sonic Intel")
            with st.container():
                music_mode = st.selectbox("Frequency", 
                    ["Om Chanting (Spiritual)", "Binaural Beats (Focus)", "Divine Flute (Flow)", "Rainfall (Calm)"], 
                    label_visibility="collapsed"
                )
                local_map = {
                    "Om Chanting (Spiritual)": "om.mp3", 
                    "Binaural Beats (Focus)": "binaural.mp3", 
                    "Divine Flute (Flow)": "flute.mp3", 
                    "Rainfall (Calm)": "rain.mp3"
                }
                
                target_file = local_map.get(music_mode)
                if target_file and os.path.exists(target_file):
                    st.audio(target_file, format="audio/mp3", loop=True)
                else:
                    st.caption("⚠️ Audio file missing locally.")
            
            st.markdown("---")
            
            # Location Override
            with st.expander("📍 Sector Location"):
                city_input = st.text_input("Base City", value=st.session_state.get('user_city', 'Jaipur'))
                if city_input != st.session_state.get('user_city', 'Jaipur'):
                    st.session_state['user_city'] = city_input
                    st.rerun()

            st.markdown("---")
            
            # Navigation Menu
            nav = option_menu(
                menu_title=None,
                options=["Home", "Scheduler", "Calendar", "AI Assistant", "Timer", "Dashboard", "Help", "About", "Settings"], 
                icons=["house", "list-check", "calendar-week", "robot", "hourglass-split", "graph-up", "life-preserver", "info-circle", "gear"], 
                default_index=0,
                styles={
                    "container": {"padding": "0!important", "background-color": "transparent"},
                    "icon": {"color": "#B5FF5F", "font-size": "16px"}, 
                    "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": "#333"},
                    "nav-link-selected": {"background-color": "#00E5FF", "color": "black"},
                }
            )

            st.caption(f"🆔 **Agent:** {st.session_state.get('user_name', 'Hunter')}")

        # Page Routing
        if nav == "Home": page_home()
        elif nav == "Scheduler": page_scheduler()
        elif nav == "Calendar": page_calendar()
        elif nav == "AI Assistant": 
            st.session_state['page_mode'] = 'chat'
            st.rerun()
        elif nav == "Timer": page_timer()  
        elif nav == "Dashboard": page_dashboard()
        elif nav == "Help": page_help()
        elif nav == "About": page_about()
        elif nav == "Settings": page_settings()

if __name__ == "__main__":
    main()