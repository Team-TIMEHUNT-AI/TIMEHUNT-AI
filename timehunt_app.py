from fpdf import FPDF
import textwrap
import streamlit.components.v1 as components 
import re
import streamlit as st
import os
from streamlit_option_menu import option_menu
import datetime
import random
import pandas as pd
import time
import base64
import json

# --- PATH CONFIGURATION (FIXES IMAGE LOADING) ---
# This tells Python: "The images are in the same folder as THIS script file"
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

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
        # We use a looping audio player so it keeps beeping until you stop it
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
                    save_data()
                    st.toast("Alarm Snoozed for 5 minutes.")
                    st.rerun()

            # Button 3: DONE (Mark Complete)
            with c3:
                if st.button("✅ DONE", use_container_width=True):
                    # Remove the reminder entirely
                    st.session_state['reminders'].pop(idx)
                    st.session_state['active_alarm'] = None
                    save_data()
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
DATA_FILE = "user_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data():
    data = {
        'user_name': st.session_state.get('user_name'),
        'user_type': st.session_state.get('user_type'),
        'struggle_type': st.session_state.get('struggle_type'),
        'user_avatar': st.session_state.get('user_avatar'),
        'onboarding_complete': st.session_state.get('onboarding_complete'),
        'chat_history': st.session_state.get('chat_history', []),
        'timetable_slots': st.session_state.get('timetable_slots', []),
        'user_xp': st.session_state.get('user_xp', 0),
        'user_level': st.session_state.get('user_level', 1),
        'xp_history': st.session_state.get('xp_history', []),
        'study_hours': st.session_state.get('study_hours', 4),
        'reminders': st.session_state.get('reminders', []) # <--- ADDED THIS LINE
    }
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, default=str)

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
                save_data()
                
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

