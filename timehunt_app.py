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
import json # <--- ADD THIS

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
    """Saves current Reminders & Timetable to Google Sheets using WRITE mode"""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        uid = st.session_state.get('user_id')
        if not uid: return

        # 1. READ EXISTING SHEET
        try:
            df_cloud = conn.read(worksheet="Reminders", ttl=0)
            if not df_cloud.empty and "UserID" in df_cloud.columns:
                df_others = df_cloud[df_cloud["UserID"] != uid]
            else:
                df_others = pd.DataFrame(columns=["UserID", "Task", "Time", "Status", "Type"])
        except:
            df_others = pd.DataFrame(columns=["UserID", "Task", "Time", "Status", "Type"])

        # 2. PREPARE NEW ROWS
        new_rows = []
        
        # Alarms
        for rem in st.session_state.get('reminders', []):
            new_rows.append({
                "UserID": str(uid),
                "Task": str(rem['task']),
                "Time": str(rem['time']), 
                "Status": "Done" if rem.get('notified') else "Pending",
                "Type": "Alarm"
            })
            
        # Timetable
        for slot in st.session_state.get('timetable_slots', []):
             new_rows.append({
                "UserID": str(uid),
                "Task": str(slot['Activity']),
                "Time": str(slot['Time']),
                "Status": "Done" if slot['Done'] else "Pending",
                "Type": f"Schedule-{slot['Category']}"
            })

        # 3. MERGE & WRITE
        if new_rows:
            df_my_data = pd.DataFrame(new_rows)
            df_final = pd.concat([df_others, df_my_data], ignore_index=True)
        else:
            df_final = df_others

        # Force String Type to prevent Google rejection
        df_final = df_final.astype(str)
        
        # --- CRITICAL CHANGE: USE WRITE INSTEAD OF UPDATE ---
        conn.write(worksheet="Reminders", data=df_final)
        
    except Exception as e:
        print(f"Cloud Sync Error: {e}")



