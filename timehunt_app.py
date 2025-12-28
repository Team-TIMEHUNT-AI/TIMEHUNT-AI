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
from streamlit_mic_recorder import mic_recorder
from gtts import gTTS
import tempfile

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
    # 1. Define Defaults
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    # --- FIX: Removed extra spaces before 'defaults' ---
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

    # 2. Setup Session State
    for key, default_val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_val

    # 3. API Key Setup
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
# --- REPLACEMENT FOR SECTION 5: AI ENGINE ---

def get_system_context():
    """
    Constructs a dynamic 'Brain Dump' of the user's current life state.
    The AI reads this before every single response.
    """
    # 1. User Profile
    user_name = st.session_state.get('user_name', 'Hunter')
    role = st.session_state.get('user_type', 'Agent')
    xp = st.session_state.get('user_xp', 0)
    
    # 2. Time & Date
    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M")
    current_date = now.strftime("%Y-%m-%d")
    
    # 3. The Schedule (The AI "sees" this)
    schedule_txt = "NO ACTIVE MISSIONS."
    slots = st.session_state.get('timetable_slots', [])
    if slots:
        # Filter for today's tasks only
        todays_tasks = [s for s in slots if s.get('Date') == current_date or not s.get('Date')]
        if todays_tasks:
            schedule_txt = "\n".join(
                [f"- [Time: {s['Time']}] {s['Activity']} ({s['Category']}) - {'DONE' if s['Done'] else 'PENDING'}" 
                 for s in todays_tasks]
            )
    
    # 4. Active Alarms/Reminders
    reminders_txt = "NO ACTIVE ALERTS."
    rems = st.session_state.get('reminders', [])
    if rems:
        pending_rems = [r for r in rems if not r['notified']]
        if pending_rems:
            reminders_txt = "\n".join([f"- {r['task']} at {r['time']}" for r in pending_rems])

    # 5. The Master Prompt
    system_prompt = f"""
    IDENTITY: You are TimeHunt AI, a tactical productivity command center.
    USER: {user_name} | RANK: {role} | XP: {xp}
    CURRENT STATUS: Date: {current_date} | Time: {current_time}
    
    === LIVE INTELLIGENCE FEED ===
    [TODAY'S SCHEDULE]
    {schedule_txt}
    
    [PENDING ALARMS]
    {reminders_txt}
    
    === OPERATIONAL PROTOCOLS ===
    1. BE CONTEXT AWARE: If the user asks "What should I do?", look at the [TODAY'S SCHEDULE] above and tell them specifically based on the current time ({current_time}).
    2. TONE: Use "Military/Tactical" style but be supportive. Use words like "Mission", "Deploy", "Intel", "Sector".
    3. STRICT DEADLINES: If a task is pending and time is close, warn them aggressively.
    """
    return system_prompt

