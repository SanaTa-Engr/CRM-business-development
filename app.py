import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

APP_NAME = "Ultimate Outsourcing | Business Development CRM"
DB_PATH = Path(__file__).with_name("crm.db")
GEMINI_MODEL = "gemini-2.5-flash"

st.set_page_config(page_title="Ultimate Outsourcing CRM", page_icon="🤝", layout="wide")


def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def db_init():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT NOT NULL, contact_name TEXT, email TEXT, phone TEXT,
        country TEXT, service TEXT, source TEXT, status TEXT DEFAULT 'New',
        score INTEGER DEFAULT 0, notes TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER, title TEXT NOT NULL, service TEXT,
        value_gbp REAL DEFAULT 0, stage TEXT DEFAULT 'Discovery',
        probability INTEGER DEFAULT 20, expected_close TEXT, notes TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(lead_id) REFERENCES leads(id)
    );
    CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER, activity_type TEXT, subject TEXT NOT NULL,
        due_date TEXT, priority TEXT DEFAULT 'Medium', completed INTEGER DEFAULT 0,
        notes TEXT, created_at TEXT NOT NULL,
        FOREIGN KEY(lead_id) REFERENCES leads(id)
    );
    """)
    c.commit(); c.close()


def run(sql, params=(), fetch=False):
    c = conn(); cur = c.execute(sql, params); c.commit()
    rows = cur.fetchall() if fetch else None
    c.close()
    return rows


def seed():
    if run("SELECT COUNT(*) n FROM leads", fetch=True)[0]["n"]: return
    now = datetime.now().isoformat(timespec="seconds")
    run("""INSERT INTO leads(company,contact_name,email,phone,country,service,source,status,score,notes,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        ("Example UK Retail Ltd", "Sarah Ahmed", "sarah@example.co.uk", "+44 20 0000 0000", "UK",
         "BPO / Customer Support", "Website", "Qualified", 82,
         "Needs outsourced customer support and back-office operations.", now))
    lid = run("SELECT id FROM leads WHERE company=?", ("Example UK Retail Ltd",), fetch=True)[0]["id"]
    run("""INSERT INTO opportunities(lead_id,title,service,value_gbp,stage,probability,expected_close,notes,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (lid, "Customer Support Outsourcing", "BPO / Customer Support", 18000, "Proposal", 60,
         str(date.today()), "Proposal requested.", now))
    run("""INSERT INTO activities(lead_id,activity_type,subject,due_date,priority,completed,notes,created_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (lid, "Follow-up", "Follow up on outsourcing proposal", str(date.today()), "High", 0,
         "Confirm requirements and decision timeline.", now))


def get_secret(key):
    try:
        value = st.secrets.get(key)
        if value: return value
    except Exception:
        pass
    return os.getenv(key)


@st.cache_resource
def gemini_client():
    key = get_secret("GEMINI_API_KEY")
    return genai.Client(api_key=key) if key else None


def ai(prompt):
    client = gemini_client()
    if not client:
        return "Gemini is not configured. Add GEMINI_API_KEY in Streamlit Secrets."
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are the business-development AI assistant for Ultimate Outsourcing, "
                    "a UK-focused BPO and recruitment outsourcing company. Use only the CRM "
                    "data supplied. Never invent client facts. Give practical sales advice."
                ),
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                temperature=0.3,
            ),
        )
        return response.text or "No AI response returned."
    except Exception as e:
        return f"Gemini error: {e}"


def df(sql, params=()):
    return pd.DataFrame([dict(x) for x in run(sql, params, True)])


def crm_context():
    leads = df("SELECT * FROM leads ORDER BY id DESC")
    opps = df("""SELECT o.*, l.company, l.contact_name FROM opportunities o
                 LEFT JOIN leads l ON l.id=o.lead_id ORDER BY o.id DESC""")
    acts = df("""SELECT a.*, l.company, l.contact_name FROM activities a
                 LEFT JOIN leads l ON l.id=a.lead_id ORDER BY a.completed, a.due_date""")
    return leads, opps, acts



# -----------------------------------------------------------------------------
# Dashboard visual helpers
# -----------------------------------------------------------------------------