def load_cloud_data():
    """Loads Reminders & Timetable from Google Sheets on Login"""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        uid = st.session_state.get('user_id')
        
        # Read Reminders Tab
        try:
            df = conn.read(worksheet="Reminders", ttl=0)
        except:
            return # Tab might not exist yet

        if not df.empty and "UserID" in df.columns:
            my_data = df[df["UserID"] == uid]
            
            loaded_reminders = []
            loaded_timetable = []
            
            for _, row in my_data.iterrows():
                # Parse Alarms
                if row['Type'] == "Alarm":
                    loaded_reminders.append({
                        "task": row['Task'],
                        "time": row['Time'], # Will be string, parsed later by check_reminders
                        "notified": (row['Status'] == "Done")
                    })
                # Parse Schedule
                elif "Schedule" in str(row['Type']):
                    cat = row['Type'].split("-")[1] if "-" in row['Type'] else "General"
                    loaded_timetable.append({
                        "Time": row['Time'],
                        "Activity": row['Task'],
                        "Category": cat,
                        "Done": (row['Status'] == "Done"),
                        "XP": 50, # Default XP
                        "Difficulty": "Medium" # Default
                    })
            
            st.session_state['reminders'] = loaded_reminders
            st.session_state['timetable_slots'] = loaded_timetable
            
    except Exception as e:
        print(f"Cloud Load Error: {e}")


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
        'user_id': f"ID-{random.randint(1000, 9999)}-{int(time.time())}", # Generate unique ID per session
        'active_alarm': None,
        'splash_played': False,
        'chat_history': [], 
        'user_xp': 0, 
        'user_level': 1,
        'streak': 1,
        'last_active_date': today_str,
        'timetable_slots': [], 
        'reminders': [],
        'onboarding_step': 1,
        'onboarding_complete': False, 
        'user_name': "Hunter",        
        'user_type': "Student",
        'user_goal': "General Productivity",
        'struggle_type': "Procrastination",
        'user_avatar': "🏹",
        'study_hours': 6,
        'xp_history': [], 
        'theme_mode': 'Light',
        'theme_color': 'Venom Green (Default)'
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

    PERSONALIZED_INSTRUCTION = f"""
    You are TimeHunt AI.
    --- USER INTEL ---
    NAME: {user_name} | ROLE: {user_role} 
    GOAL: {user_goal} | OBSTACLE: {user_struggle}
    
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
            if 'Difficulty' not in slot: slot['Difficulty'] = "Medium" # NEW
            if 'XP' not in slot: slot['XP'] = 50

    col_header, col_av = st.columns([4,1])
    with col_header:
        st.markdown('<div class="big-title">Mission Control ⚙️</div>', unsafe_allow_html=True)
        # SHOW STREAK HERE
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
                # NEW DIFFICULTY SELECTOR
                diff = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"])
            
            submitted = st.form_submit_button("Add to Schedule ➔")
            
            if submitted and task:
                # Assign XP based on difficulty
                base_xp = 30 if diff == "Easy" else 50 if diff == "Medium" else 100
                
                st.session_state['timetable_slots'].append({
                    "Time": datetime.datetime.now().strftime("%H:%M"),
                    "Activity": task, 
                    "Category": m_type, 
                    "Difficulty": diff,
                    "Done": False, 
                    "XP": base_xp
                })
                st.toast(f"Mission Deployed: {task}", icon="🦅")
                st.rerun()

    with c2:
        total_tasks = len(st.session_state['timetable_slots'])
        pending_tasks = len([t for t in st.session_state['timetable_slots'] if not t['Done']])
        completed_tasks = total_tasks - pending_tasks
        
        # CLEAN CARD HTML (Uses proper CSS classes for styling)
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
                        # 1. Calculate Gain with Multiplier
                        streak = st.session_state.get('streak', 1)
                        multiplier = 1 + (streak * 0.1)
                        
                        raw_xp = sum([t['XP'] for t in completed_now])
                        final_xp = int(raw_xp * multiplier)
                        
                        # 2. Update Stats
                        st.session_state['user_xp'] += final_xp
                        st.session_state['user_level'] = (st.session_state['user_xp'] // 500) + 1
                        
                        # Remove completed items
                        st.session_state['timetable_slots'] = [t for t in current_slots if not t['Done']]
                        
                        # 3. Log History
                        today_str = datetime.date.today().strftime("%Y-%m-%d")
                        st.session_state['xp_history'].append({"Date": today_str, "XP": final_xp})
                        sync_data() 
                        
                        st.balloons() # CELEBRATION
                        st.toast(f"Reward: {raw_xp} x {multiplier:.1f} Streak = +{final_xp} XP!", icon="🎉")
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.toast("Mark tasks as done first.", icon="🚫")
    else:
        st.info("No active protocols. Deploy a mission above.")
        
# --- 8. PAGE: AI ASSISTANT (ENHANCED) ---
def page_ai_assistant():
    # 1. Header with Clear Button
    c_head, c_btn = st.columns([3, 1])
    with c_head:
        st.markdown('<div class="big-title">Tactical AI Support 🤖</div>', unsafe_allow_html=True)
    with c_btn:
        # --- NEW: DELETE CHAT BUTTON ---
        if st.button("🗑️ Clear Comms"):
            st.session_state['chat_history'] = []
            sync_data() # Update file
            st.rerun()

    st.markdown('<div class="sub-title">Intelligence & Strategy Center</div>', unsafe_allow_html=True)

    # 2. Custom CSS (Kept same)
    st.markdown("""
    <style>
    .stChatMessage { background-color: rgba(255, 255, 255, 0.7); border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.5); box-shadow: 0 2px 10px rgba(0,0,0,0.03); margin-bottom: 10px; }
    .stButton button { border-radius: 20px; border: 1px solid #eee; background: white; box-shadow: 0 2px 5px rgba(0,0,0,0.05); transition: all 0.3s; height: 50px; }
    .stButton button:hover { border-color: #B5FF5F; background: #f9f9f9; transform: translateY(-2px); }
    </style>
    """, unsafe_allow_html=True)

    # 3. Dynamic Greeting Logic
    if not st.session_state['chat_history']:
        greetings = [
            f"How can I help you reach your objective today, {st.session_state['user_name']}?",
            "Ready to strategize? Describe your current mission bottleneck.",
            "Mission intelligence is online. What are we tackling?",
            "Standing by for your command. Give me a deadline.",
            "Systems green. Ready to optimize your trajectory."
        ]
        
        # We use a placeholder to keep it clean
        selected_greeting = random.choice(greetings)

        st.markdown(f"""
            <div class="css-card" style="text-align: center; padding: 40px; margin-top: 20px;">
                <div style="font-size: 60px; margin-bottom: 10px;">⚡</div>
                <div class="card-title" style="font-size: 28px; margin-bottom: 10px;">{selected_greeting}</div>
                <div class="card-sub" style="margin-bottom: 30px;">
                    Target: {st.session_state['struggle_type']} Protocol | Capacity: {st.session_state['study_hours']}h
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # Action Buttons
        c1, c2, c3 = st.columns(3)
        if c1.button("📝 Make Timetable", use_container_width=True): 
            handle_chat(f"Create a strict tactical timetable for a {st.session_state['user_type']} with {st.session_state['study_hours']} hours of focus. Ask me if I am at base or school first.")
        if c2.button("💡 Explain Concept", use_container_width=True): 
            handle_chat("Explain a complex topic for my current level.")
        if c3.button("🚀 Elite Motivation", use_container_width=True): 
            handle_chat("I am feeling demotivated. Remind me of my mission goals and my rank.")

    # 4. Render Chat History
    else:
        for msg in st.session_state['chat_history']:
            role = msg['role']
            if role == "model" or role == "assistant":
                with st.chat_message(role, avatar="1000592991.png"): 
                    st.write(msg['text'])
            else:
                # USER AVATAR LOGIC (FORCE PATH)
                user_av = st.session_state.get('user_avatar', "👤")
                
                # 1. CREATE FULL PATH (combines C:/Users/... with filename.png)
                # str(user_av) ensures we don't crash if it's an emoji object
                full_path = os.path.join(current_dir, str(user_av))
                
                # 2. CHECK IF FILE EXISTS AT THAT EXACT PATH
                # We check extensions to avoid errors with emojis
                if str(user_av).endswith(('.png', '.jpg', '.jpeg')) and os.path.exists(full_path):
                    avatar_to_use = full_path
                else:
                    # If file check fails, check if it is a simple emoji
                    avatar_to_use = user_av if len(str(user_av)) < 5 else "👤"

                with st.chat_message(role, avatar=avatar_to_use):
                    st.write(msg['text'])

    # 5. Chat Input
    if prompt := st.chat_input("Input command parameters..."):
        handle_chat(prompt)

# --- HELPER: CHAT HANDLER (SMARTER VERSION) ---
import re # Make sure this is imported at the top of your file!

def handle_chat(prompt):
    # 1. Add User Message
    st.session_state['chat_history'].append({"role": "user", "text": prompt})
    
    # 2. Get AI Response
    with st.spinner("Processing Strategy..."):
         res_text, source = perform_auto_search(prompt)
         
         # --- IMPROVED PARSER: Uses Regex to find JSON anywhere ---
         # This looks for content between [ and ] that looks like JSON
         json_match = re.search(r'\[\s*\{.*?\}\s*\]', res_text, re.DOTALL)
         
         if json_match:
             try:
                 json_str = json_match.group(0)
                 new_slots = json.loads(json_str)
                 
                 # Add to Scheduler
                 for slot in new_slots:
                     st.session_state['timetable_slots'].append({
                         "Time": slot.get("Time", "00:00"),
                         "Activity": slot.get("Activity", "Mission"),
                         "Category": slot.get("Category", "Study"),
                         "Done": False,
                         "XP": 50
                     })
                 res_text = "✅ **Protocol Established.** I have automatically added the new timetable to your Scheduler tab."
                 sync_data() 
             except Exception as e:
                 print(f"JSON Parse Error: {e}")
                 # If parsing fails, we just keep the text response
                 pass

         # 3. Add AI Message
         st.session_state['chat_history'].append({"role": "assistant", "text": res_text})
         sync_data() 
    
    st.rerun()

# --- 9. CUSTOM UI STYLING (SIDEBAR & MAIN THEME) ---

def inject_custom_css():
    # 1. Load User Preferences
    theme_color = st.session_state.get('theme_color', 'Venom Green (Default)')
    theme_mode = st.session_state.get('theme_mode', 'Light') # Default to Light to match your screenshot
    
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
        # ORIGINAL PREMIUM LOOK (The "Morning" Gradient)
        main_bg = "linear-gradient(180deg, #FFF6E5 0%, #FFFFFF 40%, #Eef2ff 100%)"
        sidebar_bg = "linear-gradient(180deg, #FDF3E6 0%, #FFFFFF 100%)"
        card_bg = "#FFFFFF"
        text_color = "#1A1A1A"
        sub_text = "#444444"
        border_color = "rgba(0,0,0,0.05)"
        shadow = "0 10px 40px -10px rgba(0,0,0,0.08)" # The "Floating" shadow
        input_bg = "#FFFFFF"
        nav_active_bg = accent
        nav_active_text = "#000000"
    else:
        # PREMIUM DARK MODE (Deep & Glassy)
        main_bg = "linear-gradient(180deg, #0E1117 0%, #151922 100%)"
        sidebar_bg = "#0E1117"
        card_bg = "#1E232F" # Slightly lighter than bg
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
            
            /* --- TYPOGRAPHY (BIG & BOLD) --- */
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
            
            /* --- CARDS (The key to the look) --- */
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
            
            /* --- BLACK CARD OVERRIDE (For Schedule) --- */
            .black-card {{
                background-color: #1A1A1A !important; 
                color: white !important; 
                border-radius: 32px; 
                padding: 24px;
                border: 1px solid #333;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }}
            .black-card * {{ color: white !important; }} 
        </style>
    """, unsafe_allow_html=True)

# --- 10. MAIN ROUTER ---
# --- PDF REPORT GENERATOR ---
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

def page_home():
    # Greeting Logic
    current_hour = datetime.datetime.now().hour
    if current_hour < 12: greeting = "Good Morning"
    elif current_hour < 18: greeting = "Good Afternoon"
    else: greeting = "Good Evening"

    # Quotes
    quotes = ["Be Productive Today 🙌", "Hunt Down Your Goals 🏹", "Focus. Execute. Win. 🏆"]
    random_sub = random.choice(quotes)

    # Variables
    if 'current_objective' not in st.session_state:
        st.session_state['current_objective'] = "Clear Backlog"
    xp_in_level = st.session_state['user_xp'] % 500
    progress_pct = min((xp_in_level / 500) * 100, 100)
    
    # Render Header (Classes will use the big fonts from CSS now)
    st.markdown(f'<div class="big-title">{greeting}, {st.session_state["user_name"]}!</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title">{random_sub}</div>', unsafe_allow_html=True)

    with st.expander("🖊️ Update Dashboard Status"):
        new_obj = st.text_input("Current Objective", value=st.session_state['current_objective'])
        if st.button("Update"):
            st.session_state['current_objective'] = new_obj
            st.rerun()

    col1, col2 = st.columns([2, 1])

    with col1:
        # CLEAN CARD (Removed hardcoded styles, uses CSS classes)
        st.markdown(f"""
        <div class="css-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="card-title">Current Objective</span>
                <span style="background:rgba(181, 255, 95, 0.2); padding:5px 10px; border-radius:15px; font-size:12px; color:var(--text);">Protocol Active</span>
            </div>
            <br>
            <div class="card-sub" style="font-size:18px; margin-bottom:15px;">{st.session_state['current_objective']}</div>
            <div style="height:8px; width:100%; background:rgba(0,0,0,0.1); border-radius:4px;">
                <div style="height:100%; width:{progress_pct}%; background:var(--accent); border-radius:4px;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:15px;">
                <div><div class="stat-num">{st.session_state['user_xp']}</div><div class="card-sub">Total XP</div></div>
                <div><div class="stat-num">{st.session_state['user_level']}</div><div class="card-sub">Level</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Breathing Exercise (ANIMATED NEON CIRCLE)
        with st.expander("🧘 Tactical Decompression"):
            st.markdown("""
            <style>
                @keyframes breathe {
                    0% { transform: scale(1); opacity: 0.5; box-shadow: 0 0 5px var(--accent); }
                    50% { transform: scale(1.6); opacity: 1; box-shadow: 0 0 25px var(--accent); }
                    100% { transform: scale(1); opacity: 0.5; box-shadow: 0 0 5px var(--accent); }
                }
                .breath-container {
                    display: flex; flex-direction: column; align-items: center; padding: 20px;
                }
                .breath-circle {
                    width: 60px; height: 60px;
                    border-radius: 50%;
                    background: radial-gradient(circle, var(--accent) 0%, transparent 70%);
                    border: 2px solid var(--accent);
                    animation: breathe 5s infinite ease-in-out;
                    margin-bottom: 15px;
                }
                .breath-text {
                    font-family: monospace; color: var(--text); opacity: 0.8; letter-spacing: 2px;
                }
            </style>
            <div class="breath-container">
                <div class="breath-circle"></div>
                <div class="breath-text">INHALE ... HOLD ... EXHALE</div>
            </div>
            """, unsafe_allow_html=True)

    with col2:
        # Green Card (Hardcoded Green is okay here for emphasis, but we use the variable)
        st.markdown(f"""
        <div class="css-card" style="background-color: var(--accent) !important;">
            <div class="card-title" style="color:#000 !important;">Daily Focus</div>
            <div style="color:#000; opacity:0.8;">No active missions</div>
        </div>
        """, unsafe_allow_html=True)

        # Black Card (Specific Design)
        next_task = st.session_state['reminders'][-1]['task'] if st.session_state['reminders'] else "No alerts"
        st.markdown(f"""
        <div class="black-card">
            <div style="font-weight:bold; margin-bottom:10px; font-size:18px;">Scheduled</div>
            <div style="background:#333; padding:10px; border-radius:10px; text-align:center; margin-bottom:15px;">
                <div style="font-size:20px; font-weight:bold;">{datetime.datetime.now().strftime("%b %d")}</div>
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
def main():
    initialize_session_state()
    
    # --- 1. GLOBAL ALARM SYSTEM ---
    alarm_container = st.container()
    check_reminders()
    with alarm_container:
        render_alarm_ui()
    
    # --- 2. CSS & SPLASH ---
    inject_custom_css()
    show_comet_splash()

    # --- 3. SESSION STATE CHECKS ---
    if 'user_name' not in st.session_state: st.session_state['user_name'] = "Hunter"
    if 'user_xp' not in st.session_state: st.session_state['user_xp'] = 0
    if 'user_level' not in st.session_state: st.session_state['user_level'] = 1
    if 'xp_history' not in st.session_state: st.session_state['xp_history'] = [] 
    if 'timetable_slots' not in st.session_state: st.session_state['timetable_slots'] = []
    
    # --- 4. CHECK ONBOARDING ---
    if not st.session_state['onboarding_complete']:
        page_onboarding()
        return 

    # --- 5. SIDEBAR ---
    with st.sidebar:
        st.markdown("<h1 style='text-align: center; margin-bottom: 20px;'>🏹<br>TimeHunt</h1>", unsafe_allow_html=True)
        render_live_clock()
        
        st.markdown("---")
        st.markdown("### 🎧 Sonic Intel")
        
        with st.container():
            music_mode = st.selectbox("Frequency", ["Om Chanting (Spiritual)", "Binaural Beats (Focus)", "Divine Flute (Flow)", "Rainfall (Calm)"], label_visibility="collapsed")
            local_map = {"Om Chanting (Spiritual)": "om.mp3", "Binaural Beats (Focus)": "binaural.mp3", "Divine Flute (Flow)": "flute.mp3", "Rainfall (Calm)": "rain.mp3"}
            target_file = local_map.get(music_mode)

            if target_file and os.path.exists(target_file):
                st.audio(target_file, format="audio/mp3", loop=True)
            else:
                st.caption("Upload .mp3 to root directory.")

        st.markdown("### ⏱️ Focus Timer")
        pomo_html = """
        <style>
            .timer-box { background: #1A1A1A; color: #B5FF5F; font-family: monospace; font-size: 35px; text-align: center; border-radius: 15px; padding: 10px; border: 2px solid #B5FF5F; margin-bottom: 10px; }
            .btn-grid { display: flex; gap: 10px; }
            .btn { flex: 1; padding: 10px; border-radius: 10px; border: none; cursor: pointer; font-weight: bold; }
            .btn-start { background: #B5FF5F; color: black; }
            .btn-reset { background: #333; color: white; }
        </style>
        <div class="timer-box"><span id="timer-display">25:00</span></div>
        <div class="btn-grid"><button class="btn btn-start" onclick="startTimer()">START</button><button class="btn btn-reset" onclick="resetTimer()">RESET</button></div>
        <script>
            let timeLeft = 25 * 60; let timerId = null; const display = document.getElementById('timer-display');
            function updateDisplay() { let mins = Math.floor(timeLeft / 60); let secs = timeLeft % 60; display.innerText = (mins < 10 ? '0' : '') + mins + ':' + (secs < 10 ? '0' : '') + secs; }
            function startTimer() { if (timerId) return; timerId = setInterval(() => { if (timeLeft > 0) { timeLeft--; updateDisplay(); } else { clearInterval(timerId); alert("Mission Complete!"); } }, 1000); }
            function resetTimer() { clearInterval(timerId); timerId = null; timeLeft = 25 * 60; updateDisplay(); }
        </script>
        """
        components.html(pomo_html, height=160)

        st.markdown("---")
        nav = option_menu(
            menu_title=None,
            options=["Home", "Scheduler", "AI Assistant", "Dashboard", "About", "Settings"], 
            icons=["house", "calendar-check", "robot", "graph-up", "info-circle", "gear"], 
            default_index=0
        )
        st.markdown("---")
        st.caption(f"🆔 **Agent:** {st.session_state['user_name']}")

    # --- 6. PAGE ROUTING (ALIGNED CORRECTLY) ---
    if nav == "Home":
        page_home()
    elif nav == "Scheduler":
        page_scheduler()
    elif nav == "AI Assistant":
        page_ai_assistant()
    elif nav == "Dashboard":
        # --- 1. CONNECT TO REAL DATABASE ---
        try:
            from streamlit_gsheets import GSheetsConnection
            conn = st.connection("gsheets", type=GSheetsConnection)
            df = conn.read(worksheet="Sheet1", ttl=0) 
        except Exception as e:
            st.error(f"📡 Connection Failed: {e}")
            st.stop()

        # --- 2. UPDATE YOUR DATA TO CLOUD ---
        current_user = st.session_state['user_name']
        current_xp = st.session_state['user_xp']
        current_league = st.session_state.get('league', "Bronze")
        current_avatar = str(st.session_state.get('user_avatar', "👤"))
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        if df.empty or 'UserID' not in df.columns:
            df = pd.DataFrame(columns=["UserID", "Name", "XP", "League", "Avatar", "LastActive"])

        uid = st.session_state['user_id']
        if uid in df['UserID'].values:
            df.loc[df['UserID'] == uid, ['Name', 'XP', 'League', 'Avatar', 'LastActive']] = [current_user, current_xp, current_league, current_avatar, today_str]
        else:
            new_row = pd.DataFrame([{ "UserID": uid, "Name": current_user, "XP": current_xp, "League": current_league, "Avatar": current_avatar, "LastActive": today_str }])
            df = pd.concat([df, new_row], ignore_index=True)

        conn.update(worksheet="Sheet1", data=df)
        
        # --- FIX 1: SORT DATA ---
        if not df.empty and 'XP' in df.columns:
            df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
            df_sorted = df.sort_values(by='XP', ascending=False)
        else:
            df_sorted = pd.DataFrame(columns=["Name", "XP", "Avatar"])

        # --- FIX 2: CREATE COLUMNS ---
        c_leaderboard, c_stats = st.columns([2, 1])

                # --- 3. RENDER LEADERBOARD ---
        st.markdown(f'<div class="big-title">Global Rankings 🏆</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="sub-title">Live Data from Cloud Database</div>', unsafe_allow_html=True)

        st.markdown("### 🌍 Top Hunters")
        
        # .head(5) ensures we only take the first 5 winners
        for i, row in df_sorted.head(5).iterrows():
            is_me = row['Name'] == current_user
            bg_color = "#B5FF5F" if is_me else "#FFFFFF"
            text_color = "#1A1A1A" if is_me else "#333"
            border = "2px solid #1A1A1A" if is_me else "1px solid #eee"
            
            # --- NEW: AVATAR IMAGE LOGIC ---
            # Get the avatar filename from the database
            avatar_filename = str(row['Avatar'])
            avatar_html = ""
            
            # Check if the file exists locally to convert it to base64 for the HTML block
            if os.path.exists(avatar_filename):
                with open(avatar_filename, "rb") as f:
                    data = base64.b64encode(f.read()).decode()
                    avatar_html = f'<img src="data:image/png;base64,{data}" style="width:30px; height:30px; border-radius:50%;">'
            else:
                # Fallback if image file is missing
                avatar_html = '<span style="font-size:24px;">👤</span>'

            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; align-items:center; background:{bg_color}; padding:15px; border-radius:12px; margin-bottom:10px; border:{border}; box-shadow:0 2px 5px rgba(0,0,0,0.05);">
                <div style="display:flex; align-items:center; gap:15px;">
                    <span style="font-size:20px; font-weight:bold; color:{text_color};">#{i+1}</span>
                    {avatar_html}
                    <span style="font-weight:bold; font-size:16px; color:{text_color};">{row['Name']}</span>
                </div>
                <div style="font-family:monospace; font-weight:bold; font-size:18px; color:{text_color};">
                    {row['XP']} XP
                </div>
            </div>
            """, unsafe_allow_html=True)


        # --- 4. RENDER STATS ---
        with c_stats:
            st.markdown("### 📊 Your Status")
            try:
                # Find rank safely
                rank = df_sorted.index[df_sorted['UserID'] == uid].tolist()
                my_rank = rank[0] + 1 if rank else "?"
                
                st.markdown(f"""
                <div class="css-card" style="text-align:center;">
                    <div style="font-size:40px;">👑</div>
                    <div class="card-title">Rank #{my_rank}</div>
                </div>
                """, unsafe_allow_html=True)
            except Exception as e:
                st.info(f"Syncing... {e}")
            
            if st.button("🔄 Force Refresh"):
                st.rerun()
            st.write("")
            
            # REPORT BUTTON
            if st.button("📄 Download Report"):
                try:
                    pdf_data = create_mission_report(st.session_state['user_name'], st.session_state['user_level'], st.session_state['user_xp'], st.session_state['xp_history'])
                    st.download_button(label="⬇️ Save PDF", data=pdf_data, file_name=f"TimeHunt_Report_{today_str}.pdf", mime="application/pdf")
                except:
                    st.error("Install fpdf: pip install fpdf")

    elif nav == "About":
        page_about()
    elif nav == "Settings":
        page_settings()

if __name__ == "__main__":

    main()