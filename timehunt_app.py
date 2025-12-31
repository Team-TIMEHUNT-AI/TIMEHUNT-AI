import streamlit as st
from streamlit_option_menu import option_menu
import streamlit.components.v1 as components 
import datetime
import textwrap
import os

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="TimeHunt AI", 
    layout="wide", 
    page_icon="🏹", 
    initial_sidebar_state="collapsed"
)

# --- 2. THE VISUAL ENGINE (CSS) ---
def inject_custom_css():
    st.markdown("""
        <style>
            /* 1. Global Reset & Fonts */
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
            
            .stApp { 
                background-color: #000000 !important; 
                font-family: 'Inter', sans-serif; 
            }
            
            /* 2. Hide Default Streamlit Elements */
            [data-testid="stSidebarNav"], [data-testid="collapsedControl"], header, footer, #MainMenu { 
                display: none !important; 
            }

            /* 3. Mobile Grid Fix (The "Notion" 2-Column Look) */
            [data-testid="column"] {
                width: calc(50% - 10px) !important;
                flex: 1 1 calc(50% - 10px) !important;
                min-width: 150px !important;
            }

            /* 4. Google "Pill" Buttons (Mood Tracker) */
            div.stButton > button {
                background-color: #1A1A1A;
                color: #FFF;
                border: 1px solid #333;
                border-radius: 50px;
                padding: 12px 10px;
                font-weight: 600;
                transition: 0.2s;
                width: 100%;
                font-size: 18px; /* Bigger Emoji */
            }
            div.stButton > button:hover {
                border-color: #B5FF5F;
                color: #B5FF5F;
                transform: translateY(-2px);
                box-shadow: 0 4px 10px rgba(181, 255, 95, 0.2);
            }
            
            /* 5. Horizontal Layout Spacing */
            div[data-testid="stHorizontalBlock"] { 
                gap: 8px !important; 
            }
            
            /* 6. Floating Action Button (FAB) */
            .fab {
                position: fixed; bottom: 90px; right: 20px;
                width: 55px; height: 55px;
                background: #B5FF5F; border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                box-shadow: 0 4px 20px rgba(181, 255, 95, 0.4);
                z-index: 1000; font-size: 24px; cursor: pointer;
            }
        </style>
        <div class="fab">🤖</div>
    """, unsafe_allow_html=True)

# --- 3. SESSION STATE ---
def initialize_session_state():
    if 'user_xp' not in st.session_state:
        st.session_state.update({
            'user_name': "Achiever",
            'user_xp': 1250,
            'user_level': 5,
            'user_avatar': "🏹",
            'current_mood': "Neutral",
            'splash_played': False
        })

# --- 4. UI COMPONENTS (The Blocks) ---

def render_hero_header():
    """
    Renders the Gamified Profile Header. 
    """
    xp = st.session_state.get('user_xp', 0)
    lvl = st.session_state.get('user_level', 1)
    progress = min(100, (xp % 1000) / 10) 
    
    # HTML Block for the Gradient Header
    html_code = textwrap.dedent(f"""
    <div style="padding: 20px; background: linear-gradient(180deg, #161616 0%, #000000 100%); border-radius: 0 0 24px 24px; border-bottom: 1px solid #222; margin-bottom: 25px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap: 15px;">
                <div style="font-size: 32px; background: #1A1A1A; width: 60px; height: 60px; border-radius: 20px; display:flex; align-items:center; justify-content:center; border: 1px solid #333; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
                    {st.session_state.get('user_avatar', '🏹')}
                </div>
                <div>
                    <div style="font-size: 20px; font-weight: 800; color: white; letter-spacing: -0.5px; font-family: sans-serif;">{st.session_state.get('user_name', 'Achiever')}</div>
                    <div style="font-size: 11px; color: #B5FF5F; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; font-family: sans-serif;">Level {lvl} • {xp} XP</div>
                </div>
            </div>
            <div style="text-align:right;">
                <div style="font-size: 10px; color: #666; font-weight:700; letter-spacing:1px; text-transform: uppercase; font-family: sans-serif;">TODAY</div>
                <div style="font-size: 24px; font-weight: 700; color: #FFF; font-family: monospace;">{datetime.datetime.now().strftime('%H:%M')}</div>
            </div>
        </div>
        
        <div style="margin-top: 20px;">
            <div style="display:flex; justify-content: space-between; font-size: 10px; color: #555; margin-bottom: 6px; font-weight: 600; font-family: sans-serif;">
                <span>PROGRESS TO LVL {lvl + 1}</span>
                <span>{int(progress)}%</span>
            </div>
            <div style="width: 100%; height: 8px; background: #222; border-radius: 10px; overflow: hidden;">
                <div style="width: {progress}%; height: 100%; background: linear-gradient(90deg, #B5FF5F, #00E5FF); border-radius: 10px; box-shadow: 0 0 10px rgba(181, 255, 95, 0.4);"></div>
            </div>
        </div>
    </div>
    """)
    # CRITICAL FIX: unsafe_allow_html=True enables the graphics
    st.markdown(html_code, unsafe_allow_html=True)

