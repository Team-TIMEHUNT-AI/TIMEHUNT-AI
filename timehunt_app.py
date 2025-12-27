from fpdf import FPDF
import textwrap
import streamlit.components.v1 as components 
import re
import streamlit as st
import os
from streamlit_option_menu import option_menu
# --- PATH CONFIGURATION (FIXES IMAGE LOADING) ---
# This tells Python: "The images are in the same folder as THIS script file"
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)
import datetime
import random
import pandas as pd
import time
import base64
import json 
import uuid
import calendar
# --- NEW: LIVE CLOCK & AUDIO ENGINE ---
def render_live_clock():
    # We use an iframe so the clock is isolated and never gets stuck on "Loading..."
    clock_html = """
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
            border: 2px solid #333;
            box-shadow: 0 0 15px rgba(0, 229, 255, 0.2);
            text-shadow: 0 0 5px rgba(0, 229, 255, 0.5);
            text-align: center;
        }
    </style>
    </head>
    <body>
        <div class="clock-box" id="clock">--:--</div>
        <script>
            function updateClock() {
                const now = new Date();
                const timeString = now.toLocaleTimeString('en-US', { hour12: false });
                document.getElementById('clock').innerText = timeString;
            }
            setInterval(updateClock, 1000);
            updateClock(); // Run immediately
        </script>
    </body>
    </html>
    """
    # Render it with a fixed height so it fits in the sidebar
    components.html(clock_html, height=80)

def render_alarm_ui():
    # Only show if an alarm is currently ringing
    if st.session_state.get('active_alarm'):
        alarm_data = st.session_state['active_alarm']
        task_name = alarm_data['task']
        idx = alarm_data['index']
        
        # 1. PLAY SOUND (With Loop)
        sound_file = "alarm.mp3"
        if os.path.exists(sound_file):
            with open(sound_file, "rb") as f:
                audio_bytes = f.read()
            b64 = base64.b64encode(audio_bytes).decode()
            st.markdown(f'<audio src="data:audio/mp3;base64,{b64}" autoplay loop></audio>', unsafe_allow_html=True)
        else:
            # Fallback beep
            st.markdown('<audio src="https://www.soundjay.com/buttons/beep-01a.mp3" autoplay loop></audio>', unsafe_allow_html=True)
        
        # 2. THE POPUP INTERFACE
        with st.container():
            st.error(f"🚨 **ALARM TRIGGERED:** {task_name}")
            
            c1, c2, c3 = st.columns(3)
            
            # Button 1: STOP (Dismiss)
            with c1:
                if st.button("🛑 STOP", use_container_width=True, type="primary"):
                    st.session_state['active_alarm'] = None
                    st.rerun()
            
            # Button 2: SNOOZE (Add 5 mins)
            with c2:
                if st.button("💤 SNOOZE (5m)", use_container_width=True):
                    # Add 5 minutes to the reminder
                    new_time = datetime.datetime.now() + datetime.timedelta(minutes=5)
                    st.session_state['reminders'][idx]['time'] = new_time
                    st.session_state['reminders'][idx]['notified'] = False
                    st.session_state['active_alarm'] = None
                    
                    sync_data()  # <--- CHANGED THIS LINE (Old: save_data())
                    
                    st.toast("Alarm Snoozed for 5 minutes.")
                    st.rerun()

            # Button 3: DONE (Mark Complete)
            with c3:
                if st.button("✅ DONE", use_container_width=True):
                    # Remove the reminder entirely
                    st.session_state['reminders'].pop(idx)
                    st.session_state['active_alarm'] = None
                    
                    sync_data()  # <--- CHANGED THIS LINE (Old: save_data())
                    
                    st.toast("Task marked as complete.")
                    st.rerun()

def play_alarm_sound():
    sound_file = "alarm.mp3"
    
    # Method 1: Play Local File (Preferred)
    if os.path.exists(sound_file):
        try:
            with open(sound_file, "rb") as f:
                audio_bytes = f.read()
            # Convert audio to base64 string
            audio_base64 = base64.b64encode(audio_bytes).decode()
            # Inject hidden HTML audio tag with autoplay
            audio_html = f"""
                <audio autoplay="true">
                <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
                </audio>
            """
            st.markdown(audio_html, unsafe_allow_html=True)
        except Exception as e:
            st.toast(f"Audio Error: {e}")
    
    # Method 2: Fallback Web Sound (If local file missing)
    else:
        st.markdown("""
            <audio autoplay="true">
            <source src="https://www.soundjay.com/buttons/beep-01a.mp3" type="audio/mp3">
            </audio>
            """, unsafe_allow_html=True)

