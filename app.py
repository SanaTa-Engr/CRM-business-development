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
GEMINI_MODEL = "gemini-3.5-flash"

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


db_init(); seed()

st.sidebar.title("🤝 Ultimate Outsourcing CRM")
st.sidebar.caption("Business Development • BPO • Recruitment")
page = st.sidebar.radio("Go to", ["Dashboard", "Leads", "Pipeline", "Activities", "AI Sales Assistant"])
st.sidebar.divider()
st.sidebar.caption("MVP: Streamlit + SQLite + Gemini 2.5 Flash")

if page == "Dashboard":
    st.title("Business Development Dashboard")
    st.caption("Track prospects, outsourcing opportunities, follow-ups and AI-assisted sales decisions.")
    leads, opps, acts = crm_context()
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Leads", len(leads))
    c2.metric("Qualified Leads", int((leads.status == "Qualified").sum()) if not leads.empty else 0)
    c3.metric("Open Opportunities", int((~opps.stage.isin(["Won","Lost"])).sum()) if not opps.empty else 0)
    c4.metric("Pipeline", f"£{opps.value_gbp.sum():,.0f}" if not opps.empty else "£0")
    st.subheader("Pipeline by Stage")
    if opps.empty: st.info("No opportunities yet.")
    else:
        summary = opps.groupby("stage", as_index=False).agg(Opportunities=("id","count"), Value=("value_gbp","sum"))
        summary["Value"] = summary["Value"].map(lambda x:f"£{x:,.0f}")
        st.dataframe(summary, use_container_width=True, hide_index=True)
    st.subheader("Recent Leads")
    st.dataframe(leads[["company","contact_name","service","source","status","score"]].head(10), use_container_width=True, hide_index=True)

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