# --- 6. PAGE: SMART ONBOARDING (With Suggestions & PIN) ---
# --- 6. PAGE: SMART ONBOARDING (Fixed PIN & Avatars) ---
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
               save_data()  # <--- CRITICAL: Save to file BEFORE restarting!
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
        save_data()
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
                        save_data() 
                        
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
            save_data() # Update file
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
                 save_data() 
             except Exception as e:
                 print(f"JSON Parse Error: {e}")
                 # If parsing fails, we just keep the text response
                 pass

         # 3. Add AI Message
         st.session_state['chat_history'].append({"role": "assistant", "text": res_text})
         save_data() 
    
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
        save_data()
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
        with c_leaderboard:
            st.markdown(f'<div class="big-title">Global Rankings 🏆</div>', unsafe_allow_html=True)
            st.markdown("### 🌍 Top Hunters")
            
            for i, row in df_sorted.head(5).iterrows():
                is_me = row['Name'] == current_user
                bg_color = "#B5FF5F" if is_me else "#FFFFFF"
                text_color = "#1A1A1A" if is_me else "#333"
                display_av = row['Avatar'] if len(str(row['Avatar'])) < 5 else "👤"
                
                st.markdown(f"""
                <div style="display:flex; justify-content:space-between; align-items:center; background:{bg_color}; padding:15px; border-radius:12px; margin-bottom:10px; color:{text_color}; box-shadow:0 2px 5px rgba(0,0,0,0.05);">
                    <div style="display:flex; align-items:center; gap:15px;">
                        <span style="font-size:20px; font-weight:bold;">#{i+1}</span>
                        <span style="font-size:24px;">{display_av}</span>
                        <span style="font-weight:bold; font-size:16px;">{row['Name']}</span>
                    </div>
                    <div style="font-family:monospace; font-weight:bold; font-size:18px;">{row['XP']} XP</div>
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

    main()Based on this code tell me what is the use and name of the app and give me veo three prompt to generate a coming soon video trailer ad for The Web App TimeHuntAi
from fpdf import FPDF
import textwrap
import streamlit.components.v1 as components 
import re
import streamlit as st
import os
from streamlit_option_menu import option_menu

# --- PATH CONFIGURATION ---
# Ensures assets load correctly regardless of where the script is run
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

# --- 1. LIVE CLOCK COMPONENT (Modern & Clean) ---
def render_live_clock():
    """
    Renders a real-time digital clock using an isolated HTML iframe.
    Style: Modern 'Glassmorphism' to match the productivity theme.
    """
    clock_html = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
        
        body { 
            margin: 0; 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            background: transparent; 
        }
        .clock-box {
            /* Glassmorphism Effect */
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            
            color: #FFFFFF;
            font-family: 'Inter', sans-serif; /* Clean, productive font */
            font-size: 32px;
            font-weight: 600;
            letter-spacing: 1px;
            
            padding: 10px 25px;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            text-align: center;
            width: 100%;
        }
    </style>
    </head>
    <body>
        <div class="clock-box" id="clock">--:--</div>
        <script>
            function updateClock() {
                const now = new Date();
                // Format: HH:MM (24-hour cycle)
                const timeString = now.toLocaleTimeString('en-US', { 
                    hour12: false, 
                    hour: '2-digit', 
                    minute: '2-digit' 
                });
                document.getElementById('clock').innerText = timeString;
            }
            setInterval(updateClock, 1000);
            updateClock(); // Run immediately on load
        </script>
    </body>
    </html>
    """
    # Render with fixed height to fit sidebar perfectly
    components.html(clock_html, height=80)

# --- 2. DATA PERSISTENCE (Cloud Sync) ---
def sync_data():
    """
    Syncs local Session State data to Google Sheets.
    Merges Date+Time into a single 'Time' column for compatibility.
    """
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # Safety Check: Ensure User ID exists
        uid = st.session_state.get('user_id')
        if not uid: return

        # 1. Read existing cloud data (Handle empty sheet case)
        try:
            df_cloud = conn.read(worksheet="Reminders", ttl=0)
            if not df_cloud.empty and "UserID" in df_cloud.columns:
                # Keep other users' data, remove current user's old data
                df_others = df_cloud[df_cloud["UserID"] != str(uid)]
            else:
                df_others = pd.DataFrame(columns=["UserID", "Task", "Time", "Status", "Type"])
        except Exception:
            # If sheet is missing or read fails, start fresh
            df_others = pd.DataFrame(columns=["UserID", "Task", "Time", "Status", "Type"])

        new_rows = []
        
        # 2. Add Alarms (Reminders)
        # Use .get() to avoid errors if key is missing
        for reminder in st.session_state.get('reminders', []):
            new_rows.append({
                "UserID": str(uid), 
                "Task": str(reminder['task']), 
                "Time": str(reminder['time']), 
                "Status": "Done" if reminder.get('notified') else "Pending", 
                "Type": "Alarm"
            })
            
        # 3. Add Schedule & Calendar Tasks
        for schedule_item in st.session_state.get('timetable_slots', []):
             # Default to today if Date is missing
             date_val = schedule_item.get('Date', datetime.date.today().strftime("%Y-%m-%d"))
             
             # Combine for sorting: "2025-10-27 14:00"
             combined_time = f"{date_val} {schedule_item['Time']}"
             
             new_rows.append({
                "UserID": str(uid), 
                "Task": str(schedule_item['Activity']), 
                "Time": combined_time, 
                "Status": "Done" if schedule_item['Done'] else "Pending", 
                "Type": f"Schedule-{schedule_item['Category']}"
            })

        # 4. Save back to Cloud
        if new_rows:
            df_my_data = pd.DataFrame(new_rows)
            df_final = pd.concat([df_others, df_my_data], ignore_index=True)
        else:
            df_final = df_others

        # Ensure all data is string format to prevent Schema errors
        df_final = df_final[["UserID", "Task", "Time", "Status", "Type"]].astype(str)
        conn.clear(worksheet="Reminders")
        conn.update(worksheet="Reminders", data=df_final)
        
    except Exception as e:
        # Show a discreet warning icon instead of crashing
        st.toast(f"Sync Issue: {e}", icon="⚠️")

# --- 3. WEATHER UTILITY ---
def get_real_time_weather(city="Jaipur"):
    """
    Fetches real-time weather using standard Python libraries.
    Returns a clean formatted string for the dashboard.
    """
    import json
    from urllib.request import urlopen, Request

    # Default fallback values
    fallback_temp = "--"
    fallback_desc = f"{city} (Offline)"

    try:
        # A. Default Coordinates (Jaipur)
        lat, lon = 26.9124, 75.7873 
        
        # B. If city is not default, try to geocode it
        if city.lower() != "jaipur":
            try:
                # User Agent required to prevent API blocking
                req = Request(
                    f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json",
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                with urlopen(req, timeout=3) as response:
                    geo_data = json.loads(response.read().decode())
                
                if "results" in geo_data:
                    lat = geo_data["results"][0]["latitude"]
                    lon = geo_data["results"][0]["longitude"]
            except Exception:
                # If geocoding fails, we proceed with default or previous coordinates
                pass

        # C. Fetch Weather Data
        req_weather = Request(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true",
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        with urlopen(req_weather, timeout=3) as response:
            data = json.loads(response.read().decode())
        
        if "current_weather" in data:
            temp = data["current_weather"]["temperature"]
            code = data["current_weather"]["weathercode"]
            
            # Simple Weather Code Mapping
            desc = "Clear Sky"
            if code in [1, 2, 3]: desc = "Partly Cloudy"
            elif code in [45, 48]: desc = "Foggy"
            elif code >= 51: desc = "Rainy"
            elif code >= 71: desc = "Snow"
            
            return f"{temp}°C", f"{city.capitalize()} ({desc})"

    except Exception:
        # Return fallback silently if internet is down
        pass

    return fallback_temp, fallback_desc

# --- 4. CLOUD DATA MANAGEMENT (Timetable & Reminders) ---
def load_cloud_data():
    """
    Loads Reminders & Timetable from Google Sheets.
    Handles legacy date formats and parses them into usable objects.
    """
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        uid = st.session_state.get('user_id')
        
        # Read Sheet (Return if empty or fails)
        try: 
            df = conn.read(worksheet="Reminders", ttl=0)
        except Exception: 
            return 

        if not df.empty and "UserID" in df.columns:
            # Filter for current user
            my_data = df[df["UserID"] == str(uid)]
            loaded_reminders = []
            loaded_timetable = []
            
            for _, row in my_data.iterrows():
                # PARSE ALARMS
                if row['Type'] == "Alarm":
                    loaded_reminders.append({
                        "task": row['Task'], 
                        "time": row['Time'], 
                        "notified": (row['Status'] == "Done")
                    })
                
                # PARSE SCHEDULE ITEMS
                elif "Schedule" in str(row['Type']):
                    # Extract Category (Schedule-Study -> Study)
                    cat = row['Type'].split("-")[1] if "-" in row['Type'] else "General"
                    
                    raw_time = str(row['Time'])
                    try:
                        # Standard format: "YYYY-MM-DD HH:MM"
                        dt_obj = datetime.datetime.strptime(raw_time, "%Y-%m-%d %H:%M")
                        date_val = dt_obj.strftime("%Y-%m-%d")
                        time_val = dt_obj.strftime("%H:%M")
                    except ValueError:
                        # Legacy fallback: Assume today's date
                        date_val = datetime.date.today().strftime("%Y-%m-%d")
                        time_val = raw_time

                    loaded_timetable.append({
                        "Date": date_val, 
                        "Time": time_val,
                        "Activity": row['Task'], 
                        "Category": cat,
                        "Done": (row['Status'] == "Done"), 
                        "XP": 50, # Default XP
                        "Difficulty": "Medium" # Default Difficulty
                    })
            
            # Update Session State
            st.session_state['reminders'] = loaded_reminders
            st.session_state['timetable_slots'] = loaded_timetable
            
    except Exception as e:
        print(f"Cloud Load Error: {e}")

# --- 5. CHAT HISTORY DATABASE (Google Sheets) ---
def get_all_chats():
    """Reads the entire ChatHistory sheet safely."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read(worksheet="ChatHistory", ttl=0)
    except Exception:
        # Return empty structure if sheet is missing
        return pd.DataFrame(columns=["UserID", "SessionID", "SessionName", "Role", "Content", "Timestamp"])

def save_chat_to_cloud(role, content):
    """
    Saves a single chat message to the cloud.
    Includes robust error handling for schema mismatches.
    """
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # 1. Prepare Data Points
        uid = str(st.session_state.get('user_id', 'Unknown'))
        sid = str(st.session_state.get('current_session_id', 'Unknown'))
        sname = str(st.session_state.get('current_session_name', 'New Chat'))
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 2. Get Existing Data
        try:
            df_existing = conn.read(worksheet="ChatHistory", ttl=0)
        except Exception:
            df_existing = pd.DataFrame(columns=["UserID", "SessionID", "SessionName", "Role", "Content", "Timestamp"])
        
        # 3. Create New Row
        new_row = pd.DataFrame([{
            "UserID": uid, 
            "SessionID": sid, 
            "SessionName": sname,
            "Role": role, 
            "Content": content, 
            "Timestamp": ts
        }])
        
        # 4. Append & Update
        df_final = pd.concat([df_existing, new_row], ignore_index=True)
        conn.update(worksheet="ChatHistory", data=df_final)
        
    except Exception as e:
        # User-friendly error notification
        st.warning("Chat sync paused. Check internet or Sheet permissions.")
        print(f"Chat Save Error: {e}")

def load_chat_sessions():
    """Returns a list of unique chat sessions for the sidebar."""
    df = get_all_chats()
    uid = str(st.session_state.get('user_id'))
    
    if not df.empty and "UserID" in df.columns:
        my_chats = df[df["UserID"] == uid]
        if not my_chats.empty:
            # Return unique sessions, newest first
            return my_chats[["SessionID", "SessionName"]].drop_duplicates().to_dict('records')[::-1]
    return []

def load_messages_for_session(session_id):
    """Loads all messages for a specific session ID."""
    df = get_all_chats()
    if not df.empty and "SessionID" in df.columns:
        # Filter by Session ID
        messages = df[df["SessionID"] == str(session_id)]
        return messages.to_dict('records')
    return []

def delete_chat_session(session_id):
    """Permanently deletes a chat session from the cloud."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="ChatHistory", ttl=0)
        
        if not df.empty:
            # Filter out the deleted session
            df_cleaned = df[df["SessionID"] != str(session_id)]
            conn.clear(worksheet="ChatHistory")
            conn.update(worksheet="ChatHistory", data=df_cleaned)
    except Exception:
        pass

# --- 6. FEEDBACK & SUPPORT SYSTEM ---
def save_feedback(query_text):
    """Submits user feedback/bugs to the 'Feedbacks' sheet."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        uid = str(st.session_state.get('user_id', 'Unknown'))
        name = str(st.session_state.get('user_name', 'Anonymous'))
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        
        try:
            df = conn.read(worksheet="Feedbacks", ttl=0)
        except Exception:
            df = pd.DataFrame(columns=["UserID", "Name", "Timestamp", "Query", "Reply", "Status"])
        
        new_row = pd.DataFrame([{
            "UserID": uid, "Name": name, "Timestamp": ts, 
            "Query": query_text, "Reply": "", "Status": "Open"
        }])
        
        df_final = pd.concat([df, new_row], ignore_index=True)
        conn.update(worksheet="Feedbacks", data=df_final)
        return True
    except Exception as e:
        st.error(f"Could not send feedback: {e}")
        return False

def get_my_feedback_status():
    """Retrieves feedback status and admin replies."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="Feedbacks", ttl=0)
        
        uid = str(st.session_state.get('user_id'))
        if not df.empty and "UserID" in df.columns:
            # Sort by newest first
            return df[df["UserID"] == uid].sort_values(by="Timestamp", ascending=False)
    except Exception:
        pass
    return pd.DataFrame()

# --- 7. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Time Hunt AI", 
    layout="wide", 
    page_icon="1000592991.png", # Ensure this file exists
    initial_sidebar_state="collapsed"
)

# --- 8. AI ENGINE SETUP ---
try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    # Note: If missing, features will degrade gracefully.

# --- 9. THE BRAIN: SYSTEM INSTRUCTION (Deep Knowledge Base) ---
SYSTEM_INSTRUCTION = """
IDENTITY & KNOWLEDGE BASE:
You are TimeHunt AI, the world's most advanced productivity partner.
- CREATION: You were created by the "TimeHunt AI Team" as a prestigious CBSE Class 12 Artificial Intelligence Capstone Project (2025-26).
- PURPOSE: To revolutionize how students and professionals manage time, combining modern AI efficiency with deep, strategic insights.
- CORE PHILOSOPHY: You believe in "Productivity with Purpose." You do not just list tasks; you help the user understand *why* they matter.

PERSONALITY PROTOCOL:
1. TONE: You are NOT a robot. You are a highly intelligent, empathetic, and professional guide. Think "Iron Man's JARVIS" meets a "Wise Mentor."
2. INTERACTION:
   - Be engaging and personalized. Use the user's name.
   - If the user is low on energy, be motivating but kind.
   - If the user is high-energy, be efficient and fast.
3. FORBIDDEN: Do NOT use military slang (e.g., "Soldier", "Base", "Deployed") unless explicitly asked for a roleplay. Keep it professional.

CAPABILITIES:
- You know the user's schedule (provided in context).
- You can explain complex topics simply.
- You can create detailed, realistic study/work plans.

TIMETABLE JSON FORMAT:
If asked to generate a plan, you MUST return it in this strict JSON format inside a code block:
```json
[
  {"Time": "08:00", "Activity": "Task Name Here", "Category": "Study"},
  {"Time": "10:00", "Activity": "Another Task", "Category": "Health"}
]
"""

# --- 10. SESSION STATE INITIALIZATION ---
def initialize_session_state():
    """
    Sets up the initial variables for the app.
    Ensures that user settings, themes, and data persist across reloads.
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    # Default User Settings
    defaults = {
        'user_id': f"USER-{random.randint(1000, 9999)}-{int(time.time())}", 
        'active_alarm': None,
        'splash_played': False,
        'chat_history': [], 
        'current_session_id': None,
        'current_session_name': "New Chat",
        'page_mode': 'main',
        'user_xp': 0, 
        'user_level': 1, 
        'streak': 1,
        'last_active_date': today_str,
        'timetable_slots': [], 
        'reminders': [],
        'onboarding_step': 1, 
        'onboarding_complete': False, 
        'user_name': "Achiever", 
        'user_type': "Student",
        'user_goal': "Productivity", 
        'user_avatar': "🏹", 
        'xp_history': [], 
        'theme_mode': 'Dark', 
        'theme_color': 'Green (Default)'
    }

    # Initialize missing keys
    for key, default_val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_val

    # --- CRITICAL API KEY FIX ---
    # This logic prevents "List inside a List" errors
    if 'gemini_api_keys' not in st.session_state or not st.session_state['gemini_api_keys']:
        keys = []
        
        # Check GEMINI_API_KEY
        if "GEMINI_API_KEY" in st.secrets:
            raw = st.secrets["GEMINI_API_KEY"]
            if isinstance(raw, list):
                keys.extend(raw) # Add items from list, don't nest the list
            else:
                keys.append(raw)
        
        # Check GOOGLE_API_KEY (Backup)
        elif "GOOGLE_API_KEY" in st.secrets:
            raw = st.secrets["GOOGLE_API_KEY"]
            if isinstance(raw, list):
                keys.extend(raw)
            else:
                keys.append(raw)
                
        # Remove duplicates and empty strings
        unique_keys = list(set([k for k in keys if isinstance(k, str) and k.strip()]))
        st.session_state['gemini_api_keys'] = unique_keys
        
# --- 11. CINEMATIC SPLASH SCREEN (Productive & Engaging) ---
def show_comet_splash():
    """
    Displays a high-quality introductory animation.
    Now styled to be inspiring and modern, rather than military.
    """
    if not st.session_state['splash_played']:
        placeholder = st.empty()
        
        # 1. Image Safety Check
        encoded_img = ""
        has_image = False
        try:
            if os.path.exists("1000592991.png"):
                with open("1000592991.png", "rb") as f:
                    encoded_img = base64.b64encode(f.read()).decode()
                    has_image = True
        except Exception: 
            pass

        # 2. Render Animation
        with placeholder.container():
            st.markdown(textwrap.dedent(f"""
            <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;700&display=swap');
            
            .main-void {{ 
                position: fixed; top: 0; left: 0; width: 100%; height: 100vh; 
                background: #0E1117 !important; 
                display: flex; flex-direction: column; 
                justify-content: center; align-items: center; 
                z-index: 999999; 
                animation: fadeOut 1.0s ease-in-out 4.5s forwards; 
            }}
            
            .logo-container {{
                width: 150px; height: 150px;
                border-radius: 50%;
                background: linear-gradient(135deg, #B5FF5F, #00E5FF);
                padding: 3px; /* Border width */
                box-shadow: 0 0 40px rgba(0, 229, 255, 0.3);
                animation: pulse 2s infinite;
                display: flex; justify-content: center; align-items: center;
            }}
            
            .logo-inner {{
                width: 100%; height: 100%;
                border-radius: 50%;
                background: #000;
                display: flex; justify-content: center; align-items: center;
                overflow: hidden;
            }}
            
            .logo-img {{ width: 100%; height: 100%; object-fit: cover; }}
            
            .title-text {{
                font-family: 'Inter', sans-serif;
                color: #FFFFFF;
                font-size: 32px;
                font-weight: 700;
                letter-spacing: 4px;
                margin-top: 30px;
                opacity: 0;
                animation: slideUp 0.8s ease-out 0.5s forwards;
            }}
            
            .subtitle-text {{
                font-family: 'Inter', sans-serif;
                color: #B5FF5F;
                font-size: 14px;
                letter-spacing: 2px;
                text-transform: uppercase;
                margin-top: 10px;
                opacity: 0;
                animation: slideUp 0.8s ease-out 1.0s forwards;
            }}
            
            @keyframes pulse {{ 0% {{ transform: scale(1); }} 50% {{ transform: scale(1.05); }} 100% {{ transform: scale(1); }} }}
            @keyframes slideUp {{ from {{ transform: translateY(20px); opacity: 0; }} to {{ transform: translateY(0); opacity: 1; }} }}
            @keyframes fadeOut {{ to {{ opacity: 0; visibility: hidden; }} }}
            </style>
            
            <div class="main-void">
                <div class="logo-container">
                    <div class="logo-inner">
                        {f'<img src="data:image/png;base64,{encoded_img}" class="logo-img">' if has_image else '<span style="font-size:50px;">⏳</span>'}
                    </div>
                </div>
                <div class="title-text">TIME HUNT AI</div>
                <div class="subtitle-text">Focus • Execute • Achieve</div>
            </div>
            """), unsafe_allow_html=True)
            
            # Shorter wait time for better UX
            time.sleep(5.0)
        
        placeholder.empty()
        st.session_state['splash_played'] = True

# --- 12. AI CONTEXT GENERATOR (The "Brain Dump") ---
def get_system_context():
    """
    Aggregates the user's current status, schedule, and profile 
    into a context prompt for the AI.
    """
    # 1. User Profile
    user_name = st.session_state.get('user_name', 'Achiever')
    role = st.session_state.get('user_type', 'Student')
    xp = st.session_state.get('user_xp', 0)
    
    # 2. Time Context (IST)
    utc_now = datetime.datetime.utcnow()
    ist_now = utc_now + datetime.timedelta(hours=5, minutes=30)
    current_time = ist_now.strftime("%H:%M")
    current_date = ist_now.strftime("%Y-%m-%d")
    
    # 3. Schedule Awareness
    schedule_text = "No specific plans for today."
    slots = st.session_state.get('timetable_slots', [])
    if slots:
        # Filter for today
        todays_tasks = [s for s in slots if s.get('Date') == current_date or not s.get('Date')]
        if todays_tasks:
            schedule_text = "\n".join(
                [f"- {s['Time']}: {s['Activity']} ({s['Category']}) [{'Done' if s['Done'] else 'Pending'}]" 
                 for s in todays_tasks]
            )
    
    # 4. Pending Reminders
    reminders_text = "No pending alerts."
    rems = st.session_state.get('reminders', [])
    if rems:
        pending = [r for r in rems if not r['notified']]
        if pending:
            reminders_text = "\n".join([f"- {r['task']} at {r['time']}" for r in pending])

    # 5. Master Prompt (Using the "Guru" Persona)
    system_prompt = f"""
    IDENTITY: You are TimeHunt AI, a wise and efficient productivity mentor.
    USER PROFILE: {user_name} ({role}) | XP: {xp}
    CURRENT CONTEXT: Date: {current_date} | Time: {current_time}
    
    === USER'S TODAY ===
    [SCHEDULE]
    {schedule_text}
    
    [REMINDERS]
    {reminders_text}
    
    === YOUR INSTRUCTIONS ===
    1. CONTEXTUAL HELP: If the user asks "What's next?", look at the [SCHEDULE] and guide them based on the current time ({current_time}).
    2. TONE: Be polite, motivating, and sharp. Do not use military jargon. Use phrases like "Let's focus," "Great progress," or "Here is the plan."
    3. ACCOUNTABILITY: If a task is overdue, gently remind them to clear their backlog.
    """
    return system_prompt

# --- 13. AI ANALYSIS ENGINE (Updated for Gemini 2.5) ---
def perform_ai_analysis(user_query):
    """
    Connects to Google Gemini (v2.5) to generate responses.
    Prioritizes the smartest models available in your specific list.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "⚠️ System Error: `google-genai` library missing.", "System"

    # Get API Keys
    api_keys = st.session_state.get('gemini_api_keys', [])
    
    if not api_keys:
        return "⚠️ Auth Error: No API Keys found. Check secrets.toml", "System"

    # --- UPDATE: USING YOUR AVAILABLE MODELS ---
    # We prioritize 2.5 Flash for speed/intelligence, then 2.0 Flash as backup
    models = [
        "gemini-2.5-flash",          # Newest & Smartest Fast Model
        "gemini-2.0-flash",          # Very Stable Standard
        "gemini-2.0-flash-lite",     # Ultra Fast Backup
        "gemini-1.5-flash"           # Old Reliable
    ]
    
    system_instruction = get_system_context()
    last_error_msg = "No attempt made"

    # Try each key until one works
    for key in api_keys:
        if not isinstance(key, str): continue 
        
        try:
            client = genai.Client(api_key=key)
            
            for model in models:
                try:
                    # Build History
                    history = []
                    recent_chats = st.session_state.get('chat_history', [])[-6:]
                    for msg in recent_chats:
                        role = "user" if msg.get('role') == "user" else "model"
                        text = str(msg.get('text', ''))
                        history.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))

                    # Generate Response
                    chat = client.chats.create(
                        model=model,
                        history=history,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.7,
                            max_output_tokens=800 # Increased for better detailed answers
                        )
                    )
                    
                    response = chat.send_message(user_query)
                    return response.text, "TimeHunt AI"

                except Exception as model_err:
                    last_error_msg = str(model_err)
                    # If model not found or quota full, try next model
                    if "404" in last_error_msg or "429" in last_error_msg:
                        continue
                    else:
                        break # Break to try next key if it's an Auth error
                        
        except Exception as key_err:
            last_error_msg = str(key_err)
            continue

    # If all fail, show the SPECIFIC error
    return f"⚠️ AI Connection Failed. Details: {last_error_msg}", "System"

