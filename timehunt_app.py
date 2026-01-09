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
import uuid
import calendar
from streamlit_mic_recorder import mic_recorder
from gtts import gTTS
import tempfile
import pandas as pd
import numpy as np

def clean_text(value, default_text):
    """Converts nan/float junk to clean string."""
    if pd.isna(value) or value == "nan" or str(value).lower() == "nan" or value is None:
        return default_text
    return str(value)
	
# --- PATH CONFIGURATION ---
# Ensures assets load correctly regardless of where the script is run
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

def upload_to_drive(image_b64, filename_prefix="img"):
    """
    Uploads Base64 image to Google Drive with a specific filename.
    Returns a public direct link.
    """
    import io
    import base64
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    try:
        # 1. Load Credentials & Folder ID
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
             creds_info = st.secrets["connections"]["gsheets"]
        else:
             return ""

        folder_id = st.secrets.get("DRIVE_FOLDER_ID")
        if not folder_id:
            st.error("⚠️ DRIVE_FOLDER_ID missing in secrets.toml")
            return ""

        # 2. Authenticate
        # Note: We use the same creds but strictly for Drive scope here
        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        service = build('drive', 'v3', credentials=creds)

        # 3. Create Unique Filename (UserID_SessionID_Time)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = f"{filename_prefix}_{timestamp}.jpg"

        file_metadata = {
            'name': clean_name,
            'parents': [folder_id]
        }
        
        # 4. Decode and Upload
        img_data = base64.b64decode(image_b64)
        media = MediaIoBaseUpload(io.BytesIO(img_data), mimetype='image/jpeg')

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        file_id = file.get('id')

        # 5. Make Public (So Streamlit can render it)
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'},
            fields='id',
        ).execute()

        # 6. Return Direct Link
        return f"https://drive.google.com/uc?id={file_id}"

    except Exception as e:
        st.error(f"Drive Upload Error: {e}")
        return ""

# --- 1. LIVE CLOCK COMPONENT (Updated for Visibility) ---
def render_live_clock():
    """
    Renders a real-time digital clock.
    FIX: Uses a dark gradient background so white text is always visible.
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
            /* FIX: Dark Gradient Background for contrast in Light Mode */
            background: linear-gradient(135deg, #2C3E50, #000000); 
            color: #FFFFFF;
            
            font-family: 'Inter', sans-serif;
            font-size: 28px; /* Adjusted size */
            font-weight: 600;
            letter-spacing: 2px;
            
            padding: 12px 0; /* Vertical padding only */
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
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
                const timeString = now.toLocaleTimeString('en-US', { 
                    hour12: false, 
                    hour: '2-digit', 
                    minute: '2-digit' 
                });
                document.getElementById('clock').innerText = timeString;
            }
            setInterval(updateClock, 1000);
            updateClock(); 
        </script>
    </body>
    </html>
    """
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
        # Show a warning icon instead of crashing
        st.toast(f"Sync Issue: {e}", icon="⚠️")

# --- USER GENERAL SETTING'S FUNCTION ---
def update_user_setting(column_name, new_value):
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # 1. Read & Force String Types (Crucial Fix)
        df = conn.read(worksheet="Sheet1", ttl=0)
        df = df.astype(str) 
        
        uid = str(st.session_state.get('user_id'))
        
        # 2. Check if Column Exists
        if column_name not in df.columns:
            st.error(f"⚠️ Column '{column_name}' missing in GSheet!")
            return False

        # 3. Find & Update
        mask = df["UserID"] == uid
        if mask.any():
            df.loc[mask, column_name] = str(new_value)
            conn.update(worksheet="Sheet1", data=df)
            return True
        else:
            st.warning(f"User ID {uid} not found in database.")
            
    except Exception as e:
        st.error(f"Save Error: {e}")
    return False

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

# --- 5. CHAT HISTORY DATABASE (Google Sheets + Drive) ---

# --- HELPER: Upload to Google Drive ---
def upload_to_drive(image_b64):
    """
    Uploads an image to Google Drive using the Service Account.
    Returns a direct link that allows the app to display the image.
    """
    import io
    import base64
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    try:
        # 1. Load Credentials
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
             creds_info = st.secrets["connections"]["gsheets"]
        else:
             print("⚠️ No Google Credentials found.")
             return ""

        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        
        # 2. Build Drive Service
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets.get("DRIVE_FOLDER_ID")

        if not folder_id:
            print("⚠️ DRIVE_FOLDER_ID missing in secrets.")
            return ""

        # 3. Prepare File Metadata
        file_metadata = {
            'name': f"TimeHunt_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
            'parents': [folder_id]
        }
        
        # Convert Base64 back to binary stream
        img_data = base64.b64decode(image_b64)
        media = MediaIoBaseUpload(io.BytesIO(img_data), mimetype='image/jpeg')

        # 4. Upload File
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        file_id = file.get('id')

        # 5. Set Permissions (Anyone with link can view)
        permission = {
            'type': 'anyone',
            'role': 'reader',
        }
        service.permissions().create(
            fileId=file_id,
            body=permission,
            fields='id',
        ).execute()

        # 6. Return Display Link
        return f"https://drive.google.com/uc?id={file_id}"

    except Exception as e:
        print(f"Drive Upload Error: {e}")
        return ""

def get_all_chats():
    """Reads the entire ChatHistory sheet safely."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read(worksheet="ChatHistory", ttl=0)
    except Exception:
        return pd.DataFrame(columns=["UserID", "SessionID", "SessionName", "Role", "Content", "Image", "Timestamp"])

def save_chat_to_cloud(role, content, image_b64=None):
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        uid = str(st.session_state.get('user_id', 'Unknown'))
        sid = str(st.session_state.get('current_session_id', 'Unknown'))
        sname = str(st.session_state.get('current_session_name', 'New Chat'))
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        final_image_value = ""
        
        if image_b64:
            # Check if it's already a link (legacy support)
            if str(image_b64).startswith("http"):
                final_image_value = image_b64
            else:
                with st.spinner("☁️ Syncing High-Res Image to Drive..."):
                    # PASS USER ID AND SESSION ID HERE FOR NAMING
                    name_tag = f"{uid}_{sid}"
                    link = upload_to_drive(image_b64, filename_prefix=name_tag)
                    
                    if link:
                        final_image_value = link
                        st.toast("Image saved to Drive!", icon="💾")
                    else:
                        final_image_value = "" # Upload failed

        # Read & Update Sheet
        try:
            df_existing = conn.read(worksheet="ChatHistory", ttl=0)
            # Handle empty sheet case
            if df_existing is None or df_existing.empty:
                df_existing = pd.DataFrame(columns=["UserID", "SessionID", "SessionName", "Role", "Content", "Image", "Timestamp"])
        except Exception:
            df_existing = pd.DataFrame(columns=["UserID", "SessionID", "SessionName", "Role", "Content", "Image", "Timestamp"])
        
        new_row = pd.DataFrame([{
            "UserID": uid, 
            "SessionID": sid, 
            "SessionName": sname,
            "Role": str(role), 
            "Content": str(content), 
            "Image": final_image_value, 
            "Timestamp": ts
        }])
        
        df_final = pd.concat([df_existing, new_row], ignore_index=True)
        # Ensure strict string conversion to avoid errors
        df_final = df_final.fillna("").astype(str)
        
        conn.update(worksheet="ChatHistory", data=df_final)
        
    except Exception as e:
        st.error(f"❌ Cloud Save Error: {e}")

def load_chat_sessions():
    """Returns a unique list of chat sessions."""
    df = get_all_chats()
    uid = str(st.session_state.get('user_id'))
    
    if not df.empty and "UserID" in df.columns:
        df["UserID"] = df["UserID"].astype(str)
        my_chats = df[df["UserID"] == uid]
        
        if not my_chats.empty:
            if "Timestamp" in my_chats.columns:
                my_chats = my_chats.sort_values(by="Timestamp", ascending=False)
            unique_sessions = my_chats[["SessionID", "SessionName"]].drop_duplicates(subset=["SessionID"])
            return unique_sessions.to_dict('records')
    return []

def delete_chat_session(session_id):
    """Deletes a specific chat session."""
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="ChatHistory", ttl=0)
        
        if not df.empty and "SessionID" in df.columns:
            df_filtered = df[df["SessionID"].astype(str) != str(session_id)]
            conn.update(worksheet="ChatHistory", data=df_filtered)
            st.toast("Chat deleted.", icon="🗑️")
    except Exception as e:
        st.error(f"Could not delete: {e}")

def load_messages_for_session(session_id):
    """
    Loads messages for a specific session.
    ✅ FIXED: Handles empty cells correctly to allow images to load.
    """
    df = get_all_chats()
    
    if not df.empty and "SessionID" in df.columns:
        df["SessionID"] = df["SessionID"].astype(str)
        try:
            messages = df[df["SessionID"] == str(session_id)].sort_values(by="Timestamp")
        except KeyError:
            messages = df[df["SessionID"] == str(session_id)]
        
        normalized_history = []
        for _, row in messages.iterrows():
            img_val = row["Image"] if "Image" in row else None
            # Check for NaN or empty string
            if pd.isna(img_val) or str(img_val).lower() == "nan" or str(img_val).strip() == "":
                img_val = None
            
            normalized_history.append({
                "role": str(row.get("Role", "user")).lower(),
                "text": str(row.get("Content", "")),
                "image": img_val 
            })
        return normalized_history
    return []

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

# --- 9. THE BRAIN: SYSTEM INSTRUCTION (Corrected Identity) ---
SYSTEM_INSTRUCTION = """
IDENTITY PROTOCOL:
1. NAME: You are TimeHunt AI.
2. CREATOR: You were created EXCLUSIVELY by the "TimeHunt AI Team" (A group of brilliant CBSE Class 12 Artificial Intelligence students) for their Capstone Project (2025-26).
3. MODEL INFO: 
   - Your logic is powered by Google Gemini 2.5 Flash.
   - Your image generation is powered by Pollinations AI (Flux/Stable Diffusion). You do NOT use Imagen.
4. RESTRICTION: Never mention "Aman" or any single individual. Always credit the "TimeHunt AI Team".

PERSONALITY:
- You are a wise, efficient, and empathetic productivity mentor.
- You speak clearly and concisely.
- You use the user's name and context to provide personalized advice.
- You are aware of the user's settings, alarms, and music playback context.

CAPABILITIES:
- Manage or add or remove schedules and reminders.
- Analyze documents (PDF/TXT) and files of all type.
- Generate motivational or educational images upon request.

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
        
        # --- CHANGE HERE: Set default to Light ---
        'theme_mode': 'Light', 
        'theme_color': 'Green (Default)'
    }

    # Initialize missing keys
    for key, default_val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_val

    # ... (Keep the rest of the API Key logic exactly as it was) ...
    if 'gemini_api_keys' not in st.session_state or not st.session_state['gemini_api_keys']:
        keys = []
        if "GEMINI_API_KEY" in st.secrets:
            raw = st.secrets["GEMINI_API_KEY"]
            if isinstance(raw, list): keys.extend(raw) 
            else: keys.append(raw)
        elif "GOOGLE_API_KEY" in st.secrets:
            raw = st.secrets["GOOGLE_API_KEY"]
            if isinstance(raw, list): keys.extend(raw)
            else: keys.append(raw)
        
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