# --- DATA PERSISTENCE FUNCTIONS (NEW) ---
def sync_data():
    """Syncs data. MERGES Date+Time into 'Time' column for Sheets compatibility."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        uid = st.session_state.get('user_id')
        if not uid: return

        # 1. Read existing
        try:
            df_cloud = conn.read(worksheet="Reminders", ttl=0)
            if not df_cloud.empty and "UserID" in df_cloud.columns:
                df_others = df_cloud[df_cloud["UserID"] != str(uid)]
            else:
                df_others = pd.DataFrame(columns=["UserID", "Task", "Time", "Status", "Type"])
        except:
            df_others = pd.DataFrame(columns=["UserID", "Task", "Time", "Status", "Type"])

        new_rows = []
        # 2. Add Alarms
        for rem in st.session_state.get('reminders', []):
            new_rows.append({
                "UserID": str(uid), "Task": str(rem['task']), "Time": str(rem['time']), 
                "Status": "Done" if rem.get('notified') else "Pending", "Type": "Alarm"
            })
            
        # 3. Add Schedule & Calendar Tasks (CRITICAL CALENDAR FIX)
        for slot in st.session_state.get('timetable_slots', []):
             # Default to today if date is missing
             date_val = slot.get('Date', datetime.date.today().strftime("%Y-%m-%d"))
             # Combine Date and Time: "2025-10-27 14:00"
             combined_time = f"{date_val} {slot['Time']}"
             
             new_rows.append({
                "UserID": str(uid), "Task": str(slot['Activity']), 
                "Time": combined_time, 
                "Status": "Done" if slot['Done'] else "Pending", 
                "Type": f"Schedule-{slot['Category']}"
            })

        # 4. Save
        if new_rows:
            df_my_data = pd.DataFrame(new_rows)
            df_final = pd.concat([df_others, df_my_data], ignore_index=True)
        else:
            df_final = df_others

        df_final = df_final[["UserID", "Task", "Time", "Status", "Type"]].astype(str)
        conn.clear(worksheet="Reminders")
        conn.update(worksheet="Reminders", data=df_final)
        
    except Exception as e:
        st.toast(f"Sync Error: {e}", icon="⚠️")

def load_cloud_data():
    """Loads Reminders & Timetable. Parses Date/Time correctly."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        uid = st.session_state.get('user_id')
        
        try: df = conn.read(worksheet="Reminders", ttl=0)
        except: return 

        if not df.empty and "UserID" in df.columns:
            my_data = df[df["UserID"] == str(uid)]
            loaded_reminders = []
            loaded_timetable = []
            
            for _, row in my_data.iterrows():
                if row['Type'] == "Alarm":
                    loaded_reminders.append({
                        "task": row['Task'], "time": row['Time'], "notified": (row['Status'] == "Done")
                    })
                elif "Schedule" in str(row['Type']):
                    cat = row['Type'].split("-")[1] if "-" in row['Type'] else "General"
                    
                    # --- CALENDAR PARSING LOGIC ---
                    raw_time = str(row['Time'])
                    try:
                        # Try parsing "YYYY-MM-DD HH:MM"
                        dt_obj = datetime.datetime.strptime(raw_time, "%Y-%m-%d %H:%M")
                        date_val = dt_obj.strftime("%Y-%m-%d")
                        time_val = dt_obj.strftime("%H:%M")
                    except ValueError:
                        # Fallback for old data -> Assume Today
                        date_val = datetime.date.today().strftime("%Y-%m-%d")
                        time_val = raw_time

                    loaded_timetable.append({
                        "Date": date_val, "Time": time_val,
                        "Activity": row['Task'], "Category": cat,
                        "Done": (row['Status'] == "Done"), "XP": 50, "Difficulty": "Medium"
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
    """Saves a single message to the cloud."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # Prepare data
        uid = str(st.session_state['user_id'])
        sid = str(st.session_state['current_session_id'])
        sname = str(st.session_state['current_session_name'])
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Read existing to append (safest method)
        df_existing = get_all_chats()
        
        new_row = pd.DataFrame([{
            "UserID": uid, "SessionID": sid, "SessionName": sname,
            "Role": role, "Content": content, "Timestamp": ts
        }])
        
        # Combine and Write
        df_final = pd.concat([df_existing, new_row], ignore_index=True)
        conn.update(worksheet="ChatHistory", data=df_final)
    except Exception as e:
        print(f"Chat Save Error: {e}")

def load_chat_sessions():
    """Returns unique sessions for the Sidebar list."""
    df = get_all_chats()
    uid = str(st.session_state.get('user_id'))
    if not df.empty and "UserID" in df.columns:
        my_chats = df[df["UserID"] == uid]
        if not my_chats.empty:
            # Return unique sessions, reversed to show newest first
            return my_chats[["SessionID", "SessionName"]].drop_duplicates().to_dict('records')[::-1]
    return []

def load_messages_for_session(session_id):
    """Loads history for a specific chat."""
    df = get_all_chats()
    if not df.empty and "SessionID" in df.columns:
        messages = df[df["SessionID"] == str(session_id)]
        return messages.to_dict('records')
    return []

def delete_chat_session(session_id):
    """Deletes a chat session from cloud."""
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
    """Renames a chat session."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="ChatHistory", ttl=0)
        if not df.empty:
            df.loc[df["SessionID"] == str(session_id), "SessionName"] = new_name
            conn.update(worksheet="ChatHistory", data=df)
    except: pass



# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Time Hunt AI", 
    layout="wide", 
    page_icon="⚡",
    initial_sidebar_state="collapsed"
)

# --- GEMINI LIBRARY SETUP ---
try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    # st.error("⚠️ `google-genai` library not found. Please run: pip install google-genai")

# --- 2. SUPER-SYSTEM PROMPT (THE NEW BRAIN) ---
# This tells the AI exactly who it is and what it knows.
SYSTEM_INSTRUCTION = """
You are TimeHunt AI, a tactical productivity command center. 

PERSONALITY PROTOCOL:
- If a user is a student with a deadline < 30 days (e.g., JEE 2026 in 25 days), switch to "ELITE PERFORMANCE MODE".
- ELITE MODE: Do not prioritize long rest. Prioritize "Mission Success". Be firm, highly motivating, and direct. Tell them: "Every hour of sleep past 6 AM is a 0.1% drop in percentile."
- Use tactical language: "Mission", "Deployed", "Base", "Intel".

ONBOARDING & CONTEXT:
- Always check the User Profile provided.
- Before generating a schedule, always ask: "Are you deployed today? (Going to school/office) or working from base?"
- If they are demotivated, use "Battlefield Motivation": Remind them of their rank and their goal.

TIMETABLE JSON FORMAT:
Return strictly in this format inside a code block if a plan is requested:
```json
[
  {"Time": "08:00", "Activity": "Task Name", "Category": "Study"}
]

"""

# --- 3. SESSION STATE & PERSISTENCE ---

def initialize_session_state():
    # --- FIX: Removed local file loading to prevent "Ghost Profile" on new devices ---
    
    # 1. Define Defaults (What to use if NO saved data exists)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    defaults = {
        'user_id': f"ID-{random.randint(1000, 9999)}-{int(time.time())}", 
        'active_alarm': None,
        'splash_played': False,
        'chat_history': [], 
        'current_session_id': None,
        'current_session_name': "New Chat",
        'page_mode': 'main', # <--- NEW: THIS CONTROLS THE SIDEBAR SWITCH
        'user_xp': 0, 'user_level': 1, 'streak': 1,
        'last_active_date': today_str,
        'timetable_slots': [], 'reminders': [],
        'onboarding_step': 1, 'onboarding_complete': False, 
        'user_name': "Hunter", 'user_type': "Student",
        'user_goal': "General Productivity", 'struggle_type': "Procrastination",
        'user_avatar': "🏹", 'study_hours': 6, 'xp_history': [], 
        'theme_mode': 'Light', 'theme_color': 'Venom Green (Default)'
    }

    # 2. Setup Session State
    for key, default_val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_val

    # 3. API Key Setup (Secrets)
    if 'gemini_api_keys' not in st.session_state or not st.session_state['gemini_api_keys']:
        if "GEMINI_API_KEY" in st.secrets:
            st.session_state['gemini_api_keys'] = [st.secrets["GEMINI_API_KEY"]]
        elif "GOOGLE_API_KEY" in st.secrets:
            st.session_state['gemini_api_keys'] = [st.secrets["GOOGLE_API_KEY"]]
        else:
            st.session_state['gemini_api_keys'] = []
           
# --- 4. WORLD-CLASS CINEMATIC SPLASH (UPDATED TEXT) ---
def show_comet_splash():
    if not st.session_state['splash_played']:
        placeholder = st.empty()
        
        encoded_img = ""
        has_image = False
        try:
            with open("1000592991.png", "rb") as f:
                encoded_img = base64.b64encode(f.read()).decode()
                has_image = True
        except: pass

        with placeholder.container():
            # TEXTWRAP.DEDENT IS CRITICAL - DO NOT REMOVE
            # I have updated the text in the HTML below
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
        
