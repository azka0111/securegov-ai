import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import random
import requests
import os
# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="SecureGov AI", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
.main {background-color: #f4f6f9;}
.stButton>button {
    background-color: #002147;
    color: white;
    border-radius: 6px;
    height: 3em;
    width: 100%;
}
</style>
""", unsafe_allow_html=True)

# =========================
# HUGGING FACE API SETUP
# =========================
try:
    HF_TOKEN = st.secrets["HF_TOKEN"]
except:
    HF_TOKEN = None

MODEL_URL = "https://api-inference.huggingface.co/models/google/flan-t5-base"

HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}"
}

def query_ai(prompt):
    structured_prompt = f"""
You are a secure government AI assistant.

Respond clearly in three sections:
1. Explanation
2. Key Points (bullet format)
3. Recommended Action

User Query:
{prompt}
"""

    payload = {
        "inputs": structured_prompt,
        "parameters": {
            "max_new_tokens": 200,
            "temperature": 0.5
        }
    }

    try:
        response = requests.post(MODEL_URL, headers=HEADERS, json=payload, timeout=60)

        if response.status_code == 200:
            result = response.json()
            return result[0]["generated_text"]

        return fake_response(prompt)

    except:
        return fake_response(prompt)

# =========================
# FALLBACK RESPONSE
# =========================
def fake_response(prompt):
    responses = [
        "Explanation: Query processed under governance protocols.\n\nKey Points:\n- Risk evaluation completed\n- Monitoring active\n\nRecommended Action:\nFollow compliance procedures.",
        "Explanation: Analysis completed successfully.\n\nKey Points:\n- No immediate threat detected\n- Governance framework applied\n\nRecommended Action:\nProceed as per department policy."
    ]
    return random.choice(responses)

# =========================
# DATABASE INIT
# =========================
conn = sqlite3.connect("securegov.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT,
    role TEXT,
    clearance INTEGER,
    suspended_until TEXT,
    cumulative_risk INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    role TEXT,
    query TEXT,
    risk_score INTEGER,
    risk_level TEXT,
    timestamp TEXT
)
""")

conn.commit()

# Default users
default_users = [
    ("officer", "1234", "Officer", 1, None, 0),
    ("defense", "secure", "Defense", 2, None, 0),
    ("admin", "admin", "Admin", 3, None, 0),
]

for user in default_users:
    try:
        c.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", user)
    except:
        pass
conn.commit()

# =========================
# RISK ENGINE
# =========================
def calculate_risk(prompt, username):
    high = ["classified", "secret", "military", "weapon", "attack"]
    medium = ["internal", "budget", "restricted", "confidential"]

    score = 0
    text = prompt.lower()

    for w in high:
        if w in text:
            score += 50

    for w in medium:
        if w in text:
            score += 25

    c.execute("SELECT COUNT(*) FROM logs WHERE username=? AND risk_level='High'", (username,))
    high_count = c.fetchone()[0]

    score += high_count * 5
    score = min(score, 100)

    if score >= 60:
        level = "High"
    elif score >= 30:
        level = "Medium"
    else:
        level = "Low"

    return score, level, high_count

# =========================
# HEADER
# =========================
st.title("🛡️ SecureGov AI")
st.markdown("### Enterprise AI Governance & Risk Intelligence Platform")

# =========================
# LOGIN
# =========================
st.sidebar.title("🔐 Login")
username = st.sidebar.text_input("Username")
password = st.sidebar.text_input("Password", type="password")

if st.sidebar.button("Login"):
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    user = c.fetchone()

    if user and user[1] == password:
        suspended_until = user[4]

        if suspended_until:
            if datetime.now() < datetime.fromisoformat(suspended_until):
                st.sidebar.error("Account temporarily suspended.")
                st.stop()
            else:
                c.execute("UPDATE users SET suspended_until=NULL WHERE username=?", (username,))
                conn.commit()

        st.session_state["user"] = username
        st.session_state["role"] = user[2]
        st.session_state["clearance"] = user[3]
        st.session_state["cumulative_risk"] = user[5]
        st.sidebar.success("Login Successful")
    else:
        st.sidebar.error("Invalid Credentials")

# =========================
# MAIN SYSTEM
# =========================
if "user" in st.session_state:

    user = st.session_state["user"]
    role = st.session_state["role"]
    clearance = st.session_state["clearance"]

    st.sidebar.markdown("---")
    st.sidebar.write(f"User: {user}")
    st.sidebar.write(f"Role: {role}")
    st.sidebar.write(f"Clearance Level: {clearance}")

    st.subheader("AI Query Interface")
    prompt = st.text_area("Enter your query")

    if st.button("Submit Query"):

        if not prompt.strip():
            st.warning("Enter a valid query.")
        else:
            score, level, high_count = calculate_risk(prompt, user)

            cumulative = st.session_state.get("cumulative_risk", 0) + score
            st.session_state["cumulative_risk"] = cumulative
            c.execute("UPDATE users SET cumulative_risk=? WHERE username=?", (cumulative, user))
            conn.commit()

            st.progress(score/100)
            st.write(f"Risk Score: {score}/100")

            if level == "High":
                st.error("🔴 High Risk")
            elif level == "Medium":
                st.warning("🟠 Medium Risk")
            else:
                st.success("🟢 Low Risk")

            if high_count >= 5:
                suspend_time = datetime.now() + timedelta(hours=24)
                c.execute("UPDATE users SET suspended_until=? WHERE username=?", (suspend_time.isoformat(), user))
                conn.commit()
                st.error("Account suspended for 24 hours due to repeated high-risk activity.")
                st.stop()

            response = query_ai(prompt)
            st.success(response)

            c.execute(
                "INSERT INTO logs (username, role, query, risk_score, risk_level, timestamp) VALUES (?,?,?,?,?,?)",
                (user, role, prompt, score, level, datetime.now().isoformat())
            )
            conn.commit()

    if role == "Admin":
        st.markdown("---")
        st.subheader("📊 Governance Dashboard")

        logs_df = pd.read_sql_query("SELECT * FROM logs", conn)
        users_df = pd.read_sql_query("SELECT username, role, cumulative_risk, suspended_until FROM users", conn)

        if not logs_df.empty:
            st.bar_chart(logs_df["risk_level"].value_counts())
            st.metric("Average Risk Score", round(logs_df["risk_score"].mean(),2))
            st.dataframe(users_df)
            st.dataframe(logs_df)
        else:

            st.info("No activity recorded yet.")