def perform_ai_analysis(user_query):
    """
    Advanced AI Engine:
    1. Loads ALL API keys from secrets (Rotational System).
    2. Tries multiple models (Prioritizing 2.0, falling back to 1.5).
    3. If Key #1 hits a limit, it auto-switches to Key #2.
    """
    # 1. Setup Library
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "⚠️ SYSTEM FAILURE: `google-genai` library not installed.", "System"

    # 2. Load ALL API Keys (The "List" you mentioned)
    api_keys_list = []
    
    # Check GEMINI_API_KEY
    if "GEMINI_API_KEY" in st.secrets:
        raw = st.secrets["GEMINI_API_KEY"]
        # If it's a list, use it. If it's a string, wrap it in a list.
        api_keys_list = raw if isinstance(raw, list) else [raw]
    
    # Fallback to GOOGLE_API_KEY
    elif "GOOGLE_API_KEY" in st.secrets:
        raw = st.secrets["GOOGLE_API_KEY"]
        api_keys_list = raw if isinstance(raw, list) else [raw]
    
    if not api_keys_list:
        return "⚠️ AUTH ERROR: No API Keys found in secrets.toml", "System"

    # 3. Define Models (Your preferred list + Stable backup)
    models_to_try = [
        "gemini-2.0-flash",                     # The Smartest/Newest
        "gemini-2.0-flash-lite-preview-02-05", # Fast Preview
        "gemini-1.5-flash"                      # The Reliable Workhorse (Backup)
    ]

    current_system_context = get_system_context()
    
    # 4. The "Rotational" Loop
    last_error = "No connection attempted."

    # Loop through every Key you have
    for key_index, current_key in enumerate(api_keys_list):
        try:
            client = genai.Client(api_key=current_key)
            
            # Loop through every Model
            for model_name in models_to_try:
                try:
                    # Construct History
                    history_for_model = []
                    past_chats = st.session_state.get('chat_history', [])[-6:]
                    for msg in past_chats:
                        role_label = msg.get('role') or msg.get('Role')
                        content_text = msg.get('text') or msg.get('Content')
                        api_role = "user" if role_label == "user" else "model"
                        history_for_model.append(types.Content(role=api_role, parts=[types.Part.from_text(text=str(content_text))]))

                    # Attempt Generation
                    chat = client.chats.create(
                        model=model_name,
                        history=history_for_model,
                        config=types.GenerateContentConfig(
                            system_instruction=current_system_context,
                            temperature=0.7,
                            max_output_tokens=400
                        )
                    )
                    response = chat.send_message(user_query)
                    
                    # If successful, return immediately!
                    return response.text, "TimeHunt AI"

                except Exception as model_err:
                    # If it's a Rate Limit error, log it and try next model/key
                    error_msg = str(model_err)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        print(f"⚠️ Key #{key_index+1} / {model_name} exhausted. Switching...")
                        last_error = f"Rate Limit on Key #{key_index+1}"
                        continue # Try next model
                    else:
                        # If it's a real error (like bad request), keep track but keep trying
                        last_error = f"Error: {error_msg}"
                        continue 

        except Exception as key_err:
            print(f"❌ Key #{key_index+1} Invalid: {key_err}")
            continue

    # 5. Total Failure (If all Keys and Models failed)
    return f"⚠️ SYSTEM OVERLOAD: All {len(api_keys_list)} API Keys are currently exhausted. Please wait 30s. ({last_error})", "System"
    
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
    # --- 1. SETUP & XP LOGIC ---
    def calculate_streak_multiplier(streak_days):
        if streak_days >= 30: return 2.5  # TITAN
        elif streak_days >= 14: return 2.0  # ELITE
        elif streak_days >= 7: return 1.5   # VETERAN
        elif streak_days >= 3: return 1.2   # ROOKIE
        return 1.0

    # Ensure data integrity
    if 'timetable_slots' in st.session_state:
        for slot in st.session_state['timetable_slots']:
            if 'Done' not in slot: slot['Done'] = False
            if 'XP' not in slot: slot['XP'] = 50
            if 'Difficulty' not in slot: slot['Difficulty'] = 'Medium'

    # --- 2. HEADER & STATS ---
    st.markdown('<div class="big-title">Mission Control ⚙️</div>', unsafe_allow_html=True)
    
    # Calculate Stats
    total_missions = len(st.session_state['timetable_slots'])
    completed_missions = len([t for t in st.session_state['timetable_slots'] if t['Done']])
    pending_missions = total_missions - completed_missions
    progress = completed_missions / total_missions if total_missions > 0 else 0
    
    streak = st.session_state.get('streak', 1)
    multiplier = calculate_streak_multiplier(streak)
    
    # Visual Header with Progress
    c_stats, c_add = st.columns([2, 1])
    
    with c_stats:
        st.markdown(f"""
        <div style="background: rgba(255,255,255,0.05); border-radius: 15px; padding: 20px; border: 1px solid rgba(255,255,255,0.1);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="font-size:18px; font-weight:bold; color:#B5FF5F;">Daily Progress</span>
                <span style="font-size:14px; color:#aaa;">{int(progress*100)}% Clear</span>
            </div>
            <div style="width:100%; background:#333; height:8px; border-radius:4px; overflow:hidden;">
                <div style="width:{progress*100}%; background: linear-gradient(90deg, #B5FF5F, #00E5FF); height:100%;"></div>
            </div>
            <div style="margin-top:15px; font-size:14px; color:#ccc;">
                🔥 <b>Streak:</b> {streak} Days <span style="color:#00E5FF; margin-left:10px;">(x{multiplier} Multiplier Active)</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c_add:
        # Mini Card for Quick Status
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1A1A1A, #252525); border-radius: 15px; padding: 20px; text-align:center; border: 1px solid #333;">
            <div style="font-size: 32px; font-weight:bold; color:white;">{pending_missions}</div>
            <div style="font-size: 12px; color:#888; text-transform:uppercase; letter-spacing:1px;">Pending Missions</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("") # Spacer

    # --- 3. MISSION DEPLOYMENT INTERFACE ---
    with st.expander("🚁 DEPLOY NEW MISSION", expanded=True):
        with st.form("mission_form", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 1.5, 1.5])
            with c1:
                task_input = st.text_input("Objective", placeholder="Enter mission details...")
            with c2:
                cat_input = st.selectbox("Sector", ["Study", "Project", "Health", "Errand", "Drill"])
            with c3:
                # Updated Difficulty Logic
                diff_input = st.selectbox("Class", ["Easy (20 XP)", "Medium (50 XP)", "Hard (150 XP)", "BOSS (300 XP)"])
            
            c_sub, c_clear = st.columns([1, 4])
            with c_sub:
                submitted = st.form_submit_button("Deploy ➔", type="primary", use_container_width=True)
            
            if submitted and task_input:
                # Map Selection to XP
                xp_map = {"Easy (20 XP)": 20, "Medium (50 XP)": 50, "Hard (150 XP)": 150, "BOSS (300 XP)": 300}
                clean_diff = diff_input.split(" ")[0] # Extracts "Easy", "Hard" etc.
                
                # Timezone Fix
                ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
                
                new_mission = {
                    "Time": ist_now.strftime("%H:%M"),
                    "Activity": task_input,
                    "Category": cat_input,
                    "Difficulty": clean_diff,
                    "Done": False,
                    "XP": xp_map.get(diff_input, 50),
                    "Date": ist_now.strftime("%Y-%m-%d")
                }
                
                st.session_state['timetable_slots'].append(new_mission)
                sync_data()
                st.rerun()

    st.divider()

    # --- 4. ACTIVE MISSIONS (CUSTOM CARD UI) ---
    st.markdown("### 📋 Active Protocols")
    
    if not st.session_state['timetable_slots']:
        st.info("System Idle. No active protocols found.")
    else:
        # Separate Pending and Done for cleaner UI
        pending = [t for t in st.session_state['timetable_slots'] if not t['Done']]
        done_list = [t for t in st.session_state['timetable_slots'] if t['Done']]

        # A. RENDER PENDING MISSIONS
        if pending:
            for i, mission in enumerate(st.session_state['timetable_slots']):
                if not mission['Done']:
                    # Difficulty Color Coding
                    d_color = "#B5FF5F" # Easy/Green
                    if mission['Difficulty'] == "Medium": d_color = "#FFD700" # Gold
                    elif mission['Difficulty'] == "Hard": d_color = "#FF4B4B" # Red
                    elif mission['Difficulty'] == "BOSS": d_color = "#9D00FF" # Purple
                    
                    # Custom Card Container
                    with st.container():
                        # Create a layout: Checkbox | Details | XP Badge
                        c_chk, c_det, c_xp = st.columns([1, 6, 2], vertical_alignment="center")
                        
                        with c_chk:
                            # The actual interactive element
                            if st.button("⬜", key=f"btn_done_{i}", help="Mark Complete"):
                                st.session_state['timetable_slots'][i]['Done'] = True
                                sync_data()
                                st.rerun()
                        
                        with c_det:
                            st.markdown(f"""
                            <div style="font-weight:600; font-size:16px;">{mission['Activity']}</div>
                            <div style="font-size:12px; color:#888;">
                                <span style="color:{d_color}; font-weight:bold;">● {mission['Difficulty']}</span> 
                                | {mission['Category']} | 🕒 {mission['Time']}
                            </div>
                            """, unsafe_allow_html=True)
                            
                        with c_xp:
                            st.markdown(f"""
                            <div style="background:{d_color}20; color:{d_color}; border:1px solid {d_color}; 
                            border-radius:8px; padding:5px 10px; text-align:center; font-weight:bold; font-size:12px;">
                            +{mission['XP']} XP
                            </div>
                            """, unsafe_allow_html=True)
                        
                        st.markdown("<hr style='margin:5px 0; border:0; border-top:1px solid #333;'>", unsafe_allow_html=True)

        else:
            st.caption("All systems clear. Good job, Hunter.")

        # B. RENDER COMPLETED SECTION (Collapsible)
        if done_list:
            with st.expander(f"✅ Completed Missions ({len(done_list)})"):
                for t in done_list:
                     st.markdown(f"~~{t['Activity']}~~ <span style='color:#666; font-size:12px;'>({t['XP']} XP)</span>", unsafe_allow_html=True)
                
                # CLAIM REWARDS BUTTON
                if st.button("🎁 CLAIM REWARDS & ARCHIVE", type="primary", use_container_width=True):
                    # Calculate Total XP Gain
                    raw_xp = sum([t['XP'] for t in done_list])
                    final_xp = int(raw_xp * multiplier)
                    
                    # Update Session
                    st.session_state['user_xp'] += final_xp
                    st.session_state['user_level'] = (st.session_state['user_xp'] // 1000) + 1
                    
                    # Archive (Remove from active list)
                    st.session_state['timetable_slots'] = [t for t in st.session_state['timetable_slots'] if not t['Done']]
                    
                    # Log History
                    today_str = datetime.date.today().strftime("%Y-%m-%d")
                    st.session_state['xp_history'].append({"Date": today_str, "XP": final_xp})
                    
                    sync_data()
                    
                    # Celebration
                    st.balloons()
                    msg = f"**MISSION SUCCESS!**\n\nBase XP: {raw_xp}\nStreak Bonus: x{multiplier}\n**TOTAL GAIN: +{final_xp} XP**"
                    st.toast(msg, icon="🚀")
                    time.sleep(2)
                    st.rerun()

    # Reset Option (Subtle)
    st.write("")
    if st.button("🗑️ Clear All Data", help="Deletes all active and completed tasks"):
        st.session_state['timetable_slots'] = []
        sync_data()
        st.rerun()

# --- NEW PAGE: FOCUS TIMER ---
def page_timer():
    # --- 1. SESSION STATE FOR TIMER CONFIG ---
    if 'timer_duration' not in st.session_state: st.session_state['timer_duration'] = 25
    if 'timer_mode' not in st.session_state: st.session_state['timer_mode'] = "Focus"

    st.markdown('<div class="big-title" style="text-align:center;">⏱️ Tactical Chronometer</div>', unsafe_allow_html=True)

    # --- 2. MODE SELECTION (PYTHON SIDE) ---
    c_mode1, c_mode2, c_mode3 = st.columns(3)
    
    # Helper to style buttons based on active state
    def get_type(mode): return "primary" if st.session_state['timer_mode'] == mode else "secondary"

    with c_mode1:
        if st.button("🎯 FOCUS (25m)", type=get_type("Focus"), use_container_width=True):
            st.session_state['timer_duration'] = 25
            st.session_state['timer_mode'] = "Focus"
            st.rerun()
    with c_mode2:
        if st.button("☕ SHORT (5m)", type=get_type("Short"), use_container_width=True):
            st.session_state['timer_duration'] = 5
            st.session_state['timer_mode'] = "Short"
            st.rerun()
    with c_mode3:
        if st.button("🔋 LONG (15m)", type=get_type("Long"), use_container_width=True):
            st.session_state['timer_duration'] = 15
            st.session_state['timer_mode'] = "Long"
            st.rerun()

    # --- 3. TASK DEFINITION ---
    # User types what they are doing. We pass this to the JS notification.
    current_focus = st.text_input("Current Mission Objective", placeholder="What are you hunting?", label_visibility="collapsed")
    if not current_focus: current_focus = "Deep Work Protocol"

    # --- 4. THE ADVANCED TIMER COMPONENT ---
    # We inject the python variable `st.session_state['timer_duration']` into the HTML
    duration_min = st.session_state['timer_duration']
    
    # Colors based on mode
    ring_color = "#B5FF5F" if st.session_state['timer_mode'] == "Focus" else "#00E5FF"
    
    timer_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{ background: transparent; display: flex; flex-direction: column; align-items: center; justify-content: center; font-family: 'Inter', sans-serif; }}
        
        /* The Circular Progress Container */
        .base-timer {{
            position: relative;
            width: 300px;
            height: 300px;
        }}

        .base-timer__svg {{
            transform: scaleX(-1);
        }}

        .base-timer__circle {{
            fill: none;
            stroke: none;
        }}

        .base-timer__path-elapsed {{
            stroke-width: 10px;
            stroke: rgba(255, 255, 255, 0.1);
        }}

        .base-timer__path-remaining {{
            stroke-width: 10px;
            stroke-linecap: round;
            transform: rotate(90deg);
            transform-origin: center;
            transition: 1s linear all;
            fill-rule: nonzero;
            stroke: {ring_color}; 
            filter: drop-shadow(0 0 10px {ring_color});
        }}

        .base-timer__label {{
            position: absolute;
            width: 300px;
            height: 300px;
            top: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 55px;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            color: white;
            text-shadow: 0 0 20px rgba(0,0,0,0.8);
        }}

        /* Buttons */
        .controls {{
            margin-top: 30px;
            display: flex;
            gap: 20px;
        }}
        
        .btn {{
            border: none;
            padding: 12px 30px;
            border-radius: 50px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: 0.2s;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .btn-start {{ background: {ring_color}; color: #000; box-shadow: 0 0 15px {ring_color}40; }}
        .btn-start:hover {{ transform: scale(1.05); box-shadow: 0 0 25px {ring_color}60; }}
        
        .btn-stop {{ background: #333; color: #fff; border: 1px solid #555; }}
        .btn-stop:hover {{ background: #FF2A2A; border-color: #FF2A2A; }}

    </style>
    </head>
    <body>
        
        <div class="base-timer">
            <svg class="base-timer__svg" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <g class="base-timer__circle">
                    <circle class="base-timer__path-elapsed" cx="50" cy="50" r="45"></circle>
                    <path
                        id="base-timer-path-remaining"
                        stroke-dasharray="283"
                        class="base-timer__path-remaining"
                        d="
                          M 50, 50
                          m -45, 0
                          a 45,45 0 1,0 90,0
                          a 45,45 0 1,0 -90,0
                        "
                    ></path>
                </g>
            </svg>
            <span id="base-timer-label" class="base-timer__label">
                {duration_min}:00
            </span>
        </div>

        <div class="controls">
            <button class="btn btn-start" onclick="startTimer()">Initiate</button>
            <button class="btn btn-stop" onclick="resetTimer()">Abort</button>
        </div>

        <script>
            // CONFIGURATION
            const FULL_DASH_ARRAY = 283;
            const TIME_LIMIT = {duration_min} * 60;
            let timePassed = 0;
            let timeLeft = TIME_LIMIT;
            let timerInterval = null;
            const COLOR_CODES = {{ info: {{ color: "green" }} }};

            // NOTIFICATION PERMISSION
            if ("Notification" in window) {{
                Notification.requestPermission();
            }}

            function onTimesUp() {{
                clearInterval(timerInterval);
                timerInterval = null;
                
                // Audio Beep
                const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const oscillator = audioCtx.createOscillator();
                const gainNode = audioCtx.createGain();
                oscillator.connect(gainNode);
                gainNode.connect(audioCtx.destination);
                oscillator.type = "square";
                oscillator.frequency.value = 440; 
                oscillator.start();
                gainNode.gain.exponentialRampToValueAtTime(0.00001, audioCtx.currentTime + 1);
                
                // Browser Notification
                if (Notification.permission === "granted") {{
                    new Notification("TIME HUNT AI", {{
                        body: "Protocol Complete: {current_focus}",
                        icon: "https://cdn-icons-png.flaticon.com/512/2921/2921226.png"
                    }});
                }}
            }}

            function startTimer() {{
                if (timerInterval) return; // Prevent multiple clicks
                
                timerInterval = setInterval(() => {{
                    timePassed = timePassed += 1;
                    timeLeft = TIME_LIMIT - timePassed;
                    
                    document.getElementById("base-timer-label").innerHTML = formatTime(timeLeft);
                    setCircleDasharray();
        
                    if (timeLeft <= 0) {{
                        onTimesUp();
                    }}
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
                if (seconds < 10) {{ seconds = `0${{seconds}}`; }}
                return `${{minutes}}:${{seconds}}`;
            }}

            function calculateTimeFraction() {{
                const rawTimeFraction = timeLeft / TIME_LIMIT;
                return rawTimeFraction - (1 / TIME_LIMIT) * (1 - rawTimeFraction);
            }}

            function setCircleDasharray() {{
                const circleDasharray = `${{(
                    calculateTimeFraction() * FULL_DASH_ARRAY
                ).toFixed(0)}} 283`;
                document
                    .getElementById("base-timer-path-remaining")
                    .setAttribute("stroke-dasharray", circleDasharray);
            }}
        </script>
    </body>
    </html>
    """
    
    # We use a container to center the iframe horizontally
    with st.container():
        components.html(timer_html, height=450)

    # --- 5. REWARD SECTION (GAMIFICATION) ---
    st.markdown("---")
    c_reward, c_info = st.columns([2, 1])
    
    with c_reward:
        st.markdown("### 🎁 Claim Session Rewards")
        st.caption("Upon timer completion, verify your work to claim XP.")
        
        # Reward Logic based on Duration
        possible_xp = 50 if st.session_state['timer_duration'] == 25 else 100 if st.session_state['timer_duration'] == 15 else 10
        
        if st.button(f"Verify & Claim +{possible_xp} XP", use_container_width=True):
            st.session_state['user_xp'] += possible_xp
            # Update Level
            st.session_state['user_level'] = (st.session_state['user_xp'] // 1000) + 1
            
            # Log History
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            st.session_state['xp_history'].append({"Date": today_str, "XP": possible_xp})
            
            sync_data()
            st.balloons()
            st.toast(f"Session Recorded! +{possible_xp} XP", icon="🧠")
            time.sleep(1)
            st.rerun()

    with c_info:
        st.info(f"**Current Mode:** {st.session_state['timer_mode']}\n\nMaintain focus on '{current_focus}'. Do not switch tabs if possible.")

# --- NEW: CALENDAR PAGE ---

def page_calendar():
    # --- 📱 CRITICAL CSS FIX FOR CALENDAR GRID 📱 ---
    # This forces the columns (days) to stay side-by-side on mobile
    st.markdown("""
    <style>
        /* Force all columns on this page to be side-by-side with equal width */
        [data-testid="column"], [data-testid="stColumn"] {
            flex: 1 1 0% !important;
            min-width: 0 !important;
            padding: 0 1px !important; 
        }
        
        /* Make the text centered and smaller so it fits */
        [data-testid="column"] button, [data-testid="stColumn"] button {
            padding: 0px 5px !important;
            min-height: 40px !important; 
            font-size: 12px !important;
        }
        
        /* Fix the header alignment */
        h3 { text-align: center; font-size: 20px !important; margin: 0 !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="big-title">📅 Tactical Grid</div>', unsafe_allow_html=True)

    if 'cal_year' not in st.session_state: st.session_state['cal_year'] = datetime.date.today().year
    if 'cal_month' not in st.session_state: st.session_state['cal_month'] = datetime.date.today().month
    if 'sel_date' not in st.session_state: st.session_state['sel_date'] = datetime.date.today().strftime("%Y-%m-%d")

    # 1. Navigation
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

    # 2. Grid Headers (M T W T F S S)
    # Use a container to slightly separate headers from days
    with st.container():
        cols = st.columns(7)
        days = ["M","T","W","T","F","S","S"]
        for i, d in enumerate(days):
            # We use small font for mobile headers
            cols[i].markdown(f"<div style='text-align:center; font-weight:bold; color:#888; font-size:12px;'>{d}</div>", unsafe_allow_html=True)

    # 3. Grid Days
    month_matrix = calendar.monthcalendar(st.session_state['cal_year'], st.session_state['cal_month'])
    for week in month_matrix:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].write("")
            else:
                d_str = f"{st.session_state['cal_year']}-{st.session_state['cal_month']:02d}-{day:02d}"
                has_task = any(t.get('Date') == d_str for t in st.session_state['timetable_slots'])
                label = f"{day}"
                if has_task: label += " •"
                
                # Highlight selected date
                btn_type = "primary" if st.session_state['sel_date'] == d_str else "secondary"
                
                if cols[i].button(label, key=f"d_{d_str}", type=btn_type, use_container_width=True):
                    st.session_state['sel_date'] = d_str
                    st.rerun()

    # 4. Selected Date Details
    st.markdown("---")
    sel = st.session_state['sel_date']
    st.markdown(f"### 🎯 Missions: {sel}")
    
    # Task List & Add Form - Use tabs or simple stack on mobile
    
    tasks = [t for t in st.session_state['timetable_slots'] if t.get('Date') == sel]
    
    if tasks:
        for t in tasks:
            status = "✅" if t['Done'] else "⭕"
            st.info(f"{status} **{t['Time']}** {t['Activity']}")
    else:
        st.caption("No missions.")

    with st.form("add_cal", clear_on_submit=True):
        st.markdown("**Add New Mission**")
        c_t, c_time = st.columns([3, 2]) # These will also be side-by-side now due to our CSS, which is good
        with c_t:
            task = st.text_input("Task", label_visibility="collapsed", placeholder="Enter Task...")
        with c_time:
            time_at = st.time_input("Time", label_visibility="collapsed")
            
        if st.form_submit_button("Deploy Mission", use_container_width=True):
            st.session_state['timetable_slots'].append({
                "Date": sel, "Time": time_at.strftime("%H:%M"), "Activity": task, "Done":False, "Category":"General", "XP":50
            })
            sync_data()
            st.rerun()

# --- 8. PAGE: AI ASSISTANT ---

def page_ai_assistant():
    # Import the mic recorder library (ensure you pip installed it)
    from streamlit_mic_recorder import mic_recorder
    
    # --- 1. SETUP & HELPER TO SEND MESSAGES ---
    def process_message(prompt_text):
        """Helper to send message, get AI response, and save to history."""
        # A. User Msg
        st.session_state['chat_history'].append({"role": "user", "text": prompt_text})
        
        # B. AI Response (The Brain)
        response_text, _ = perform_ai_analysis(prompt_text)
        
        # C. Save AI Msg
        st.session_state['chat_history'].append({"role": "model", "text": response_text})
        
        # D. TRIGGER VOICE OUTPUT (The "Voice" of the AI)
        # We use a hidden HTML audio element with Google Translate's TTS API (Free & supports Indian langs)
        # This handles Hindi/Tamil/English automatically based on the text script detection roughly, 
        # or defaults to English. 
        
        # Clean text for URL (basic cleanup)
        clean_text = response_text.replace('\n', ' ').replace('#', '').replace('*', '')[:200] # Limit length for TTS
        tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&q={clean_text}&tl=en"
        
        # Determine language (Basic heuristic: if hindi char found -> 'hi', else 'en')
        if any("\u0900" <= char <= "\u097F" for char in response_text): # Hindi Block
            tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&q={clean_text}&tl=hi"
        
        # Auto-play audio
        st.markdown(f"""
            <audio autoplay="true" style="display:none;">
                <source src="{tts_url}" type="audio/mpeg">
            </audio>
        """, unsafe_allow_html=True)
        
        st.rerun()

    # --- 2. HEADER ---
    c_title, c_mic = st.columns([5, 1], vertical_alignment="bottom")
    with c_title:
        st.markdown(f'<div class="big-title">Tactical Support 🤖</div>', unsafe_allow_html=True)
    
    with c_mic:
        # --- NEW: MICROPHONE BUTTON ---
        # Returns a dictionary with audio bytes if recorded
        audio_data = mic_recorder(
            start_prompt="🎤 Speak",
            stop_prompt="⏹️ Stop",
            just_once=True,
            use_container_width=True,
            format="wav",
            key="voice_input"
        )

    # --- 3. VOICE PROCESSING LOGIC ---
    if audio_data:
        # If audio was recorded, we need to transcribe it.
        # Since we want to avoid paid APIs like OpenAI Whisper if possible, 
        # we can rely on the user typing OR use a simple workaround if you have a key.
        # FOR NOW: We will assume you want to use Gemini's multimodal capability to "hear" the audio.
        
        # Convert audio bytes to Gemini-friendly format
        import io
        audio_bytes = audio_data['bytes']
        
        # Send Audio directly to Gemini (It can listen!)
        # Note: This requires the 'perform_ai_analysis' to handle audio, 
        # or we just simulate it here for simplicity.
        
        # 1. Save temp file
        with open("temp_voice.wav", "wb") as f:
            f.write(audio_bytes)
            
        st.toast("Processing Voice Command...", icon="🎧")
        
        # 2. Use Gemini to Transcribe & Reply (Multimodal)
        # We need to tweak the prompt slightly to say "User sent audio".
        # For simplicity in this UI, we will just send a text placeholder 
        # but in a full implementation, you'd pass the audio file to the API.
        
        # *Feature Note:* Real-time browser STT (Speech-to-Text) requires JS. 
        # The 'mic_recorder' saves audio. To keep it simple without heavy STT models,
        # we will use Gemini's audio capability if your API key supports Gemini 1.5 Flash (which handles audio).
        
        # Let's assume text input for now to prevent breaking, 
        # unless you add SpeechRecognition library: `pip install SpeechRecognition`
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.AudioFile("temp_voice.wav") as source:
                audio_data_sr = r.record(source)
                # Supports 'hi-IN' (Hindi), 'ta-IN' (Tamil), etc.
                # We default to auto or English/Hindi mix
                text_input = r.recognize_google(audio_data_sr, language="en-IN") # English (India) catches mixed hints
                process_message(text_input)
        except ImportError:
            st.error("Please install `SpeechRecognition`: pip install SpeechRecognition")
        except Exception as e:
            st.warning(f"Voice unreadable. Try typing. ({e})")

    # --- 4. LOGIC: WELCOME SCREEN vs CHAT HISTORY ---
    
    # IF HISTORY IS EMPTY -> SHOW WELCOME SCREEN (Gemini Style)
    if not st.session_state.get('chat_history'):
        
        # A. Get User Name
        user_name = st.session_state.get('user_name', 'Hunter').split()[0]
        
        # B. Randomize the Greeting Message
        greetings = [
            "Where should we start?",
            "What is the mission?",
            "Ready to optimize?",
            "Awaiting instructions.",
            "Let's hunt some goals.",
            "Systems operational."
        ]
        random_greet = random.choice(greetings)

        # C. CSS for the Welcome Screen
        st.markdown(f"""
        <style>
            .welcome-text {{
                font-family: 'Inter', sans-serif;
                font-size: 45px;
                font-weight: 600;
                background: -webkit-linear-gradient(0deg, #B5FF5F, #00E5FF);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-top: 20px;
                line-height: 1.2;
            }}
            .sub-text {{
                font-family: 'Inter', sans-serif;
                font-size: 45px;
                font-weight: 600;
                color: #555; /* Dark grey for visibility */
                margin-bottom: 40px;
                line-height: 1.2;
            }}
            /* Suggestion Chips */
            div.stButton > button {{
                border-radius: 20px;
                background-color: #f0f2f6;
                color: #31333F;
                border: none;
                padding: 10px 20px;
                font-weight: 500;
                transition: 0.2s;
            }}
            div.stButton > button:hover {{
                background-color: #e0e2e6;
                color: #000;
            }}
        </style>
        
        <div>
            <div class="welcome-text">Hi, {user_name}</div>
            <div class="sub-text">{random_greet}</div>
        </div>
        """, unsafe_allow_html=True)

        # Suggestion Buttons (The "Chips")
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            if st.button("📅 Plan Day", use_container_width=True):
                process_message("Create a strict hourly schedule for me today based on my tasks.")
        with c2:
            if st.button("🧠 Learn", use_container_width=True):
                process_message("Explain a complex topic simply.")
        with c3:
            if st.button("🔥 Motivate", use_container_width=True):
                process_message("I am tired. Give me elite military-style motivation.")
        with c4:
            if st.button("📝 Study Tips", use_container_width=True):
                process_message("Give me the best scientific study techniques.")

    # ELSE -> SHOW CHAT HISTORY
    else:
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state['chat_history']:
                # Determine role for UI
                role = "assistant" if (msg.get('role') == "model" or msg.get('role') == "assistant") else "user"
                content = msg.get('text') or msg.get('Content')
                
                # Render
                with st.chat_message(role):
                    st.write(content)

    # --- 5. CHAT INPUT (ALWAYS VISIBLE) ---
    if prompt := st.chat_input("Input command parameters..."):
        process_message(prompt)


# --- 9. CUSTOM UI STYLING ---
def inject_custom_css():
    # 1. Load User Preferences
    theme_color = st.session_state.get('theme_color', 'Venom Green (Default)')
    theme_mode = st.session_state.get('theme_mode', 'Light') 
    
    # 2. Define Colors
    colors = {"Venom Green (Default)": "#B5FF5F", "Cyber Blue": "#00E5FF", "Crimson Alert": "#FF2A2A", "Stealth Grey": "#A0A0A0"}
    accent = colors.get(theme_color, "#B5FF5F")
    
    # 3. Mode Logic
    if theme_mode == "Light":
        main_bg, sidebar_bg, card_bg, text_color = "linear-gradient(180deg, #FFF6E5 0%, #FFFFFF 100%)", "linear-gradient(180deg, #FDF3E6 0%, #FFFFFF 100%)", "#FFFFFF", "#1A1A1A"
        input_bg = "#FFFFFF"
    else:
        main_bg, sidebar_bg, card_bg, text_color = "linear-gradient(180deg, #0E1117 0%, #151922 100%)", "#0E1117", "#1E232F", "#FAFAFA"
        input_bg = "#262730"

    # 4. INJECT CSS (WITH MOBILE GRID FIX)
    st.markdown(f"""
        <style>
            :root {{ --accent: {accent}; --text: {text_color}; --card-bg: {card_bg}; }}
            .stApp {{ background: {main_bg} !important; color: {text_color} !important; }}
            section[data-testid="stSidebar"] {{ background: {sidebar_bg} !important; }}
            
            /* Typography */
            .big-title {{ font-size: 42px !important; font-weight: 900 !important; color: {text_color} !important; margin-bottom: 5px; }}
            .sub-title {{ font-size: 18px !important; color: {text_color} !important; opacity: 0.8; margin-bottom: 20px; }}
            
            /* Cards & Inputs */
            .css-card {{ background-color: {card_bg}; border-radius: 24px; padding: 25px; margin-bottom: 15px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); }}
            .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {{ background-color: {input_bg} !important; border-radius: 12px; }}
            
            /* Buttons */
            .stButton button {{ border-radius: 20px; font-weight: 600; width: 100%; border: 1px solid rgba(0,0,0,0.1); }}
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
    # --- 1. TIME & GREETING LOGIC ---
    ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    current_hour = ist_now.hour
    
    if 5 <= current_hour < 12: greeting = "Good Morning"
    elif 12 <= current_hour < 17: greeting = "Good Afternoon"
    elif 17 <= current_hour < 22: greeting = "Good Evening"
    else: greeting = "Night Operations"

    # Dynamic Quotes
    quotes = [
        "Discipline is the bridge between goals and accomplishment.", 
        "The only bad workout is the one that didn't happen.", 
        "Focus on the mission, not the noise.", 
        "Your future self is watching you right now."
    ]
    random_sub = random.choice(quotes)

    # --- 2. HEADER SECTION (PREMIUM LOOK) ---
    # Custom CSS for this page only
    st.markdown("""
    <style>
        .hero-container {
            padding: 20px;
            background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.01) 100%);
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 25px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .glass-card {
            background: rgba(20, 20, 20, 0.6);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
            padding: 20px;
            transition: transform 0.2s;
        }
        .glass-card:hover {
            transform: translateY(-2px);
            border-color: var(--accent);
        }
        .progress-bg {
            width: 100%;
            height: 8px;
            background: #333;
            border-radius: 4px;
            margin-top: 10px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent), #00E5FF);
            border-radius: 4px;
        }
    </style>
    """, unsafe_allow_html=True)

    # Hero Banner
    col_hero_text, col_hero_weather = st.columns([3, 1])
    with col_hero_text:
        st.markdown(f'<div class="big-title">{greeting}, {st.session_state["user_name"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="color:#aaa; font-size:16px;">{random_sub}</div>', unsafe_allow_html=True)
    
    with col_hero_weather:
        # Simulated "Tactical Weather"
        st.markdown(f"""
        <div style="text-align:right; color:#888; font-family:monospace;">
            <div style="font-size:24px; color:var(--accent);">24°C</div>
            <div>JAIPUR, IN</div>
            <div>{ist_now.strftime('%H:%M')} IST</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    # --- 3. LEVEL & XP SYSTEM (VISUALIZED) ---
    # Logic: Level 1 clears at 1000 XP.
    current_xp = st.session_state.get('user_xp', 0)
    current_lvl = st.session_state.get('user_level', 1)
    
    # Calculate progress to next level
    xp_for_next_lvl = current_lvl * 1000
    xp_in_current_lvl = current_xp - ((current_lvl - 1) * 1000)
    progress_percent = min(100, max(0, (xp_in_current_lvl / 1000) * 100))
    
    col_level, col_obj = st.columns([2, 1])
    
    with col_level:
        st.markdown(f"""
        <div class="glass-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                <span style="font-weight:bold; font-size:18px;">Hunter Rank: {current_lvl}</span>
                <span style="color:var(--accent);">{int(xp_in_current_lvl)} / 1000 XP</span>
            </div>
            <div class="progress-bg">
                <div class="progress-fill" style="width: {progress_percent}%;"></div>
            </div>
            <div style="margin-top:8px; font-size:12px; color:#888;">
                Next Rank Unlocks: <b>Elite Status</b> (at {xp_for_next_lvl} XP)
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_obj:
        # Quick Objective Editor
        current_obj = st.session_state.get('current_objective', 'Clear Backlog')
        with st.container(border=True):
            st.caption("🎯 CURRENT OBJECTIVE")
            st.markdown(f"**{current_obj}**")
            if st.button("Edit", key="edit_obj_btn", help="Update your main focus"):
                 # Using session state to toggle an input box would be complex here, 
                 # so we use a popover for cleanliness
                 with st.popover("Update Objective"):
                     new_obj = st.text_input("New Focus", value=current_obj)
                     if st.button("Save Focus"):
                         st.session_state['current_objective'] = new_obj
                         st.rerun()

    # --- 4. DASHBOARD GRID ---
    c1, c2, c3 = st.columns(3)
    
    # CARD 1: NEXT MISSION (Intelligence)
    next_mission = "No Active Missions"
    mission_time = "--:--"
    
    # Find the nearest future task
    sorted_slots = sorted(st.session_state.get('timetable_slots', []), key=lambda x: x['Time'])
    pending_slots = [s for s in sorted_slots if not s['Done']]
    
    if pending_slots:
        next_mission = pending_slots[0]['Activity']
        mission_time = pending_slots[0]['Time']
    
    with c1:
        st.markdown(f"""
        <div class="glass-card" style="height: 180px; position:relative;">
            <div style="color:#888; font-size:12px; letter-spacing:1px;">NEXT PROTOCOL</div>
            <div style="font-size:22px; font-weight:bold; margin-top:5px; line-height:1.2;">{next_mission}</div>
            <div style="position:absolute; bottom:20px; left:20px; font-family:monospace; color:var(--accent); font-size:28px;">
                {mission_time}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # CARD 2: QUICK ACTIONS
    with c2:
        with st.container(border=True):
            st.markdown("**⚡ Quick Actions**")
            if st.button("➕ New Task", use_container_width=True):
                # Redirect logic (simulated by setting a session flag if we had a router, 
                # but for now we just open the expander in scheduler manually or just show a toast)
                st.toast("Go to Scheduler Tab to add detailed tasks.", icon="ℹ️")
            
            if st.button("🧘 Decompress", use_container_width=True):
                st.session_state['show_breathing'] = not st.session_state.get('show_breathing', False)
                st.rerun()
                
            if st.button("🤖 Ask AI", use_container_width=True):
                st.toast("Switching to AI Assistant...", icon="🧠")
                # In a real multi-page app, we'd switch the page index here.

    # CARD 3: STREAK STATUS
    streak = st.session_state.get('streak', 1)
    with c3:
        st.markdown(f"""
        <div class="glass-card" style="height: 180px; text-align:center; display:flex; flex-direction:column; justify-content:center;">
            <div style="font-size:40px;">🔥</div>
            <div style="font-size:30px; font-weight:bold; color:#fff;">{streak} Day</div>
            <div style="color:#888; font-size:12px;">ACTIVE STREAK</div>
            <div style="margin-top:5px; color:var(--accent); font-size:12px;">XP Multiplier: {1 + (streak*0.1):.1f}x</div>
        </div>
        """, unsafe_allow_html=True)

    # --- 5. BREATHING OVERLAY (CONDITIONAL) ---
    if st.session_state.get('show_breathing', False):
        st.markdown("---")
        st.markdown("### 🧘 Tactical Decompression")
        st.markdown("""
        <div style="display:flex; justify-content:center; margin: 20px 0;">
            <div style="
                width: 80px; height: 80px; 
                background: radial-gradient(circle, var(--accent) 0%, transparent 70%);
                border-radius: 50%;
                animation: pulse 4s infinite ease-in-out;
            "></div>
        </div>
        <div style="text-align:center; font-family:monospace; color:#aaa;">INHALE... HOLD... EXHALE...</div>
        <style>
            @keyframes pulse {
                0% { transform: scale(0.8); opacity: 0.3; }
                50% { transform: scale(1.5); opacity: 0.8; }
                100% { transform: scale(0.8); opacity: 0.3; }
            }
        </style>
        """, unsafe_allow_html=True)
        if st.button("Close Exercise"):
            st.session_state['show_breathing'] = False
            st.rerun()

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

def page_dashboard():
    # --- 1. DASHBOARD STYLING (Cyberpunk/Tactical Look) ---
    st.markdown("""
    <style>
        .dash-card {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            backdrop-filter: blur(10px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        .stat-value { font-size: 32px; font-weight: 800; color: #B5FF5F; }
        .stat-label { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #aaa; }
        .rank-badge {
            font-size: 50px;
            animation: float 3s ease-in-out infinite;
        }
        @keyframes float {
            0% { transform: translateY(0px); }
            50% { transform: translateY(-10px); }
            100% { transform: translateY(0px); }
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="big-title">📊 Intelligence Report</div>', unsafe_allow_html=True)

    # --- 2. DATA PROCESSING ---
    slots = st.session_state.get('timetable_slots', [])
    xp = st.session_state.get('user_xp', 0)
    level = st.session_state.get('user_level', 1)
    
    # Calculate Metrics
    total_tasks = len(slots)
    completed = len([t for t in slots if t.get('Done')])
    pending = total_tasks - completed
    success_rate = int((completed / total_tasks * 100)) if total_tasks > 0 else 0
    
    # Calculate Rank Title
    rank_titles = {1: "Scout", 5: "Ranger", 10: "Veteran", 20: "Commander", 50: "Titan"}
    # Find closest rank without going over
    current_title = "Rookie"
    for lvl, title in rank_titles.items():
        if level >= lvl: current_title = title
    
    # --- 3. TOP ROW: HUD STATS ---
    c_rank, c_stats = st.columns([1, 3])
    
    with c_rank:
        # Animated Rank Badge
        st.markdown(f"""
        <div class="dash-card">
            <div class="rank-badge">🛡️</div>
            <div style="font-size:18px; font-weight:bold; color:white; margin-top:5px;">{current_title}</div>
            <div style="font-size:12px; color:#B5FF5F;">Level {level}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c_stats:
        # 3-Column Metrics
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"""<div class="dash-card"><div class="stat-value">{xp}</div><div class="stat-label">Total XP</div></div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class="dash-card"><div class="stat-value">{completed}</div><div class="stat-label">Missions Done</div></div>""", unsafe_allow_html=True)
        with c3:
            color = "#00E5FF" if success_rate > 80 else "#FF2A2A"
            st.markdown(f"""<div class="dash-card"><div class="stat-value" style="color:{color} !important;">{success_rate}%</div><div class="stat-label">Success Rate</div></div>""", unsafe_allow_html=True)

    st.write("")
    
    # --- 4. MIDDLE ROW: CHARTS & SECTOR ANALYSIS ---
    col_chart, col_breakdown = st.columns([2, 1])
    
    with col_chart:
        st.markdown("### 📈 XP Velocity (Growth)")
        if st.session_state.get('xp_history'):
            history_df = pd.DataFrame(st.session_state['xp_history'])
            # Create a clean line chart
            st.line_chart(history_df.set_index('Date')['XP'], color="#B5FF5F")
        else:
            st.info("Awaiting mission data to generate tactical graph.")
            
    with col_breakdown:
        st.markdown("### 🧩 Sector Split")
        if slots:
            # Pandas magic to count categories
            df_slots = pd.DataFrame(slots)
            if 'Category' in df_slots.columns:
                cat_counts = df_slots['Category'].value_counts()
                st.dataframe(cat_counts, use_container_width=True, column_config={"count": st.column_config.ProgressColumn("Volume", format="%d", min_value=0, max_value=int(cat_counts.max()))})
        else:
            st.caption("No sectors defined.")

    st.divider()

    # --- 5. EXPORT & LOGS ---
    c_log, c_export = st.columns([3, 1])
    
    with c_log:
        with st.expander("📜 Mission Log (Recent History)"):
            if st.session_state.get('xp_history'):
                st.dataframe(pd.DataFrame(st.session_state['xp_history']).tail(10), use_container_width=True)
            else:
                st.caption("Log is empty.")

    with c_export:
        st.markdown("### 🗂️ Archive")
        if st.button("📄 Export Dossier (PDF)", type="primary", use_container_width=True):
            try:
                pdf_bytes = create_mission_report(
                    st.session_state.get('user_name', 'Agent'),
                    level,
                    xp,
                    st.session_state.get('xp_history', [])
                )
                b64 = base64.b64encode(pdf_bytes).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="Mission_Report.pdf" style="text-decoration:none; color:#B5FF5F; font-weight:bold; border:1px solid #B5FF5F; padding:10px; border-radius:10px; display:block; text-align:center;">📥 Download Now</a>'
                st.markdown(href, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Generation Failed: {e}")

    
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
            st.rerun()
 
# --- MISSING ALARM OVERLAY FUNCTION ---
def render_alarm_ui():
    """
    Renders a Full-Screen 'Code Red' Overlay when an alarm triggers.
    Works on ANY page because it is injected at the top level.
    """
    if st.session_state.get('active_alarm'):
        alarm_data = st.session_state['active_alarm']
        task_name = alarm_data['task']
        idx = alarm_data['index']
        
        # --- 1. PLAY SOUND (Hidden Loop) ---
        sound_file = "alarm.mp3"
        if os.path.exists(sound_file):
            try:
                with open(sound_file, "rb") as f:
                    audio_bytes = f.read()
                b64 = base64.b64encode(audio_bytes).decode()
                # Autoplay, Loop, Hidden
                st.markdown(f'<audio src="data:audio/mp3;base64,{b64}" autoplay loop></audio>', unsafe_allow_html=True)
            except: pass
        else:
            # Fallback Beep
            st.markdown('<audio src="https://www.soundjay.com/buttons/beep-01a.mp3" autoplay loop></audio>', unsafe_allow_html=True)

        # --- 2. CSS FOR FULL-SCREEN OVERLAY ---
        st.markdown("""
        <style>
            /* The Overlay Background */
            .alarm-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: rgba(0, 0, 0, 0.95);
                z-index: 999999;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                backdrop-filter: blur(15px);
                animation: fadeIn 0.3s ease-out;
            }
            
            /* The Alarm Box */
            .alarm-box {
                width: 90%;
                max-width: 500px;
                background: linear-gradient(135deg, #1a0000 0%, #2d0000 100%);
                border: 2px solid #FF2A2A;
                border-radius: 20px;
                padding: 40px;
                text-align: center;
                box-shadow: 0 0 60px rgba(255, 42, 42, 0.6);
                animation: pulse-red 1.2s infinite ease-in-out;
            }
            
            .alarm-title {
                font-family: 'Courier New', monospace;
                font-size: 32px;
                font-weight: 900;
                color: #FF2A2A;
                margin-bottom: 15px;
                text-transform: uppercase;
                letter-spacing: 3px;
                text-shadow: 0 0 10px rgba(255, 42, 42, 0.8);
            }
            
            .alarm-task {
                font-size: 28px;
                color: white;
                margin-bottom: 10px;
                font-weight: bold;
            }
            
            @keyframes pulse-red {
                0% { box-shadow: 0 0 0 0 rgba(255, 42, 42, 0.7); transform: scale(1); }
                50% { box-shadow: 0 0 0 20px rgba(255, 42, 42, 0); transform: scale(1.02); }
                100% { box-shadow: 0 0 0 0 rgba(255, 42, 42, 0); transform: scale(1); }
            }
        </style>
        """, unsafe_allow_html=True)

        # --- 3. RENDER VISUALS ---
        st.markdown(f"""
        <div class="alarm-overlay">
            <div class="alarm-box">
                <div style="font-size:70px; margin-bottom:10px;">🚨</div>
                <div class="alarm-title">MISSION CRITICAL</div>
                <div class="alarm-task">"{task_name}"</div>
                <div style="color:#ffaaaa; margin-bottom:30px; font-family:monospace;">DEADLINE PROTOCOL ACTIVE</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # --- 4. RENDER BUTTONS (Streamlit native buttons float on top) ---
        # We use a container that sits effectively "above" the HTML overlay due to Streamlit's layout engine
        with st.container():
            col1, col2, col3 = st.columns([1, 1, 1])
            
            with col1:
                if st.button("🛑 STOP ALARM", type="primary", use_container_width=True):
                    st.session_state['active_alarm'] = None
                    st.rerun()
            
            with col2:
                if st.button("💤 SNOOZE (5m)", use_container_width=True):
                    # Logic: Add 5 mins
                    st.session_state['reminders'][idx]['time'] += datetime.timedelta(minutes=5)
                    st.session_state['reminders'][idx]['notified'] = False
                    st.session_state['active_alarm'] = None
                    sync_data()
                    st.rerun()

            with col3:
                if st.button("✅ MARK DONE", use_container_width=True):
                    # Logic: Remove Task
                    st.session_state['reminders'].pop(idx)
                    st.session_state['active_alarm'] = None
                    sync_data()
                    st.rerun()
        
        # STOP EXECUTION so the user is forced to interact
        st.stop()

# --- MAIN APP FUNCTION ---

def main():
    # 1. Initialize System
    initialize_session_state()
    
    # 2. GLOBAL ALARM SYSTEM (The "Code Red" Overlay)
    # We check reminders first. If one triggers, render_alarm_ui() 
    # will launch the full-screen overlay and stop the rest of the app from loading.
    check_reminders()
    render_alarm_ui()

    # 3. Load Styles & Visuals
    inject_custom_css()
    show_comet_splash()

    # 4. Onboarding Gate
    if not st.session_state['onboarding_complete']:
        page_onboarding()
        return 

    # --- LOGIC SWITCH: WHICH SIDEBAR TO SHOW? ---
    
    # A. CHAT MODE SIDEBAR (For AI Context Retention)
    if st.session_state.get('page_mode') == 'chat':
        with st.sidebar:
            st.markdown("### 💬 Chat History")
            if st.button("🏠 Back to Main Menu", type="primary", use_container_width=True):
                st.session_state['page_mode'] = 'main'
                st.rerun()
            
            st.divider()
            
            # New Chat Button
            if st.button("➕ New Chat", use_container_width=True):
                st.session_state['current_session_id'] = None
                st.session_state['current_session_name'] = "New Chat"
                st.session_state['chat_history'] = []
                st.rerun()
            
            st.markdown("---")
            
            # History List
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
        
        # Load the AI Page
        page_ai_assistant()

    # B. MAIN MENU SIDEBAR (Default App Mode)
    else:
        with st.sidebar:
            st.markdown("<h1 style='text-align: center;'>🏹<br>TimeHunt AI</h1>", unsafe_allow_html=True)
            render_live_clock()
            
            # --- AUDIO ENGINE ---
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
            
            # --- MAIN NAVIGATION ---
            nav = option_menu(
                menu_title=None,
                options=["Home", "Scheduler", "Calendar", "AI Assistant", "Timer", "Dashboard", "About", "Settings"], 
                icons=["house", "list-check", "calendar-week", "robot", "hourglass-split", "graph-up", "info-circle", "gear"], 
                default_index=0
            )

            st.caption(f"🆔 **Agent:** {st.session_state['user_name']}")

        # --- ROUTER LOGIC ---
        if nav == "Home": page_home()
        elif nav == "Scheduler": page_scheduler()
        elif nav == "Calendar": page_calendar()
        elif nav == "AI Assistant": 
            st.session_state['page_mode'] = 'chat'
            st.rerun()
        elif nav == "Timer": page_timer()  
        elif nav == "Dashboard": page_dashboard()
        elif nav == "About": page_about()
        elif nav == "Settings": page_settings()

if __name__ == "__main__":
    main()