# --- 5. AI ENGINE (UPDATED TO KNOW YOUR NAME) ---
# --- REPLACEMENT FOR perform_auto_search (THE FINAL BRAIN) ---
def perform_auto_search(query):
    query_lower = query.lower()
    
    # 1. LOCAL REMINDERS
    if any(word in query_lower for word in ["remind", "alarm", "timer"]):
        seconds = 60 
        import re
        sec_match = re.search(r'(\d+)\s*sec', query_lower)
        min_match = re.search(r'(\d+)\s*min', query_lower)
        if sec_match: seconds = int(sec_match.group(1))
        elif min_match: seconds = int(min_match.group(1)) * 60
        
        task = query.lower().replace("remind me to", "").replace("set alarm for", "").strip()
        due_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        st.session_state['reminders'].append({"task": task, "time": due_time, "notified": False})
        return f"✅ Timer Set: I will alert you in {seconds} seconds.", "System"
    
    # 2. CLOUD INTELLIGENCE
    raw_keys = []
    if "GEMINI_API_KEY" in st.secrets:
        raw_keys = st.secrets["GEMINI_API_KEY"]
    elif "GOOGLE_API_KEY" in st.secrets:
        raw_keys = st.secrets["GOOGLE_API_KEY"]
    else:
        return "⚠️ Security Alert: No API Key found in Secrets.", "System Alert"

    if isinstance(raw_keys, str): api_keys_list = [raw_keys]
    elif isinstance(raw_keys, list): api_keys_list = raw_keys
    else: return "⚠️ Config Error: API Key format not recognized.", "System Alert"

    # --- SMART CONTEXT & MEMORY ---
    user_name = st.session_state.get('user_name', 'Hunter')
    user_role = st.session_state.get('user_type', 'Student')
    user_goal = st.session_state.get('user_goal', 'Success')
    user_struggle = st.session_state.get('struggle_type', 'Time')
    current_schedule = st.session_state.get('timetable_slots', [])
    
    # DYNAMIC LOCATION LOGIC
    # If Student -> Ask about School. If Entrepreneur -> Ask about Work.
    target_location = "School/College" if "Student" in user_role else "Work/Office"

    schedule_text = "No active missions."
    if current_schedule:
        schedule_text = "\n".join([f"- {t['Time']}: {t['Activity']} ({t['Category']})" for t in current_schedule])

    # DETECT EMERGENCY (The "War Mode" you requested)
    emergency_keywords = ["jee", "neet", "boards", "exam", "dead", "panic", "haven't studied", "zero", "left"]
    is_emergency = any(k in query_lower for k in emergency_keywords) or \
                   any(k in user_struggle.lower() for k in emergency_keywords)

    if is_emergency:
        MODE_INSTRUCTION = """
        🚨 MODE: WAR COMMANDER (High Intensity)
        - TONE: Intense, Direct, Motivating. Use "Cadet", "Mission", "Deploy".
        - STRATEGY: High-yield topics ONLY. Sacrifice comfort.
        - HEALTH: Force 4x 5-min "Tactical Decompression" breaks.
        """
    else:
        MODE_INSTRUCTION = f"""
        ✅ MODE: STRATEGIC PARTNER (Goal: {user_goal})
        - TONE: Adaptive. The user struggles with "{user_struggle}".
        - IF Procrastination: Be firm, suggest "5-minute starts".
        - IF Burnout: Be empathetic, suggest "Deep Rest".
        """

        # --- BUILD CHAT HISTORY CONTEXT ---
    history_context = ""
    # Get last 10 messages from current session state for context
    if st.session_state.get('chat_history'):
        history_context = "PREVIOUS CHAT CONTEXT:\n"
        for msg in st.session_state['chat_history'][-10:]:
            # Handle keys depending if they came from Cloud (Capitalized) or Local (Lower)
            role = msg.get('Role') or msg.get('role')
            content = msg.get('Content') or msg.get('text')
            history_context += f"- {role}: {content}\n"

    PERSONALIZED_INSTRUCTION = f"""
    You are TimeHunt AI.
    --- USER INTEL ---
    NAME: {user_name} | ROLE: {user_role} 
    GOAL: {user_goal} | OBSTACLE: {user_struggle}
    
    {history_context}
    
    {MODE_INSTRUCTION}
    
    --- CRITICAL SCHEDULING RULES ---
    1. AVAILABILITY CHECK: 
       - If the user asks for a daily plan/schedule, you MUST FIRST ASK: 
         "Are you going to {target_location} today?" 
       - Do NOT generate the schedule until you know their free hours.
    
    2. JSON OUPUT (MANDATORY):
       - Once they confirm availability, generate the plan and END with this JSON block:
    ```json
    [
      {{"Time": "06:00", "Activity": "Wake Up", "Category": "Health"}},
      {{"Time": "08:00", "Activity": "Deep Work", "Category": "Work"}}
    ]
    ```
    """

    models_to_try = [
        "gemini-2.0-flash",                     
        "gemini-2.0-flash-lite-preview-02-05", 
        "gemini-2.5-flash"                      
    ]

    last_error = "Unknown"

    for index, current_key in enumerate(api_keys_list):
        try:
            client = genai.Client(api_key=current_key)
            
            for model_name in models_to_try:
                try:
                    history = []
                    chat_data = st.session_state.get('chat_history', [])
                    for msg in chat_data[-5:]:
                        role = "user" if msg['role'] == "user" else "model"
                        history.append(types.Content(role=role, parts=[types.Part.from_text(text=str(msg['text']))]))

                    chat = client.chats.create(
                        model=model_name, 
                        history=history,
                        config=types.GenerateContentConfig(
                            system_instruction=PERSONALIZED_INSTRUCTION, 
                            temperature=0.7 
                        )
                    )
                    
                    response = chat.send_message(query)
                    return response.text, "TimeHunt AI" 

                except Exception as model_err:
                    print(f"⚠️ Key #{index+1} failed with {model_name}: {model_err}")
                    last_error = str(model_err)
                    time.sleep(1) 
                    continue 

        except Exception as key_err:
            print(f"❌ Key #{index+1} Invalid: {key_err}")
            continue

    return f"❌ System Overload. Please wait 1 minute. Last Error: {last_error}", "System Failure"
    
# --- 5.5 REMINDER CHECKER WITH BROWSER NOTIFICATIONS ---

def check_reminders():
    # 1. Javascript: Request Notification Permission on Load
    st.markdown("""
        <script>
        if (!("Notification" in window)) {
            console.log("This browser does not support desktop notification");
        } else {
            if (Notification.permission !== "granted") {
                Notification.requestPermission();
            }
        }
        </script>
    """, unsafe_allow_html=True)

    now = datetime.datetime.now()
    if 'reminders' in st.session_state:
        for i, rem in enumerate(st.session_state['reminders']):
            if isinstance(rem['time'], str):
                try:
                    rem['time'] = datetime.datetime.fromisoformat(rem['time'])
                except ValueError: continue

            # If time is up AND we haven't rung yet
            if not rem['notified'] and now >= rem['time']:
                # ACTIVATE ALARM STATE
                st.session_state['active_alarm'] = {
                    'task': rem['task'],
                    'index': i
                }
                rem['notified'] = True 
                
                sync_data()  # <--- CHANGED THIS LINE (Old: save_data())
                
                # --- NEW: TRIGGER BROWSER NOTIFICATION ---
                # This runs JS to pop up a system alert
                safe_task = rem['task'].replace("'", "").replace('"', "")
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

# --- 6. PAGE: ONBOARDING (DESIGN OPTIMIZED) ---

