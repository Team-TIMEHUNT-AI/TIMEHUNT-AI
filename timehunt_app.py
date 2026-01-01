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
import extra_streamlit_components as stx

# --- PATH CONFIGURATION ---
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

# --- 1. SESSION MANAGEMENT ---
def init_session_state():
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if 'user_info' not in st.session_state: st.session_state.user_info = None
    if 'splash_played' not in st.session_state: st.session_state['splash_played'] = False
    # Ensure all data keys exist
    defaults = {
        'chat_history': [], 'timetable_slots': [], 'reminders': [], 
        'user_xp': 0, 'user_level': 1, 'xp_history': [],
        'user_name': "Hunter", 'theme_color': 'Venom Green (Default)', 'theme_mode': 'Light'
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def get_cookie_manager():
    return stx.CookieManager(key="auth_cookie_manager")

# --- 2. AUTHENTICATION (GSHEETS + COOKIES) ---
def login_user(username, password, cookie_manager):
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="Sheet1", ttl=0)
        
        if not df.empty and 'Name' in df.columns:
            # FIX: Remove trailing .0 from PINs if they exist
            df['PIN'] = df['PIN'].astype(str).str.replace(r'\.0$', '', regex=True)
            user_row = df[(df['Name'] == username) & (df['PIN'] == str(password))]
            
            if not user_row.empty:
                st.session_state.logged_in = True
                st.session_state.user_info = username
                st.session_state.user_name = username
                cookie_manager.set("auth_token", username, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                st.success("Access Granted.")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Access Denied: Invalid Credentials")
        else:
            st.error("Database connection failed.")
    except Exception as e:
        st.error(f"System Error: {e}")

def logout_user():
    cm = get_cookie_manager()
    cm.delete("auth_token")
    st.session_state.logged_in = False
    st.rerun()

def handle_auth():
    init_session_state()
    cookie_manager = get_cookie_manager()
    
    # Auto-login via Cookie
    cookie_val = cookie_manager.get("auth_token")
    if cookie_val and not st.session_state.logged_in:
        st.session_state.logged_in = True
        st.session_state.user_info = cookie_val
        st.session_state.user_name = cookie_val
        return True

    if st.session_state.logged_in: return True

    # Intro & Login Screen
    show_comet_splash()
    
    st.markdown('<div style="text-align:center; font-size: 32px; font-weight: 800; margin-bottom: 20px;">🔐 TimeHunt AI</div>', unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login_form"):
            username = st.text_input("Codename")
            password = st.text_input("PIN", type="password")
            if st.form_submit_button("Authenticate", use_container_width=True):
                login_user(username, password, cookie_manager)
    return False

# --- 3. UI & STYLING (WORLD CLASS) ---
def inject_custom_css():
    # Load User Preferences
    theme_color = st.session_state.get('theme_color', 'Venom Green (Default)')
    theme_mode = st.session_state.get('theme_mode', 'Light')
    
    colors = {"Venom Green (Default)": "#B5FF5F", "Cyber Blue": "#00E5FF", "Crimson Alert": "#FF2A2A"}
    accent = colors.get(theme_color, "#B5FF5F")
    
    if theme_mode == "Light":
        main_bg = "#F8F9FA"
        sidebar_bg = "#FFFFFF"
        text_color = "#1A1A1A"
        card_bg = "#FFFFFF"
    else:
        main_bg = "#0E1117"
        sidebar_bg = "#161B22"
        text_color = "#E6EDF3"
        card_bg = "#1E232F"

    st.markdown(f"""
        <style>
            :root {{ --accent: {accent}; --text: {text_color}; --card: {card_bg}; }}
            .stApp {{ background-color: {main_bg}; color: {text_color}; }}
            [data-testid="stSidebar"] {{ background-color: {sidebar_bg}; border-right: 1px solid rgba(0,0,0,0.1); }}
            
            /* Professional Headings */
            h1, h2, h3 {{ font-family: 'Helvetica', sans-serif; font-weight: 700; color: {text_color}; }}
            .big-title {{ font-size: 42px; font-weight: 800; margin-bottom: 10px; }}
            .sub-title {{ font-size: 18px; opacity: 0.7; margin-bottom: 30px; }}
            
            /* Cards */
            .css-card {{
                background-color: {card_bg};
                padding: 25px;
                border-radius: 15px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.05);
                border: 1px solid rgba(128,128,128,0.1);
                margin-bottom: 20px;
            }}
            .card-title {{ font-size: 18px; font-weight: 700; margin-bottom: 5px; }}
            .stat-num {{ font-size: 32px; font-weight: 800; color: {text_color}; }}
            
            /* Buttons */
            .stButton>button {{
                border-radius: 8px; font-weight: 600; border: none;
                transition: transform 0.2s;
            }}
            .stButton>button:hover {{ transform: translateY(-2px); }}
        </style>
    """, unsafe_allow_html=True)

# --- 4. REDESIGNED MAIN SIDEBAR ---
def render_sidebar():
    with st.sidebar:
        # 1. HEADER & FOCUS TOOLS (Top)
        st.markdown(f"### 🏹 Agent: **{st.session_state.user_name}**")
        
        with st.expander("🎧 Focus Tools", expanded=True):
            st.selectbox("Frequency", ["Om Chanting", "Binaural Beats", "Flow State"], label_visibility="collapsed")
            c1, c2 = st.columns([2, 1])
            c1.write("⏱️ Timer (25m)")
            if c2.button("Start"): st.toast("Timer Started")
        
        st.divider()

        # 2. MAIN NAVIGATION (Middle)
        selected_page = option_menu(
            menu_title=None,
            options=["Home", "Scheduler", "AI Assistant", "Dashboard", "Calendar", "Reminders", "Settings", "About", "Help"], 
            icons=["house", "calendar-check", "robot", "graph-up", "calendar3", "alarm", "gear", "info-circle", "question-circle"], 
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": "transparent"},
                "nav-link": {"font-size": "15px", "text-align": "left", "margin":"0px", "--hover-color": "#eee"},
                "nav-link-selected": {"background-color": "#333", "color": "#B5FF5F"},
            }
        )
        
        # 3. LOGOUT (Bottom)
        st.write("")
        st.write("")
        st.divider()
        if st.button("🚪 Log Out System", use_container_width=True, type="primary"):
            logout_user()

        return selected_page

# --- 5. SPLASH & INTRO ---
def show_comet_splash():
    if not st.session_state['splash_played']:
        placeholder = st.empty()
        # (Simplified splash logic for stability - ensure 1000592991.png exists)
        placeholder.empty() 
        st.session_state['splash_played'] = True

# --- 6. AI ENGINE & CHAT ---
def perform_auto_search(query):
    # DUMMY AI RESPONSE FOR DEMO (Connect your real Gemini logic here)
    time.sleep(1)
    return f"**AI Protocol:** I have received your query: *'{query}'*. \n\nHere is a strategic breakdown...", "TimeHunt AI"

def handle_chat(prompt):
    st.session_state['chat_history'].append({"role": "user", "text": prompt})
    res_text, _ = perform_auto_search(prompt)
    st.session_state['chat_history'].append({"role": "assistant", "text": res_text})
    st.rerun()

# --- 7. PAGES ---

def page_home():
    st.markdown(f'<div class="big-title">Welcome back, {st.session_state.user_name}</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Your command center is active.</div>', unsafe_allow_html=True)
    
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(f"""
        <div class="css-card">
            <div class="card-title">Current Objective</div>
            <div style="font-size: 20px; margin-bottom: 10px;">🚀 Master the Capstone Project</div>
            <div class="stat-num">{st.session_state.user_xp} XP</div>
            <div>Level {st.session_state.user_level}</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="css-card" style="background-color: var(--accent); color: black;">
            <div class="card-title" style="color: black;">Daily Streak</div>
            <div class="stat-num" style="color: black;">🔥 {st.session_state.get('streak', 1)}</div>
            <div>Keep hunting!</div>
        </div>
        """, unsafe_allow_html=True)

def page_ai_assistant():
    # LAYOUT: History (Left) | Chat (Right)
    col_hist, col_chat = st.columns([1, 3])
    
    with col_hist:
        with st.container(border=True):
            st.markdown("### 🗂️ History")
            if st.button("🗑️ Clear Chats", use_container_width=True):
                st.session_state['chat_history'] = []
                st.rerun()
            st.divider()
            if not st.session_state['chat_history']:
                st.caption("No logs available.")
            else:
                for i, msg in enumerate(reversed(st.session_state['chat_history'][-6:])):
                    if msg['role'] == "user":
                        label = (msg['text'][:15] + '..') if len(msg['text']) > 15 else msg['text']
                        st.button(f"💬 {label}", key=f"h_{i}", use_container_width=True)

    with col_chat:
        st.markdown("### 🤖 Tactical Support")
        for msg in st.session_state['chat_history']:
            with st.chat_message(msg['role']): st.write(msg['text'])
        
        if prompt := st.chat_input("Enter command..."):
            handle_chat(prompt)

def page_scheduler():
    st.title("📅 Mission Scheduler")
    st.write("Scheduler module active.")

def page_settings():
    st.title("⚙️ Settings")
    
    st.markdown("### Visual Interface")
    mode = st.radio("Theme Mode", ["Light", "Dark"])
    color = st.selectbox("Accent Color", ["Venom Green (Default)", "Cyber Blue", "Crimson Alert"])
    
    if st.button("Apply Settings"):
        st.session_state['theme_mode'] = mode
        st.session_state['theme_color'] = color
        st.toast("System Updated")
        time.sleep(1)
        st.rerun()

def check_reminders():
    # Placeholder for alarm logic
    pass

def render_alarm_ui():
    pass

# --- MAIN ROUTER ---
def main():
    # 1. INJECT THE UI (The key step!)
    inject_custom_css()
    
    # 2. CHECK AUTH
    if not handle_auth():
        return

    # 3. RENDER SIDEBAR & NAV
    nav_selection = render_sidebar() 
    
    # 4. PAGE ROUTING
    if nav_selection == "Home": page_home()
    elif nav_selection == "Scheduler": page_scheduler()
    elif nav_selection == "AI Assistant": page_ai_assistant()
    elif nav_selection == "Dashboard": 
        st.title("🏆 Dashboard"); st.info("Connect GSheets for live stats.")
    elif nav_selection == "Calendar": st.title("📅 Calendar"); st.info("Coming Soon")
    elif nav_selection == "Reminders": st.title("⏰ Reminders"); st.write(st.session_state.get('reminders', []))
    elif nav_selection == "Settings": page_settings()
    elif nav_selection == "About": st.title("ℹ️ About"); st.write("TimeHunt AI v2.0")
    elif nav_selection == "Help": st.title("❓ Help"); st.write("Documentation")

    # Global Checks
    check_reminders()

if __name__ == "__main__":
    main()