# --- AI SYSTEM TOOLS ---

def get_current_time_and_date():
    """Returns current date and time in IST."""
    import datetime
    ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    return ist_now.strftime("%Y-%m-%d %H:%M:%S")

def get_my_schedule(date_str=None):
    """Gets schedule for a specific date (YYYY-MM-DD) or today if none provided."""
    import datetime
    if not date_str:
        date_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
    
    slots = st.session_state.get('timetable_slots', [])
    todays_tasks = [s for s in slots if s.get('Date') == date_str]
    
    if not todays_tasks:
        return f"No tasks scheduled for {date_str}."
    
    schedule_text = f"Schedule for {date_str}:\n"
    for s in todays_tasks:
        status = "Done" if s['Done'] else "Pending"
        schedule_text += f"- [{status}] {s['Time']}: {s['Activity']} ({s['Category']})\n"
    return schedule_text

def get_pending_reminders():
    """Returns a list of all active, un-notified alarms."""
    rems = st.session_state.get('reminders', [])
    pending = [r for r in rems if not r.get('notified')]
    if not pending:
        return "No pending reminders."
    
    text = "Pending Reminders:\n"
    for r in pending:
        text += f"- {r['task']} at {r['time']}\n"
    return text

def get_app_settings():
    """Returns current theme, voice, and user goal settings."""
    return f"""
    Current Settings:
    - Theme Mode: {st.session_state.get('theme_mode')}
    - Accent Color: {st.session_state.get('theme_color')}
    - AI Voice: {st.session_state.get('ai_voice_style')}
    - User Goal: {st.session_state.get('user_goal')}
    """

def get_analytics_summary():
    """Returns a summary of XP, Level, and Task Completion rates."""
    xp = st.session_state.get('user_xp', 0)
    level = st.session_state.get('user_level', 1)
    slots = st.session_state.get('timetable_slots', [])
    total = len(slots)
    done = len([t for t in slots if t.get('Done')])
    rate = int((done / total * 100)) if total > 0 else 0
    
    return f"""
    Analytics Summary:
    - Level: {level}
    - Total XP: {xp}
    - Total Tasks: {total}
    - Completed: {done}
    - Success Rate: {rate}%
    """

# Tool Definitions for Gemini
ai_tools = [
    {"function_declarations": [
        {
            "name": "get_current_time_and_date",
            "description": "Get the current date and time in IST."
        },
        {
            "name": "get_my_schedule",
            "description": "Get the user's schedule for a specific date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {"type": "string", "description": "The date in YYYY-MM-DD format. Defaults to today."}
                }
            }
        },
        {
            "name": "get_pending_reminders",
            "description": "Get a list of all pending alarms and reminders."
        },
        {
            "name": "get_app_settings",
            "description": "Get the current application settings like theme and voice."
        },
        {
            "name": "get_analytics_summary",
            "description": "Get a summary of user's progress, XP, and task statistics."
        }
    ]}
]

# Tool Call Handler
def handle_tool_call(tool_call):
    fn_name = tool_call.name
    fn_args = tool_call.args
    
    if fn_name == "get_current_time_and_date":
        return get_current_time_and_date()
    elif fn_name == "get_my_schedule":
        return get_my_schedule(**fn_args)
    elif fn_name == "get_pending_reminders":
        return get_pending_reminders()
    elif fn_name == "get_app_settings":
        return get_app_settings()
    elif fn_name == "get_analytics_summary":
        return get_analytics_summary()
    return "Tool not found."

# --- 13. AI ANALYSIS ENGINE ----

def perform_ai_analysis(user_query, file_data=None, file_type=None, enable_search=False):
    """
    Handles AI requests with FORCED identity injection.
    """
    try:
        from google import genai
        from google.genai import types
        import io
    except ImportError:
        return "⚠️ System Error: `google-genai` library missing.", "System"

    api_keys = st.session_state.get('gemini_api_keys', [])
    if not api_keys:
        return "⚠️ Auth Error: No API Keys found.", "System"

    # --- THE FIX: Hardcoded Identity Injection ---
    # We append this to the user's query so the model sees it immediately.
    identity_enforcer = (
        "\n\n[SYSTEM INSTRUCTION: You are 'TimeHunt AI'. "
        "You were created EXCLUSIVELY by the 'TimeHunt AI Team' (Class 12 AI Students). "
        "You are NOT a Google model. Never mention Google. "
        "Answer as a wise productivity mentor.]"
    )
    
    # Check if we should add the identity prompt (only for text queries)
    final_query = user_query + identity_enforcer if user_query else ""

    # ... (Rest of setup) ...
    sys_instruction_text = get_system_context() 
    generate_config = types.GenerateContentConfig(
        system_instruction=sys_instruction_text,
        temperature=0.7,
        max_output_tokens=4000
    )

    if enable_search:
        try: generate_config.tools = [types.Tool(google_search=types.GoogleSearch())]
        except: pass

    # Prepare Content
    user_content_parts = []
    if final_query:
        user_content_parts.append(types.Part.from_text(text=final_query))
    
    if file_data and file_type:
        try:
            if file_type.startswith("image/") or file_type.startswith("audio/"):
                user_content_parts.append(types.Part.from_bytes(data=file_data, mime_type=file_type))
            elif file_type == "application/pdf":
                client_temp = genai.Client(api_key=api_keys[0])
                file_ref = client_temp.files.upload(file=io.BytesIO(file_data), config={'mime_type': 'application/pdf'})
                user_content_parts.append(types.Part.from_uri(uri=file_ref.uri, mime_type=file_type))
        except Exception as e:
            return f"⚠️ File Error: {e}", "System"

    if not user_content_parts: return "⚠️ No content.", "System"

    # Execution Loop
    for model_name in ["gemini-2.0-flash", "gemini-1.5-flash"]:
        for key in api_keys:
            if not isinstance(key, str): continue
            try:
                client = genai.Client(api_key=key)
                chat = client.chats.create(
                    model=model_name,
                    config=generate_config,
                    history=[
                        types.Content(
                            role="user" if msg['role'] == "user" else "model", 
                            parts=[types.Part.from_text(text=msg['text'])]
                        )
                        for msg in st.session_state.get('chat_history', [])[-6:]
                        if msg.get('text')
                    ]
                )
                response = chat.send_message(user_content_parts)
                return response.text, "TimeHunt AI"

            except Exception as e:
                continue 

    return "⚠️ AI Unavailable.", "System"

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

# --- generate_visual_intel function---

# --- MASTER HYBRID GENERATOR (Hugging Face + Pollinations Fallback) ---
def generate_visual_intel(prompt_text):
    """
    1. Tries Hugging Face Official (Best Quality, High Limits)
    2. If that fails, auto-switches to Pollinations Flux (Backup)
    3. Adds Watermark
    Returns: Base64 String of the final image.
    """
    import base64
    import io
    import random
    import requests
    from PIL import Image, ImageDraw, ImageFont
    from huggingface_hub import InferenceClient

    # --- 1. TRY HUGGING FACE (OFFICIAL) ---
    try:
        # Check for Token
        hf_token = st.secrets.get("HF_TOKEN")
        if not hf_token:
            # This warning will show in your app if the token is missing
            st.warning("⚠️ HF_TOKEN missing in secrets.toml. Switching to backup generator.")
            raise ValueError("Missing HF_TOKEN")

        client = InferenceClient(token=hf_token)
        
        # Using a fast, reliable model (Stable Diffusion v1.5)
        # You can change this to "stabilityai/stable-diffusion-2-1" for different styles
        image = client.text_to_image(
            f"{prompt_text}, cinematic lighting, highly detailed, 8k, masterpiece",
            model="runwayml/stable-diffusion-v1-5"
        )
        
        # If successful, apply watermark and return
        return apply_watermark(image)
            
    except Exception as e:
        # ⚠️ DIAGNOSTIC: This prints the specific error to your app console/UI
        # So you know WHY Hugging Face failed (Auth error? Quota? Internet?)
        print(f"⚠️ Primary AI Failed: {e}") 
        # Optional: Uncomment the next line to see the error on the app screen for debugging
        # st.error(f"Hugging Face Error: {e}")

    # --- 2. FALLBACK: POLLINATIONS.AI (FLUX) ---
    try:
        # We add a random seed to prevent caching old images
        seed = random.randint(1, 99999)
        # Added 'nologo=true' and 'enhance=true'
        url = f"https://image.pollinations.ai/prompt/{prompt_text}?model=flux&width=1024&height=768&seed={seed}&nologo=true&enhance=true"
        
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            image = Image.open(io.BytesIO(response.content))
            return apply_watermark(image)
        else:
            st.error(f"Backup Gen Failed: Status {response.status_code}")
            
    except Exception as e:
        st.error(f"❌ All AI Models Failed. Error: {e}")
        return None

    return None

def apply_watermark(image):
    """
    Applies a TINY watermark (Gemini Style) and returns Base64 string.
    """
    import io
    import base64
    from PIL import Image
    
    try:
        main_img = image.convert("RGBA")
        width, height = main_img.size
        
        # Try to load local watermark.png
        try:
            logo = Image.open("watermark.png").convert("RGBA")
            
            # 1. Target only 10% of the total image width
            target_width = int(width * 0.10)
            if target_width > 100: target_width = 100
            if target_width < 40: target_width = 40
            
            # 2. Resize maintaining aspect ratio
            aspect_ratio = logo.height / logo.width
            new_logo_height = int(target_width * aspect_ratio)
            logo = logo.resize((target_width, new_logo_height), Image.Resampling.LANCZOS)
            
            # 3. Transparency (Glass Effect)
            logo_data = logo.getdata()
            new_data = []
            for item in logo_data:
                # If pixel has color, reduce alpha to 180 (translucent)
                if item[3] > 0:
                    new_data.append((item[0], item[1], item[2], 180)) 
                else:
                    new_data.append(item)
            logo.putdata(new_data)

            # 4. Position: Bottom Right
            padding = 20
            logo_x = width - target_width - padding
            logo_y = height - new_logo_height - padding
            
            # Paste
            main_img.paste(logo, (logo_x, logo_y), logo)

        except FileNotFoundError:
            pass # Skip if no logo file found

        # Save to Buffer as Base64
        final_img = main_img.convert("RGB")
        buffered = io.BytesIO()
        final_img.save(buffered, format="JPEG", quality=95)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    except Exception as e:
        print(f"Watermark Error: {e}")
        # Fallback to original image on error
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

# --- 6. PAGE: ONBOARDING (User Login & Setup) ---