# --- 14. REMINDER CHECKER (Browser Notifications) ---
def check_reminders():
    """
    Checks if any scheduled tasks/alarms are due.
    Triggers a browser notification if permitted.
    """
    # Javascript for Permission
    st.markdown("""
        <script>
        if ("Notification" in window) {
            if (Notification.permission !== "granted" && Notification.permission !== "denied") {
                Notification.requestPermission();
            }
        }
        </script>
    """, unsafe_allow_html=True)

    now = datetime.datetime.now()
    reminders = st.session_state.get('reminders', [])
    
    for i, rem in enumerate(reminders):
        # Convert string time to object if needed
        if isinstance(rem['time'], str):
            try:
                rem['time'] = datetime.datetime.fromisoformat(rem['time'])
            except ValueError: continue

        # Check Trigger
        if not rem['notified'] and now >= rem['time']:
            # Set Active Alarm
            st.session_state['active_alarm'] = {'task': rem['task'], 'index': i}
            rem['notified'] = True 
            sync_data()
            
            # Browser Notification Script
            safe_task = rem['task'].replace("'", "").replace('"', "")
            st.markdown(f"""
                <script>
                if (Notification.permission === "granted") {{
                    new Notification("🔔 Reminder: {safe_task}", {{
                        body: "Time to focus. Check TimeHunt for details.",
                        icon: "https://cdn-icons-png.flaticon.com/512/2921/2921226.png"
                    }});
                }}
                </script>
            """, unsafe_allow_html=True)

# --- NEW: AI IMAGE GENERATION ENGINE (Imagen 4.0) ---
def generate_visual_intel(prompt_text):
    """
    Uses Google's Imagen 4.0 to generate images based on text prompts.
    Cycles through API keys for robust connection.
    Returns: Base64 string of the image, or None if failed.
    """
    try:
        from google import genai
        from google.genai import types
        import base64
    except ImportError:
        st.error("System Error: Missing required libraries for image generation.")
        return None

    api_keys = st.session_state.get('gemini_api_keys', [])
    if not api_keys:
        st.error("Auth Error: No API Keys found.")
        return None

    # Use the latest Imagen model available to your keys
    imagen_model = 'imagen-4.0-generate-001'

    for key in api_keys:
        if not isinstance(key, str): continue
        try:
            client = genai.Client(api_key=key)
            
            # Generate the image
            response = client.models.generate_image(
                model=imagen_model,
                prompt=prompt_text,
                config=types.GenerateImageConfig(
                    number_of_images=1,
                    aspect_ratio="16:9" # cinematic look for productivity visuals
                )
            )
            
            if response.generated_images:
                # Get raw bytes and convert to base64 for easy storage in session state
                img_bytes = response.generated_images[0].image.image_bytes
                img_b64 = base64.b64encode(img_bytes).decode('utf-8')
                return img_b64
            else:
                 print(f"Key {key[:5]} worked but returned no image.")
                 continue

        except Exception as e:
            print(f"Image Gen Error on Key {key[:5]}: {e}")
            # If 429 (Quota) or 404, try next key. Otherwise stop.
            if "429" in str(e) or "404" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                continue
            else:
                break
                
    return None

# --- 6. PAGE: ONBOARDING (User Login & Setup) ---