def dashboard_styles():
    st.markdown("""
    <style>
    .dash-header { display:flex; align-items:center; gap:14px; margin-bottom:4px; }
    .dash-header-icon { width:52px; height:52px; border-radius:14px; display:flex; align-items:center; justify-content:center;
        background:linear-gradient(135deg,#5b4de8,#7c3aed); color:white; font-size:25px; box-shadow:0 8px 22px rgba(91,77,232,.20); }
    .dash-title { font-size:31px; font-weight:800; line-height:1.05; color:#171923; margin:0; }
    .dash-subtitle { color:#9aa0ad; font-size:15px; margin-top:5px; }
    .metric-card { min-height:142px; border:1px solid #edf0f5; border-radius:14px; background:#fff; padding:18px 18px 15px;
        box-shadow:0 2px 10px rgba(20,25,40,.035); }
    .metric-icon { width:42px; height:42px; border-radius:11px; display:flex; align-items:center; justify-content:center;
        color:#fff; font-size:20px; margin-bottom:13px; }
    .metric-label { color:#8f95a3; font-size:13px; font-weight:600; margin-bottom:2px; }
    .metric-value { color:#171923; font-size:29px; line-height:1; font-weight:800; }
    .chart-card { border:1px solid #edf0f5; border-radius:14px; background:#fff; padding:22px 22px 18px; min-height:355px;
        box-shadow:0 2px 10px rgba(20,25,40,.035); }
    .chart-title { color:#171923; font-size:18px; font-weight:800; margin-bottom:20px; }
    .bar-chart { height:245px; display:flex; align-items:flex-end; gap:12px; padding:8px 8px 0; border-bottom:1px solid #e9ecf2; }
    .bar-item { flex:1; height:100%; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; min-width:0; }
    .bar-value { font-size:12px; font-weight:700; color:#697080; margin-bottom:6px; }
    .bar { width:min(48px,75%); min-height:3px; border-radius:6px 6px 0 0; }
    .bar-label { font-size:10px; color:#7f8694; margin-top:9px; text-align:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; width:100%; transform:rotate(-18deg); transform-origin:top center; }
    .donut-wrap { display:flex; align-items:center; justify-content:center; gap:34px; min-height:275px; }
    .donut { width:188px; height:188px; border-radius:50%; position:relative; flex:0 0 auto; }
    .donut::after { content:""; position:absolute; inset:48px; background:#fff; border-radius:50%; }
    .donut-center { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; z-index:2; font-weight:800; color:#202331; font-size:18px; }
    .legend { display:flex; flex-direction:column; gap:9px; min-width:180px; max-height:230px; overflow:auto; }
    .legend-row { display:flex; align-items:center; justify-content:space-between; gap:18px; color:#777e8d; font-size:12px; }
    .legend-name { display:flex; align-items:center; gap:8px; min-width:0; }
    .legend-dot { width:10px; height:10px; border-radius:50%; flex:0 0 auto; }
    .legend-count { font-weight:800; color:#535968; }
    .empty-chart { height:280px; display:flex; align-items:center; justify-content:center; color:#9aa0ad; font-size:14px; }
    @media (max-width: 900px) { .donut-wrap { flex-direction:column; gap:12px; } .legend { width:100%; } }
    </style>
    """, unsafe_allow_html=True)


def metric_card(label, value, icon, bg):
    return '<div class="metric-card">' \
        + f'<div class="metric-icon" style="background:{bg};">{icon}</div>' \
        + f'<div class="metric-label">{label}</div>' \
        + f'<div class="metric-value">{value}</div></div>'


def outreach_chart_html(status_counts):
    order = ["New", "Contacted", "Qualified", "Proposal", "Negotiation", "Won", "Lost"]
    colors = ["#9aa8bd", "#3b82f6", "#14b8a6", "#7c3aed", "#8b5cf6", "#f59e0b", "#10b981"]
    values = [int(status_counts.get(x, 0)) for x in order]
    max_value = max(values) if values else 1
    bars = []
    for label, value, color in zip(order, values, colors):
        height = 3 if value == 0 else max(8, int((value / max_value) * 205))
        bars.append('<div class="bar-item"><div class="bar-value">' + str(value) + '</div>'
                    + f'<div class="bar" style="height:{height}px;background:{color};"></div>'
                    + f'<div class="bar-label" title="{label}">{label}</div></div>')
    return '<div class="bar-chart">' + ''.join(bars) + '</div>'


