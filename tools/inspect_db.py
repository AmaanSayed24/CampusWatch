"""Inspect DB state for the Data Structures deadline investigation."""

import sqlite3

conn = sqlite3.connect("data/portal.db")
print("--- Data Structures subject ---")
for r in conn.execute("select id, name, portal_id from subjects where name like '%Data%'"):
    print(r)
print("--- Data Structures assignments ---")
for r in conn.execute(
    "select a.id, a.title, a.deadline, a.status, a.portal_id, a.external_key, a.last_seen_at "
    "from assignments a join subjects s on s.id=a.subject_id where s.name like '%Data%'"
):
    print(r)
print("--- all notifications ---")
for r in conn.execute("select * from notifications order by id"):
    print(r)
print("--- all assignments ---")
for r in conn.execute(
    "select a.id, s.name, a.title, a.deadline, a.status from assignments a "
    "join subjects s on s.id=a.subject_id order by s.name, a.title"
):
    print(r)
conn.close()