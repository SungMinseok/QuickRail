import sqlite3
import sys


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "instance/quickrail.db"
    con = sqlite3.connect(db_path)
    try:
        v = con.execute("select version_num from alembic_version").fetchone()
        print("db:", db_path)
        print("alembic_version:", v)
        tj = con.execute("select name from sqlite_master where type='table' and name='case_jira_links'").fetchone()
        tm = con.execute("select name from sqlite_master where type='table' and name='case_media'").fetchone()
        print("case_jira_links:", tj)
        print("case_media:", tm)
        cols = [r[1] for r in con.execute("pragma table_info(run_cases)").fetchall()]
        print("run_cases has jira_links_snapshot:", "jira_links_snapshot" in cols)
        print("run_cases has media_names_snapshot:", "media_names_snapshot" in cols)
    finally:
        con.close()


if __name__ == "__main__":
    main()