def opportunity_donut_html(opps):
    if opps.empty:
        return '<div class="empty-chart">No opportunities yet.</div>'
    series = opps["service"].fillna("Other").replace("", "Other").value_counts()
    if series.empty:
        return '<div class="empty-chart">No service data available.</div>'
    palette = ["#5b4de8", "#22a7d6", "#f59e0b", "#3b82f6", "#ef4444", "#14b8a6", "#8b5cf6", "#10b981", "#ec4899", "#64748b"]
    total = int(series.sum())
    start = 0.0
    stops, legend = [], []
    for i, (name, count) in enumerate(series.items()):
        pct = float(count) / total * 100
        end = start + pct
        color = palette[i % len(palette)]
        stops.append(f"{color} {start:.2f}% {end:.2f}%")
        legend.append('<div class="legend-row"><span class="legend-name"><span class="legend-dot" style="background:'
                      + color + '"></span>' + str(name) + '</span><span class="legend-count">' + str(int(count)) + '</span></div>')
        start = end
    return '<div class="donut-wrap"><div class="donut" style="background:conic-gradient(' + ', '.join(stops) + ');"><div class="donut-center">' + str(total) + '</div></div>' \
        + '<div class="legend">' + ''.join(legend) + '</div></div>'

db_init(); seed()

def validate_columns(df_in, required, label):
    missing = [c for c in required if c not in df_in.columns]
    if missing:
        return False, f"{label} CSV is missing required columns: {', '.join(missing)}"
    return True, "Valid"


def text_value(row, column, default=""):
    value = row.get(column, default)
    if pd.isna(value):
        return default
    return str(value).strip()