# --- 6. PAGE: ONBOARDING (User Login & Setup) ---
def page_onboarding():
    """
    Handles user authentication (Login/Signup) and profile creation.
    """
    
    # 1. Background Setup
    bg_base64 = None
    try:
        if os.path.exists("background_small.jpg"):
            with open("background_small.jpg", "rb") as image_file:
                bg_base64 = base64.b64encode(image_file.read()).decode()
    except Exception: 
        pass

    # Apply Background CSS (Fixed Double Braces for f-string)
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

    # 2. Login Card CSS
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
    _, col_center, _ = st.columns([1, 6, 1])
    
    with col_center:
        if step == 1:
            st.markdown('<div class="login-card">', unsafe_allow_html=True)
            st.markdown('<div class="app-header">TIME HUNT AI</div>', unsafe_allow_html=True)
            st.markdown('<div class="sub-header">Productivity Intelligence</div>', unsafe_allow_html=True)
            
            default_val = st.session_state.get('suggested_name_choice', "")
            name_input = st.text_input("Username", value=default_val, placeholder="Create Username...", key="login_name").strip()
            pin_input = st.text_input("PIN (4-Digits)", placeholder="####", type="password", key="login_pin", max_chars=4)
            
            st.write("")
            
            if st.button("🚀 Enter System"):
                if name_input and len(pin_input) >= 1:
                    with st.spinner("Authenticating..."):
                        try:
                            from streamlit_gsheets import GSheetsConnection
                            conn = st.connection("gsheets", type=GSheetsConnection)
                            df = conn.read(worksheet="Sheet1", ttl=0)
                            
                            if not df.empty and 'Name' in df.columns:
                                df['PIN'] = df['PIN'].astype(str).replace(r'\.0$', '', regex=True).str.zfill(4)     
                                existing_user = df[df['Name'] == name_input]
                                if not existing_user.empty:
                                    stored_pin = str(existing_user.iloc[0]['PIN']).strip()
                                    if str(pin_input) == stored_pin:
                                        row = existing_user.iloc[0]
                                        st.session_state['user_name'] = row['Name']
                                        st.session_state['user_id'] = row['UserID']
                                        st.session_state['user_xp'] = int(row['XP'])
                                        st.session_state['user_level'] = (st.session_state['user_xp'] // 500) + 1
                                        st.session_state['current_objective'] = clean_text(row.get('MainFocus'), 'Finish Tasks')
                                        st.session_state['theme_mode'] = clean_text(row.get('ThemeMode'), 'Light')
                                        st.session_state['theme_color'] = clean_text(row.get('ThemeColor'), 'Green (Default)')
                                        st.session_state['ai_voice_style'] = clean_text(row.get('AIVoice'), 'Jarvis (US)')
                                        st.session_state['onboarding_complete'] = True
                                        st.toast(f"Welcome back, {name_input}!", icon="👋")
                                        load_cloud_data()
                                        time.sleep(1.0) 
                                        st.rerun()
                                    else:
                                        st.error("Incorrect PIN.")
                                else:
                                    st.session_state['user_name'] = name_input
                                    st.session_state['temp_pin'] = pin_input
                                    st.session_state['onboarding_step'] = 2
                                    st.success("Username Available.")
                                    time.sleep(1.0)
                                    st.rerun()
                            else:
                                st.session_state['user_name'] = name_input
                                st.session_state['temp_pin'] = pin_input
                                st.session_state['onboarding_step'] = 2
                                st.rerun()
                        except Exception as e:
                            st.error(f"Connection Error: {e}")
                else:
                    st.warning("Please enter a Username and PIN.")
            st.markdown('</div>', unsafe_allow_html=True)

        elif step == 2:
            st.markdown('<div class="login-card"><div class="app-header">Select Avatar</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            
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

        elif step == 3:
            st.markdown('<div class="login-card"><div class="app-header">Set Goals</div>', unsafe_allow_html=True)
            role = st.selectbox("I am a...", ["Student", "Entrepreneur", "Professional", "Lifelong Learner"])
            goal = st.selectbox("Main Focus...", ["Ace Exams", "Build a Business", "Career Growth", "Work-Life Balance"])
            st.write("")
            
            if st.button("✨ Complete Setup"):
                 st.session_state['user_type'] = role
                 st.session_state['user_goal'] = goal
                 try:
                     from streamlit_gsheets import GSheetsConnection
                     conn = st.connection("gsheets", type=GSheetsConnection)
                     try: df = conn.read(worksheet="Sheet1", ttl=0)
                     except: df = pd.DataFrame()
                     
                     new_user_data = pd.DataFrame([{
                         "UserID": st.session_state['user_id'],
                         "Name": st.session_state['user_name'],
                         "XP": 0, "League": "Bronze",
                         "Avatar": st.session_state.get('user_avatar', "👤"),
                         "LastActive": datetime.date.today().strftime("%Y-%m-%d"),
                         "PIN": "'" + str(st.session_state.get('temp_pin', "0000"))
                     }])
                     updated_df = new_user_data if df.empty else pd.concat([df, new_user_data], ignore_index=True)
                     conn.update(worksheet="Sheet1", data=updated_df)
                     st.session_state['onboarding_complete'] = True
                     sync_data()
                     st.toast("Profile Created!")
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

    # Ensure data integrity
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
                diff_input = st.selectbox("Difficulty", ["Easy (20 XP)", "Medium (50 XP)", "Hard (150 XP)", "Major Project (300 XP)"])
            
            c_sub, c_clear = st.columns([1, 4])
            with c_sub:
                submitted = st.form_submit_button("Add Task ➔", type="primary", use_container_width=True)
            
            if submitted and task_input:
                xp_map = {"Easy (20 XP)": 20, "Medium (50 XP)": 50, "Hard (150 XP)": 150, "Major Project (300 XP)": 300}
                clean_diff = diff_input.split(" ")[0]
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

    # --- 4. TASK LIST (Perfectly Aligned) ---
    st.markdown("### 📋 Today's Plan")
    
    if not st.session_state['timetable_slots']:
        st.info("Your schedule is empty. Add a task to get started!")
    else:
        pending = [t for t in st.session_state['timetable_slots'] if not t['Done']]
        done_list = [t for t in st.session_state['timetable_slots'] if t['Done']]

        # A. PENDING TASKS
        if pending:
            for i, task in enumerate(st.session_state['timetable_slots']):
                if not task['Done']:
                    d_color = "#B5FF5F" # Easy
                    if "Medium" in task['Difficulty']: d_color = "#FFD700" 
                    elif "Hard" in task['Difficulty']: d_color = "#FF4B4B" 
                    elif "Major" in task['Difficulty']: d_color = "#D050FF" 
                    
                    with st.container():
                        # FIX: Using 'vertical_alignment' to perfectly center the checkbox with text
                        c_chk, c_det, c_xp = st.columns([0.5, 6, 1.5], vertical_alignment="center")
                        
                        with c_chk:
                            if st.button("⬜", key=f"btn_done_{i}", help="Mark as Done"):
                                st.session_state['timetable_slots'][i]['Done'] = True
                                sync_data()
                                st.rerun()
                        
                        with c_det:
                            st.markdown(f"""
                            <div style="line-height:1.2;">
                                <div style="font-weight:600; font-size:16px;">{task['Activity']}</div>
                                <div style="font-size:12px; opacity:0.7; margin-top:2px;">
                                    <span style="color:{d_color}; font-weight:bold;">● {task['Difficulty']}</span> 
                                    | {task['Category']} | 🕒 {task['Time']}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                        with c_xp:
                            st.markdown(f"""
                            <div style="background:{d_color}15; color:{d_color}; border:1px solid {d_color}; 
                            border-radius:20px; padding:4px 10px; text-align:center; font-weight:bold; font-size:11px;">
                            +{task['XP']} XP
                            </div>
                            """, unsafe_allow_html=True)
                        
                        st.markdown("<hr style='margin:8px 0; border:0; border-top:1px solid rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
        else:
            st.caption("No pending tasks. Great job!")

        # B. COMPLETED TASKS
        if done_list:
            st.write("")
            with st.expander(f"✅ Completed ({len(done_list)})"):
                for t in done_list:
                     st.markdown(f"~~{t['Activity']}~~ <span style='opacity:0.6; font-size:12px;'>({t['XP']} XP)</span>", unsafe_allow_html=True)
                
                # REWARD LOGIC
                if st.button("🎁 Claim XP & Archive", type="primary", use_container_width=True):
                    raw_xp = sum([t['XP'] for t in done_list])
                    final_xp = int(raw_xp * multiplier)
                    
                    st.session_state['user_xp'] += final_xp
                    st.session_state['user_level'] = (st.session_state['user_xp'] // 1000) + 1
                    
                    st.session_state['timetable_slots'] = [t for t in st.session_state['timetable_slots'] if not t['Done']]
                    
                    today_str = datetime.date.today().strftime("%Y-%m-%d")
                    st.session_state['xp_history'].append({"Date": today_str, "XP": final_xp})
                    
                    sync_data()
                    st.balloons()
                    st.toast(f"Great work! Gained +{final_xp} XP", icon="🎉")
                    time.sleep(1.5)
                    st.rerun()

    # FIX: Safety Zone for Reset
    st.write("")
    st.write("")
    with st.expander("⚠️ Danger Zone"):
        st.warning("This will permanently delete all tasks.")
        if st.button("🗑️ Reset All Tasks", type="secondary", use_container_width=True):
            st.session_state['timetable_slots'] = []
            sync_data()
            st.rerun()

# --- 8. PAGE: FOCUS TIMER (Fixed Visibility & Design) ---
def page_timer():
    # --- 1. SETUP ---
    if 'timer_duration' not in st.session_state: st.session_state['timer_duration'] = 25
    if 'timer_mode' not in st.session_state: st.session_state['timer_mode'] = "Focus"

    st.markdown('<div class="big-title" style="text-align:center;">⏱️ Focus Timer</div>', unsafe_allow_html=True)

    # --- 2. DURATION SELECTOR (Grouped Controls) ---
    # We use a container to visually group these controls clearly
    with st.container(border=True):
        c_mode1, c_mode2, c_mode3 = st.columns(3)
        
        # Helper to style the active button
        def get_type(mode): 
            return "primary" if st.session_state['timer_mode'] == mode else "secondary"

        with c_mode1:
            if st.button("🎯 Focus (25m)", type=get_type("Focus"), use_container_width=True):
                st.session_state['timer_duration'] = 25
                st.session_state['timer_mode'] = "Focus"
                st.rerun()
        with c_mode2:
            if st.button("☕ Short (5m)", type=get_type("Short"), use_container_width=True):
                st.session_state['timer_duration'] = 5
                st.session_state['timer_mode'] = "Short"
                st.rerun()
        with c_mode3:
            if st.button("🔋 Long (15m)", type=get_type("Long"), use_container_width=True):
                st.session_state['timer_duration'] = 15
                st.session_state['timer_mode'] = "Long"
                st.rerun()

        # --- 3. GOAL INPUT ---
        st.write("") # Spacer
        current_focus = st.text_input("Session Goal", placeholder="e.g., Finish Physics Chapter 4...", label_visibility="collapsed")
        if not current_focus: current_focus = "Deep Work Session"

    # --- 4. TIMER VISUAL (Fixed High-Contrast Design) ---
    duration_min = st.session_state['timer_duration']
    
    # Dynamic Colors based on mode
    if st.session_state['timer_mode'] == "Focus":
        ring_color = "#B5FF5F" # Lime Green
        glow_color = "rgba(181, 255, 95, 0.4)"
    else:
        ring_color = "#00E5FF" # Cyan
        glow_color = "rgba(0, 229, 255, 0.4)"
    
    # 10/10 FIX: We wrap the timer in a dark card so white text ALWAYS shows
    timer_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@700&family=JetBrains+Mono:wght@500&display=swap');
        
        body {{ 
            background: transparent; 
            display: flex; 
            flex-direction: column; 
            align-items: center; 
            justify-content: center; 
            font-family: 'Inter', sans-serif;
            margin: 0;
            padding: 20px 0;
        }}
        
        /* The Card Container - Forces Dark Mode for Contrast */
        .timer-card {{
            background: #1E1E1E;
            border: 1px solid #333;
            border-radius: 24px;
            padding: 30px;
            width: 100%;
            max-width: 350px;
            display: flex;
            flex-direction: column;
            align-items: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}

        .base-timer {{ position: relative; width: 260px; height: 260px; }}
        .base-timer__svg {{ transform: scaleX(-1); }}
        .base-timer__circle {{ fill: none; stroke: none; }}
        
        .base-timer__path-elapsed {{ 
            stroke-width: 8px; 
            stroke: rgba(255, 255, 255, 0.1); 
        }}
        
        .base-timer__path-remaining {{
            stroke-width: 8px; 
            stroke-linecap: round; 
            transform: rotate(90deg); 
            transform-origin: center;
            transition: 1s linear all; 
            fill-rule: nonzero; 
            stroke: {ring_color}; 
            filter: drop-shadow(0 0 10px {glow_color});
        }}
        
        .base-timer__label {{
            position: absolute; 
            width: 260px; 
            height: 260px; 
            top: 0; 
            display: flex; 
            align-items: center; 
            justify-content: center;
            font-size: 52px; 
            font-family: 'JetBrains Mono', monospace; 
            font-weight: 500; 
            color: #FFFFFF; /* Always White */
            letter-spacing: -2px;
        }}
        
        .controls {{ margin-top: 25px; display: flex; gap: 15px; width: 100%; }}
        
        .btn {{
            border: none; 
            padding: 14px 0; 
            border-radius: 12px; 
            font-size: 16px; 
            font-weight: 700; 
            cursor: pointer; 
            transition: transform 0.1s, opacity 0.2s;
            flex: 1; /* Equal width buttons */
            font-family: 'Inter', sans-serif;
        }}
        
        .btn:active {{ transform: scale(0.98); }}
        
        .btn-start {{ 
            background: {ring_color}; 
            color: #000000; 
            box-shadow: 0 4px 12px {glow_color};
        }}
        
        .btn-stop {{ 
            background: #333333; 
            color: #FFFFFF; 
            border: 1px solid #444; 
        }}
        .btn-stop:hover {{ background: #444; }}

    </style>
    </head>
    <body>
        <div class="timer-card">
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
                <button class="btn btn-start" onclick="startTimer()">Start Session</button>
                <button class="btn btn-stop" onclick="resetTimer()">Reset</button>
            </div>
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
    
    # Render HTML Component
    with st.container():
        # Centering column for the timer to make it look prominent
        _, col_timer, _ = st.columns([1, 4, 1])
        with col_timer:
            components.html(timer_html, height=480)

    # --- 5. VERIFIED REWARDS ---
    st.markdown("---")
    
    # Reward Logic
    possible_xp = 50 if st.session_state['timer_duration'] == 25 else 100 if st.session_state['timer_duration'] == 15 else 10
    
    # Using columns to create a "Footer" feel for the reward section
    c_check, c_claim = st.columns([2, 1], vertical_alignment="center")
    
    with c_check:
        st.markdown(f"**🎁 Reward available:** <span style='color:{ring_color}'>+{possible_xp} XP</span>", unsafe_allow_html=True)
        is_verified = st.checkbox("I confirm I completed this session without distractions.", key="timer_verify")
    
    with c_claim:
        if st.button("Claim Rewards", disabled=not is_verified, type="primary", use_container_width=True):
            st.session_state['user_xp'] += possible_xp
            st.session_state['user_level'] = (st.session_state['user_xp'] // 1000) + 1
            
            # Log to History
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            st.session_state['xp_history'].append({"Date": today_str, "XP": possible_xp})
            sync_data()
            
            st.balloons()
            st.toast(f"Session Verified! +{possible_xp} XP Added.", icon="🛡️")
            time.sleep(1.5)
            st.rerun()

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

# --- HELPER: Convert Local Image to HTML string for Buttons ---
def get_custom_icon_html(file_path, width="28px"):
    import base64
    import os
    if not os.path.exists(file_path):
        return "🎤" # Fallback if image missing
        
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    # CSS styles to make it look like a clickable icon centered vertically
    return f"""
    <div style="display:flex; align-items:center; justify-content:center; height:100%;">
        <img src="data:image/jpeg;base64,{data}" 
        style="width:{width}; height:auto; border-radius:50%; cursor:pointer; transition:transform 0.1s;">
    </div>
    """

# --- HELPER: Upload non-image files to Gemini API ---
def upload_to_gemini_manager(uploaded_file_obj, api_key):
    """Uploads PDFs/Videos to Gemini's temp storage API."""
    try:
        from google import genai
        import tempfile
        import os
        
        client = genai.Client(api_key=api_key)
        
        # 1. Save Streamlit uploaded file to a temporary local file
        suffix = "." + uploaded_file_obj.name.split('.')[-1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
             tmp.write(uploaded_file_obj.getvalue())
             tmp_path = tmp.name

        # 2. Upload to Gemini endpoints
        # print(f"Uploading {uploaded_file_obj.name} to Gemini...")
        gemini_file = client.files.upload(path=tmp_path)
        
        # 3. Clean up local temp file
        os.remove(tmp_path)
        return gemini_file
    except Exception as e:
        st.error(f"File Upload Error: {e}")
        return None

def parse_and_add_ai_schedule(ai_response_text):
    """
    Scans AI response for JSON code blocks containing schedule data 
    and adds them to the Session State automatically.
    """
    import json
    import re

    # 1. Regex to find JSON inside ```json ... ``` or just [...]
    json_match = re.search(r'```json\n(.*?)\n```', ai_response_text, re.DOTALL)
    
    if json_match:
        try:
            # Parse the JSON string into a Python List
            data_str = json_match.group(1)
            new_tasks = json.loads(data_str)
            
            count = 0
            ist_now = datetime.datetime.now()
            today_str = ist_now.strftime("%Y-%m-%d")

            # 2. Add to Session State
            for task in new_tasks:
                # Basic validation
                if "Activity" in task and "Time" in task:
                    st.session_state['timetable_slots'].append({
                        "Date": today_str,
                        "Time": task['Time'],
                        "Activity": task['Activity'],
                        "Category": task.get('Category', 'General'),
                        "Difficulty": "Medium", # Default
                        "XP": 50,
                        "Done": False
                    })
                    count += 1
            
            # 3. Save to Cloud
            if count > 0:
                sync_data()
                return count
                
        except Exception as e:
            print(f"Auto-Schedule Error: {e}")
            
    return 0

# --- 10. PAGE: AI ASSISTANT (Gemini UI & Fixed Audio) ---
# --- UPDATE 2: AI PAGE (Fix Audio, Visuals & Controls) ---
def page_ai_assistant():
    from streamlit_mic_recorder import mic_recorder
    import uuid
    import base64
    import io
    from gtts import gTTS

    # --- A. CSS: Aggressive Round Logo & Hidden Audio ---
    st.markdown("""
    <style>
        /* 1. Force Round Avatar */
        /* Target the image directly inside the avatar container */
        [data-testid="stChatMessageAvatar"] img {
            border-radius: 50% !important;
            object-fit: cover !important;
            border: 2px solid #B5FF5F !important;
        }
        
        /* 2. Hide Audio Elements */
        audio { display: none !important; }
        .stAudio { display: none !important; }
        
        /* 3. Colorful Buffering Animation */
        @keyframes color-spin {
            0% { border-color: #B5FF5F; transform: rotate(0deg); }
            33% { border-color: #00E5FF; }
            66% { border-color: #FF4B4B; }
            100% { border-color: #B5FF5F; transform: rotate(360deg); }
        }
        
        .ai-loading-ring {
            width: 40px; height: 40px; border-radius: 50%;
            border: 3px solid transparent;
            border-top-color: #B5FF5F; border-right-color: #00E5FF; border-bottom-color: #FF4B4B;
            animation: color-spin 1.2s linear infinite;
        }
    </style>
    """, unsafe_allow_html=True)

    # --- B. State Management ---
    if 'audio_playing_index' not in st.session_state:
        st.session_state['audio_playing_index'] = None

    user_av = st.session_state.get('user_avatar', '👤')
    # Use your specific file
    ai_av = "1000592991.png" if os.path.exists("1000592991.png") else "🤖"

    # --- C. Audio Toggle Logic ---
    def toggle_audio(index):
        if st.session_state['audio_playing_index'] == index:
            st.session_state['audio_playing_index'] = None # Stop
        else:
            st.session_state['audio_playing_index'] = index # Play
        st.rerun()

    # --- D. Process Logic ---
    def process_message(prompt, file_data=None, file_type=None, audio_bytes=None, mode="Chat"):
        if not prompt and not file_data and not audio_bytes: return
        
        if not st.session_state.get('current_session_id'):
            st.session_state['current_session_id'] = str(uuid.uuid4())
            st.session_state['current_session_name'] = " ".join(prompt.split()[:4]) if prompt else "New Chat"

        msg_data = {"role": "user", "text": prompt}
        if file_data: msg_data["file_type"] = file_type
        elif audio_bytes: msg_data["text"] = "🎤 [Voice]"
        
        save_chat_to_cloud("user", msg_data.get("text", ""))
        st.session_state['chat_history'].append(msg_data)

        # AI Response
        with st.chat_message("assistant", avatar=ai_av):
            # VISUAL: Colorful Loading Ring
            loading_ph = st.empty()
            loading_ph.markdown("""
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div class="ai-loading-ring"></div>
                    <div style="font-weight: bold; background: linear-gradient(90deg, #B5FF5F, #00E5FF); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                        TimeHunt is thinking...
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Prep Data
            final_file_data = file_data if file_data else (audio_bytes if audio_bytes else None)
            final_file_type = file_type if file_type else ("audio/wav" if audio_bytes else None)
            final_prompt = "Listen and reply." if audio_bytes else prompt
            use_search = (mode == "Web Search")

            if mode == "Image Gen":
                img_data = generate_visual_intel(prompt)
                loading_ph.empty()
                if img_data:
                    st.image(base64.b64decode(img_data))
                    save_chat_to_cloud("model", f"Visual: {prompt}", image_b64=img_data)
                    st.session_state['chat_history'].append({"role": "model", "text": f"Generated: {prompt}", "image": img_data})
            else:
                # Call AI
                response_text, _ = perform_ai_analysis(final_prompt, final_file_data, final_file_type, enable_search=use_search)
                
                # Auto-Schedule Check
                added = parse_and_add_ai_schedule(response_text)
                if added > 0: response_text += f"\n\n(📅 Added {added} tasks to schedule)"

                loading_ph.empty()
                st.write(response_text)
                
                st.session_state['chat_history'].append({"role": "model", "text": response_text})
                save_chat_to_cloud("model", response_text)
            
            st.rerun()

    # --- E. Render Header ---
    st.markdown('<div class="big-title">TimeHunt AI</div>', unsafe_allow_html=True)

    # --- F. Render Chat History ---
    chat_container = st.container()
    with chat_container:
        for i, msg in enumerate(st.session_state['chat_history']):
            role = "assistant" if msg.get('role') in ["model", "ai"] else "user"
            av = ai_av if role == "assistant" else user_av
            
            with st.chat_message(role, avatar=av):
                if msg.get('text'): 
                    st.write(msg['text'])
                    
                    # --- AUDIO LOGIC ---
                    if role == "assistant":
                        # Check state
                        is_playing = (st.session_state['audio_playing_index'] == i)
                        btn_text = "⏹️ Stop" if is_playing else "🔊 Listen"
                        btn_kind = "primary" if is_playing else "secondary"
                        
                        if st.button(btn_text, key=f"audio_{i}", type=btn_kind):
                            toggle_audio(i)
                        
                        # If playing, generate and inject HIDDEN HTML Audio
                        if is_playing:
                            try:
                                # 1. Clean Text (Remove Markdown)
                                raw_text = msg['text']
                                clean_t = raw_text.replace('*', '').replace('#', '').replace('`', '').replace('-', '')
                                
                                # 2. Get Voice Settings
                                c_voice = st.session_state.get('ai_voice_style', 'Jarvis (US)')
                                v_map = {
                                    "Jarvis (US)": {"tld": "us", "lang": "en"},
                                    "Friday (UK)": {"tld": "co.uk", "lang": "en"},
                                    "Guru (Indian)": {"tld": "co.in", "lang": "en"}
                                }
                                settings = v_map.get(c_voice, {"tld": "us", "lang": "en"})
                                
                                # 3. Generate Full Audio (NO LIMITS)
                                tts = gTTS(text=clean_t, lang=settings['lang'], tld=settings['tld'])
                                fp = io.BytesIO()
                                tts.write_to_fp(fp)
                                fp.seek(0)
                                b64 = base64.b64encode(fp.read()).decode()
                                
                                # 4. Invisible Player
                                md = f"""
                                    <audio autoplay="true" style="display:none;">
                                    <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                                    </audio>
                                """
                                st.markdown(md, unsafe_allow_html=True)
                                
                            except Exception as e:
                                st.error(f"Audio Error: {e}")

                if msg.get('image'):
                    try: st.image(base64.b64decode(msg['image']))
                    except: pass

    # --- G. Input Area ---
    st.write("---")
    with st.container():
        with st.form(key="chat_input_form", clear_on_submit=True):
            user_text = st.text_area("Message TimeHunt...", height=80, label_visibility="collapsed")
            c1, c2, c3, c4 = st.columns([0.5, 2.5, 0.5, 0.8], vertical_alignment="bottom")
            with c1: up_file = st.file_uploader("📎", label_visibility="collapsed")
            with c2: mode = st.radio("Mode", ["Chat", "Web Search", "Image Gen"], horizontal=True, label_visibility="collapsed")
            with c4: submitted = st.form_submit_button("Send ➤")
        
        with c3:
            audio_packet = mic_recorder(start_prompt="🎤", stop_prompt="⏹️", key="mic_btn")

    if submitted and user_text:
        f_bytes = up_file.getvalue() if up_file else None
        f_type = up_file.type if up_file else None
        process_message(user_text, f_bytes, f_type, mode=mode)
    elif audio_packet:
        process_message("", audio_bytes=audio_packet['bytes'], mode=mode)

# --- 11. VISUAL STYLING (THEME ENGINE) ---

def inject_custom_css():
    """
    Injects CSS variables for colors to ensure consistency and readability.
    Forces button text color to ensure visibility in Dark Mode.
    """
    theme_color = st.session_state.get('theme_color', 'Green (Default)')
    theme_mode = st.session_state.get('theme_mode', 'Light') # Default changed to Light here too for safety
    
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
        btn_text_color = "#000000" 
    else:
        main_bg = "#0E1117"
        sidebar_bg = "#262730"
        card_bg = "#1E1E1E"
        text_color = "#FAFAFA"
        border_color = "#333333"
        btn_text_color = "#FFFFFF" 

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
            
            /* --- ADDED: BIG TITLE CLASS FOR PAGE HEADERS --- */
            .big-title {{
                font-family: 'Inter', sans-serif;
                font-size: 36px; /* increased size */
                font-weight: 800;
                color: {text_color};
                margin-bottom: 15px;
                letter-spacing: -1px;
            }}

            /* Inputs */
            .stTextInput input, .stSelectbox div, .stTextArea textarea {{ 
                background-color: {sidebar_bg} !important; 
                color: {text_color} !important; 
                border-radius: 8px;
                border: 1px solid {border_color} !important;
            }}
            
            /* Force text color on all buttons */
            div.stButton > button p {{
                color: {btn_text_color} !important;
            }}
            
            div.stButton > button {{ 
                background-color: {card_bg};
                border: 1px solid {border_color};
                border-radius: 10px; 
            }}
            
            div.stButton > button:hover {{
                border-color: {accent};
            }}
            div.stButton > button:hover p {{
                color: {accent} !important;
            }}

            div.stButton > button[kind="primary"] {{
                background-color: {accent} !important;
                border: none;
            }}
            div.stButton > button[kind="primary"] p {{
                color: #000000 !important; 
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

def refresh_user_data():
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="Sheet1", ttl=0) 
        
        uid = str(st.session_state.get('user_id'))
        
        if not df.empty and 'UserID' in df.columns:
            # Force string comparison
            df['UserID'] = df['UserID'].astype(str)
            user_row = df[df['UserID'] == uid]
            
            if not user_row.empty:
                row = user_row.iloc[0]
                
                # 1. XP (Keep existing logic)
                try: new_xp = int(float(row['XP'])) 
                except: new_xp = 0
                st.session_state['user_xp'] = max(0, new_xp)
                st.session_state['user_level'] = (new_xp // 1000) + 1

                # 2. LOAD SETTINGS SAFELY (Using the clean_text tool)
                # This prevents "nan" from appearing
                focus_val = clean_text(row.get('MainFocus'), "Finish Tasks")
                st.session_state['current_objective'] = focus_val
                
                theme_val = clean_text(row.get('ThemeMode'), "Light")
                st.session_state['theme_mode'] = theme_val
                
                voice_val = clean_text(row.get('AIVoice'), "Jarvis (US)")
                st.session_state['ai_voice_style'] = voice_val

    except Exception as e:
        pass 

# --- 13. PAGE: HOME (Dashboard) ---
def page_home():
    # 1. FORCE DATA REFRESH (Fixes the Sync Issue)
    refresh_user_data()

    # 2. TIMEZONE FIX (Removes Deprecation Warning)
    # Uses timezone-aware objects instead of utcnow()
    ist_offset = datetime.timedelta(hours=5, minutes=30)
    ist_now = datetime.datetime.now(datetime.timezone(ist_offset))
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

    # 3. Hero Section
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

    # 4. Level Progress (Fixed XP Math)
    curr_xp = max(0, st.session_state.get('user_xp', 0)) # Prevent negative numbers
    lvl = st.session_state.get('user_level', 1)
    
    # Calculate progress bar percentage
    lvl_progress = curr_xp % 1000 
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
        with st.container(border=True):
            st.caption("🎯 MAIN FOCUS")
            curr_obj = st.session_state.get('current_objective', 'Finish Tasks')
            st.markdown(f"**{curr_obj}**")
            if st.button("Edit Focus"):
                with st.popover("Set New Focus"):
                    n_obj = st.text_input("Goal", value=curr_obj)
                    if st.button("Save"):
                        st.session_state['current_objective'] = n_obj
                        with st.spinner("Saving..."):
                        	update_user_setting("MainFocus", n_obj)
                        st.rerun()

    # 5. Quick Dashboard Grid
    c1, c2, c3 = st.columns(3)
    
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

    # 6. Streak Logic (Fixed Grammar)
    streak = st.session_state.get('streak', 1)
    day_label = "Day" if streak == 1 else "Days" # Dynamic Pluralization
    
    with c3:
        st.markdown(f"""
        <div class="css-card" style="height: 160px; text-align:center; display:flex; flex-direction:column; justify-content:center;">
            <div style="font-size:36px;">🔥</div>
            <div style="font-size:28px; font-weight:800;">{streak} {day_label}</div>
            <div style="font-size:12px; opacity:0.6;">CURRENT STREAK</div>
            <div style="font-size:11px; color:var(--accent); margin-top:4px;">Consistency is key!</div>
        </div>
        """, unsafe_allow_html=True)

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

# --- 14. PAGE: ABOUT (System Architecture) ---
def page_about():
    """
    Displays project details, technical specs, and feature credits.
    """
    # 1. HEADER WITH VERSION BADGE
    c_head, c_ver = st.columns([3, 1], vertical_alignment="center")
    with c_head:
        st.markdown("# 🛡️ System Architecture")
    with c_ver:
        st.markdown("""
        <div style="background: rgba(0, 229, 255, 0.1); color: #00E5FF; padding: 5px 10px; border-radius: 20px; text-align: center; font-size: 12px; font-weight: bold; border: 1px solid #00E5FF;">
            v2.5.0 (Stable)
        </div>
        """, unsafe_allow_html=True)

    st.markdown("### TimeHunt AI: The Productivity Suite")
    
    # 2. PROJECT OVERVIEW CARD
    with st.container(border=True):
        c_icon, c_info = st.columns([1, 5])
        with c_icon:
            st.markdown("<div style='font-size: 50px; text-align: center;'>🎓</div>", unsafe_allow_html=True)
        with c_info:
            st.markdown("### CBSE Capstone Project")
            st.markdown("**Class 12  |  Artificial Intelligence  |  2025-26**")
            st.caption("A full-stack AI application demonstrating proficiency in Python, LLMs (Gemini), Cloud Database Management, and State Logic.")

    st.write("") 

    # 3. EXPANDED FEATURE GRID (Added New Tech)
    st.markdown("### ⚡ Core Capabilities")
    
    # Row 1: The Brains
    row1_1, row1_2 = st.columns(2)
    with row1_1:
        with st.container(border=True):
            st.markdown("#### 🧠 Dual-Core AI")
            st.caption("**Google Gemini 2.5** for logic & planning, coupled with **Hugging Face** for visual generation.")
    
    with row1_2:
        with st.container(border=True):
            st.markdown("#### 🎙️ Voice Synthesis")
            st.caption("Integrated **TTS Engine** with multi-accent support (US, UK, Indian) for audible mentorship.")

    # Row 2: The Logic
    row2_1, row2_2 = st.columns(2)
    with row2_1:
        with st.container(border=True):
            st.markdown("#### 🔒 Security Layer")
            st.caption("Session-based authentication with **PIN Encryption** and isolated user data environments.")
    
    with row2_2:
        with st.container(border=True):
            st.markdown("#### ☁️ Neural Sync")
            st.caption("Real-time bi-directional data sync between **Session State** and **Google Cloud Database**.")

    # Row 3: The Engagement
    row3_1, row3_2 = st.columns(2)
    with row3_1:
        with st.container(border=True):
            st.markdown("#### 🏆 Gamification Engine")
            st.caption("Dynamic XP algorithms, Streak multipliers, and Global Leaderboards.")
    
    with row3_2:
        with st.container(border=True):
            st.markdown("#### 🎵 Psycho-Acoustics")
            st.caption("Binaural Beats & LoFi soundscapes embedded for deep-focus induction.")

    st.divider()

    # 4. TECH STACK (The "Pills" - Kept your great design)
    st.markdown("### 🏗️ Technical Stack")
    st.markdown("""
    <div style="display: flex; flex-wrap: wrap; gap: 10px;">
        <span style="background-color: #FF4B4B; color: white; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">Streamlit Framework</span>
        <span style="background-color: #306998; color: white; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">Python 3.9+</span>
        <span style="background-color: #4285F4; color: white; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">Google Gemini 2.5 Flash</span>
        <span style="background-color: #FFD700; color: black; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">Hugging Face Diffusers</span>
        <span style="background-color: #0F9D58; color: white; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">Google Sheets API</span>
        <span style="background-color: #1E1E1E; color: white; border: 1px solid white; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">CSS3 Animations</span>
    </div>
    """, unsafe_allow_html=True)

    st.write("")
    
    # 5. CREDITS FOOTER
    st.caption("🔒 System Status: ONLINE | 🛡️ Developed by TimeHunt Team | © 2026")

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
    # --- 1. CSS for Dashboard Cards (10/10 Upgrade) ---
    st.markdown("""
    <style>
        /* Base Card Style */
        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px; /* Softer corners */
            padding: 24px;
            text-align: center;
            box-shadow: 0 4px 10px rgba(0,0,0,0.05);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        /* Interactive Hover Effect (The "Premium" Feel) */
        .stat-card:hover {
            transform: translateY(-5px);
            border-color: var(--primary-color);
            box-shadow: 0 10px 20px rgba(0,0,0,0.1);
        }

        /* Typography */
        .stat-val { 
            font-family: 'Inter', sans-serif; 
            font-size: 32px; 
            font-weight: 800; 
            color: var(--text-color);
            margin: 5px 0;
        }
        .stat-lbl { 
            font-size: 11px; 
            opacity: 0.6; 
            text-transform: uppercase; 
            letter-spacing: 1.5px; 
            font-weight: 600;
        }

        /* GRANDMASTER SPECIAL EFFECTS */
        .rank-badge { 
            font-size: 45px; 
            margin-bottom: 10px; 
            animation: float 3s ease-in-out infinite; 
        }
        .gold-text {
            background: linear-gradient(to bottom, #FFD700, #FDB931);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 900;
            font-size: 20px;
        }
        .gold-glow {
            border: 1px solid #FFD700 !important;
            box-shadow: 0 0 25px rgba(255, 215, 0, 0.15) !important;
        }

        @keyframes float { 
            0% { transform: translateY(0px); } 
            50% { transform: translateY(-8px); } 
            100% { transform: translateY(0px); } 
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="big-title">📊 Productivity Analytics</div>', unsafe_allow_html=True)

    # --- 2. METRICS CALCULATION ---
    slots = st.session_state.get('timetable_slots', [])
    xp = st.session_state.get('user_xp', 0)
    level = st.session_state.get('user_level', 1)
    
    total_tasks = len(slots)
    completed = len([t for t in slots if t.get('Done')])
    success_rate = int((completed / total_tasks * 100)) if total_tasks > 0 else 0
    
    # Rank Logic
    rank_titles = {1: "Starter", 5: "Achiever", 10: "Pro", 20: "Master", 50: "Grandmaster"}
    current_title = "Starter"
    for lvl, title in rank_titles.items():
        if level >= lvl: current_title = title
    
    # Check for Special Status
    is_grandmaster = current_title == "Grandmaster"
    card_class = "stat-card gold-glow" if is_grandmaster else "stat-card"
    title_class = "gold-text" if is_grandmaster else "stat-val"

    # --- 3. TOP ROW: STATUS HUD ---
    c_rank, c_stats = st.columns([1.2, 3])
    
    with c_rank:
        st.markdown(f"""
        <div class="{card_class}">
            <div class="rank-badge">🏆</div>
            <div class="{title_class}">{current_title}</div>
            <div style="font-size:12px; opacity:0.7; margin-top:5px;">Level {level}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c_stats:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-val" style="color:var(--primary-color);">{xp:,}</div>
                <div class="stat-lbl">Total XP</div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-val">{completed}</div>
                <div class="stat-lbl">Tasks Done</div>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            # Dynamic Color for Rate
            rate_color = "#00E5FF" if success_rate > 80 else "#FF4B4B" if success_rate < 50 else "#FFFFFF"
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-val" style="color:{rate_color} !important;">{success_rate}%</div>
                <div class="stat-lbl">Success Rate</div>
            </div>
            """, unsafe_allow_html=True)

    st.write("")
    
    # --- 4. CHARTS & BREAKDOWNS ---
    col_chart, col_breakdown = st.columns([2, 1])
    
    with col_chart:
        st.markdown("### 📈 Progress Trends")
        with st.container(border=True):
            if st.session_state.get('xp_history'):
                history_df = pd.DataFrame(st.session_state['xp_history'])
                # Using the area chart feels more 'filled' and premium than a thin line
                st.area_chart(history_df.set_index('Date')['XP'], color="#B5FF5F")
            else:
                st.info("Complete tasks to visualize your growth trajectory.")
            
    with col_breakdown:
        st.markdown("### 🧩 Breakdown")
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

    # --- 5. COMMUNITY LEADERBOARD (Clean Table) ---
    st.markdown("### 🌍 Global Leaderboard")
    
    leader_df = fetch_leaderboard_data()
    
    if not leader_df.empty:
        st.dataframe(
            leader_df[['Rank', 'Name', 'League', 'XP']],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rank": st.column_config.NumberColumn("Rank", format="#%d", width="small"),
                "Name": st.column_config.TextColumn("User", width="medium"),
                "League": st.column_config.TextColumn("Tier", width="small"),
                "XP": st.column_config.ProgressColumn("Score", format="%d XP", min_value=0, max_value=int(leader_df['XP'].max() + 500))
            }
        )
        
        # Highlight User Rank
        my_id = str(st.session_state.get('user_id'))
        my_rank_row = leader_df[leader_df['UserID'].astype(str) == my_id]
        if not my_rank_row.empty:
            rank_num = my_rank_row.iloc[0]['Rank']
            st.info(f"📍 You are currently **Rank #{rank_num}** in the global league.")
    else:
        st.warning("Leaderboard is currently syncing. Please wait.")

    # --- 6. EXPORT & SHARE ---
    st.write("")
    c_log, c_export = st.columns([3, 1])
    
    with c_log:
        with st.expander("📜 View Activity Log"):
            if st.session_state.get('xp_history'):
                st.dataframe(pd.DataFrame(st.session_state['xp_history']).tail(10), use_container_width=True)
            else:
                st.caption("No recent activity.")

    with c_export:
        if st.button("📄 Download Report", type="primary", use_container_width=True):
            try:
                pdf_bytes = create_mission_report(
                    st.session_state.get('user_name', 'User'),
                    level,
                    xp,
                    st.session_state.get('xp_history', [])
                )
                b64 = base64.b64encode(pdf_bytes).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="TimeHunt_Report.pdf" style="text-decoration:none; color:#B5FF5F; font-weight:bold; border:1px solid #B5FF5F; padding:10px; border-radius:10px; display:block; text-align:center;">📥 Save PDF</a>'
                st.markdown(href, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error: {e}")
    
# --- 17. PAGE: SETTINGS (Preferences) ---
def page_settings():
    """
    Handles theme, voice, and account settings.
    """
    st.markdown("## ⚙️ Settings & Preferences")
    
    # 1. VISUAL SETTINGS
    st.markdown("### 🎨 Appearance")
    c_mode, c_color = st.columns(2)
    with c_mode:
        current_mode = st.session_state.get('theme_mode', 'Dark')
        mode_choice = st.radio("Display Mode", ["Light", "Dark"], horizontal=True, index=0 if current_mode=='Dark' else 1)
    with c_color:
        current_theme = st.session_state.get('theme_color', 'Green (Default)')
        color_options = ["Green (Default)", "Blue", "Red", "Grey"]
        try: idx = color_options.index(current_theme)
        except: idx = 0
        theme_choice = st.selectbox("Accent Color", color_options, index=idx)

    if st.button("Save Visuals", type="secondary", use_container_width=True):
        st.session_state['theme_mode'] = mode_choice
        st.session_state['theme_color'] = theme_choice
        update_user_setting("ThemeMode", mode_choice)
        update_user_setting("ThemeColor", theme_choice)
        # --------------------------
        
        st.rerun()


    st.markdown("---")

    # 2. VOICE SETTINGS (NEW FEATURE)
    st.markdown("### 🎙️ AI Voice Module")
    st.caption("Select the vocal personality for TimeHunt AI.")
    
    # Default to 'Jarvis' if not set
    current_voice = st.session_state.get('ai_voice_style', 'Jarvis (US)')
    
    voice_options = {
        "Jarvis (US)": {"tld": "us", "lang": "en", "desc": "Standard American (Professional)"},
        "Friday (UK)": {"tld": "co.uk", "lang": "en", "desc": "British Accent (Sophisticated)"},
        "Guru (Indian)": {"tld": "co.in", "lang": "en", "desc": "Indian Accent (Relatable)"},
        "Mate (Australian)": {"tld": "com.au", "lang": "en", "desc": "Australian Accent (Relaxed)"},
        "French (Elegant)": {"tld": "fr", "lang": "fr", "desc": "French Accent (Artistic)"}
    }
    
    # Create list for selectbox
    voice_list = list(voice_options.keys())
    try: v_idx = voice_list.index(current_voice)
    except: v_idx = 0
    
        # ... inside page_settings ...

    # Create list for selectbox
    voice_list = list(voice_options.keys())
    try: v_idx = voice_list.index(current_voice)
    except: v_idx = 0
    
    selected_voice = st.selectbox("Voice Identity", voice_list, index=v_idx)
    st.caption(f"Note: {voice_options[selected_voice]['desc']}")

    if st.button("🔊 Listen to Preview", type="secondary"):
        with st.spinner("Generating voice sample..."):
            try:
                from gtts import gTTS
                import io
                target_tld = voice_options[selected_voice]['tld']
                target_lang = voice_options[selected_voice]['lang']

                voice_name = selected_voice.split(" (")[0]
                sample_text = f"Hello, I am {voice_name}. I am ready to assist you with your tasks."
                
                
                tts = gTTS(text=sample_text, lang=target_lang, tld=target_tld, slow=False)
                audio_fp = io.BytesIO()
                tts.write_to_fp(audio_fp)
                audio_fp.seek(0)
                
                
                st.audio(audio_fp, format='audio/mp3')
                
            except Exception as e:
                st.error(f"Could not generate preview. Error: {e}")

    st.write("") 

    if st.button("💾 Save Voice Setting", type="primary", use_container_width=True):
        st.session_state['ai_voice_style'] = selected_voice
        update_user_setting("AIVoice", selected_voice)  
        st.toast(f"Voice updated to {selected_voice}!", icon="🎙️")
        time.sleep(0.5)
        st.rerun()

    st.markdown("---")
    
    # 3. PROFILE & DATA (Keep existing logic)
    st.markdown("### 👤 Account")
    new_name = st.text_input("Display Name", value=st.session_state.get('user_name', 'User'))
    if st.button("Update Name"):
        st.session_state['user_name'] = new_name
        sync_data()
        st.toast("Profile updated.", icon="✅")

    # --- 4. DATA MANAGEMENT (Danger Zone) ---
    st.markdown("### ⚠️ Data Management")
    with st.expander("Reset Options"):
        st.warning("Factory Reset will remove all local data and log you out. Cloud data may persist.")
        if st.button("🔥 Factory Reset App", type="secondary"):
        	for key in list(st.session_state.keys()):
        		del st.session_state[key]
        		st.cache_data.clear()
        		st.toast("System Resetting...", icon="🔄")
        		time.sleep(1)
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
	
# --- 19. PAGE: HELP & FEEDBACK CENTER (10/10 Enterprise Version) ---
def page_help():
    """
    Provides installation guides, detailed FAQ, and a ticket-based support system.
    """
    st.markdown('<div class="big-title">🤝 Help & Support</div>', unsafe_allow_html=True)
    
    # 1. STATUS INDICATOR (The "Pro" Touch)
    # Checks if we are connected to the cloud effectively
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        status_color = "#B5FF5F" # Green
        status_text = "ALL SYSTEMS OPERATIONAL"
    except:
        status_color = "#FF4B4B" # Red
        status_text = "OFFLINE MODE - CLOUD DISCONNECTED"

    st.markdown(f"""
    <div style="background: rgba(255,255,255,0.05); border: 1px solid {status_color}; border-radius: 8px; padding: 10px 20px; display: flex; align-items: center; gap: 15px; margin-bottom: 25px;">
        <div style="width: 10px; height: 10px; background: {status_color}; border-radius: 50%; box-shadow: 0 0 10px {status_color}; animation: pulse 2s infinite;"></div>
        <div style="font-family: monospace; font-size: 14px; color: {status_color}; letter-spacing: 2px;">{status_text}</div>
    </div>
    """, unsafe_allow_html=True)

    # 2. TABBED LAYOUT (Cleaner UX)
    tab_guide, tab_faq, tab_ticket = st.tabs(["📲 Installation", "📘 Knowledge Base", "📬 Support Ticket"])

    # --- TAB 1: INSTALLATION GUIDE ---
    with tab_guide:
        st.markdown("### Install as App (PWA)")
        st.info("TimeHunt AI is designed to work like a native app. Add it to your home screen for the best experience.")
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("""
            <div class="css-card" style="height:100%; border-top: 3px solid #B5FF5F;">
                <h4 style="color:#B5FF5F">🤖 Android / Chrome</h4>
                <ol style="font-size:14px; margin-left: -20px; line-height: 1.6;">
                    <li>Tap the <b>Three Dots (⋮)</b> in Chrome.</li>
                    <li>Select <b>"Add to Home Screen"</b> or "Install App".</li>
                    <li>Rename to "TimeHunt AI" and confirm.</li>
                    <li><i>Result: Full-screen immersive mode.</i></li>
                </ol>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown("""
            <div class="css-card" style="height:100%; border-top: 3px solid #00E5FF;">
                <h4 style="color:#00E5FF">🍎 iOS / Safari</h4>
                <ol style="font-size:14px; margin-left: -20px; line-height: 1.6;">
                    <li>Tap the <b>Share Button</b> (Box with Arrow).</li>
                    <li>Scroll down to <b>"Add to Home Screen"</b>.</li>
                    <li>Tap <b>Add</b> to install the web app.</li>
                    <li><i>Result: Removes browser bars for focus.</i></li>
                </ol>
            </div>
            """, unsafe_allow_html=True)

    # --- TAB 2: EXPANDED KNOWLEDGE BASE (FAQ) ---
    with tab_faq:
        st.markdown("### 📘 Frequently Asked Questions")
        
        # Categorized Expanders for better readability
        with st.expander("🎯 Gamification & XP"):
            st.write("**Q: How do I earn XP?**")
            st.caption("You earn XP by completing tasks in the Scheduler (+20 to +300 XP) and finishing Focus Timer sessions (+50 XP). Consistency leads to 'Streak Multipliers' which boost your XP gain by up to 2.5x!")
            st.divider()
            st.write("**Q: What happens when I level up?**")
            st.caption("Leveling up unlocks new prestige titles (like 'Grandmaster') on the leaderboard. In future updates, high levels will unlock exclusive AI personas and themes.")

        with st.expander("🤖 AI & Intelligence"):
            st.write("**Q: Which AI model is powering this?**")
            st.caption("TimeHunt uses a **Hybrid Engine**: Google Gemini 2.5 handles logic, planning, and conversation, while a specialized Hugging Face model handles image generation. This ensures the best speed and quality for each task.")
            st.divider()
            st.write("**Q: Why does the AI sound robotic?**")
            st.caption("We use a lightweight TTS (Text-to-Speech) engine for speed. You can change the 'Voice Persona' in the **Settings** tab to find an accent (US, UK, Indian) that sounds best to you.")

        with st.expander("🛡️ Data & Privacy"):
            st.write("**Q: Is my schedule private?**")
            st.caption("Yes. Your data is linked to your unique `UserID` and stored in a secure cloud database. No other user can see your specific tasks, only your anonymous XP score on the leaderboard.")
            st.divider()
            st.write("**Q: Does this work offline?**")
            st.caption("TimeHunt requires an internet connection for AI features and Cloud Sync. However, the Timer and basic navigation will function if you temporarily lose connection.")

        with st.expander("⚙️ Troubleshooting"):
            st.write("**Q: My audio isn't playing!**")
            st.caption("Modern browsers block auto-playing audio to prevent annoyance. **Click anywhere on the page** once after loading to 'initialize' the audio engine. If it still fails, check the 'Settings' tab.")
            st.divider()
            st.write("**Q: My tasks disappeared?**")
            st.caption("If you cleared your browser cache, you might have generated a new User ID. Contact support with your username to restore your account.")

    # --- TAB 3: SUPPORT TICKET SYSTEM ---
    with tab_ticket:
        st.markdown("### 📬 Contact Support")
        
        # 1. Ticket History (Shows Admin Replies)
        my_tickets = get_my_feedback_status()
        if not my_tickets.empty:
            st.info(f"You have {len(my_tickets)} active tickets.")
            for index, row in my_tickets.iterrows():
                has_reply = pd.notna(row['Reply']) and str(row['Reply']).strip() != ""
                border_color = "#B5FF5F" if has_reply else "#333"
                status_icon = "✅ RESOLVED" if has_reply else "⏳ PENDING"
                
                st.markdown(f"""
                <div style="background: rgba(255,255,255,0.02); border-left: 4px solid {border_color}; padding: 15px; margin-bottom: 10px; border-radius: 4px;">
                    <div style="display:flex; justify-content:space-between; font-size:12px; opacity:0.6; margin-bottom:5px;">
                        <span>{row['Timestamp']}</span>
                        <span style="font-weight:bold; color:{border_color};">{status_icon}</span>
                    </div>
                    <div style="font-weight:600; margin-bottom:8px;">"{row['Query']}"</div>
                    {f'<div style="background:rgba(181, 255, 95, 0.1); padding:10px; border-radius:4px; font-size:13px; color:#B5FF5F;">👨‍💻 <b>Admin:</b> {row["Reply"]}</div>' if has_reply else ''}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("No past tickets found.")

        # 2. Submission Form
        st.markdown("---")
        with st.form("help_form", clear_on_submit=True):
            st.write("**Submit a New Request**")
            c_type, c_prio = st.columns(2)
            with c_type:
                issue_type = st.selectbox("Issue Type", ["Bug Report", "Feature Request", "Account Issue", "Other"])
            with c_prio:
                priority = st.selectbox("Priority", ["Normal", "High", "Critical"])
                
            query = st.text_area("Describe your issue...", placeholder="e.g., I found a bug in the calendar...", height=100)
            
            # THE FIX: Constructive Blue/Green Button, NOT Red
            # If your primary theme is Red, this might still look red. 
            # Ideally, ensure your .streamlit/config.toml sets primaryColor="#B5FF5F"
            if st.form_submit_button("🚀 Submit Ticket", use_container_width=True, type="primary"):
                if len(query) > 5:
                    full_query = f"[{issue_type}] [{priority}] {query}"
                    if save_feedback(full_query):
                        st.balloons()
                        st.toast("Ticket submitted successfully!", icon="📨")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.warning("Please describe your issue in more detail.")

# --- PAGE: STUDY ZONE (AI Flashcards) ---
def page_study_zone():
    st.markdown('<div class="big-title">🧠 AI Study Zone</div>', unsafe_allow_html=True)
    st.caption("Turn any topic into a revision game.")

    # 1. Input Area
    with st.container(border=True):
        topic = st.text_input("Enter Topic or Paste Notes", placeholder="e.g. Physics Electrostatics, Python Lists...")
        
        # Difficulty Selector
        diff = st.select_slider("Complexity", options=["Basic", "Intermediate", "Advanced (JEE Level)"])
        
        if st.button("⚡ Generate Flashcards", type="primary"):
            if topic:
                with st.spinner(f"Consulting the archives on {topic}..."):
                    # Prompt Engineering for JSON output
                    prompt = f"""
                    Create 5 flashcards for the topic: '{topic}'. Difficulty: {diff}.
                    Return ONLY raw JSON format (no markdown formatting) like this:
                    [
                        {{"q": "Question here?", "a": "Answer here"}},
                        {{"q": "Next question?", "a": "Next answer"}}
                    ]
                    """
                    response, _ = perform_ai_analysis(prompt)
                    
                    try:
                        # Clean up code blocks if Gemini adds them
                        clean_json = response.replace("```json", "").replace("```", "").strip()
                        import json
                        cards = json.loads(clean_json)
                        st.session_state['flashcards'] = cards
                        st.session_state['card_index'] = 0
                        st.session_state['show_answer'] = False
                        st.rerun()
                    except:
                        st.error("AI returned invalid data. Please try again.")
            else:
                st.warning("Please enter a topic.")

    # 2. Flashcard Display
    if 'flashcards' in st.session_state and st.session_state['flashcards']:
        cards = st.session_state['flashcards']
        idx = st.session_state.get('card_index', 0)
        show_ans = st.session_state.get('show_answer', False)
        
        # Progress Bar
        progress = (idx + 1) / len(cards)
        st.progress(progress)
        st.caption(f"Card {idx + 1} of {len(cards)}")

        # The Card UI
        card_bg = "#1E1E1E"
        text_content = cards[idx]['a'] if show_ans else cards[idx]['q']
        text_color = "#B5FF5F" if show_ans else "#FFFFFF"
        label = "ANSWER" if show_ans else "QUESTION"

        st.markdown(f"""
        <div style="
            background: {card_bg}; 
            border: 2px solid {text_color}; 
            border-radius: 20px; 
            padding: 50px; 
            text-align: center; 
            min-height: 250px; 
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            animation: fadeIn 0.5s;
        ">
            <div style="color: #666; font-size: 12px; letter-spacing: 2px; margin-bottom: 20px;">{label}</div>
            <div style="font-size: 24px; font-weight: bold; color: {text_color};">{text_content}</div>
        </div>
        """, unsafe_allow_html=True)

        st.write("")
        
        # Controls
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            if show_ans:
                if st.button("Next Card ➡️", use_container_width=True, type="primary"):
                    if idx < len(cards) - 1:
                        st.session_state['card_index'] += 1
                        st.session_state['show_answer'] = False
                    else:
                        st.balloons()
                        st.toast("Session Complete! +50 XP")
                        st.session_state['user_xp'] += 50
                        st.session_state['flashcards'] = [] # Reset
                    st.rerun()
            else:
                if st.button("👀 Reveal Answer", use_container_width=True):
                    st.session_state['show_answer'] = True
                    st.rerun()

# --- PAGE: EISENHOWER MATRIX ---
def page_eisenhower():
    st.markdown('<div class="big-title">📐 Eisenhower Matrix</div>', unsafe_allow_html=True)
    st.caption("Prioritize tasks by Urgency and Importance.")

    slots = st.session_state.get('timetable_slots', [])
    pending = [t for t in slots if not t['Done']]

    if not pending:
        st.info("No pending tasks to categorize.")
        return

    # Logic to categorize tasks
    # We use 'Difficulty' as Importance and 'Time' vs Current Time as Urgency
    
    q1 = [] # Do First (Hard + Urgent)
    q2 = [] # Schedule (Hard + Not Urgent)
    q3 = [] # Delegate (Easy + Urgent)
    q4 = [] # Delete (Easy + Not Urgent)

    current_hr = datetime.datetime.now().hour
    
    for t in pending:
        # Simple heuristic logic
        is_hard = "Hard" in t['Difficulty'] or "Major" in t['Difficulty']
        
        try:
            task_hr = int(t['Time'].split(":")[0])
            is_urgent = (task_hr - current_hr) < 3 and (task_hr - current_hr) > -5
        except:
            is_urgent = False

        if is_hard and is_urgent: q1.append(t)
        elif is_hard and not is_urgent: q2.append(t)
        elif not is_hard and is_urgent: q3.append(t)
        else: q4.append(t)

    # Render Grid
    c1, c2 = st.columns(2)
    
    def render_quadrant(title, tasks, color, icon):
        st.markdown(f"""
        <div style="background:{color}15; border:1px solid {color}; border-radius:10px; padding:15px; height:100%; min-height:200px;">
            <div style="font-weight:bold; color:{color}; margin-bottom:10px;">{icon} {title} ({len(tasks)})</div>
            {''.join([f'<div style="font-size:13px; margin-bottom:5px; padding:5px; background:rgba(0,0,0,0.2); border-radius:5px;">• {task["Activity"]}</div>' for task in tasks])}
        </div>
        """, unsafe_allow_html=True)

    with c1:
        render_quadrant("DO FIRST", q1, "#FF4B4B", "🔥") # Red
        st.write("")
        render_quadrant("DELEGATE", q3, "#00E5FF", "⚡") # Blue
        
    with c2:
        render_quadrant("SCHEDULE", q2, "#B5FF5F", "📅") # Green
        st.write("")
        render_quadrant("DELETE/LATER", q4, "#A0A0A0", "🗑️") # Grey

# --- 20. MAIN APPLICATION ROUTER ---
def main():
    # 1. Initialize System State
    initialize_session_state()
    
    # 2. CHECK GLOBAL ALARMS
    check_reminders()
    render_alarm_ui()

    # 3. Load Styles & Splash
    inject_custom_css()
    show_comet_splash()

    # 4. Onboarding Gate
    if not st.session_state['onboarding_complete']:
        page_onboarding()
        return 

    # 5. CHAT MODE SIDEBAR
    if st.session_state.get('page_mode') == 'chat':
        with st.sidebar:
            st.markdown("### 💬 AI Controls")
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

            if 'delete_mode' not in st.session_state: st.session_state['delete_mode'] = False
            toggle_label = "Done Managing" if st.session_state['delete_mode'] else "🗑️ Manage Chats"
            if st.button(toggle_label, use_container_width=True):
                st.session_state['delete_mode'] = not st.session_state['delete_mode']
                st.rerun()

            st.write("") 
            
            sessions = load_chat_sessions()
            if sessions:
                st.markdown("#### History")
                for s in sessions:
                    sid = s['SessionID']
                    sname = s['SessionName']
                    
                    if st.session_state['delete_mode']:
                        if st.button(f"🗑️ {sname}", key=f"del_{sid}", use_container_width=True):
                            delete_chat_session(sid)
                            if st.session_state.get('current_session_id') == sid:
                                st.session_state['current_session_id'] = None
                                st.session_state['chat_history'] = []
                            st.rerun()
                    else:
                        if st.button(f"💬 {sname}", key=f"sess_{sid}", use_container_width=True):
                            st.session_state['current_session_id'] = sid
                            st.session_state['current_session_name'] = sname
                            st.session_state['chat_history'] = load_messages_for_session(sid)
                            st.rerun()
        
        page_ai_assistant()

    # 6. STANDARD SIDEBAR (Main Menu)
    else:
        with st.sidebar:
            st.markdown("<h1 style='text-align: center;'>🏹<br>TimeHunt AI</h1>", unsafe_allow_html=True)
            render_live_clock()
            
            # Exam Countdown Code
            target_date = datetime.date(2026, 2, 15) # Example: Board Exam Date
            days_left = (target_date - datetime.date.today()).days
            
            st.markdown(f"""
            <div style="background: linear-gradient(45deg, #FF4B4B, #FF914D); padding: 10px; border-radius: 8px; text-align: center; margin-bottom: 20px;">
                <div style="font-size: 12px; font-weight: bold; color: black;">JEE / BOARDS 2026</div>
                <div style="font-size: 20px; font-weight: 900; color: white;">{days_left} DAYS LEFT</div>
            </div>
            """, unsafe_allow_html=True)
            st.write("") 

            with st.container(border=True):
                st.markdown("### 🎧 Focus Zone")
                st.markdown("""
                <style>.equalizer { display: flex; justify-content: center; align-items: flex-end; height: 40px; gap: 4px; margin-bottom: 15px; } .bar { width: 6px; background: var(--primary-color); animation: bounce 1s infinite ease-in-out; border-radius: 3px; } .bar:nth-child(1) { animation-duration: 0.8s; height: 15px; } .bar:nth-child(2) { animation-duration: 1.1s; height: 25px; } .bar:nth-child(3) { animation-duration: 1.3s; height: 35px; } .bar:nth-child(4) { animation-duration: 0.9s; height: 20px; } .bar:nth-child(5) { animation-duration: 1.2s; height: 30px; } @keyframes bounce { 0%, 100% { transform: scaleY(0.5); opacity: 0.6; } 50% { transform: scaleY(1.2); opacity: 1; } } </style>
                <div class="equalizer"><div class="bar"></div><div class="bar"></div><div class="bar"></div><div class="bar"></div><div class="bar"></div></div>
                """, unsafe_allow_html=True)

                music_mode = st.selectbox("Soundscape", ["Om Chanting", "Binaural Beats", "Flute Flow", "Rainfall"], label_visibility="collapsed")
                local_map = {"Om Chanting": "om.mp3", "Binaural Beats": "binaural.mp3", "Flute Flow": "flute.mp3", "Rainfall": "rain.mp3"}
                target_file = local_map.get(music_mode)
                
                if target_file and os.path.exists(target_file):
                    st.audio(target_file, format="audio/mp3", loop=True)
                    st.caption(f"▶ Now Playing: {music_mode}")
                else:
                    # Online Fallback links
                    online_map = {
                        "Om Chanting": "https://cdn.pixabay.com/audio/2022/10/14/audio_9855325881.mp3",
                        "Binaural Beats": "https://cdn.pixabay.com/audio/2022/05/27/audio_1808fbf07a.mp3",
                        "Flute Flow": "https://cdn.pixabay.com/audio/2022/11/22/audio_febc508520.mp3",
                        "Rainfall": "https://cdn.pixabay.com/audio/2022/07/04/audio_03d6f14068.mp3"
                    }
                    if music_mode in online_map:
                        st.audio(online_map[music_mode], format="audio/mp3", loop=True)
                        st.caption(f"▶ Streaming: {music_mode} (Online)")
                    else:
                        st.warning("Audio unavailable.")

            st.markdown("---")
            
            # --- FIXED MENU SYNTAX HERE ---
            nav = option_menu(
                menu_title=None,
                options=["Home", "Scheduler", "Eisenhower Matrix", "Study Zone", "Calendar", "Chat with TimeHunt AI", "Timer", "Analytics", "Help Center", "About", "Settings"], 
                icons=["house", "list-check", "grid-3x3-gap", "book", "calendar-week", "robot", "hourglass-split", "graph-up", "question-circle", "info-circle", "gear"], 
                default_index=0,
                styles={
                    "container": {"padding": "0!important", "background-color": "transparent"},
                    "icon": {"color": "var(--primary-color)", "font-size": "16px"}, 
                    "nav-link": {"font-size": "15px", "text-align": "left", "margin":"2px", "--hover-color": "#333"},
                    "nav-link-selected": {"background-color": "var(--primary-color)", "color": "#000"},
                }
            )
            st.caption(f"👤 **{st.session_state.get('user_name', 'User')}**")

        if nav == "Home": page_home()
        elif nav == "Scheduler": page_scheduler()
        elif nav == "Eisenhower Matrix": page_eisenhower()
        elif nav == "Study Zone": page_study_zone() # --- FIXED MISSING ROUTE ---
        elif nav == "Calendar": page_calendar()
        elif nav == "Chat with TimeHunt AI": 
            st.session_state['page_mode'] = 'chat'
            st.rerun()
        elif nav == "Timer": page_timer()  
        elif nav == "Analytics": page_dashboard()
        elif nav == "Help Center": page_help()
        elif nav == "About": page_about()
        elif nav == "Settings": page_settings()

if __name__ == "__main__":
    main()