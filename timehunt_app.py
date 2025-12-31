import streamlit as st
import streamlit.components.v1 as components 
from streamlit_option_menu import option_menu
import datetime
import pandas as pd
import time
import base64
import os
import random

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="TimeHunt AI", 
    layout="wide", 
    page_icon="🏹", 
    initial_sidebar_state="collapsed"
)

# --- 2. SESSION STATE (The App's Memory) ---
def initialize_session_state():
    defaults = {
        'user_name': "Achiever",
        'user_xp': 1250,          # Starting XP for demo
        'user_level': 5,
        'user_avatar': "🏹",
        'current_mood': "Neutral",
        'onboarding_complete': True, # Skip onboarding for dev speed
        'timetable_slots': [
            {"Time": "09:00", "Activity": "Deep Work", "Category": "Work", "Done": False, "Difficulty": "Hard"},
            {"Time": "11:00", "Activity": "Team Meeting", "Category": "Work", "Done": True, "Difficulty": "Medium"},
        ],
        'splash_played': False 
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

# Initialize immediately
initialize_session_state()

# --- 3. THE VISUAL ENGINE (CSS) ---
def inject_custom_css():
    st.markdown("""
        <style>
            /* 1. Global Reset */
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
            .stApp { background-color: #000000 !important; font-family: 'Inter', sans-serif; }
            
            /* 2. Hide Defaults */
            [data-testid="stSidebarNav"], [data-testid="collapsedControl"], header, footer, #MainMenu { display: none; }

            /* 3. Mobile Grid Fix */
            [data-testid="column"] {
                width: calc(50% - 10px) !important;
                flex: 1 1 calc(50% - 10px) !important;
                min-width: 150px !important;
            }

            /* 4. Google "Pill" Buttons */
            div.stButton > button {
                background-color: #1A1A1A;
                color: #FFF;
                border: 1px solid #333;
                border-radius: 50px;
                padding: 12px 24px;
                font-weight: 600;
                transition: 0.2s;
                width: 100%;
            }
            div.stButton > button:hover {
                border-color: #B5FF5F;
                color: #B5FF5F;
                transform: translateY(-2px);
            }
            
            /* 5. Horizontal Layout Spacing */
            div[data-testid="stHorizontalBlock"] { gap: 10px !important; }
        </style>
    """, unsafe_allow_html=True)

# --- 4. UI COMPONENTS (The Building Blocks) ---

def ui_grid_card(title, icon, subtitle, color):
    """
    Renders a Notion-style card.
    """
    html_code = textwrap.dedent(f"""
    <div style="
        background-color: #161616;
        border-radius: 24px;
        padding: 20px;
        height: 150px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        border: 1px solid #222;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    ">
        <div style="position: absolute; top: -40px; right: -40px; width: 100px; height: 100px; background: {color}; filter: blur(50px); opacity: 0.15;"></div>

        <div style="font-size: 32px; z-index: 1;">{icon}</div>
        <div style="z-index: 1;">
            <div style="font-size: 16px; font-weight: 700; color: #EEE; letter-spacing: -0.3px;">{title}</div>
            <div style="font-size: 11px; font-weight: 500; color: #666; margin-top: 4px;">{subtitle}</div>
        </div>
    </div>
    """)
    st.markdown(html_code, unsafe_allow_html=True)

def render_hero_header():
    """
    Renders the Gamified Profile Header. 
    """
    xp = st.session_state.get('user_xp', 0)
    lvl = st.session_state.get('user_level', 1)
    # Simple progress calculation (0 to 100%)
    progress = min(100, (xp % 1000) / 10) 
    
    # We use textwrap.dedent to prevent the HTML from breaking
    html_code = textwrap.dedent(f"""
    <div style="padding: 20px; background: linear-gradient(180deg, #161616 0%, #000000 100%); border-radius: 0 0 24px 24px; border-bottom: 1px solid #222; margin-bottom: 25px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap: 15px;">
                <div style="font-size: 32px; background: #1A1A1A; width: 60px; height: 60px; border-radius: 20px; display:flex; align-items:center; justify-content:center; border: 1px solid #333; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
                    {st.session_state.get('user_avatar', '🏹')}
                </div>
                <div>
                    <div style="font-size: 20px; font-weight: 800; color: white; letter-spacing: -0.5px;">{st.session_state.get('user_name', 'Achiever')}</div>
                    <div style="font-size: 11px; color: #B5FF5F; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;">Level {lvl} • {xp} XP</div>
                </div>
            </div>
            <div style="text-align:right;">
                <div style="font-size: 10px; color: #666; font-weight:700; letter-spacing:1px; text-transform: uppercase;">TimeHunt</div>
                <div style="font-size: 24px; font-weight: 700; color: #FFF; font-family: monospace;">{datetime.datetime.now().strftime('%H:%M')}</div>
            </div>
        </div>
        
        <div style="margin-top: 20px;">
            <div style="display:flex; justify-content: space-between; font-size: 10px; color: #555; margin-bottom: 6px; font-weight: 600;">
                <span>PROGRESS TO LVL {lvl + 1}</span>
                <span>{int(progress)}%</span>
            </div>
            <div style="width: 100%; height: 8px; background: #222; border-radius: 10px; overflow: hidden;">
                <div style="width: {progress}%; height: 100%; background: linear-gradient(90deg, #B5FF5F, #00E5FF); border-radius: 10px; box-shadow: 0 0 10px rgba(181, 255, 95, 0.4);"></div>
            </div>
        </div>
    </div>
    """)
    st.markdown(html_code, unsafe_allow_html=True)


# --- 5. PAGES ---

def page_home():
    # 1. Hero Section
    render_hero_header()

    # 2. Mood Pulse (Emotional Support)
    st.markdown("<div style='padding: 0 20px; margin-bottom: 10px; font-size: 13px; color: #888; font-weight: 600;'>Mental Pulse</div>", unsafe_allow_html=True)
    
    with st.container():
        c1, c2, c3, c4, c5 = st.columns(5)
        # Using lists to generate buttons cleanly
        moods = [("🔥", "Fire"), ("🙂", "Good"), ("😐", "Okay"), ("🌧️", "Low"), ("💀", "Dead")]
        
        # Columns in Streamlit need manual assignment
        if c1.button(moods[0][0], key="m1"): st.toast(f"Mood: {moods[0][1]}")
        if c2.button(moods[1][0], key="m2"): st.toast(f"Mood: {moods[1][1]}")
        if c3.button(moods[2][0], key="m3"): st.toast(f"Mood: {moods[2][1]}")
        if c4.button(moods[3][0], key="m4"): st.toast(f"Mood: {moods[3][1]}")
        if c5.button(moods[4][0], key="m5"): st.toast(f"Mood: {moods[4][1]}")

    st.write("") # Spacer

    # 3. The "Notion" Grid (Systems)
    st.markdown("<div style='padding: 0 20px; margin-bottom: 15px; font-size: 13px; color: #888; font-weight: 600;'>Workspace</div>", unsafe_allow_html=True)
    
    r1a, r1b = st.columns(2)
    with r1a: ui_grid_card("Plan", "📅", "Calendar & Tasks", "#00E5FF")
    with r1b: ui_grid_card("Focus", "⏳", "Deep Work Timer", "#B5FF5F")
    
    r2a, r2b = st.columns(2)
    with r2a: ui_grid_card("Growth", "📈", "Analytics & XP", "#FF4B4B")
    with r2b: ui_grid_card("Assistant", "🤖", "AI Chat", "#A0A0A0")

# Placeholder pages for navigation
def page_tasks(): st.title("Tasks")
def page_chat(): st.title("AI Chat")
def page_focus(): st.title("Focus Timer")
def page_stats(): st.title("Statistics")

# --- 6. MAIN APP LOOP ---
def main():
    # A. Inject Styles
    inject_custom_css()
    
    # B. Bottom Navigation
    selected = option_menu(
        menu_title=None,
        options=["Home", "Tasks", "Chat", "Focus", "Stats"],
        icons=["house-fill", "list-check", "chat-dots-fill", "clock-fill", "bar-chart-fill"],
        menu_icon="cast",
        default_index=0,
        orientation="horizontal",
        styles={
            "container": {
                "padding": "0!important", 
                "background-color": "#000000", 
                "position": "fixed", 
                "bottom": "0", 
                "left": "0", 
                "right": "0",
                "z-index": "999",
                "border-top": "1px solid #222"
            },
            "icon": {"color": "#B5FF5F", "font-size": "20px"}, 
            "nav-link": {
                "font-size": "10px", 
                "text-align": "center", 
                "margin": "0px", 
                "color": "#666",
                "--hover-color": "#222"
            },
            "nav-link-selected": {"background-color": "transparent", "color": "#B5FF5F"},
        }
    )

    # C. Routing
    if selected == "Home": page_home()
    elif selected == "Tasks": page_tasks()
    elif selected == "Chat": page_chat()
    elif selected == "Focus": page_focus()
    elif selected == "Stats": page_stats()

    # Padding to prevent content being hidden by nav bar
    st.markdown('<div style="height: 100px;"></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()