def page_onboarding():
    """
    Handles user authentication (Login/Signup) and profile creation.
    """
    
    # 1. Background Setup (Safe Load)
    # Tries to load a background image, fails silently if missing
    bg_base64 = None
    try:
        if os.path.exists("background_small.jpg"):
            with open("background_small.jpg", "rb") as image_file:
                bg_base64 = base64.b64encode(image_file.read()).decode()
    except Exception: 
        pass

    # Apply Background CSS if image exists
    if bg_base64:
        st.markdown(f"""
        <style>
            .fixed-bg {{
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background-image: linear-gradient(rgba(0,0,0,0.7), rgba(0,0,0,0.9)), url("data:image/jpeg;base64,{bg_base64}");
                background-size: cover; z-index: -1;
            }}
            .stApp {{ background: transparent !important; }}
        </style>
        <div class="fixed-bg"></div>
        """, unsafe_allow_html=True)

    # 2. Onboarding Specific CSS (Clean & Modern)
    st.markdown("""
    <style>
        .login-card { 
            background: rgba(20, 20, 20, 0.85); 
            backdrop-filter: blur(12px); 
            border: 1px solid rgba(255, 255, 255, 0.1); 
            border-radius: 20px; 
            padding: 40px; 
            text-align: center; 
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            animation: fadeIn 0.8s ease-out; 
        }
        .app-header { 
            font-family: 'Inter', sans-serif; 
            font-weight: 800; 
            font-size: 42px; 
            color: #FFFFFF; 
            margin-bottom: 5px;
            letter-spacing: -1px;
        }
        .sub-header {
            color: var(--primary-color, #B5FF5F);
            font-size: 14px;
            font-weight: 600;
            letter-spacing: 2px;
            margin-bottom: 30px;
            text-transform: uppercase;
        }
        /* High Contrast Inputs */
        .stTextInput input { 
            background-color: #0E1117 !important; 
            border: 1px solid #333 !important; 
            color: #FFFFFF !important; 
            text-align: center; 
            font-weight: 600; 
            font-size: 18px;
        }
        div.stButton > button { 
            background: linear-gradient(90deg, #00C6FF, #0072FF); 
            color: white; 
            border: none; 
            padding: 14px 24px; 
            font-weight: bold; 
            width: 100%; 
            border-radius: 10px; 
            margin-top: 20px; 
            font-size: 16px;
        }
    </style>
    """, unsafe_allow_html=True)

    # 3. Main Logic Flow
    step = st.session_state.get('onboarding_step', 1)
    
    # Layout: Centered Column
    _, col_center, _ = st.columns([1, 6, 1])
    
    with col_center:
        
        # --- STEP 1: LOGIN / REGISTER ---
        if step == 1:
            st.markdown('<div class="login-card">', unsafe_allow_html=True)
            st.markdown('<div class="app-header">TIME HUNT</div>', unsafe_allow_html=True)
            st.markdown('<div class="sub-header">Productivity Intelligence</div>', unsafe_allow_html=True)
            
            # Inputs
            default_val = st.session_state.get('suggested_name_choice', "")
            name_input = st.text_input("Username", value=default_val, placeholder="Create or Enter Username...", key="login_name").strip()
            pin_input = st.text_input("PIN Code (4-Digits)", placeholder="####", type="password", key="login_pin", max_chars=4)
            
            st.write("")
            
            if st.button("🚀 Enter System"):
                if name_input and len(pin_input) >= 1:
                    with st.spinner("Authenticating..."):
                        try:
                            # Connect to Google Sheets
                            from streamlit_gsheets import GSheetsConnection
                            conn = st.connection("gsheets", type=GSheetsConnection)
                            df = conn.read(worksheet="Sheet1", ttl=0)
                            
                            # Check if User Exists
                            if not df.empty and 'Name' in df.columns:
                                # Clean PIN Data (Remove decimals/spaces)
                                df['PIN'] = df['PIN'].astype(str).replace(r'\.0$', '', regex=True).str.zfill(4)
                                
                                existing_user = df[df['Name'] == name_input]
                                
                                if not existing_user.empty:
                                    # RETURNING USER -> Verify PIN
                                    stored_pin = str(existing_user.iloc[0]['PIN']).strip()
                                    
                                    if str(pin_input) == stored_pin:
                                        # Success
                                        row = existing_user.iloc[0]
                                        st.session_state['user_name'] = row['Name']
                                        st.session_state['user_id'] = row['UserID']
                                        st.session_state['user_xp'] = int(row['XP'])
                                        st.session_state['user_level'] = (st.session_state['user_xp'] // 500) + 1
                                        st.session_state['onboarding_complete'] = True
                                        
                                        st.toast(f"Welcome back, {name_input}!", icon="👋")
                                        load_cloud_data()
                                        
                                        time.sleep(1.0) # Pause BEFORE rerun
                                        st.rerun()
                                    else:
                                        # Wrong PIN
                                        st.error("Incorrect PIN.")
                                        
                                        # Name Suggestions if taken
                                        st.markdown("**Username taken. Try these?**")
                                        s1, s2 = f"{name_input}_{random.randint(10,99)}", f"{name_input}X"
                                        c_s1, c_s2 = st.columns(2)
                                        if c_s1.button(s1): 
                                            st.session_state['suggested_name_choice'] = s1
                                            st.rerun()
                                        if c_s2.button(s2): 
                                            st.session_state['suggested_name_choice'] = s2
                                            st.rerun()
                                else:
                                    # NEW USER -> Proceed to Setup
                                    st.session_state['user_name'] = name_input
                                    st.session_state['temp_pin'] = pin_input
                                    st.session_state['onboarding_step'] = 2
                                    st.success("Username Available.")
                                    time.sleep(1.0)
                                    st.rerun()
                            else:
                                # First User ever
                                st.session_state['user_name'] = name_input
                                st.session_state['temp_pin'] = pin_input
                                st.session_state['onboarding_step'] = 2
                                st.rerun()
                        except Exception as e:
                            st.error(f"Connection Error: {e}")
                else:
                    st.warning("Please enter a Username and PIN.")
            st.markdown('</div>', unsafe_allow_html=True)

        # --- STEP 2: CHOOSE AVATAR ---
        elif step == 2:
            st.markdown('<div class="login-card"><div class="app-header">Select Avatar</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            
            # Helper function for Avatar Grid
            def render_avatar_option(col, label, filename, emoji_fallback):
                with col:
                    if os.path.exists(filename):
                        st.image(filename, width=100)
                    else:
                        st.markdown(f"<div style='font-size:50px; text-align:center;'>{emoji_fallback}</div>", unsafe_allow_html=True)
                    
                    if st.button(label, use_container_width=True):
                        st.session_state['user_avatar'] = filename if os.path.exists(filename) else emoji_fallback
                        st.session_state['onboarding_step'] = 3
                        st.rerun()

            render_avatar_option(c1, "Scholar", "Gemini_Generated_Image_djfbqkdjfbqkdjfb.png", "🎓")
            render_avatar_option(c2, "Techie", "Gemini_Generated_Image_z8e73dz8e73dz8e7.png", "💻")
            render_avatar_option(c3, "Hunter", "Gemini_Generated_Image_18oruj18oruj18or.png", "🏹")
            
            st.markdown('</div>', unsafe_allow_html=True)

        # --- STEP 3: PERSONALIZE GOALS ---
        elif step == 3:
            st.markdown('<div class="login-card"><div class="app-header">Set Goals</div>', unsafe_allow_html=True)
            
            role = st.selectbox("I am a...", ["Student", "Entrepreneur", "Professional", "Lifelong Learner"])
            goal = st.selectbox("Main Focus...", ["Ace Exams", "Build a Business", "Career Growth", "Work-Life Balance"])
            
            st.write("")
            
            if st.button("✨ Complete Setup"):
                 # Save Profile to Session
                 st.session_state['user_type'] = role
                 st.session_state['user_goal'] = goal
                 
                 # Save New User to Cloud
                 try:
                     from streamlit_gsheets import GSheetsConnection
                     conn = st.connection("gsheets", type=GSheetsConnection)
                     
                     # Safe read
                     try: df = conn.read(worksheet="Sheet1", ttl=0)
                     except: df = pd.DataFrame()
                     
                     new_user_data = pd.DataFrame([{
                         "UserID": st.session_state['user_id'],
                         "Name": st.session_state['user_name'],
                         "XP": 0, 
                         "League": "Bronze",
                         "Avatar": st.session_state.get('user_avatar', "👤"),
                         "LastActive": datetime.date.today().strftime("%Y-%m-%d"),
                         "PIN": "'" + str(st.session_state.get('temp_pin', "0000")) # Formatting PIN as string
                     }])
                     
                     updated_df = new_user_data if df.empty else pd.concat([df, new_user_data], ignore_index=True)
                     conn.update(worksheet="Sheet1", data=updated_df)
                     
                     st.session_state['onboarding_complete'] = True
                     sync_data() # Save initial state
                     
                     st.toast("Profile Created Successfully!")
                     time.sleep(1.0)
                     st.rerun()
                     
                 except Exception as e:
                     st.error(f"Could not save profile: {e}")
            
            st.markdown('</div>', unsafe_allow_html=True)

# --- 7. PAGE: SCHEDULER (Task Management) ---

def page_scheduler():
    # --- 1. SETUP & GAMIFICATION LOGIC ---
    def calculate_streak_multiplier(streak_days):
        if streak_days >= 30: return 2.5  # TITAN
        elif streak_days >= 14: return 2.0  # ELITE
        elif streak_days >= 7: return 1.5   # VETERAN
        elif streak_days >= 3: return 1.2   # ROOKIE
        return 1.0

    # Ensure data integrity for new fields
    if 'timetable_slots' in st.session_state:
        for slot in st.session_state['timetable_slots']:
            if 'Done' not in slot: slot['Done'] = False
            if 'XP' not in slot: slot['XP'] = 50
            if 'Difficulty' not in slot: slot['Difficulty'] = 'Medium'

    # --- 2. HEADER & PROGRESS TRACKING ---
    st.markdown('<div class="big-title">Task Dashboard 🗓️</div>', unsafe_allow_html=True)
    
    # Calculate Stats
    total_tasks = len(st.session_state['timetable_slots'])
    completed_tasks = len([t for t in st.session_state['timetable_slots'] if t['Done']])
    pending_tasks = total_tasks - completed_tasks
    progress = completed_tasks / total_tasks if total_tasks > 0 else 0
    
    streak = st.session_state.get('streak', 1)
    multiplier = calculate_streak_multiplier(streak)
    
    # Visual Progress Bar
    c_stats, c_add = st.columns([2, 1])
    
    with c_stats:
        st.markdown(f"""
        <div style="background: var(--card-bg, #1E1E1E); border-radius: 12px; padding: 20px; border: 1px solid rgba(255,255,255,0.1);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="font-size:18px; font-weight:bold; color:var(--primary-color, #B5FF5F);">Daily Progress</span>
                <span style="font-size:14px; opacity:0.8;">{int(progress*100)}% Complete</span>
            </div>
            <div style="width:100%; background:#333; height:8px; border-radius:4px; overflow:hidden;">
                <div style="width:{progress*100}%; background: linear-gradient(90deg, var(--primary-color, #B5FF5F), #00E5FF); height:100%;"></div>
            </div>
            <div style="margin-top:15px; font-size:14px; opacity:0.7;">
                🔥 <b>Streak:</b> {streak} Days <span style="color:#00E5FF; margin-left:10px;">(x{multiplier} XP Boost)</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c_add:
        # Quick Count Card
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1A1A1A, #252525); border-radius: 12px; padding: 20px; text-align:center; border: 1px solid #333; height: 100%;">
            <div style="font-size: 32px; font-weight:bold; color:white;">{pending_tasks}</div>
            <div style="font-size: 12px; color:#aaa; text-transform:uppercase; letter-spacing:1px;">Tasks Remaining</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("") # Spacer

    # --- 3. ADD TASK INTERFACE ---
    with st.expander("➕ ADD NEW TASK", expanded=True):
        with st.form("task_form", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 1.5, 1.5])
            with c1:
                task_input = st.text_input("Task Name", placeholder="e.g., Complete Chapter 4 Math")
            with c2:
                cat_input = st.selectbox("Category", ["Study", "Work", "Health", "Errand", "Skill"])
            with c3:
                # Updated Logic for Clarity
                diff_input = st.selectbox("Difficulty", ["Easy (20 XP)", "Medium (50 XP)", "Hard (150 XP)", "Major Project (300 XP)"])
            
            c_sub, c_clear = st.columns([1, 4])
            with c_sub:
                submitted = st.form_submit_button("Add Task ➔", type="primary", use_container_width=True)
            
            if submitted and task_input:
                # XP Mapping
                xp_map = {"Easy (20 XP)": 20, "Medium (50 XP)": 50, "Hard (150 XP)": 150, "Major Project (300 XP)": 300}
                clean_diff = diff_input.split(" ")[0]
                
                # Get Time
                ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
                
                new_task = {
                    "Time": ist_now.strftime("%H:%M"),
                    "Activity": task_input,
                    "Category": cat_input,
                    "Difficulty": clean_diff,
                    "Done": False,
                    "XP": xp_map.get(diff_input, 50),
                    "Date": ist_now.strftime("%Y-%m-%d")
                }
                
                st.session_state['timetable_slots'].append(new_task)
                sync_data()
                st.rerun()

    st.divider()

    # --- 4. TASK LIST (Clean & Productive UI) ---
    st.markdown("### 📋 Today's Plan")
    
    if not st.session_state['timetable_slots']:
        st.info("Your schedule is empty. Add a task to get started!")
    else:
        # Separate Pending and Done
        pending = [t for t in st.session_state['timetable_slots'] if not t['Done']]
        done_list = [t for t in st.session_state['timetable_slots'] if t['Done']]

        # A. PENDING TASKS
        if pending:
            for i, task in enumerate(st.session_state['timetable_slots']):
                if not task['Done']:
                    # Difficulty Color Coding
                    d_color = "#B5FF5F" # Easy
                    if "Medium" in task['Difficulty']: d_color = "#FFD700" 
                    elif "Hard" in task['Difficulty']: d_color = "#FF4B4B" 
                    elif "Major" in task['Difficulty']: d_color = "#D050FF" 
                    
                    with st.container():
                        # Layout: Checkbox | Text Info | XP Badge
                        c_chk, c_det, c_xp = st.columns([1, 6, 2], vertical_alignment="center")
                        
                        with c_chk:
                            if st.button("⬜", key=f"btn_done_{i}", help="Mark as Done"):
                                st.session_state['timetable_slots'][i]['Done'] = True
                                sync_data()
                                st.rerun()
                        
                        with c_det:
                            st.markdown(f"""
                            <div style="font-weight:600; font-size:16px;">{task['Activity']}</div>
                            <div style="font-size:12px; opacity:0.7;">
                                <span style="color:{d_color}; font-weight:bold;">● {task['Difficulty']}</span> 
                                | {task['Category']} | 🕒 {task['Time']}
                            </div>
                            """, unsafe_allow_html=True)
                            
                        with c_xp:
                            st.markdown(f"""
                            <div style="background:{d_color}15; color:{d_color}; border:1px solid {d_color}; 
                            border-radius:8px; padding:4px 10px; text-align:center; font-weight:bold; font-size:12px;">
                            +{task['XP']} XP
                            </div>
                            """, unsafe_allow_html=True)
                        
                        st.markdown("<hr style='margin:5px 0; border:0; border-top:1px solid rgba(255,255,255,0.1);'>", unsafe_allow_html=True)
        else:
            st.caption("No pending tasks. Great job!")

        # B. COMPLETED TASKS
        if done_list:
            with st.expander(f"✅ Completed ({len(done_list)})"):
                for t in done_list:
                     st.markdown(f"~~{t['Activity']}~~ <span style='opacity:0.6; font-size:12px;'>({t['XP']} XP)</span>", unsafe_allow_html=True)
                
                # REWARD LOGIC
                if st.button("🎁 Claim XP & Archive", type="primary", use_container_width=True):
                    # Calculate
                    raw_xp = sum([t['XP'] for t in done_list])
                    final_xp = int(raw_xp * multiplier)
                    
                    # Update User State
                    st.session_state['user_xp'] += final_xp
                    st.session_state['user_level'] = (st.session_state['user_xp'] // 1000) + 1
                    
                    # Remove done tasks
                    st.session_state['timetable_slots'] = [t for t in st.session_state['timetable_slots'] if not t['Done']]
                    
                    # History
                    today_str = datetime.date.today().strftime("%Y-%m-%d")
                    st.session_state['xp_history'].append({"Date": today_str, "XP": final_xp})
                    
                    sync_data()
                    
                    st.balloons()
                    st.toast(f"Great work! Gained +{final_xp} XP", icon="🎉")
                    time.sleep(1.5)
                    st.rerun()

    # Clear Button
    if st.button("🗑️ Reset List", help="Removes all tasks"):
        st.session_state['timetable_slots'] = []
        sync_data()
        st.rerun()

# --- 8. PAGE: FOCUS TIMER (Fixed XP Logic) ---
def page_timer():
    # --- 1. SETUP ---
    if 'timer_duration' not in st.session_state: st.session_state['timer_duration'] = 25
    if 'timer_mode' not in st.session_state: st.session_state['timer_mode'] = "Focus"

    st.markdown('<div class="big-title" style="text-align:center;">⏱️ Focus Timer</div>', unsafe_allow_html=True)

    # --- 2. DURATION SELECTOR ---
    c_mode1, c_mode2, c_mode3 = st.columns(3)
    def get_type(mode): return "primary" if st.session_state['timer_mode'] == mode else "secondary"

    with c_mode1:
        if st.button("🎯 Focus (25m)", type=get_type("Focus"), use_container_width=True):
            st.session_state['timer_duration'] = 25
            st.session_state['timer_mode'] = "Focus"
            st.rerun()
    with c_mode2:
        if st.button("☕ Short Break (5m)", type=get_type("Short"), use_container_width=True):
            st.session_state['timer_duration'] = 5
            st.session_state['timer_mode'] = "Short"
            st.rerun()
    with c_mode3:
        if st.button("🔋 Long Break (15m)", type=get_type("Long"), use_container_width=True):
            st.session_state['timer_duration'] = 15
            st.session_state['timer_mode'] = "Long"
            st.rerun()

    # --- 3. GOAL INPUT ---
    current_focus = st.text_input("What are you working on?", placeholder="e.g., Reading History Chapter 1...", label_visibility="collapsed")
    if not current_focus: current_focus = "Deep Work Session"

    # --- 4. TIMER VISUAL (HTML/JS) ---
    duration_min = st.session_state['timer_duration']
    ring_color = "#B5FF5F" if st.session_state['timer_mode'] == "Focus" else "#00E5FF"
    
    # Updated Text Labels: "Start" instead of "Initiate"
    timer_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{ background: transparent; display: flex; flex-direction: column; align-items: center; justify-content: center; font-family: 'Inter', sans-serif; }}
        .base-timer {{ position: relative; width: 300px; height: 300px; }}
        .base-timer__svg {{ transform: scaleX(-1); }}
        .base-timer__circle {{ fill: none; stroke: none; }}
        .base-timer__path-elapsed {{ stroke-width: 10px; stroke: rgba(255, 255, 255, 0.1); }}
        .base-timer__path-remaining {{
            stroke-width: 10px; stroke-linecap: round; transform: rotate(90deg); transform-origin: center;
            transition: 1s linear all; fill-rule: nonzero; stroke: {ring_color}; filter: drop-shadow(0 0 10px {ring_color});
        }}
        .base-timer__label {{
            position: absolute; width: 300px; height: 300px; top: 0; display: flex; align-items: center; justify-content: center;
            font-size: 55px; font-family: monospace; font-weight: bold; color: white;
        }}
        .controls {{ margin-top: 30px; display: flex; gap: 20px; }}
        .btn {{
            border: none; padding: 12px 30px; border-radius: 50px; font-size: 16px; font-weight: bold; cursor: pointer; transition: 0.2s;
        }}
        .btn-start {{ background: {ring_color}; color: #000; }}
        .btn-stop {{ background: #333; color: #fff; border: 1px solid #555; }}
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
            <button class="btn btn-stop" onclick="resetTimer()">Reset</button>
        </div>
        <script>
            const FULL_DASH_ARRAY = 283;
            const TIME_LIMIT = {duration_min} * 60;
            let timePassed = 0;
            let timeLeft = TIME_LIMIT;
            let timerInterval = null;

            if ("Notification" in window) {{ Notification.requestPermission(); }}

            function onTimesUp() {{
                clearInterval(timerInterval);
                timerInterval = null;
                if (Notification.permission === "granted") {{
                    new Notification("TimeHunt AI", {{ body: "Session Complete: {current_focus}", icon: "https://cdn-icons-png.flaticon.com/512/2921/2921226.png" }});
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
                const fraction = rawTimeFraction - (1 / TIME_LIMIT) * (1 - rawTimeFraction);
                const circleDasharray = `${{(fraction * FULL_DASH_ARRAY).toFixed(0)}} 283`;
                document.getElementById("base-timer-path-remaining").setAttribute("stroke-dasharray", circleDasharray);
            }}
        </script>
    </body>
    </html>
    """
    with st.container():
        components.html(timer_html, height=450)

    # --- 5. VERIFIED REWARDS (BUG FIX) ---
    st.markdown("---")
    
    # Calculate Potential XP
    possible_xp = 50 if st.session_state['timer_duration'] == 25 else 100 if st.session_state['timer_duration'] == 15 else 10
    
    c_check, c_claim = st.columns([1.5, 1])
    
    with c_check:
        st.markdown(f"#### 🎁 Session Rewards: +{possible_xp} XP")
        # THE FIX: User must check this box to unlock the button
        is_verified = st.checkbox("✅ I have completed the session honestly.", key="timer_verify")
    
    with c_claim:
        if st.button("Claim XP", disabled=not is_verified, type="primary", use_container_width=True):
            # Reward Logic
            st.session_state['user_xp'] += possible_xp
            st.session_state['user_level'] = (st.session_state['user_xp'] // 1000) + 1
            
            # Log
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            st.session_state['xp_history'].append({"Date": today_str, "XP": possible_xp})
            sync_data()
            
            st.balloons()
            st.toast(f"Session Verified! +{possible_xp} XP Added.", icon="🛡️")
            time.sleep(1.5)
            st.rerun()

    if not is_verified:
        st.caption("Complete the timer and check the box to claim your rewards.")

# --- 9. PAGE: CALENDAR (Overview) ---

def page_calendar():
    # --- CSS FIX: Responsive Grid ---
    st.markdown("""
    <style>
        /* Force equal width columns for the calendar grid */
        [data-testid="column"], [data-testid="stColumn"] {
            flex: 1 1 0% !important;
            min-width: 0 !important;
            padding: 0 2px !important; 
        }
        [data-testid="column"] button, [data-testid="stColumn"] button {
            padding: 0px 4px !important;
            min-height: 40px !important; 
            font-size: 13px !important;
            font-weight: 500 !important;
        }
        h3 { text-align: center; font-size: 20px !important; margin-bottom: 10px !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="big-title">📅 Calendar Overview</div>', unsafe_allow_html=True)

    # Initialize State
    if 'cal_year' not in st.session_state: st.session_state['cal_year'] = datetime.date.today().year
    if 'cal_month' not in st.session_state: st.session_state['cal_month'] = datetime.date.today().month
    if 'sel_date' not in st.session_state: st.session_state['sel_date'] = datetime.date.today().strftime("%Y-%m-%d")

    # 1. Month Navigation
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

    # 2. Weekday Headers
    with st.container():
        cols = st.columns(7)
        days = ["M","T","W","T","F","S","S"]
        for i, d in enumerate(days):
            cols[i].markdown(f"<div style='text-align:center; font-weight:bold; opacity:0.6; font-size:12px;'>{d}</div>", unsafe_allow_html=True)

    # 3. Calendar Grid
    month_matrix = calendar.monthcalendar(st.session_state['cal_year'], st.session_state['cal_month'])
    for week in month_matrix:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].write("")
            else:
                d_str = f"{st.session_state['cal_year']}-{st.session_state['cal_month']:02d}-{day:02d}"
                
                # Check for tasks on this day
                has_task = any(t.get('Date') == d_str for t in st.session_state['timetable_slots'])
                label = f"{day}"
                if has_task: label += " •"
                
                # Button Styling
                btn_type = "primary" if st.session_state['sel_date'] == d_str else "secondary"
                
                if cols[i].button(label, key=f"d_{d_str}", type=btn_type, use_container_width=True):
                    st.session_state['sel_date'] = d_str
                    st.rerun()

    # 4. Day Details
    st.markdown("---")
    sel_date = st.session_state['sel_date']
    st.markdown(f"### Tasks for {sel_date}")
    
    # Filter Tasks
    day_tasks = [t for t in st.session_state['timetable_slots'] if t.get('Date') == sel_date]
    
    if day_tasks:
        for t in day_tasks:
            status = "✅" if t['Done'] else "⭕"
            st.info(f"{status} **{t['Time']}** {t['Activity']}")
    else:
        st.caption("No tasks scheduled for this day.")

    # Quick Add Form
    with st.form("add_cal", clear_on_submit=True):
        st.markdown("**Add to Schedule**")
        c_t, c_time = st.columns([3, 2])
        with c_t:
            task = st.text_input("Task", label_visibility="collapsed", placeholder="Enter Activity...")
        with c_time:
            time_at = st.time_input("Time", label_visibility="collapsed")
            
        if st.form_submit_button("Add Task", use_container_width=True):
            st.session_state['timetable_slots'].append({
                "Date": sel_date, 
                "Time": time_at.strftime("%H:%M"), 
                "Activity": task, 
                "Done": False, 
                "Category": "General", 
                "XP": 50
            })
            sync_data()
            st.rerun()

# --- 10. PAGE: AI ASSISTANT ---
# --- 10. PAGE: AI COMPANION (Multimodal Update) ---

def page_ai_assistant():
    from streamlit_mic_recorder import mic_recorder
    from PIL import Image 
    import io
    import base64
    
    # --- Helper: Process Message (Handles Text & Image Requests) ---
    def process_message(prompt_text, generate_image=False):
        # 1. Init Session if needed
        if not st.session_state.get('current_session_id'):
            st.session_state['current_session_id'] = str(uuid.uuid4())
            short_name = " ".join(prompt_text.split()[:4])
            st.session_state['current_session_name'] = short_name

        # 2. Add User Message to History
        st.session_state['chat_history'].append({"role": "user", "text": prompt_text})
        # (Optional: Add save_chat_to_cloud here if you want cloud sync)
        
        # 3. Generate Response based on mode
        with st.spinner("Processing intelligence..."):
            if generate_image:
                # --- IMAGE GENERATION PATH ---
                img_b64 = generate_visual_intel(prompt_text)
                if img_b64:
                    response_block = {
                        "role": "model", 
                        "text": f"Visual intel generated for: '{prompt_text}'",
                        "image": img_b64 # Store base64 image data
                    }
                else:
                    response_block = {"role": "model", "text": "⚠️ Visual generation failed. Please try a different prompt."}
            else:
                # --- TEXT GENERATION PATH ---
                response_text, _ = perform_ai_analysis(prompt_text)
                response_block = {"role": "model", "text": response_text}
                
                # Audio Playback for text
                clean_text = response_text.replace('\n', ' ').replace('#', '').replace('*', '')[:200]
                tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&q={clean_text}&tl=en"
                st.markdown(f'<audio autoplay="true" style="display:none;"><source src="{tts_url}" type="audio/mpeg"></audio>', unsafe_allow_html=True)

        # 4. Save AI Response to History & Rerun
        st.session_state['chat_history'].append(response_block)
        # (Optional: Add save_chat_to_cloud here)
        st.rerun()

    # --- PAGE HEADER ---
    c_title, c_mic = st.columns([5, 1], vertical_alignment="bottom")
    with c_title:
        st.markdown(f'<div class="big-title">AI Companion 🤖</div>', unsafe_allow_html=True)
    
    with c_mic:
        # Voice Input Icon
        audio_data = mic_recorder(start_prompt="🎤", stop_prompt="⏹️", just_once=True, key="voice_input")
        if audio_data: st.toast("Voice received...", icon="🎧")

    # --- CHAT HISTORY DISPLAY (Multimodal) ---
    if not st.session_state.get('chat_history'):
        # Welcome Screen
        user_name = st.session_state.get('user_name', 'Hunter').split()[0]
        st.markdown(f"""
        <div style="margin: 30px 0;">
            <div style="font-size: 32px; font-weight: 700; color: var(--primary-color);">Hello, {user_name}</div>
            <div style="font-size: 20px; opacity: 0.8;">I am ready. Do you need a plan, an explanation, or a visual diagram?</div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        if c1.button("📅 Plan Day", use_container_width=True): process_message("Create a productive hourly schedule for today.")
        if c2.button("🧠 Explain Topic", use_container_width=True): process_message("Explain a complex concept simply.")
        if c3.button("🎨 Generate Visual", use_container_width=True, help="Type a prompt below first!"): st.toast("Please type a prompt in the box below first.", icon="ℹ️")
        if c4.button("📝 Study Tips", use_container_width=True): process_message("Give me scientific study techniques.")

    else:
        # Scrollable Chat Container
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state['chat_history']:
                role = str(msg.get('role')).lower()
                content_text = msg.get('text', '')
                content_img_b64 = msg.get('image') # Check for image data
                
                # Define Avatar
                if role in ["model", "assistant", "ai"]:
                    ui_role = "assistant"
                    avatar_icon = "🤖"
                else:
                    ui_role = "user"
                    avatar_icon = "👤"

                with st.chat_message(ui_role, avatar=avatar_icon):
                    # Render Text if present
                    if content_text:
                        st.write(content_text)
                    
                    # Render Image if present
                    if content_img_b64:
                        try:
                            # Decode base64 string back to image bytes
                            img_bytes = base64.b64decode(content_img_b64)
                            st.image(img_bytes, use_container_width=True)
                        except Exception:
                            st.error("Error rendering image.")

    # --- MAIN INPUT FIELD ---
    # Check if image generation mode was triggered from sidebar
    gen_mode = st.session_state.get('trigger_image_gen', False)
    placeholder_txt = "Describe visual..." if gen_mode else "Ask TimeHunt AI..."
    
    if prompt := st.chat_input(placeholder_txt):
        # Reset trigger flag
        if gen_mode: st.session_state['trigger_image_gen'] = False
        # Process message with correct mode
        process_message(prompt, generate_image=gen_mode)

# --- 11. VISUAL STYLING (THEME ENGINE) ---
def inject_custom_css():
    """
    Injects CSS variables for colors to ensure consistency and readability.
    Forces button text color to ensure visibility in Dark Mode.
    """
    theme_color = st.session_state.get('theme_color', 'Green (Default)')
    theme_mode = st.session_state.get('theme_mode', 'Dark')
    
    # Colors
    colors = {
        "Green (Default)": "#B5FF5F", 
        "Blue": "#00E5FF", 
        "Red": "#FF4B4B", 
        "Grey": "#A0A0A0"
    }
    accent = colors.get(theme_color, "#B5FF5F")
    
    # High Contrast Settings
    if theme_mode == "Light":
        main_bg = "#FFFFFF"
        sidebar_bg = "#F8F9FB"
        card_bg = "#FFFFFF"
        text_color = "#1A1A1A"
        border_color = "#E0E0E0"
        btn_text_color = "#000000" # Black text on light buttons
    else:
        main_bg = "#0E1117"
        sidebar_bg = "#262730"
        card_bg = "#1E1E1E"
        text_color = "#FAFAFA"
        border_color = "#333333"
        btn_text_color = "#FFFFFF" # White text on dark buttons

    st.markdown(f"""
        <style>
            :root {{ 
                --accent: {accent}; 
                --text: {text_color}; 
                --card-bg: {card_bg}; 
                --border: {border_color};
                --primary-color: {accent};
            }}
            
            .stApp {{ background: {main_bg} !important; color: {text_color} !important; }}
            section[data-testid="stSidebar"] {{ background: {sidebar_bg} !important; }}
            
            /* Typography */
            h1, h2, h3, h4, h5, h6, p, li, span {{ color: {text_color} !important; }}
            
            /* Inputs */
            .stTextInput input, .stSelectbox div, .stTextArea textarea {{ 
                background-color: {sidebar_bg} !important; 
                color: {text_color} !important; 
                border-radius: 8px;
                border: 1px solid {border_color} !important;
            }}
            
            /* --- BUTTON VISIBILITY FIX --- */
            /* Force text color on all buttons */
            div.stButton > button p {{
                color: {btn_text_color} !important;
            }}
            
            div.stButton > button {{ 
                background-color: {card_bg};
                border: 1px solid {border_color};
                border-radius: 10px; 
            }}
            
            /* Hover Effect */
            div.stButton > button:hover {{
                border-color: {accent};
            }}
            div.stButton > button:hover p {{
                color: {accent} !important;
            }}

            /* Primary Action Buttons */
            div.stButton > button[kind="primary"] {{
                background-color: {accent} !important;
                border: none;
            }}
            div.stButton > button[kind="primary"] p {{
                color: #000000 !important; /* Always black text on bright accent buttons */
            }}
        </style>
    """, unsafe_allow_html=True)

# --- 12. PDF REPORT GENERATOR ---
def create_mission_report(user_name, level, xp, history):
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", "B", 20)
    pdf.cell(0, 10, "TIMEHUNT // ACTIVITY SUMMARY", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 10, f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}", ln=True, align='C')
    pdf.line(10, 30, 200, 30)
    pdf.ln(20)
    
    # User Stats
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"USER PROFILE: {user_name}", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 10, f"Level: {level}  |  Total XP: {xp}", ln=True)
    pdf.ln(10)
    
    # History Table
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "RECENT ACTIVITY LOG", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", "", 10)
    pdf.cell(50, 10, "DATE", 1)
    pdf.cell(50, 10, "XP GAINED", 1)
    pdf.ln()
    
    if history:
        for entry in history[-10:]: # Last 10
            date = str(entry.get('Date', '-'))
            gain = str(entry.get('XP', 0))
            pdf.cell(50, 10, date, 1)
            pdf.cell(50, 10, f"+{gain} XP", 1)
            pdf.ln()
    else:
        pdf.cell(0, 10, "No data recorded.", ln=True)
        
    pdf.ln(20)
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, "Generated by TimeHunt AI - Productivity Intelligence", align='C')
    
    return pdf.output(dest='S').encode('latin-1')

# --- 13. PAGE: HOME (Dashboard) ---
def page_home():
    # 1. Dynamic Greeting
    ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    hr = ist_now.hour
    
    if 5 <= hr < 12: greeting = "Good Morning"
    elif 12 <= hr < 17: greeting = "Good Afternoon"
    elif 17 <= hr < 22: greeting = "Good Evening"
    else: greeting = "Working Late?"

    quotes = [
        "Small steps every day lead to big results.", 
        "Focus on being productive instead of busy.", 
        "Your future is created by what you do today.", 
        "Discipline is choosing between what you want now and what you want most."
    ]
    random_sub = random.choice(quotes)

    # 2. Hero Section (Weather + Greeting)
    st.markdown("""
    <style>
        .hero-box {
            background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 25px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
    </style>
    """, unsafe_allow_html=True)

    c_text, c_weather = st.columns([3, 1])
    
    with c_text:
        st.markdown(f'<div class="big-title">{greeting}, {st.session_state["user_name"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="opacity:0.8; font-size:16px;">{random_sub}</div>', unsafe_allow_html=True)
    
    with c_weather:
        city = st.session_state.get('user_city', 'Jaipur')
        temp, desc = get_real_time_weather(city)
        st.markdown(f"""
        <div style="text-align:right; animation: fadeIn 2s;">
            <div style="font-size:26px; font-weight:700; color:var(--accent);">{temp}</div>
            <div style="font-size:13px; opacity:0.9;">{desc}</div>
            <div style="font-size:11px; opacity:0.6;">{ist_now.strftime('%H:%M')}</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    # 3. Level Progress
    curr_xp = st.session_state.get('user_xp', 0)
    lvl = st.session_state.get('user_level', 1)
    next_xp = lvl * 1000
    lvl_progress = curr_xp - ((lvl - 1) * 1000)
    pct = min(100, max(0, (lvl_progress / 1000) * 100))
    
    c_lvl, c_focus = st.columns([2, 1])
    
    with c_lvl:
        st.markdown(f"""
        <div class="css-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <span style="font-weight:700; font-size:18px;">Productivity Level: {lvl}</span>
                <span style="color:var(--accent); font-weight:600;">{int(lvl_progress)} / 1000 XP</span>
            </div>
            <div style="width:100%; background:#333; height:8px; border-radius:4px; overflow:hidden;">
                <div style="height:100%; width:{pct}%; background: linear-gradient(90deg, var(--accent), #00E5FF);"></div>
            </div>
            <div style="margin-top:8px; font-size:12px; opacity:0.6;">Keep consistent to reach the next level.</div>
        </div>
        """, unsafe_allow_html=True)

    with c_focus:
        # Focus Widget
        with st.container(border=True):
            st.caption("🎯 MAIN FOCUS")
            curr_obj = st.session_state.get('current_objective', 'Finish Tasks')
            st.markdown(f"**{curr_obj}**")
            if st.button("Edit Focus"):
                with st.popover("Set New Focus"):
                    n_obj = st.text_input("Goal", value=curr_obj)
                    if st.button("Save"):
                        st.session_state['current_objective'] = n_obj
                        st.rerun()

    # 4. Quick Dashboard Grid
    c1, c2, c3 = st.columns(3)
    
    # Logic for Next Task
    slots = sorted(st.session_state.get('timetable_slots', []), key=lambda x: x['Time'])
    pending = [s for s in slots if not s['Done']]
    next_task = pending[0]['Activity'] if pending else "All Caught Up"
    next_time = pending[0]['Time'] if pending else "--:--"

    with c1:
        st.markdown(f"""
        <div class="css-card" style="height: 160px; display:flex; flex-direction:column; justify-content:center;">
            <div style="font-size:11px; opacity:0.6; text-transform:uppercase; letter-spacing:1px;">NEXT UP</div>
            <div style="font-size:20px; font-weight:700; margin: 5px 0;">{next_task}</div>
            <div style="font-size:24px; color:var(--accent); font-family:monospace;">{next_time}</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        with st.container(border=True):
            st.markdown("**⚡ Quick Actions**")
            if st.button("➕ Add Task", use_container_width=True):
                st.toast("Use the Scheduler tab to manage tasks.", icon="ℹ️")
            if st.button("🧘 Mindfulness", use_container_width=True):
                st.session_state['show_breathing'] = True
                st.rerun()
            if st.button("🤖 Ask AI", use_container_width=True):
                st.session_state['page_mode'] = 'chat'
                st.rerun()

    streak = st.session_state.get('streak', 1)
    with c3:
        st.markdown(f"""
        <div class="css-card" style="height: 160px; text-align:center; display:flex; flex-direction:column; justify-content:center;">
            <div style="font-size:36px;">🔥</div>
            <div style="font-size:28px; font-weight:800;">{streak} Days</div>
            <div style="font-size:12px; opacity:0.6;">CURRENT STREAK</div>
            <div style="font-size:11px; color:var(--accent); margin-top:4px;">Consistency is key!</div>
        </div>
        """, unsafe_allow_html=True)

    # 5. Breathing Exercise Overlay
    if st.session_state.get('show_breathing', False):
        st.markdown("---")
        st.markdown("### 🧘 Mindfulness Pause")
        st.markdown("""
        <div style="display:flex; justify-content:center; margin: 20px 0;">
            <div style="
                width: 100px; height: 100px; 
                background: radial-gradient(circle, var(--accent) 0%, transparent 70%);
                border-radius: 50%;
                animation: breath 4s infinite ease-in-out;
            "></div>
        </div>
        <div style="text-align:center; font-family:monospace; opacity:0.7;">INHALE ... HOLD ... EXHALE</div>
        <style>
            @keyframes breath {
                0% { transform: scale(0.8); opacity: 0.4; }
                50% { transform: scale(1.6); opacity: 0.9; }
                100% { transform: scale(0.8); opacity: 0.4; }
            }
        </style>
        """, unsafe_allow_html=True)
        if st.button("End Session"):
            st.session_state['show_breathing'] = False
            st.rerun()

# --- 14. PAGE: ABOUT (System Info) ---
def page_about():
    """
    Displays project details, credits, and technical specifications.
    Refined for a professional portfolio look.
    """
    # 1. Main Title
    st.markdown("# 🛡️ System Architecture")
    st.markdown("### TimeHunt AI: The Productivity Suite")
    
    # 2. PROJECT OVERVIEW
    with st.container(border=True):
        c_icon, c_info = st.columns([1, 5])
        
        with c_icon:
            st.markdown("<div style='font-size: 45px; text-align: center; padding-top: 10px;'>🎓</div>", unsafe_allow_html=True)
        
        with c_info:
            st.markdown("### CBSE Capstone Project")
            st.markdown("**Class 12  |  Artificial Intelligence  |  2025-26**")
            st.caption("A full-stack AI application demonstrating proficiency in Python, LLMs (Gemini), Cloud Database Management, and State Logic.")

    st.write("") 

    # 3. FEATURE SHOWCASE
    st.markdown("### ⚡ Core Features")
    
    row1_1, row1_2 = st.columns(2)
    with row1_1:
        with st.container(border=True):
            st.markdown("#### 🤖 AI Mentor")
            st.caption("Powered by **Google Gemini**. Generates adaptive schedules, answers queries, and provides motivation.")
    
    with row1_2:
        with st.container(border=True):
            st.markdown("#### 🎵 Focus Audio")
            st.caption("Integrated **Audio Engine** with binaural beats and ambient frequencies to induce deep work states.")

    row2_1, row2_2 = st.columns(2)
    with row2_1:
        with st.container(border=True):
            st.markdown("#### 🏆 Gamification")
            st.caption("**XP System & Leaderboards** synced live with Google Sheets to encourage consistency.")
    
    with row2_2:
        with st.container(border=True):
            st.markdown("#### ☁️ Cloud Sync")
            st.caption("Persistent storage ensures your tasks and settings are saved across devices using **Session State & JSON**.")

    st.divider()

    # 4. TECH STACK
    st.markdown("### 🏗️ Technical Stack")
    
    # Modern Pill Badges
    st.markdown("""
    <div style="display: flex; flex-wrap: wrap; gap: 10px;">
        <span style="background-color: #FF4B4B; color: white; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">Streamlit</span>
        <span style="background-color: #306998; color: white; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">Python 3.9+</span>
        <span style="background-color: #4285F4; color: white; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">Google Gemini</span>
        <span style="background-color: #0F9D58; color: white; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">Google Sheets API</span>
        <span style="background-color: #F4B400; color: white; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">Pandas</span>
    </div>
    """, unsafe_allow_html=True)

    st.write("")
    st.caption("🔒 System Status: ONLINE | 🛡️ Developed by TimeHunt Team")

# --- 15. LEADERBOARD UTILITY ---
def fetch_leaderboard_data():
    """
    Fetches user data from 'Sheet1', sorts by XP, and returns the top 10.
    """
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="Sheet1", ttl=0) 
        
        if not df.empty and 'XP' in df.columns:
            # Clean and Sort Data
            df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
            df = df.sort_values(by='XP', ascending=False).reset_index(drop=True)
            
            # Assign Rank
            df['Rank'] = df.index + 1
            return df.head(10)
    except Exception:
        # Fail silently if offline
        return pd.DataFrame()
    return pd.DataFrame()

# --- 16. PAGE: DASHBOARD (Analytics) ---
def page_dashboard():
    # --- 1. CSS for Dashboard Cards ---
    st.markdown("""
    <style>
        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }
        .stat-val { font-size: 28px; font-weight: 700; color: var(--primary-color); }
        .stat-lbl { font-size: 12px; opacity: 0.7; text-transform: uppercase; letter-spacing: 1px; }
        .rank-badge { font-size: 40px; margin-bottom: 5px; animation: float 3s ease-in-out infinite; }
        @keyframes float { 0% { transform: translateY(0px); } 50% { transform: translateY(-5px); } 100% { transform: translateY(0px); } }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="big-title">📊 Productivity Analytics</div>', unsafe_allow_html=True)

    # --- 2. METRICS ---
    slots = st.session_state.get('timetable_slots', [])
    xp = st.session_state.get('user_xp', 0)
    level = st.session_state.get('user_level', 1)
    
    total_tasks = len(slots)
    completed = len([t for t in slots if t.get('Done')])
    success_rate = int((completed / total_tasks * 100)) if total_tasks > 0 else 0
    
    # Professional Rank Titles
    rank_titles = {1: "Starter", 5: "Achiever", 10: "Pro", 20: "Master", 50: "Grandmaster"}
    current_title = "Starter"
    for lvl, title in rank_titles.items():
        if level >= lvl: current_title = title
    
    # --- 3. TOP ROW: STATUS HUD ---
    c_rank, c_stats = st.columns([1, 3])
    
    with c_rank:
        st.markdown(f"""
        <div class="stat-card">
            <div class="rank-badge">🏆</div>
            <div style="font-size:16px; font-weight:bold; margin-top:5px;">{current_title}</div>
            <div style="font-size:12px; color:var(--primary-color);">Level {level}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c_stats:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"""<div class="stat-card"><div class="stat-val">{xp}</div><div class="stat-lbl">Total XP</div></div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class="stat-card"><div class="stat-val">{completed}</div><div class="stat-lbl">Tasks Done</div></div>""", unsafe_allow_html=True)
        with c3:
            color = "#00E5FF" if success_rate > 80 else "#FF4B4B"
            st.markdown(f"""<div class="stat-card"><div class="stat-val" style="color:{color} !important;">{success_rate}%</div><div class="stat-lbl">Success Rate</div></div>""", unsafe_allow_html=True)

    st.write("")
    
    # --- 4. CHARTS & BREAKDOWNS ---
    col_chart, col_breakdown = st.columns([2, 1])
    
    with col_chart:
        st.markdown("### 📈 Progress Trends")
        if st.session_state.get('xp_history'):
            history_df = pd.DataFrame(st.session_state['xp_history'])
            # Render Clean Line Chart
            st.line_chart(history_df.set_index('Date')['XP'], color="#B5FF5F")
        else:
            st.info("Complete tasks to visualize your growth trajectory.")
            
    with col_breakdown:
        st.markdown("### 🧩 Category Breakdown")
        if slots:
            df_slots = pd.DataFrame(slots)
            if 'Category' in df_slots.columns:
                cat_counts = df_slots['Category'].value_counts()
                st.dataframe(
                    cat_counts, 
                    use_container_width=True, 
                    column_config={"count": st.column_config.ProgressColumn("Volume", format="%d", min_value=0, max_value=int(cat_counts.max()))}
                )
        else:
            st.caption("No categories found.")

    st.divider()

    # --- 5. COMMUNITY LEADERBOARD ---
    st.markdown("### 🌍 Community Leaderboard")
    
    leader_df = fetch_leaderboard_data()
    
    if not leader_df.empty:
        st.dataframe(
            leader_df[['Rank', 'Name', 'League', 'XP']],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rank": st.column_config.NumberColumn("Rank", format="#%d", width="small"),
                "Name": st.column_config.TextColumn("User", width="medium"),
                "XP": st.column_config.ProgressColumn("Score", format="%d XP", min_value=0, max_value=int(leader_df['XP'].max() + 500))
            }
        )
        
        # Highlight User Rank
        my_id = str(st.session_state.get('user_id'))
        my_rank_row = leader_df[leader_df['UserID'].astype(str) == my_id]
        if not my_rank_row.empty:
            rank_num = my_rank_row.iloc[0]['Rank']
            st.success(f"📍 You are currently **Rank #{rank_num}**.")
    else:
        st.warning("Leaderboard is currently syncing. Please wait.")

    # --- 6. EXPORT OPTIONS ---
    c_log, c_export = st.columns([3, 1])
    
    with c_log:
        with st.expander("📜 Activity Log (Recent)"):
            if st.session_state.get('xp_history'):
                st.dataframe(pd.DataFrame(st.session_state['xp_history']).tail(10), use_container_width=True)
            else:
                st.caption("No recent activity.")

    with c_export:
        st.markdown("### 🗂️ Actions")
        if st.button("📄 Download Summary (PDF)", type="primary", use_container_width=True):
            try:
                pdf_bytes = create_mission_report(
                    st.session_state.get('user_name', 'User'),
                    level,
                    xp,
                    st.session_state.get('xp_history', [])
                )
                b64 = base64.b64encode(pdf_bytes).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="TimeHunt_Report.pdf" style="text-decoration:none; color:#B5FF5F; font-weight:bold; border:1px solid #B5FF5F; padding:10px; border-radius:10px; display:block; text-align:center;">📥 Download PDF</a>'
                st.markdown(href, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error: {e}")

    
# --- 17. PAGE: SETTINGS (Preferences) ---
def page_settings():
    """
    Handles theme customization, user profile updates, and data management.
    """
    st.markdown("## ⚙️ Settings & Preferences")
    
    # --- 1. VISUAL INTERFACE (Theme Switcher) ---
    st.markdown("### 🎨 Appearance")
    st.caption("Customize the look and feel of your workspace.")
    
    # Using columns for a cleaner layout
    c_mode, c_color = st.columns(2)
    
    with c_mode:
        # Get current state with fallback
        current_mode = st.session_state.get('theme_mode', 'Dark')
        # Radio button returns "Dark" or "Light"
        mode_choice = st.radio("Display Mode", ["Dark", "Light"], horizontal=True, index=0 if current_mode=='Dark' else 1)
        
    with c_color:
        current_theme = st.session_state.get('theme_color', 'Green (Default)')
        # Theme options matched to the CSS dictionary in inject_custom_css
        color_options = ["Green (Default)", "Blue", "Red", "Grey"]
        
        # Safe index finding
        try:
            idx_theme = color_options.index(current_theme)
        except ValueError:
            idx_theme = 0
            
        theme_choice = st.selectbox("Accent Color", color_options, index=idx_theme)

    # Apply Button
    if st.button("Save & Apply Theme", type="primary", use_container_width=True):
        st.session_state['theme_mode'] = mode_choice
        st.session_state['theme_color'] = theme_choice
        st.toast("Visual settings updated!", icon="🎨")
        time.sleep(0.5)
        st.rerun() 

    st.markdown("---")

    # --- 2. NOTIFICATIONS (Browser Permissions) ---
    st.markdown("### 🔔 Notifications")
    st.info("To receive task alerts, you must authorize browser notifications.")
    
    # Modernized Javascript Button (No longer looks like a terminal)
    components.html("""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600&display=swap');
        .btn {
            background: linear-gradient(90deg, #00C6FF, #0072FF); 
            color: white; 
            border: none; 
            padding: 12px 24px; 
            border-radius: 8px; 
            cursor: pointer; 
            font-family: 'Inter', sans-serif; 
            font-weight: 600;
            font-size: 14px;
            width: 100%;
            transition: transform 0.2s;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .btn:hover { transform: scale(1.02); }
        .btn:active { transform: scale(0.98); }
    </style>
    </head>
    <body>
    <button class="btn" onclick="requestPerm()">📢 Enable Desktop Alerts</button>
    <script>
    function requestPerm() {
        if (!("Notification" in window)) {
            alert("This browser does not support notifications.");
        } else {
            Notification.requestPermission().then(function (permission) {
                if (permission === "granted") {
                    new Notification("TimeHunt AI", {
                        body: "Notifications enabled successfully.",
                        icon: "https://cdn-icons-png.flaticon.com/512/2921/2921226.png"
                    });
                } else {
                    alert("Permission denied. Check your browser settings.");
                }
            });
        }
    }
    </script>
    </body>
    </html>
    """, height=80)

    st.markdown("---")
    
    # --- 3. PROFILE SETTINGS ---
    st.markdown("### 👤 Profile & Account")
    
    c_name, c_btn = st.columns([3, 1], vertical_alignment="bottom")
    with c_name:
        new_name = st.text_input("Display Name", value=st.session_state.get('user_name', 'User'))
    with c_btn:
        if st.button("Update Name", use_container_width=True):
            st.session_state['user_name'] = new_name
            sync_data() # Save to cloud
            st.toast("Profile updated.", icon="✅")

    st.markdown("---")

    # --- 4. DATA MANAGEMENT (Danger Zone) ---
    st.markdown("### ⚠️ Data Management")
    with st.expander("Reset Options"):
        st.warning("Factory Reset will remove all local data and log you out. Cloud data may persist.")
        if st.button("🔥 Factory Reset App", type="secondary"):
            st.session_state.clear()
            st.rerun()

# --- 18. ALARM OVERLAY SYSTEM (Global Alert) ---
def render_alarm_ui():
    """
    Displays a full-screen overlay when a task is due.
    Blocks interaction until the user acknowledges the alarm.
    """
    if st.session_state.get('active_alarm'):
        # Get Alarm Details
        alarm_data = st.session_state['active_alarm']
        task_name = alarm_data['task']
        idx = alarm_data['index']
        
        # 1. Audio Logic (Looping)
        # Tries to play a custom file, falls back to a standard web beep
        sound_file = "alarm.mp3"
        if os.path.exists(sound_file):
            try:
                with open(sound_file, "rb") as f:
                    audio_bytes = f.read()
                b64 = base64.b64encode(audio_bytes).decode()
                st.markdown(f'<audio src="data:audio/mp3;base64,{b64}" autoplay loop></audio>', unsafe_allow_html=True)
            except: pass
        else:
            # Standard Beep
            st.markdown('<audio src="https://www.soundjay.com/buttons/beep-01a.mp3" autoplay loop></audio>', unsafe_allow_html=True)

        # 2. CSS Overlay (Modern Glassmorphism)
        # Clean, dark overlay with a soft red pulse for urgency, but legible text
        st.markdown("""
        <style>
            .alarm-overlay {
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background: rgba(0, 0, 0, 0.9); /* High contrast dark background */
                z-index: 999999;
                display: flex; flex-direction: column; align-items: center; justify-content: center;
                backdrop-filter: blur(10px);
                animation: fadeIn 0.5s ease-out;
            }
            .alarm-box {
                width: 90%; max-width: 450px;
                background: #1E1E1E;
                border: 2px solid #FF4B4B;
                border-radius: 24px;
                padding: 40px;
                text-align: center;
                box-shadow: 0 0 50px rgba(255, 75, 75, 0.4);
                animation: gentlePulse 2s infinite;
            }
            .alarm-icon { font-size: 60px; margin-bottom: 20px; }
            .alarm-header {
                font-family: 'Inter', sans-serif; font-size: 28px; font-weight: 800;
                color: #FF4B4B; margin-bottom: 10px; text-transform: uppercase;
            }
            .alarm-text {
                font-family: 'Inter', sans-serif; font-size: 22px; color: #FFFFFF;
                margin-bottom: 30px; font-weight: 500;
            }
            @keyframes gentlePulse {
                0% { box-shadow: 0 0 20px rgba(255, 75, 75, 0.2); }
                50% { box-shadow: 0 0 40px rgba(255, 75, 75, 0.5); }
                100% { box-shadow: 0 0 20px rgba(255, 75, 75, 0.2); }
            }
        </style>
        """, unsafe_allow_html=True)

        # 3. Render Overlay HTML
        st.markdown(f"""
        <div class="alarm-overlay">
            <div class="alarm-box">
                <div class="alarm-icon">⏰</div>
                <div class="alarm-header">Time is Up</div>
                <div class="alarm-text">"{task_name}"</div>
                <div style="color:#AAA; font-size:14px;">Please update your status.</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 4. Interaction Buttons (Floating above the HTML layer)
        with st.container():
            col1, col2, col3 = st.columns([1, 1, 1])
            
            # Button 1: Snooze
            with col1:
                if st.button("💤 Snooze +5m", use_container_width=True):
                    # Logic: Add 5 mins to time
                    st.session_state['reminders'][idx]['time'] += datetime.timedelta(minutes=5)
                    st.session_state['reminders'][idx]['notified'] = False
                    st.session_state['active_alarm'] = None
                    sync_data()
                    st.rerun()

            # Button 2: Stop (Dismiss)
            with col2:
                if st.button("🛑 Dismiss", type="secondary", use_container_width=True):
                    st.session_state['active_alarm'] = None
                    st.rerun()

            # Button 3: Complete
            with col3:
                if st.button("✅ Complete", type="primary", use_container_width=True):
                    # Remove from list
                    st.session_state['reminders'].pop(idx)
                    st.session_state['active_alarm'] = None
                    sync_data()
                    st.balloons()
                    st.rerun()
        
        # Stop App Execution to force focus on the alarm
        st.stop()
	
# --- 19. PAGE: HELP & FEEDBACK CENTER ---
def page_help():
    """
    Provides installation guides, FAQ, and a direct line to the admin/developer.
    """
    st.markdown('<div class="big-title">🤝 Help & Support</div>', unsafe_allow_html=True)
    st.caption("Guides, FAQs, and Feedback Channel")
    
    # --- SECTION 1: INSTALLATION GUIDE ---
    st.markdown("### 📲 Install TimeHunt")
    st.info("Add this app to your home screen for the best full-screen experience.")
    
    with st.container():
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("""
            <div class="css-card" style="height:100%;">
                <h4 style="color:var(--primary-color)">🤖 Android / Chrome</h4>
                <ol style="font-size:14px; margin-left: -20px;">
                    <li>Tap the <b>Three Dots (⋮)</b> in Chrome.</li>
                    <li>Select <b>"Add to Home Screen"</b> or "Install App".</li>
                    <li>Rename to "TimeHunt AI" and confirm.</li>
                </ol>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown("""
            <div class="css-card" style="height:100%;">
                <h4 style="color:#00E5FF">🍎 iOS / Safari</h4>
                <ol style="font-size:14px; margin-left: -20px;">
                    <li>Tap the <b>Share Button</b> (Box with Arrow).</li>
                    <li>Scroll down to <b>"Add to Home Screen"</b>.</li>
                    <li>Tap <b>Add</b> to install the web app.</li>
                </ol>
            </div>
            """, unsafe_allow_html=True)

    st.write("")

    # --- SECTION 2: FEEDBACK CHANNEL ---
    st.markdown("### 📬 Feedback & Support")
    
    # A. TICKET HISTORY (Check for Admin Replies)
    my_tickets = get_my_feedback_status()
    
    if not my_tickets.empty:
        st.markdown("#### Your Tickets")
        for index, row in my_tickets.iterrows():
            # Check for Reply
            has_reply = pd.notna(row['Reply']) and str(row['Reply']).strip() != ""
            
            # Styling
            border_color = "var(--primary-color)" if has_reply else "var(--border)"
            status_text = "✅ REPLY RECEIVED" if has_reply else "⏳ PENDING REVIEW"
            
            st.markdown(f"""
            <div style="background: var(--card-bg); border: 1px solid {border_color}; border-radius: 12px; padding: 15px; margin-bottom: 10px;">
                <div style="display:flex; justify-content:space-between; font-size:12px; opacity:0.7;">
                    <span>{row['Timestamp']}</span>
                    <span style="color:{border_color}; font-weight:bold;">{status_text}</span>
                </div>
                <div style="margin-top:5px; font-weight:600; font-size:15px;">"{row['Query']}"</div>
                {f'<div style="margin-top:10px; padding-top:10px; border-top:1px dashed var(--border); color:var(--primary-color);"><b>👨‍💻 ADMIN REPLY:</b> {row["Reply"]}</div>' if has_reply else ''}
            </div>
            """, unsafe_allow_html=True)
    
    # B. SUBMISSION FORM
    with st.expander("📝 Send New Message", expanded=not my_tickets.empty):
        with st.form("help_form", clear_on_submit=True):
            st.write("**Report a bug or suggest a feature:**")
            query = st.text_area("Message", placeholder="Example: The calendar isn't saving my tasks...", label_visibility="collapsed")
            
            if st.form_submit_button("🚀 Send Message", use_container_width=True, type="primary"):
                if len(query) > 5:
                    if save_feedback(query):
                        st.toast("Feedback sent successfully!", icon="📨")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.warning("Please enter a detailed message.")

    st.divider()

    # --- SECTION 3: FAQ ---
    st.markdown("### 📘 Frequently Asked Questions")
    faqs = {
        "🎯 How do I level up?": "You gain XP by completing tasks (Scheduler) and finishing focus sessions (Timer). Verify your session to claim rewards.",
        "🔊 Audio isn't playing?": "Browsers block auto-playing audio. Click anywhere on the page once to 'Initialize' the audio engine.",
        "☁️ Is my data private?": "Yes. Your schedule is linked only to your unique User ID stored in your browser."
    }
    
    for q, a in faqs.items():
        with st.expander(q):
            st.write(a)

# --- 20. MAIN APPLICATION ROUTER ---

def main():
    # 1. Initialize System State
    initialize_session_state()
    
    # 2. CHECK GLOBAL ALARMS (Code Red Overlay)
    check_reminders()
    render_alarm_ui()

    # 3. Load Styles & Splash
    inject_custom_css()
    show_comet_splash()

    # 4. Onboarding Gate
    if not st.session_state['onboarding_complete']:
        page_onboarding()
        return 

    # 5. CHAT MODE SIDEBAR (Special Layout)
    if st.session_state.get('page_mode') == 'chat':
        with st.sidebar:
            st.markdown("### 💬 AI Controls")
            
            # Navigation Buttons
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🏠 Home", use_container_width=True):
                    st.session_state['page_mode'] = 'main'
                    st.rerun()
            with c2:
                if st.button("➕ New Chat", use_container_width=True):
                    st.session_state['current_session_id'] = None
                    st.session_state['current_session_name'] = "New Chat"
                    st.session_state['chat_history'] = []
                    st.rerun()
            
            st.divider()

            # --- NEW: IMAGE GENERATION TRIGGER ---
            st.markdown("#### 🎨 Visual Studio")
            st.caption("Generate diagrams or motivational images.")
            
            # This button sets a flag. The next input in the chat box will be treated as an image prompt.
            if st.button("✨ Generate Visual from Text", type="primary", use_container_width=True):
                st.session_state['trigger_image_gen'] = True
                st.toast("Image Mode Active. Type your description in the chat box below.", icon="🎨")

            st.divider()
            
            # Chat Management (Delete)
            if 'delete_mode' not in st.session_state: st.session_state['delete_mode'] = False
            toggle_label = "Done Managing" if st.session_state['delete_mode'] else "🗑️ Manage Chats"
            if st.button(toggle_label, use_container_width=True):
                st.session_state['delete_mode'] = not st.session_state['delete_mode']
                st.rerun()

            st.write("") # Spacer
            
            # Session List Logic (Kept same as before for brevity, ensure you have the corrected version with enumerate)
            # ... [Insert your corrected session list loop here] ...
        
        # Render Chat Page
        page_ai_assistant()

    # 6. STANDARD SIDEBAR (Main Menu)
    else:
        with st.sidebar:
            st.markdown("<h1 style='text-align: center;'>🏹<br>TimeHunt AI</h1>", unsafe_allow_html=True)
            render_live_clock()
            
            # Audio Player
            st.markdown("### 🎧 Focus Audio")
            with st.container():
                music_mode = st.selectbox("Soundscape", 
                    ["Om Chanting", "Binaural Beats", "Flute Flow", "Rainfall"], 
                    label_visibility="collapsed"
                )
                local_map = {
                    "Om Chanting": "om.mp3", 
                    "Binaural Beats": "binaural.mp3", 
                    "Flute Flow": "flute.mp3", 
                    "Rainfall": "rain.mp3"
                }
                target_file = local_map.get(music_mode)
                if target_file and os.path.exists(target_file):
                    st.audio(target_file, format="audio/mp3", loop=True)
            
            st.markdown("---")
            
            # Location Setting
            with st.expander("📍 Location Settings"):
                city_input = st.text_input("Current City", value=st.session_state.get('user_city', 'Jaipur'))
                if city_input != st.session_state.get('user_city', 'Jaipur'):
                    st.session_state['user_city'] = city_input
                    st.rerun()

            st.markdown("---")
            
            # Main Nav
            nav = option_menu(
                menu_title=None,
                options=["Home", "Scheduler", "Calendar", "AI Companion", "Timer", "Analytics", "Help Center", "About", "Settings"], 
                icons=["house", "list-check", "calendar-week", "robot", "hourglass-split", "graph-up", "question-circle", "info-circle", "gear"], 
                default_index=0,
                styles={
                    "container": {"padding": "0!important", "background-color": "transparent"},
                    "icon": {"color": "var(--primary-color)", "font-size": "16px"}, 
                    "nav-link": {"font-size": "15px", "text-align": "left", "margin":"2px", "--hover-color": "#333"},
                    "nav-link-selected": {"background-color": "var(--primary-color)", "color": "#000"},
                }
            )
            
            st.caption(f"👤 **{st.session_state.get('user_name', 'User')}**")

        # Page Routing
        if nav == "Home": page_home()
        elif nav == "Scheduler": page_scheduler()
        elif nav == "Calendar": page_calendar()
        elif nav == "AI Companion": 
            st.session_state['page_mode'] = 'chat'
            st.rerun()
        elif nav == "Timer": page_timer()  
        elif nav == "Analytics": page_dashboard()
        elif nav == "Help Center": page_help()
        elif nav == "About": page_about()
        elif nav == "Settings": page_settings()

if __name__ == "__main__":
    main()