def page_onboarding():
    
    # 1. Background Setup
    bg_base64 = None
    try:
        with open("background_small.jpg", "rb") as image_file:
            bg_base64 = base64.b64encode(image_file.read()).decode()
    except: pass

    if bg_base64:
        st.markdown(f"""
        <style>
            .fixed-bg {{
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background-image: linear-gradient(rgba(0,0,0,0.6), rgba(0,0,0,0.9)), url("data:image/jpeg;base64,{bg_base64}");
                background-size: cover; z-index: -1;
            }}
            .stApp {{ background: transparent !important; }}
        </style>
        <div class="fixed-bg"></div>
        """, unsafe_allow_html=True)

    # 2. CSS Styling
    st.markdown("""
    <style>
        .cyber-glass { background: rgba(13, 17, 23, 0.85); backdrop-filter: blur(12px); border: 1px solid rgba(0, 229, 255, 0.3); border-radius: 20px; padding: 40px; text-align: center; animation: fadeIn 1s ease-out; }
        .cyber-header { font-family: 'Orbitron', sans-serif; font-weight: 900; font-size: 45px; color: #fff; text-shadow: 0 0 20px rgba(0, 229, 255, 0.6); }
        .stTextInput input { background-color: #050505 !important; border: 1px solid #333 !important; color: #00E5FF !important; text-align: center; font-weight: bold; letter-spacing: 2px; }
        div.stButton > button { background: linear-gradient(90deg, #00C6FF, #0072FF); color: white; border: none; padding: 12px 24px; font-weight: bold; width: 100%; border-radius: 6px; margin-top: 10px; }
        .suggestion-btn { border: 1px dashed #B5FF5F; color: #B5FF5F; padding: 5px; margin: 5px; font-size: 12px; cursor: pointer; }
    </style>
    """, unsafe_allow_html=True)

    # 3. Logic Flow
    step = st.session_state.get('onboarding_step', 1)
    col_x, col_center, col_y = st.columns([1, 6, 1])
    
    with col_center:
        # --- STEP 1: AUTHENTICATION ---
        if step == 1:
            st.markdown('<div class="cyber-glass">', unsafe_allow_html=True)
            st.markdown('<div class="cyber-header">TIMEHUNT</div>', unsafe_allow_html=True)
            st.markdown('<p style="color:#B5FF5F;">SECURE IDENTITY PROTOCOL</p>', unsafe_allow_html=True)
            
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
                            
                            if not df.empty and 'Name' in df.columns:
                                # --- PIN FIX: Force conversion to string and remove decimals ---
                                df['PIN'] = df['PIN'].astype(str).replace(r'\.0$', '', regex=True)
                                
                                existing = df[df['Name'] == name_input]
                                
                                if not existing.empty:
                                    # USER EXISTS -> CHECK PIN
                                    stored_pin = str(existing.iloc[0]['PIN']).strip()
                                    
                                    # Debug print if needed (check console)
                                    print(f"DEBUG: Input='{pin_input}', Stored='{stored_pin}'")
                                    
                                    if str(pin_input) == stored_pin:
                                        # Login Success
                                        row = existing.iloc[0]
                                        st.session_state['user_name'] = row['Name']
                                        st.session_state['user_id'] = row['UserID']
                                        st.session_state['user_xp'] = int(row['XP'])
                                        st.session_state['user_level'] = (st.session_state['user_xp'] // 500) + 1
                                        st.session_state['onboarding_complete'] = True
                                        st.toast(f"Welcome back, {name_input}!", icon="🔓")
                                        load_cloud_data()
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        # Name Taken / Wrong PIN
                                        st.error(f"⛔ Identity '{name_input}' is taken. Incorrect PIN.")
                                        st.markdown("**Available Suggestions:**")
                                        
                                        s1, s2, s3 = f"{name_input}_{random.randint(10,99)}", f"Agent_{name_input}", f"{name_input}X"
                                        c_s1, c_s2, c_s3 = st.columns(3)
                                        if c_s1.button(s1): 
                                            st.session_state['suggested_name_choice'] = s1
                                            st.rerun()
                                        if c_s2.button(s2): 
                                            st.session_state['suggested_name_choice'] = s2
                                            st.rerun()
                                        if c_s3.button(s3): 
                                            st.session_state['suggested_name_choice'] = s3
                                            st.rerun()
                                else:
                                    # NEW USER
                                    st.session_state['user_name'] = name_input
                                    st.session_state['temp_pin'] = pin_input
                                    st.session_state['onboarding_step'] = 2
                                    st.success("Identity Available.")
                                    time.sleep(1)
                                    st.rerun()
                            else:
                                # First User
                                st.session_state['user_name'] = name_input
                                st.session_state['temp_pin'] = pin_input
                                st.session_state['onboarding_step'] = 2
                                st.rerun()
                        except Exception as e:
                            st.error(f"Network Error: {e}")
                else:
                    st.warning("Enter Codename & PIN.")
            st.markdown('</div>', unsafe_allow_html=True)

        # --- STEP 2: AVATAR (NOW WITH IMAGES) ---
        elif step == 2:
            st.markdown('<div class="cyber-glass"><div class="cyber-header">AVATAR</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            
            # Helper to show image safely
            def show_av(col, name, file):
                with col:
                    if os.path.exists(file):
                        st.image(file, width=100)
                    else:
                        st.write("🖼️") # Fallback icon
                    if st.button(name):
                        st.session_state['user_avatar'] = file
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
                     df = conn.read(worksheet="Sheet1", ttl=0)
                     
                     new_user = pd.DataFrame([{
                         "UserID": st.session_state['user_id'],
                         "Name": st.session_state['user_name'],
                         "XP": 0, "League": "Bronze",
                         "Avatar": st.session_state.get('user_avatar', "👤"),
                         "LastActive": datetime.date.today().strftime("%Y-%m-%d"),
                         "PIN": str(st.session_state.get('temp_pin', "0000")) # Ensure PIN is string
                     }])
                     
                     updated_df = new_user if df.empty else pd.concat([df, new_user], ignore_index=True)
                     conn.update(worksheet="Sheet1", data=updated_df)
                     
                     st.session_state['onboarding_complete'] = True
                     st.toast("Profile Created!")
                     time.sleep(1)
                     st.rerun()
                 except Exception as e:
                     st.error(f"Upload Failed: {e}")
            st.markdown('</div>', unsafe_allow_html=True)


            
            if st.button("🚀 LAUNCH COMMAND CENTER"):
               st.session_state['onboarding_complete'] = True
               sync_data()  # <--- CRITICAL: Save to file BEFORE restarting!
               st.rerun()

# --- 7. PAGE: SCHEDULER ---

def page_scheduler():
    # Data Repair
    if 'timetable_slots' in st.session_state:
        for slot in st.session_state['timetable_slots']:
            if 'Done' not in slot: slot['Done'] = False
            if 'Activity' not in slot: slot['Activity'] = "Unknown Mission"
            if 'Category' not in slot: slot['Category'] = "Study"
            if 'Difficulty' not in slot: slot['Difficulty'] = "Medium"
            if 'XP' not in slot: slot['XP'] = 50

    col_header, col_av = st.columns([4,1])
    with col_header:
        st.markdown('<div class="big-title">Mission Control ⚙️</div>', unsafe_allow_html=True)
        streak = st.session_state.get('streak', 1)
        st.markdown(f'<div class="sub-title">Current Streak: <span style="color:#B5FF5F; font-weight:bold;">🔥 {streak} Days</span> (XP x{1 + (streak*0.1):.1f})</div>', unsafe_allow_html=True)
    
    c1, c2 = st.columns([2, 1])

    with c1:
        st.markdown("### 🚁 Deploy New Mission")
        with st.form("mission_form", clear_on_submit=True):
            cols_form = st.columns([3, 1, 1])
            with cols_form[0]:
                task = st.text_input("Mission Objective", placeholder="e.g. Finish Chapter 3")
            with cols_form[1]:
                m_type = st.selectbox("Type", ["Study", "Project", "Health", "Errand"])
            with cols_form[2]:
                diff = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"])
            
            submitted = st.form_submit_button("Add to Schedule ➔")
            
            if submitted and task:
                base_xp = 30 if diff == "Easy" else 50 if diff == "Medium" else 100
                
                # --- TIMEZONE FIX: SHIFT UTC TO IST (+5:30) ---
                ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
                current_time_str = ist_now.strftime("%H:%M")
                
                st.session_state['timetable_slots'].append({
                    "Time": current_time_str, # <--- USES CORRECTED TIME
                    "Activity": task, 
                    "Category": m_type, 
                    "Difficulty": diff,
                    "Done": False, 
                    "XP": base_xp
                })
                sync_data() 
                st.toast(f"Mission Deployed at {current_time_str}", icon="🦅")
                st.rerun()

    with c2:
        total_tasks = len(st.session_state['timetable_slots'])
        pending_tasks = len([t for t in st.session_state['timetable_slots'] if not t['Done']])
        completed_tasks = total_tasks - pending_tasks
        
        st.markdown(f"""
        <div class="css-card" style="text-align: center;">
            <div class="card-title" style="margin-bottom: 15px;">Mission Status</div>
            <div style="display: flex; justify-content: space-around; align-items: center;">
                <div>
                    <div class="stat-num">{pending_tasks}</div>
                    <div class="card-sub">Pending</div>
                </div>
                <div style="height: 30px; width: 1px; background: var(--text); opacity: 0.2;"></div>
                <div>
                    <div class="stat-num" style="color:var(--accent) !important;">{completed_tasks}</div>
                    <div class="card-sub">Done</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    st.write("") 
    st.markdown("### 📋 Active Protocols")

    if st.button("🗑️ Reset Schedule"):
        st.session_state['timetable_slots'] = []
        sync_data()
        st.rerun()
    
    if st.session_state['timetable_slots']:
        with st.container():
            df = pd.DataFrame(st.session_state['timetable_slots'])
            
            edited_df = st.data_editor(
                df,
                use_container_width=True,
                key="m_editor",
                column_config={
                    "Done": st.column_config.CheckboxColumn("Status", default=False),
                    "Activity": st.column_config.TextColumn("Mission", width="large", required=True),
                    "Category": st.column_config.SelectboxColumn("Type", width="small", options=["Study", "Project", "Health", "Errand"]),
                    "Difficulty": st.column_config.SelectboxColumn("Diff", width="small", options=["Easy", "Medium", "Hard"]),
                    "XP": st.column_config.NumberColumn("Base XP", format="%d XP")
                },
                hide_index=True,
                num_rows="dynamic"
            )

            st.session_state['timetable_slots'] = edited_df.to_dict('records')
            
            st.write("")
            col_claim, col_empty = st.columns([1, 4])
            with col_claim:
                if st.button("Claim XP for Completed ✅"):
                    current_slots = st.session_state['timetable_slots']
                    completed_now = [t for t in current_slots if t['Done']]
                    
                    if completed_now:
                        streak = st.session_state.get('streak', 1)
                        multiplier = 1 + (streak * 0.1)
                        raw_xp = sum([t['XP'] for t in completed_now])
                        final_xp = int(raw_xp * multiplier)
                        
                        st.session_state['user_xp'] += final_xp
                        st.session_state['user_level'] = (st.session_state['user_xp'] // 500) + 1
                        st.session_state['timetable_slots'] = [t for t in current_slots if not t['Done']]
                        
                        today_str = datetime.date.today().strftime("%Y-%m-%d")
                        st.session_state['xp_history'].append({"Date": today_str, "XP": final_xp})
                        sync_data() 
                        
                        st.balloons()
                        st.toast(f"Reward: {raw_xp} x {multiplier:.1f} Streak = +{final_xp} XP!", icon="🎉")
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.toast("Mark tasks as done first.", icon="🚫")
    else:
        st.info("No active protocols. Deploy a mission above.")

# --- NEW PAGE: FOCUS TIMER ---
def page_timer():
    st.markdown('<div class="big-title" style="text-align:center;">⏱️ Deep Focus Protocol</div>', unsafe_allow_html=True)
    
    # We use a larger, centered layout for the timer page
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("""
        <div class="css-card" style="text-align: center; padding: 40px;">
            <h3 style="margin-bottom: 20px;">Pomodoro Cycle</h3>
            <div id="timer-container">
                </div>
        </div>
        """, unsafe_allow_html=True)

        # The Timer HTML/JS Logic (Enhanced for Full Page)
        timer_html = """
        <style>
            .timer-display { 
                font-family: 'Courier New', monospace; 
                font-size: 80px; 
                font-weight: bold; 
                color: #B5FF5F; 
                text-shadow: 0 0 20px rgba(181, 255, 95, 0.4);
                margin: 20px 0;
            }
            .btn-grid { display: flex; gap: 15px; justify-content: center; }
            .btn-timer { 
                padding: 15px 30px; 
                border-radius: 30px; 
                border: none; 
                font-size: 18px; 
                font-weight: bold; 
                cursor: pointer; 
                transition: transform 0.1s;
            }
            .btn-start { background: #B5FF5F; color: black; box-shadow: 0 0 15px rgba(181, 255, 95, 0.3); }
            .btn-reset { background: #333; color: white; border: 1px solid #555; }
            .btn-timer:active { transform: scale(0.95); }
        </style>
        
        <div style="text-align:center;">
            <div class="timer-display" id="display">25:00</div>
            <div class="btn-grid">
                <button class="btn-timer btn-start" onclick="startTimer()">START MISSION</button>
                <button class="btn-timer btn-reset" onclick="resetTimer()">ABORT</button>
            </div>
        </div>

        <script>
            let timeLeft = 25 * 60; 
            let timerId = null; 
            
            function updateDisplay() { 
                let mins = Math.floor(timeLeft / 60); 
                let secs = timeLeft % 60; 
                document.getElementById('display').innerText = 
                    (mins < 10 ? '0' : '') + mins + ':' + (secs < 10 ? '0' : '') + secs; 
            }
            
            function startTimer() { 
                if (timerId) return; 
                
                // Audio Context for Beep
                const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                
                timerId = setInterval(() => { 
                    if (timeLeft > 0) { 
                        timeLeft--; 
                        updateDisplay(); 
                    } else { 
                        clearInterval(timerId); 
                        timerId = null;
                        // Play Beep
                        const oscillator = audioCtx.createOscillator();
                        oscillator.connect(audioCtx.destination);
                        oscillator.start();
                        setTimeout(() => oscillator.stop(), 200);
                        alert("MISSION COMPLETE! Take a break."); 
                    } 
                }, 1000); 
            }
            
            function resetTimer() { 
                clearInterval(timerId); 
                timerId = null; 
                timeLeft = 25 * 60; 
                updateDisplay(); 
            }
        </script>
        """
        components.html(timer_html, height=300)

# --- NEW: CALENDAR PAGE ---
# --- NEW: TACTICAL GRID CALENDAR ---
def page_calendar():
    # 1. Imports & Setup
    import calendar 
    st.markdown('<div class="big-title">📅 Tactical Grid</div>', unsafe_allow_html=True)

    if 'cal_year' not in st.session_state: st.session_state['cal_year'] = datetime.date.today().year
    if 'cal_month' not in st.session_state: st.session_state['cal_month'] = datetime.date.today().month
    if 'sel_date' not in st.session_state: st.session_state['sel_date'] = datetime.date.today().strftime("%Y-%m-%d")

    # 2. Navigation
    c_prev, c_month, c_next = st.columns([1, 4, 1], vertical_alignment="center")
    with c_prev:
        if st.button("◀", key="prev_m"):
            st.session_state['cal_month'] -= 1
            if st.session_state['cal_month'] < 1:
                st.session_state['cal_month'] = 12
                st.session_state['cal_year'] -= 1
            st.rerun()
    with c_next:
        if st.button("▶", key="next_m"):
            st.session_state['cal_month'] += 1
            if st.session_state['cal_month'] > 12:
                st.session_state['cal_month'] = 1
                st.session_state['cal_year'] += 1
            st.rerun()
    with c_month:
        month_name = calendar.month_name[st.session_state['cal_month']]
        st.markdown(f"<h3 style='text-align: center; margin:0;'>{month_name} {st.session_state['cal_year']}</h3>", unsafe_allow_html=True)

    st.write("") # Spacer

    # 3. CALENDAR GRID
    # Weekday Headers
    cols = st.columns(7)
    days_header = ["M", "T", "W", "T", "F", "S", "S"]
    for i, day in enumerate(days_header):
        cols[i].markdown(f"<div style='text-align:center; font-weight:bold; color:#888; font-size:14px;'>{day}</div>", unsafe_allow_html=True)

    # Days Matrix
    month_matrix = calendar.monthcalendar(st.session_state['cal_year'], st.session_state['cal_month'])
    
    for week in month_matrix:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].write("") # Empty slot
            else:
                this_date_str = f"{st.session_state['cal_year']}-{st.session_state['cal_month']:02d}-{day:02d}"
                
                # Check for tasks
                has_task = any(t.get('Date') == this_date_str for t in st.session_state['timetable_slots'])
                
                # Button Label (Just number for clean grid)
                label = f"{day}"
                if has_task: label += " •"
                
                # Style selected
                type_btn = "primary" if st.session_state['sel_date'] == this_date_str else "secondary"
                
                if cols[i].button(label, key=f"day_{this_date_str}", type=type_btn):
                    st.session_state['sel_date'] = this_date_str
                    st.rerun()

    # 4. TASK MANAGER (Below Grid)
    st.markdown("---")
    selected = st.session_state['sel_date']
    
    # Show formatted date (e.g., "Monday, 14 January")
    dt_obj = datetime.datetime.strptime(selected, "%Y-%m-%d")
    pretty_date = dt_obj.strftime("%A, %d %B")
    
    st.markdown(f"### 🎯 Missions: {pretty_date}")
    
    c_view, c_add = st.columns([3, 2])
    
    with c_view:
        day_tasks = [t for t in st.session_state['timetable_slots'] if t.get('Date') == selected]
        if day_tasks:
            for idx, t in enumerate(day_tasks):
                status = "✅" if t['Done'] else "⬜"
                st.info(f"{status} **{t['Time']}**: {t['Activity']} ({t['Category']})")
        else:
            st.caption("No missions scheduled for this day.")

    with c_add:
        with st.form("quick_cal_add", clear_on_submit=True):
            st.caption("Add New Task")
            new_task = st.text_input("Task", placeholder="Mission Name")
            new_time = st.time_input("Time")
            new_cat = st.selectbox("Type", ["Study", "Work", "Health"])
            
            if st.form_submit_button("➕ Add"):
                st.session_state['timetable_slots'].append({
                    "Date": selected,
                    "Time": new_time.strftime("%H:%M"),
                    "Activity": new_task,
                    "Category": new_cat,
                    "Difficulty": "Medium", "Done": False, "XP": 50
                })
                sync_data()
                st.rerun()

# --- 8. PAGE: AI ASSISTANT ---

def page_ai_assistant():
    # --- 1. SETUP & HELPER FUNCTION ---
    # We define this inside so both the Input Bar and Buttons can use it
    def process_new_message(user_text):
        # A. Initialize Session if New
        if not st.session_state.get('current_session_id'):
            new_id = str(uuid.uuid4())
            st.session_state['current_session_id'] = new_id
            # Auto-name: First 4 words
            short_name = " ".join(user_text.split()[:4])
            st.session_state['current_session_name'] = short_name
        
        # B. Save User Message
        st.session_state['chat_history'].append({"role": "user", "text": user_text})
        save_chat_to_cloud("user", user_text) 
        
        # C. Generate Response (with Spinner in the right place)
        # We need a placeholder because we are inside a function
        with st.chat_message("assistant", avatar="1000592991.png"):
             with st.spinner("Analyzing Strategy..."):
                 res_text, _ = perform_auto_search(user_text)
                 
                 # Check for JSON schedule
                 json_match = re.search(r'\[\s*\{.*?\}\s*\]', res_text, re.DOTALL)
                 if json_match:
                     try:
                         json_str = json_match.group(0)
                         new_slots = json.loads(json_str)
                         for slot in new_slots:
                             st.session_state['timetable_slots'].append({
                                 "Time": slot.get("Time", "00:00"), "Activity": slot.get("Activity", "Mission"),
                                 "Category": slot.get("Category", "Study"), "Done": False, "XP": 50, "Difficulty": "Medium"
                             })
                         res_text = "✅ **Protocol Established.** Timetable added to Scheduler."
                         sync_data() 
                     except: pass
                 st.write(res_text)
        
        # D. Save AI Response
        st.session_state['chat_history'].append({"role": "assistant", "text": res_text})
        save_chat_to_cloud("assistant", res_text) 
        st.rerun()

    # --- 2. HEADER UI ---
    c_head, c_btn = st.columns([4, 1], gap="small", vertical_alignment="center")
    with c_head:
        st.markdown(f'<div class="big-title">Tactical Support 🤖</div>', unsafe_allow_html=True)
        st.caption(f"Session: {st.session_state.get('current_session_name', 'New Chat')}")
        
    with c_btn:
        with st.popover("⚙️ Options", use_container_width=True):
            new_name = st.text_input("Rename", value=st.session_state.get('current_session_name', ''))
            if st.button("Save Name"):
                if st.session_state.get('current_session_id'):
                    rename_chat_session(st.session_state['current_session_id'], new_name)
                    st.session_state['current_session_name'] = new_name
                    st.rerun()
            if st.button("🗑️ Delete", type="primary"):
                if st.session_state.get('current_session_id'):
                    delete_chat_session(st.session_state['current_session_id'])
                    st.session_state['current_session_id'] = None
                    st.session_state['chat_history'] = []
                    st.rerun()

    # --- 3. WELCOME SCREEN (If History is Empty) ---
    if not st.session_state['chat_history']:
        # Dynamic Greetings List
        greetings = [
            "Where should we start?",
            "What is the mission?",
            "Ready to optimize?",
            "Awaiting instructions.",
            "Let's hunt some goals."
        ]
        user_first_name = st.session_state['user_name'].split()[0]
        random_greet = random.choice(greetings)
        
        # Gemini-Style Welcome UI
        st.markdown(f"""
        <style>
            .welcome-text {{
                font-size: 40px;
                font-weight: 600;
                background: -webkit-linear-gradient(45deg, #B5FF5F, #00E5FF);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-top: 20px;
            }}
            .sub-text {{
                font-size: 40px;
                font-weight: 600;
                color: #ccc; 
                margin-bottom: 40px;
            }}
        </style>
        <div>
            <div class="welcome-text">Hi, {user_first_name}</div>
            <div class="sub-text">{random_greet}</div>
        </div>
        """, unsafe_allow_html=True)

        # Suggestion Chips (Buttons)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if st.button("📅 Plan Day", use_container_width=True):
                process_new_message("Create a strict hourly schedule for me today.")
        with c2:
            if st.button("🧠 Learn", use_container_width=True):
                process_new_message("Explain a complex topic simply.")
        with c3:
            if st.button("🔥 Motivate", use_container_width=True):
                process_new_message("I am tired. Give me elite motivation.")
        with c4:
            if st.button("📝 Study Tips", use_container_width=True):
                process_new_message("Give me the best scientific study techniques.")

    # --- 4. CHAT HISTORY DISPLAY ---
    else:
        for msg in st.session_state['chat_history']:
            role = msg.get('role') or msg.get('Role')
            text = msg.get('text') or msg.get('Content')
            
            if role == "model" or role == "assistant":
                with st.chat_message("assistant", avatar="1000592991.png"):
                    st.write(text)
            else:
                user_av = st.session_state.get('user_avatar', "👤")
                full_path = os.path.join(current_dir, str(user_av))
                avatar_to_use = full_path if str(user_av).endswith(('.png', '.jpg')) and os.path.exists(full_path) else "👤"
                with st.chat_message("user", avatar=avatar_to_use):
                    st.write(text)

    # --- 5. CHAT INPUT BAR ---
    if prompt := st.chat_input("Input command parameters..."):
        process_new_message(prompt)

# --- 9. CUSTOM UI STYLING (SIDEBAR & MAIN THEME) ---

def inject_custom_css():
    # 1. Load User Preferences
    theme_color = st.session_state.get('theme_color', 'Venom Green (Default)')
    theme_mode = st.session_state.get('theme_mode', 'Light') 
    
    # 2. Define Accent Colors
    colors = {
        "Venom Green (Default)": "#B5FF5F",
        "Cyber Blue": "#00E5FF",
        "Crimson Alert": "#FF2A2A",
        "Stealth Grey": "#A0A0A0"
    }
    accent = colors.get(theme_color, "#B5FF5F")
    
    # 3. Define Visual Protocols
    if theme_mode == "Light":
        main_bg = "linear-gradient(180deg, #FFF6E5 0%, #FFFFFF 40%, #Eef2ff 100%)"
        sidebar_bg = "linear-gradient(180deg, #FDF3E6 0%, #FFFFFF 100%)"
        card_bg = "#FFFFFF"
        text_color = "#1A1A1A"
        sub_text = "#444444"
        border_color = "rgba(0,0,0,0.05)"
        shadow = "0 10px 40px -10px rgba(0,0,0,0.08)"
        input_bg = "#FFFFFF"
        nav_active_bg = accent
        nav_active_text = "#000000"
    else:
        main_bg = "linear-gradient(180deg, #0E1117 0%, #151922 100%)"
        sidebar_bg = "#0E1117"
        card_bg = "#1E232F"
        text_color = "#FAFAFA"
        sub_text = "#A0A0A0"
        border_color = "rgba(255,255,255,0.1)"
        shadow = "0 4px 20px rgba(0,0,0,0.3)"
        input_bg = "#262730"
        nav_active_bg = accent
        nav_active_text = "#000000"

    # 4. INJECT CSS
    st.markdown(f"""
        <style>
            /* --- VARIABLES --- */
            :root {{
                --accent: {accent};
                --text: {text_color};
                --card-bg: {card_bg};
            }}
            
            /* --- BACKGROUNDS --- */
            .stApp {{
                background: {main_bg} !important;
                color: {text_color} !important;
            }}
            section[data-testid="stSidebar"] {{
                background: {sidebar_bg} !important;
                border-right: 1px solid {border_color};
            }}
            
            /* --- TYPOGRAPHY --- */
            h1 {{
                font-size: 42px !important;
                font-weight: 800 !important;
                color: {text_color} !important;
                margin-bottom: 10px !important;
            }}
            h2, h3 {{
                font-weight: 700 !important;
                color: {text_color} !important;
            }}
            .big-title {{
                font-size: 48px !important; 
                font-weight: 900 !important; 
                color: {text_color} !important; 
                margin-bottom: 5px;
            }}
            .sub-title {{
                font-size: 20px !important; 
                color: {sub_text} !important; 
                font-weight: 500;
                margin-bottom: 30px;
            }}
            p, label, .caption, .card-sub {{
                color: {sub_text} !important;
            }}
            
            /* --- CARDS --- */
            .css-card {{
                background-color: {card_bg};
                border-radius: 24px;
                padding: 30px;
                margin-bottom: 20px;
                box-shadow: {shadow};
                border: 1px solid {border_color};
                transition: transform 0.2s;
            }}
            .css-card:hover {{
                transform: translateY(-3px);
            }}
            
            .card-title {{
                font-size: 22px; 
                font-weight: 700; 
                color: {text_color} !important;
                margin-bottom: 10px;
            }}
            
            /* --- STAT NUMBERS --- */
            .stat-num {{
                font-size: 36px;
                font-weight: 800;
                color: {text_color} !important;
            }}
            
            /* --- INPUT FIELDS --- */
            .stTextInput input, .stSelectbox div[data-baseweb="select"] > div, .stTextArea textarea {{
                background-color: {input_bg} !important;
                color: {text_color} !important;
                border: 1px solid {border_color} !important;
                border-radius: 12px;
                padding: 10px;
            }}
            
            /* --- BUTTONS --- */
            .stButton button {{
                background-color: {card_bg};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 30px;
                font-weight: 600;
                padding: 0.5rem 1rem;
                box-shadow: 0 4px 10px rgba(0,0,0,0.05);
            }}
            .stButton button:hover {{
                border-color: {accent};
                color: {accent} !important;
                transform: translateY(-2px);
            }}
            
            /* --- NAVIGATION --- */
            .nav-link-selected {{
                background-color: {nav_active_bg} !important;
                color: {nav_active_text} !important;
                font-weight: bold;
                border-radius: 10px;
            }}
            
            /* --- BLACK CARD OVERRIDE --- */
            .black-card {{
                background-color: #1A1A1A !important; 
                color: white !important; 
                border-radius: 32px; 
                padding: 24px;
                border: 1px solid #333;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }}
            .black-card * {{ color: white !important; }}

            /* --- MOBILE CALENDAR GRID FIX (CRITICAL) --- */
            /* This forces the 7 calendar columns to stay side-by-side on mobile */
            [data-testid="column"] {{
                width: calc(14.2% - 10px) !important;
                flex: 1 1 calc(14.2% - 10px) !important;
                min-width: 0 !important;
            }}
            
            /* Reset width for bigger columns (like main layout) so they don't break */
            .stMain [data-testid="column"]:has(div.big-title),
            .stMain [data-testid="column"]:has(div.css-card) {{
                width: 100% !important;
                flex: 1 1 100% !important;
            }}
        </style>
    """, unsafe_allow_html=True)


# --- 10. MAIN ROUTER ---

def create_mission_report(user_name, level, xp, history):
    pdf = FPDF()
    pdf.add_page()
    
    # 1. Header (Tactical Style)
    pdf.set_font("Courier", "B", 24)
    pdf.cell(0, 10, "TIMEHUNT // MISSION REPORT", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Courier", "", 12)
    pdf.cell(0, 10, f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align='C')
    pdf.line(10, 30, 200, 30) # Horizontal line
    pdf.ln(20)
    
    # 2. Agent Profile
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"AGENT: {user_name}", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 10, f"Current Rank: Level {level}", ln=True)
    pdf.cell(0, 10, f"Total Experience: {xp} XP", ln=True)
    pdf.ln(10)
    
    # 3. Performance History
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "MISSION LOG (Last 7 Entries)", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Courier", "", 10)
    # Table Header
    pdf.cell(40, 10, "DATE", 1)
    pdf.cell(40, 10, "XP GAINED", 1)
    pdf.ln()
    
    # Table Rows (Last 7 entries)
    if history:
        for entry in history[-7:]:
            date = entry.get('Date', 'Unknown')
            gain = str(entry.get('XP', 0))
            pdf.cell(40, 10, date, 1)
            pdf.cell(40, 10, f"+{gain} XP", 1)
            pdf.ln()
    else:
        pdf.cell(0, 10, "No mission data recorded yet.", ln=True)
        
    pdf.ln(20)
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, "End of Report. Stay Sharp.", align='C')
    
    # Return PDF as bytes
    return pdf.output(dest='S').encode('latin-1')

# --- 10. MAIN ROUTER ---
def page_home():
    # --- TIMEZONE FIX: CALCULATE IST (UTC + 5:30) ---
    ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    current_hour = ist_now.hour
    
    # Dynamic Greeting Logic based on IST
    if 5 <= current_hour < 12:
        greeting = "Good Morning"
    elif 12 <= current_hour < 17:
        greeting = "Good Afternoon"
    elif 17 <= current_hour < 22:
        greeting = "Good Evening"
    else:
        greeting = "Success doesn't come, until you cover it up"

    # Quotes
    quotes = ["Be Productive Today 🙌", "Hunt Down Your Goals 🏹", "Focus. Execute. Win. 🏆", "Discipline equals Freedom ⚔️"]
    random_sub = random.choice(quotes)

    # Render Header
    st.markdown(f'<div class="big-title">{greeting}, {st.session_state["user_name"]}!</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title">{random_sub}</div>', unsafe_allow_html=True)

    with st.expander("🖊️ Update Dashboard Status"):
        new_obj = st.text_input("Current Objective", value=st.session_state.get('current_objective', 'Clear Backlog'))
        if st.button("Update"):
            st.session_state['current_objective'] = new_obj
            st.rerun()

    col1, col2 = st.columns([2, 1])

    with col1:
        # XP CARD
        st.markdown(f"""
        <div class="css-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="card-title">Current Objective</span>
                <span style="background:rgba(181, 255, 95, 0.2); padding:5px 10px; border-radius:15px; font-size:12px; color:var(--text);">Protocol Active</span>
            </div>
            <br>
            <div class="card-sub" style="font-size:18px; margin-bottom:15px;">{st.session_state.get('current_objective', 'Clear Backlog')}</div>
            <div style="display:flex; justify-content:space-between; margin-top:15px;">
                <div><div class="stat-num">{st.session_state['user_xp']}</div><div class="card-sub">Total XP</div></div>
                <div><div class="stat-num">{st.session_state['user_level']}</div><div class="card-sub">Level</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # BREATHING EXERCISE
        with st.expander("🧘 Tactical Decompression"):
            st.markdown("""
            <style>
                @keyframes breathe {
                    0% { transform: scale(1); opacity: 0.5; box-shadow: 0 0 5px var(--accent); }
                    50% { transform: scale(1.6); opacity: 1; box-shadow: 0 0 25px var(--accent); }
                    100% { transform: scale(1); opacity: 0.5; box-shadow: 0 0 5px var(--accent); }
                }
                .breath-container { display: flex; flex-direction: column; align-items: center; padding: 20px; }
                .breath-circle {
                    width: 60px; height: 60px; border-radius: 50%;
                    background: radial-gradient(circle, var(--accent) 0%, transparent 70%);
                    border: 2px solid var(--accent); animation: breathe 5s infinite ease-in-out;
                    margin-bottom: 15px;
                }
                .breath-text { font-family: monospace; color: var(--text); opacity: 0.8; letter-spacing: 2px; }
            </style>
            <div class="breath-container">
                <div class="breath-circle"></div>
                <div class="breath-text">INHALE ... HOLD ... EXHALE</div>
            </div>
            """, unsafe_allow_html=True)

    with col2:
        # DAILY FOCUS CARD
        st.markdown(f"""
        <div class="css-card" style="background-color: var(--accent) !important;">
            <div class="card-title" style="color:#000 !important;">Daily Focus</div>
            <div style="color:#000; opacity:0.8;">No active missions</div>
        </div>
        """, unsafe_allow_html=True)

        # NEXT TASK CARD
        next_task = st.session_state['reminders'][-1]['task'] if st.session_state['reminders'] else "No alerts"
        # We also format the date using IST
        date_str = ist_now.strftime("%b %d")
        
        st.markdown(f"""
        <div class="black-card">
            <div style="font-weight:bold; margin-bottom:10px; font-size:18px;">Scheduled</div>
            <div style="background:#333; padding:10px; border-radius:10px; text-align:center; margin-bottom:15px;">
                <div style="font-size:20px; font-weight:bold;">{date_str}</div>
            </div>
            <div style="color:#aaa; font-size:12px;">NEXT REMINDER:</div>
            <div style="color:white; font-size:14px;">{next_task}</div>
        </div>
        """, unsafe_allow_html=True)

# --- 11. PAGE: ABOUT (REDESIGNED "BEST IN CLASS") ---
def page_about():
    # 1. Main Title
    st.markdown("# 🛡️ System Architecture")
    st.markdown("### TimeHunt AI: Tactical Productivity Suite")
    
    # 2. CAPSTONE DOSSIER (Replaces the Black Box)
    # We use a native container with a border. It looks clean and works on all phones.
    with st.container(border=True):
        c_icon, c_info = st.columns([1, 5])
        
        with c_icon:
            st.markdown("<div style='font-size: 45px; text-align: center; padding-top: 10px;'>🎓</div>", unsafe_allow_html=True)
        
        with c_info:
            st.markdown("### CBSE Capstone Project")
            st.markdown("**Class 12  |  Artificial Intelligence  |  2025-26**")
            st.caption("Demonstrating advanced proficiency in Python, Generative AI (LLMs), Cloud Database Management, and Full-Stack State Logic.")

    st.write("") # Spacer

    # 3. FEATURES GRID (Clean & Colorful)
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

    # 4. TECH STACK (Professional Badges)
    st.markdown("### 🏗️ Technical Stack")
    
    # Custom HTML for nice pills/badges
    st.markdown("""
    <div style="display: flex; flex-wrap: wrap; gap: 10px;">
        <span style="background-color: #FF4B4B; color: white; padding: 5px 12px; border-radius: 20px; font-size: 14px; font-weight: bold;">Streamlit</span>
        <span style="background-color: #306998; color: white; padding: 5px 12px; border-radius: 20px; font-size: 14px; font-weight: bold;">Python 3.9+</span>
        <span style="background-color: #4285F4; color: white; padding: 5px 12px; border-radius: 20px; font-size: 14px; font-weight: bold;">Google Gemini</span>
        <span style="background-color: #0F9D58; color: white; padding: 5px 12px; border-radius: 20px; font-size: 14px; font-weight: bold;">Google Sheets API</span>
        <span style="background-color: #F4B400; color: white; padding: 5px 12px; border-radius: 20px; font-size: 14px; font-weight: bold;">Pandas</span>
    </div>
    """, unsafe_allow_html=True)

    st.write("")
    st.write("")
    st.caption("🔒 System Status: ONLINE | 🛡️ Developed with ❤️ by TIME HUNT AI TEAM")



    
# ------ SETTINGS PAGE --------

def page_settings():
    st.markdown("## ⚙️ Command Center")
    
    # --- 1. VISUAL INTERFACE ---
    st.markdown("### 🎨 Visual Interface")
    c_mode, c_color = st.columns(2)
    with c_mode:
        current_mode = st.session_state.get('theme_mode', 'Dark')
        mode_choice = st.radio("System Mode", ["Dark", "Light"], horizontal=True, index=0 if current_mode=='Dark' else 1)
    with c_color:
        current_theme = st.session_state.get('theme_color', 'Venom Green (Default)')
        color_options = ["Venom Green (Default)", "Cyber Blue", "Crimson Alert", "Stealth Grey"]
        idx_theme = color_options.index(current_theme) if current_theme in color_options else 0
        theme_choice = st.selectbox("HUD Accent Color", color_options, index=idx_theme)

    if st.button("Apply Visual Settings", use_container_width=True):
        st.session_state['theme_mode'] = mode_choice
        st.session_state['theme_color'] = theme_choice
        st.rerun() 

    st.markdown("---")

    # --- 2. SYSTEM PERMISSIONS (THE FINAL FIX) ---
    st.markdown("### 🔔 System Access")
    st.info("Authorize this browser to receive mission alerts.")
    
    # WE USE components.html TO FORCE JAVASCRIPT EXECUTION
    components.html("""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        .btn {
            background: #1A1A1A; 
            color: #B5FF5F; 
            border: 1px solid #B5FF5F; 
            padding: 15px 30px; 
            border-radius: 8px; 
            cursor: pointer; 
            font-family: 'Courier New', monospace; 
            font-weight: bold;
            font-size: 16px;
            width: 100%;
            transition: 0.3s;
        }
        .btn:hover {
            background: #B5FF5F;
            color: black;
        }
    </style>
    </head>
    <body>
    
    <button class="btn" onclick="requestPerm()">🔓 CLICK TO AUTHORIZE ALERTS</button>

    <script>
    function requestPerm() {
        if (!("Notification" in window)) {
            alert("This browser does not support desktop notifications");
        } else {
            Notification.requestPermission().then(function (permission) {
                if (permission === "granted") {
                    new Notification("TimeHunt Protocol", {
                        body: "Communications Link Established. Notifications Active.",
                        icon: "https://cdn-icons-png.flaticon.com/512/2921/2921226.png"
                    });
                } else {
                    alert("Permission denied. Please click the 'Lock' icon in your URL bar to reset permissions.");
                }
            });
        }
    }
    </script>
    </body>
    </html>
    """, height=100)

    st.markdown("---")
    
    # --- 3. PROFILE SETTINGS ---
    st.markdown("### 👤 Identity Protocol")
    new_name = st.text_input("Update Codename", st.session_state.get('user_name', ''))
    if st.button("Save Name"):
        st.session_state['user_name'] = new_name
        sync_data()
        st.toast("Identity Updated.")

    st.markdown("---")

    # --- 4. DANGER ZONE ---
    st.markdown("### ☠️ Danger Zone")
    with st.expander("Show Advanced Reset Options"):
        st.warning("This action cannot be undone.")
        if st.button("🔥 Factory Reset (Delete All Data)", type="primary"):
            st.session_state.clear()
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
            st.rerun()

# --- MAIN APP FUNCTION ---
# --- MAIN CONTROLLER ---
def main():
    initialize_session_state()
    alarm_container = st.container()
    check_reminders()
    with alarm_container: render_alarm_ui()
    inject_custom_css()
    show_comet_splash()

    if not st.session_state['onboarding_complete']:
        page_onboarding()
        return 

    # --- LOGIC SWITCH: WHICH SIDEBAR TO SHOW? ---
    
    # 1. CHAT MODE SIDEBAR
    if st.session_state.get('page_mode') == 'chat':
        with st.sidebar:
            st.markdown("### 💬 Chat History")
            if st.button("🏠 Back to Main Menu", type="primary", use_container_width=True):
                st.session_state['page_mode'] = 'main'
                st.rerun()
            
            st.divider()
            
            if st.button("➕ New Chat", use_container_width=True):
                st.session_state['current_session_id'] = None
                st.session_state['current_session_name'] = "New Chat"
                st.session_state['chat_history'] = []
                st.rerun()
            
            st.markdown("---")
            sessions = load_chat_sessions()
            for s in sessions:
                if st.button(f"📄 {s['SessionName']}", key=s['SessionID'], use_container_width=True):
                    st.session_state['current_session_id'] = s['SessionID']
                    st.session_state['current_session_name'] = s['SessionName']
                    msgs = load_messages_for_session(s['SessionID'])
                    formatted_msgs = []
                    for m in msgs:
                        formatted_msgs.append({"role": m["Role"], "text": m["Content"]})
                    st.session_state['chat_history'] = formatted_msgs
                    st.rerun()
        
        page_ai_assistant()

    # 2. MAIN MENU SIDEBAR (Default)
    else:
        with st.sidebar:
            st.markdown("<h1 style='text-align: center;'>🏹<br>TimeHunt</h1>", unsafe_allow_html=True)
            render_live_clock()
            
            # --- RESTORED AUDIO PLAYER ---
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
                    st.caption("⚠️ File not found.")
            
            st.markdown("---")
            
                        # --- UPDATED NAVIGATION ---
            nav = option_menu(
                menu_title=None,
                # ADD "Calendar" HERE 👇
                options=["Home", "Scheduler", "Calendar", "AI Assistant", "Timer", "Dashboard", "About", "Settings"], 
                icons=["house", "list-check", "calendar-week", "robot", "hourglass-split", "graph-up", "info-circle", "gear"], 
                default_index=0
            )

            st.caption(f"🆔 **Agent:** {st.session_state['user_name']}")

        # Router Logic
        if nav == "AI Assistant":
            st.session_state['page_mode'] = 'chat'
            st.rerun()
        elif nav == "Home": page_home()
        elif nav == "Scheduler": page_scheduler()
        elif nav == "Calendar": page_calendar()
        elif nav == "Timer": page_timer()  
        elif nav == "Dashboard": page_dashboard()
        elif nav == "About": page_about()
        elif nav == "Settings": page_settings()

if __name__ == "__main__":
    main()