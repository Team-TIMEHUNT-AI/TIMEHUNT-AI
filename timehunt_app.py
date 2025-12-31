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
            /* --- GOOGLE MATERIAL COLOR SYSTEM --- */
            :root {
                --primary: #B5FF5F;       /* Neon Green (Growth) */
                --surface: #121212;       /* Material Dark */
                --surface-card: #1E1E1E;  /* Slightly lighter for cards */
                --background: #000000;    /* Pure Black */
                --text: #FFFFFF;
            }

            /* --- GLOBAL RESET --- */
            .stApp {
                background-color: var(--background) !important;
                font-family: 'Inter', sans-serif;
            }
            
            /* HIDE DEFAULT STREAMLIT ELEMENTS */
            [data-testid="stSidebarNav"], [data-testid="collapsedControl"], 
            section[data-testid="stSidebar"], header, footer, #MainMenu {
                display: none;
            }

            /* --- MOBILE GRID FIX (The "Notion" Layout) --- */
            [data-testid="column"] {
                width: calc(50% - 10px) !important;
                flex: 1 1 calc(50% - 10px) !important;
                min-width: 150px !important;
            }

            /* --- GOOGLE "PILL" BUTTONS --- */
            div.stButton > button {
                background-color: var(--surface-card);
                color: var(--text);
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 50px; /* Pill Shape */
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
                transition: all 0.2s ease;
                width: 100%;
            }
            div.stButton > button:hover {
                transform: translateY(-2px);
                border-color: var(--primary);
                color: var(--primary);
                box-shadow: 0 5px 15px rgba(181, 255, 95, 0.2);
            }

            /* --- XP PROGRESS BAR --- */
            .xp-bar-bg {
                width: 100%; height: 6px; background: #333; border-radius: 10px; margin-top: 8px; overflow: hidden;
            }
            .xp-bar-fill {
                height: 100%; background: linear-gradient(90deg, #B5FF5F, #00E5FF); border-radius: 10px;
            }
            
            /* --- MOOD TRACKER SPACING --- */
            div[data-testid="stHorizontalBlock"] { gap: 8px !important; }
        </style>
    """, unsafe_allow_html=True)

# --- 4. UI COMPONENTS (The Building Blocks) ---

def ui_grid_card(title, icon, subtitle, color):
    """
    The 'Notion Block' Card. 
    Clean, rectangular, with a glowing accent color on hover.
    """
    st.markdown(f"""
    <div style="
        background-color: #1E1E1E;
        border-radius: 20px;
        padding: 20px;
        height: 140px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        border: 1px solid rgba(255,255,255,0.05);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        cursor: pointer;
        position: relative;
        overflow: hidden;
        margin-bottom: 10px;
    " onmouseover="this.style.transform='scale(1.02)'; this.style.borderColor='{color}';" 
       onmouseout="this.style.transform='scale(1)'; this.style.borderColor='rgba(255,255,255,0.05)';">
        
        <div style="position: absolute; top: -30px; right: -30px; width: 80px; height: 80px; background: {color}; filter: blur(40px); opacity: 0.15;"></div>

        <div style="font-size: 32px; margin-bottom: 10px;">{icon}</div>
        <div>
            <div style="font-size: 15px; font-weight: 700; color: #FFF;">{title}</div>
            <div style="font-size: 11px; font-weight: 500; color: #888;">{subtitle}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_hero_header():
    """
    The 'Gamified' Profile Header. 
    Shows Avatar + XP Bar (Psychology Hook).
    """
    xp = st.session_state['user_xp']
    lvl = st.session_state['user_level']
    progress = (xp % 1000) / 10  # Simple % calc
    
    st.markdown(f"""
    <div style="padding: 20px; background: linear-gradient(180deg, rgba(30,30,30,0.5) 0%, rgba(0,0,0,0) 100%); border-radius: 0 0 30px 30px; margin-bottom: 20px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap: 15px;">
                <div style="font-size: 32px; background: #111; width: 55px; height: 55px; border-radius: 18px; display:flex; align-items:center; justify-content:center; border: 1px solid #333;">
                    {st.session_state['user_avatar']}
                </div>
                <div>
                    <div style="font-size: 18px; font-weight: 800; color: white;">{st.session_state['user_name']}</div>
                    <div style="font-size: 11px; color: #B5FF5F; font-weight: 600;">LVL {lvl} • {xp} XP</div>
                </div>
            </div>
            <div style="text-align:right;">
                <div style="font-size: 12px; color: #666; font-weight:700; letter-spacing:1px;">TODAY</div>
                <div style="font-size: 24px; font-weight: 700; color: #FFF;">{datetime.datetime.now().strftime('%H:%M')}</div>
            </div>
        </div>
        
        <div class="xp-bar-bg">
            <div class="xp-bar-fill" style="width: {progress}%;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

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