def ui_grid_card(title, icon, subtitle, color):
    """
    Renders a Notion-style card block.
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
            <div style="font-size: 16px; font-weight: 700; color: #EEE; letter-spacing: -0.3px; font-family: sans-serif;">{title}</div>
            <div style="font-size: 11px; font-weight: 500; color: #666; margin-top: 4px; font-family: sans-serif;">{subtitle}</div>
        </div>
    </div>
    """)
    st.markdown(html_code, unsafe_allow_html=True)

def show_cinematic_intro():
    if not st.session_state.get('splash_played', False):
        svg_inner = """
        <path d="M200,500 C200,300 500,300 500,500 C500,700 800,700 800,500" stroke="#4061FD" stroke-width="5" fill="none" />
        <path d="M800,500 C800,300 500,300 500,500 C500,700 200,700 200,500" stroke="#4061FD" stroke-width="5" fill="none" />
        <path d="M500,200 L500,800" stroke="#B5FF5F" stroke-width="5" />
        """
        
        # Safe File Load
        if os.path.exists("logo_data.txt"):
            try:
                with open("logo_data.txt", "r") as f:
                    content = f.read()
                    if "<path" in content:
                        svg_inner = content[content.find("<path"):content.rfind("</svg>")]
            except: pass

        intro_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            body {{ background-color: #000; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; overflow: hidden; }}
            svg {{ width: 50%; max-width: 250px; animation: glow 3s infinite alternate; }}
            .text {{ font-family: sans-serif; color: white; font-size: 20px; letter-spacing: 5px; opacity: 0; animation: fadeUp 1s ease 2.5s forwards; margin-top: 20px; font-weight: bold; }}
            path {{ stroke-dasharray: 1000; stroke-dashoffset: 1000; animation: draw 2.5s ease-out forwards; }}
            @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
            @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(20px); }} to {{ opacity: 1; transform: translateY(0); }} }}
            @keyframes glow {{ from {{ filter: drop-shadow(0 0 5px #4061FD); }} to {{ filter: drop-shadow(0 0 20px #B5FF5F); }} }}
        </style>
        </head>
        <body>
            <svg viewBox="0 0 1000 1000" xmlns="http://www.w3.org/2000/svg">{svg_inner}</svg>
            <div class="text">TIMEHUNT</div>
        </body>
        </html>
        """
        components.html(intro_html, height=800)
        time.sleep(4.0) 
        st.session_state['splash_played'] = True
        st.rerun()

# --- 5. PAGES ---

def page_home():
    # 1. Hero
    render_hero_header()

    # 2. Mood Pulse
    st.markdown("<div style='padding: 0 5px; margin-bottom: 10px; font-size: 12px; color: #666; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;'>Mental Pulse</div>", unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    
    if c1.button("🔥", key="m1"): st.toast("Stay lit! 🔥")
    if c2.button("🙂", key="m2"): st.toast("Glad you're good! 🙂")
    if c3.button("😐", key="m3"): st.toast("It's okay to be neutral. 😐")
    if c4.button("🌧️", key="m4"): st.toast("Take it easy. 🌧️")
    if c5.button("💀", key="m5"): st.toast("Rest required. 💀")

    st.write("") # Spacer

    # 3. Notion-Style Grid
    st.markdown("<div style='padding: 0 5px; margin-bottom: 15px; font-size: 12px; color: #666; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;'>Workspace</div>", unsafe_allow_html=True)
    
    r1a, r1b = st.columns(2)
    with r1a: ui_grid_card("Plan", "📅", "Calendar", "#00E5FF")
    with r1b: ui_grid_card("Focus", "⏳", "Timer", "#B5FF5F")
    
    r2a, r2b = st.columns(2)
    with r2a: ui_grid_card("Growth", "📈", "Analytics", "#FF4B4B")
    with r2b: ui_grid_card("Assistant", "🤖", "AI Chat", "#A0A0A0")

# --- 6. PLACEHOLDERS FOR OTHER PAGES ---
def page_scheduler(): st.title("📅 Tasks Page")
def page_ai_assistant(): st.title("🤖 AI Chat Page")
def page_timer(): st.title("⏳ Focus Page")
def page_dashboard(): st.title("📊 Stats Page")

# --- 7. MAIN APP LOOP ---
def main():
    initialize_session_state()
    inject_custom_css()
    show_cinematic_intro()
    
    # Bottom Navigation
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
                "border-top": "1px solid #333"
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

    # Routing
    if selected == "Home": page_home()
    elif selected == "Tasks": page_scheduler()
    elif selected == "Chat": page_ai_assistant()
    elif selected == "Focus": page_timer()
    elif selected == "Stats": page_dashboard()

    st.markdown('<div style="height: 100px;"></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()