def import_leads_csv(uploaded_df):
    required = ["company", "contact_name", "email", "industry", "location", "lead_source", "service_interest", "status", "lead_score"]
    ok, message = validate_columns(uploaded_df, required, "Leads")
    if not ok:
        return 0, 0, message

    imported = skipped = 0
    now = datetime.now().isoformat(timespec="seconds")
    for _, r in uploaded_df.iterrows():
        company = text_value(r, "company")
        email = text_value(r, "email")
        if not company:
            skipped += 1
            continue
        exists = run("SELECT id FROM leads WHERE lower(company)=lower(?) AND lower(coalesce(email,''))=lower(?)", (company, email), fetch=True)
        if exists:
            skipped += 1
            continue
        try:
            score = int(float(r.get("lead_score", 0)))
        except (TypeError, ValueError):
            score = 0
        run("""INSERT INTO leads(company,contact_name,email,phone,country,service,source,status,score,notes,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (company, text_value(r,"contact_name"), email, text_value(r,"phone"),
             text_value(r,"location", "UK"), text_value(r,"service_interest"),
             text_value(r,"lead_source"), text_value(r,"status", "New"), score,
             text_value(r,"notes"), now))
        imported += 1
    return imported, skipped, None


def find_lead_id(row):
    company = text_value(row, "company")
    if company:
        found = run("SELECT id FROM leads WHERE lower(company)=lower(?) ORDER BY id LIMIT 1", (company,), fetch=True)
        if found:
            return found[0]["id"]
    raw_id = row.get("lead_id")
    try:
        if not pd.isna(raw_id):
            found = run("SELECT id FROM leads WHERE id=?", (int(float(raw_id)),), fetch=True)
            if found:
                return found[0]["id"]
    except (TypeError, ValueError):
        pass
    return None


def import_opportunities_csv(uploaded_df):
    required = ["lead_id", "company", "opportunity_name", "service", "stage", "estimated_value_gbp", "probability_pct", "expected_close_date"]
    ok, message = validate_columns(uploaded_df, required, "Opportunities")
    if not ok:
        return 0, 0, message

    imported = skipped = 0
    now = datetime.now().isoformat(timespec="seconds")
    for _, r in uploaded_df.iterrows():
        lead_id = find_lead_id(r)
        title = text_value(r, "opportunity_name")
        if not lead_id or not title:
            skipped += 1
            continue
        duplicate = run("SELECT id FROM opportunities WHERE lead_id=? AND lower(title)=lower(?)", (lead_id, title), fetch=True)
        if duplicate:
            skipped += 1
            continue
        try:
            value = float(r.get("estimated_value_gbp", 0))
        except (TypeError, ValueError):
            value = 0.0
        try:
            probability = int(float(r.get("probability_pct", 20)))
        except (TypeError, ValueError):
            probability = 20
        stage = text_value(r, "stage", "Discovery")
        # Normalize the stage name used by the CRM.
        if stage == "Qualification":
            stage = "Qualified"
        run("""INSERT INTO opportunities(lead_id,title,service,value_gbp,stage,probability,expected_close,notes,created_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (lead_id, title, text_value(r,"service"), value, stage, probability,
             text_value(r,"expected_close_date"), text_value(r,"notes"), now))
        imported += 1
    return imported, skipped, None


def import_activities_csv(uploaded_df):
    required = ["lead_id", "company", "activity_type", "activity_date", "subject", "outcome", "notes"]
    ok, message = validate_columns(uploaded_df, required, "Activities")
    if not ok:
        return 0, 0, message

    imported = skipped = 0
    now = datetime.now().isoformat(timespec="seconds")
    for _, r in uploaded_df.iterrows():
        lead_id = find_lead_id(r)
        subject = text_value(r, "subject")
        due_date = text_value(r, "activity_date")
        if not subject:
            skipped += 1
            continue
        duplicate = run("SELECT id FROM activities WHERE coalesce(lead_id,0)=coalesce(?,0) AND lower(subject)=lower(?) AND coalesce(due_date,'')=?", (lead_id, subject, due_date), fetch=True)
        if duplicate:
            skipped += 1
            continue
        outcome = text_value(r, "outcome")
        notes = text_value(r, "notes")
        combined_notes = f"Outcome: {outcome}. {notes}" if outcome else notes
        run("""INSERT INTO activities(lead_id,activity_type,subject,due_date,priority,completed,notes,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (lead_id, text_value(r,"activity_type"), subject, due_date, "Medium", 0, combined_notes, now))
        imported += 1
    return imported, skipped, None


def render_csv_import(label, uploader_key, importer, required_columns):
    uploaded = st.file_uploader(f"Upload {label} CSV", type=["csv"], key=uploader_key)
    if uploaded is None:
        return
    try:
        uploaded_df = pd.read_csv(uploaded)
    except Exception as exc:
        st.error(f"Could not read the CSV: {exc}")
        return

    st.caption(f"Detected {len(uploaded_df):,} rows and {len(uploaded_df.columns):,} columns.")
    missing = [c for c in required_columns if c not in uploaded_df.columns]
    if missing:
        st.error(f"Validation failed — missing columns: {', '.join(missing)}")
        st.code(", ".join(required_columns), language="text")
        return

    st.success("CSV validation passed.")
    st.dataframe(uploaded_df.head(10), use_container_width=True, hide_index=True)
    if st.button(f"Import {len(uploaded_df):,} {label.lower()}", type="primary", key=f"import_{uploader_key}"):
        imported, skipped, error = importer(uploaded_df)
        if error:
            st.error(error)
        else:
            st.success(f"Imported {imported:,} rows. Skipped {skipped:,} duplicate/invalid rows.")
            st.rerun()


def data_import_page():
    st.title("Data Import")
    st.caption("Upload CSV files, validate them, import them into SQLite, and refresh the CRM dashboard automatically.")

    st.info("Use the supplied Ultimate Outsourcing dummy CSVs. Duplicate leads, opportunities, and activities are skipped automatically.")

    with st.expander("📥 Import Leads", expanded=True):
        render_csv_import(
            "Leads", "leads_csv",
            import_leads_csv,
            ["company", "contact_name", "email", "industry", "location", "lead_source", "service_interest", "status", "lead_score"]
        )

    with st.expander("📥 Import Opportunities"):
        render_csv_import(
            "Opportunities", "opportunities_csv",
            import_opportunities_csv,
            ["lead_id", "company", "opportunity_name", "service", "stage", "estimated_value_gbp", "probability_pct", "expected_close_date"]
        )

    with st.expander("📥 Import Activities"):
        render_csv_import(
            "Activities", "activities_csv",
            import_activities_csv,
            ["lead_id", "company", "activity_type", "activity_date", "subject", "outcome", "notes"]
        )


st.sidebar.title("🤝 Ultimate Outsourcing CRM")
st.sidebar.caption("Business Development • BPO • Recruitment")
page = st.sidebar.radio("Go to", ["Dashboard", "Leads", "Pipeline", "Activities", "Data Import", "AI Sales Assistant"])
st.sidebar.divider()
st.sidebar.caption("MVP: Streamlit + SQLite + Gemini 2.5 Flash")

if page == "Data Import":
    data_import_page()

elif page == "Dashboard":
    dashboard_styles()
    leads, opps, acts = crm_context()

    # KPI definitions use the live CRM database, so the dashboard changes
    # automatically whenever records are added or imported.
    total_leads = len(leads)
    high_priority = int((pd.to_numeric(leads["score"], errors="coerce").fillna(0) >= 80).sum()) if not leads.empty else 0
    contacted = int((leads["status"].fillna("").str.lower() == "contacted").sum()) if not leads.empty else 0
    interested = int(leads["status"].fillna("").str.lower().isin(["qualified", "proposal", "negotiation", "interested"]).sum()) if not leads.empty else 0
    won_clients = int((leads["status"].fillna("").str.lower() == "won").sum()) if not leads.empty else 0

    # The current schema does not store website information. If a website
    # column is added later, this KPI automatically uses it.
    if "website" in leads.columns:
        no_website = int(leads["website"].fillna("").astype(str).str.strip().eq("").sum())
    else:
        no_website = 0

    st.markdown('''
        <div class="dash-header">
            <div class="dash-header-icon">⌘</div>
            <div><div class="dash-title">Dashboard</div><div class="dash-subtitle">Your CRM command center</div></div>
        </div>
    ''', unsafe_allow_html=True)
    st.write("")

    cards = [
        ("Total Leads", total_leads, "♧", "#5b4de8"),
        ("High Priority", high_priority, "♨", "#ef4444"),
        ("No Website", no_website, "⊕", "#475569"),
        ("Contacted", contacted, "➤", "#2495e9"),
        ("Interested", interested, "✦", "#8b32d8"),
        ("Won Clients", won_clients, "♕", "#10a77a"),
    ]
    cols = st.columns(6, gap="medium")
    for col, (label, value, icon, bg) in zip(cols, cards):
        with col:
            st.markdown(metric_card(label, f"{value:,}", icon, bg), unsafe_allow_html=True)

    st.write("")
    left, right = st.columns([1.05, 1], gap="large")

    with left:
        status_counts = leads["status"].fillna("New").replace("", "New").value_counts().to_dict() if not leads.empty else {}
        st.markdown('<div class="chart-card"><div class="chart-title">Outreach Pipeline</div>' + outreach_chart_html(status_counts) + '</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="chart-card"><div class="chart-title">Opportunity Breakdown</div>' + opportunity_donut_html(opps) + '</div>', unsafe_allow_html=True)

    st.write("")
    with st.expander("📋 Recent Leads", expanded=False):
        if leads.empty:
            st.info("No leads yet. Use Find Lead, Leads, or Data Import to add prospects.")
        else:
            recent_cols = [c for c in ["id", "company", "contact_name", "service", "source", "status", "score"] if c in leads.columns]
            st.dataframe(leads[recent_cols].head(10), use_container_width=True, hide_index=True)

elif page == "Leads":
    st.title("Leads & Prospects")
    with st.expander("➕ Add new business lead"):
        with st.form("lead_form", clear_on_submit=True):
            company=st.text_input("Company *"); contact=st.text_input("Contact name")
            email=st.text_input("Email"); phone=st.text_input("Phone")
            country=st.text_input("Country", value="UK")
            service=st.selectbox("Service interest", ["BPO / Customer Support","Recruitment Outsourcing","Back Office / Admin","Finance & Accounting","Other"])
            source=st.selectbox("Lead source", ["Website","LinkedIn","Referral","Email","Cold Outreach","Partner","Other"])
            status=st.selectbox("Status", ["New","Contacted","Qualified","Proposal","Negotiation","Won","Lost"])
            notes=st.text_area("Notes")
            if st.form_submit_button("Save lead", type="primary"):
                if not company.strip(): st.error("Company is required.")
                else:
                    run("""INSERT INTO leads(company,contact_name,email,phone,country,service,source,status,notes,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",(company,contact,email,phone,country,service,source,status,notes,datetime.now().isoformat(timespec="seconds")))
                    st.success("Lead saved."); st.rerun()
    leads=df("SELECT * FROM leads ORDER BY id DESC")
    q=st.text_input("Search company, contact, email or service")
    if q: leads=leads[leads.apply(lambda r:r.astype(str).str.contains(q,case=False,regex=False).any(),axis=1)]
    st.dataframe(leads[["id","company","contact_name","email","country","service","source","status","score"]],use_container_width=True,hide_index=True)
    if not leads.empty:
        st.subheader("AI Qualification")
        lid=st.selectbox("Lead", leads.id.tolist(), format_func=lambda x: f"{leads.loc[leads.id==x,'company'].iloc[0]} — {leads.loc[leads.id==x,'contact_name'].iloc[0] or 'No contact'}")
        if st.button("Score selected lead with Gemini", type="primary"):
            r=leads[leads.id==lid].iloc[0]
            prompt=f"""Score this B2B outsourcing lead from 0-100. Return: score, Hot/Warm/Cold classification, buying signals, risks, and 5 next actions.\nCompany: {r.company}\nContact: {r.contact_name}\nCountry: {r.country}\nService: {r.service}\nSource: {r.source}\nStatus: {r.status}\nNotes: {r.notes}"""
            with st.spinner("Gemini is qualifying the lead..."): st.markdown(ai(prompt))

elif page == "Pipeline":
    st.title("Sales Pipeline")
    leads=run("SELECT id,company FROM leads ORDER BY company",fetch=True)
    cmap={x["id"]:x["company"] for x in leads}
    with st.expander("➕ Add opportunity"):
        if not cmap: st.warning("Add a lead first.")
        else:
            with st.form("opp_form",clear_on_submit=True):
                lid=st.selectbox("Lead",list(cmap),format_func=lambda x:cmap[x])
                title=st.text_input("Opportunity title *")
                service=st.selectbox("Service",["BPO / Customer Support","Recruitment Outsourcing","Back Office / Admin","Finance & Accounting","Other"])
                value=st.number_input("Estimated contract value (£)",min_value=0.0,step=1000.0)
                stage=st.selectbox("Stage",["Discovery","Qualification","Proposal","Negotiation","Won","Lost"])
                probability=st.slider("Probability (%)",0,100,20)
                close=st.date_input("Expected close",value=date.today())
                notes=st.text_area("Notes")
                if st.form_submit_button("Save opportunity",type="primary"):
                    if not title.strip(): st.error("Opportunity title is required.")
                    else:
                        run("""INSERT INTO opportunities(lead_id,title,service,value_gbp,stage,probability,expected_close,notes,created_at)
                               VALUES(?,?,?,?,?,?,?,?,?)""",(lid,title,service,value,stage,probability,str(close),notes,datetime.now().isoformat(timespec="seconds")))
                        st.success("Opportunity saved."); st.rerun()
    opps=df("""SELECT o.*,l.company,l.contact_name FROM opportunities o LEFT JOIN leads l ON l.id=o.lead_id ORDER BY o.id DESC""")
    if opps.empty: st.info("No opportunities yet.")
    else:
        opps["weighted"] = opps.value_gbp*opps.probability/100
        st.dataframe(opps[["id","company","title","service","value_gbp","stage","probability","weighted","expected_close"]],use_container_width=True,hide_index=True)

elif page == "Activities":
    st.title("Follow-ups & Activities")
    leads=run("SELECT id,company FROM leads ORDER BY company",fetch=True); cmap={x["id"]:x["company"] for x in leads}
    with st.expander("➕ Add follow-up"):
        with st.form("activity_form",clear_on_submit=True):
            lid=st.selectbox("Lead",[0]+list(cmap),format_func=lambda x:"No lead" if x==0 else cmap[x])
            typ=st.selectbox("Activity type",["Call","Email","Meeting","Follow-up","LinkedIn","Proposal"])
            subject=st.text_input("Subject *"); due=st.date_input("Due date",value=date.today()); priority=st.selectbox("Priority",["Low","Medium","High"]); notes=st.text_area("Notes")
            if st.form_submit_button("Save activity",type="primary"):
                if not subject.strip(): st.error("Subject is required.")
                else:
                    run("""INSERT INTO activities(lead_id,activity_type,subject,due_date,priority,notes,created_at) VALUES(?,?,?,?,?,?,?)""",(None if lid==0 else lid,typ,subject,str(due),priority,notes,datetime.now().isoformat(timespec="seconds")))
                    st.success("Activity saved."); st.rerun()
    acts=df("""SELECT a.*,l.company FROM activities a LEFT JOIN leads l ON l.id=a.lead_id ORDER BY a.completed,a.due_date,a.id DESC""")
    if acts.empty: st.info("No activities yet.")
    else:
        for _,r in acts.iterrows():
            a,b,c=st.columns([5,2,1])
            with a: st.write(("✅ " if r.completed else "⬜ ")+f"**{r.subject}**"); st.caption(r.company or "No lead")
            with b: st.write(f"{r.due_date} • {r.priority}")
            with c:
                if not r.completed and st.button("Done",key=f"done{r.id}"):
                    run("UPDATE activities SET completed=1 WHERE id=?",(int(r.id),)); st.rerun()
            st.divider()

else:
    st.title("AI Sales Assistant")
    st.caption("Use Gemini to prioritize prospects, prepare outreach, and analyze your sales pipeline.")
    leads,opps,acts=crm_context()
    question=st.text_area("What do you want help with?",value="Which leads should our business development team contact first this week, and why?",height=110)
    if st.button("Ask Gemini",type="primary"):
        context=f"LEADS:\n{leads.to_string(index=False) if not leads.empty else 'None'}\n\nOPPORTUNITIES:\n{opps.to_string(index=False) if not opps.empty else 'None'}\n\nACTIVITIES:\n{acts.to_string(index=False) if not acts.empty else 'None'}"
        with st.spinner("Gemini is analyzing your CRM..."):
            st.markdown(ai(f"User request:\n{question}\n\nCRM data:\n{context}"))
    st.divider(); st.subheader("Quick sales actions")
    action=st.selectbox("Action",["Draft an outreach email for the highest-value open opportunity","Create a 7-day follow-up plan","Summarize the pipeline and identify risks"])
    if st.button("Run action"):
        if action.startswith("Draft") and not opps.empty:
            openo=opps[~opps.stage.isin(["Won","Lost"])].sort_values("value_gbp",ascending=False)
            if openo.empty: st.info("No open opportunities.")
            else:
                r=openo.iloc[0]
                st.markdown(ai(f"Draft a concise professional UK B2B outreach/follow-up email. Do not invent details. Company={r.company}; Contact={r.contact_name}; Service={r.service}; Opportunity={r.title}; Value=£{r.value_gbp:,.0f}; Stage={r.stage}; Notes={r.notes}"))
        elif action.startswith("Create"):
            st.markdown(ai(f"Create a practical 7-day business-development follow-up plan from this CRM data.\nLEADS:\n{leads.to_string(index=False)}\nOPPORTUNITIES:\n{opps.to_string(index=False)}\nACTIVITIES:\n{acts.to_string(index=False)}"))
        else:
            st.markdown(ai(f"Summarize pipeline performance, strongest opportunities, risks, and recommended actions.\n{opps.to_string(index=False) if not opps.empty else 'No opportunities.'}"))
