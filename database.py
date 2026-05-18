import json
import sqlite3
from datetime import datetime

DB_NAME = "medical_rmf.db"  


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rmf_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,  

        device_name TEXT,  

        intended_use TEXT,  

        device_type TEXT,  

        version_name TEXT,  

        status TEXT,  

        created_at TEXT  
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS risk_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        rmf_id INTEGER,  

        hazard TEXT,
        hazardous_situation TEXT,
        possible_harm TEXT,
        severity TEXT,
        probability TEXT,
        initial_risk_level TEXT,
        risk_control_measure TEXT,
        residual_risk TEXT,
        verification_method TEXT,
        status TEXT,

        created_at TEXT,

        FOREIGN KEY (rmf_id) REFERENCES rmf_versions(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rmp_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lifecycle_scope          TEXT,
        risk_acceptability_criteria TEXT,
        residual_risk_method     TEXT,
        residual_risk_basis      TEXT,
        verification_methods     TEXT,
        team_members             TEXT,
        created_at               TEXT,
        updated_at               TEXT,
        is_confirmed             INTEGER NOT NULL DEFAULT 0
    )
    """)

    try:
        cursor.execute(
            "ALTER TABLE rmp_config ADD COLUMN is_confirmed INTEGER NOT NULL DEFAULT 0"
        )
    except Exception:
        pass  # column already exists

    # user_id isolation — added for per-user data separation.
    # Existing rows get NULL, which naturally excludes them from per-user queries.
    try:
        cursor.execute("ALTER TABLE rmf_versions ADD COLUMN user_id TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE rmp_config ADD COLUMN user_id TEXT")
    except Exception:
        pass

    conn.commit()
    conn.close()


def create_rmf_version(device_name, intended_use, device_type, user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO rmf_versions
    (device_name, intended_use, device_type, version_name, status, created_at, user_id)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        device_name,
        intended_use,
        device_type,
        "Version 1",
        "Draft",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_id,
    ))

    rmf_id = cursor.lastrowid  
 

    conn.commit()
    conn.close()

    return rmf_id


def get_all_rmf_versions(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, device_name, intended_use, device_type, version_name, status, created_at
    FROM rmf_versions
    WHERE user_id = ?
    ORDER BY created_at DESC
    """, (user_id,))

    rows = cursor.fetchall()  

    conn.close()

    return rows

def delete_rmf_version(rmf_id, user_id):

    conn = get_connection()
    cursor = conn.cursor()

    # Ownership check: only delete if the version belongs to this user.
    cursor.execute(
        "SELECT id FROM rmf_versions WHERE id = ? AND user_id = ?",
        (rmf_id, user_id),
    )
    if cursor.fetchone() is None:
        conn.close()
        return

    cursor.execute("DELETE FROM risk_records WHERE rmf_id = ?", (rmf_id,))
    cursor.execute("DELETE FROM rmf_versions WHERE id = ? AND user_id = ?", (rmf_id, user_id))

    conn.commit()
    conn.close()


def clone_rmf_version(old_rmf_id, user_id):
    """
    Create a new RMF version by cloning an existing one.

    1. Reads the source rmf_version row (must belong to user_id).
    2. Increments the version number (e.g. Version 1 → Version 2).
    3. Inserts a new rmf_version row with the same device info and user_id.
    4. Copies all risk_records from old_rmf_id to the new version.
    5. Returns the new rmf_id.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT device_name, intended_use, device_type, version_name "
        "FROM rmf_versions WHERE id = ? AND user_id = ?",
        (old_rmf_id, user_id),
    )
    src = cursor.fetchone()
    if src is None:
        conn.close()
        raise ValueError(f"RMF version {old_rmf_id} not found or access denied.")

    try:
        num = int(src["version_name"].split()[-1]) + 1
    except (ValueError, IndexError):
        num = 2
    new_version_name = f"Version {num}"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    INSERT INTO rmf_versions
        (device_name, intended_use, device_type, version_name, status, created_at, user_id)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        src["device_name"],
        src["intended_use"],
        src["device_type"],
        new_version_name,
        "Draft",
        now,
        user_id,
    ))
    new_rmf_id = cursor.lastrowid

    cursor.execute("""
    SELECT hazard, hazardous_situation, possible_harm,
           severity, probability, initial_risk_level,
           risk_control_measure, residual_risk,
           verification_method, status
    FROM risk_records
    WHERE rmf_id = ?
    ORDER BY id ASC
    """, (old_rmf_id,))

    for rec in cursor.fetchall():
        cursor.execute("""
        INSERT INTO risk_records
            (rmf_id, hazard, hazardous_situation, possible_harm,
             severity, probability, initial_risk_level,
             risk_control_measure, residual_risk,
             verification_method, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_rmf_id,
            rec["hazard"],
            rec["hazardous_situation"],
            rec["possible_harm"],
            rec["severity"],
            rec["probability"],
            rec["initial_risk_level"],
            rec["risk_control_measure"],
            rec["residual_risk"],
            rec["verification_method"],
            rec["status"],
            now,
        ))

    conn.commit()
    conn.close()

    return new_rmf_id


# Maps display-name keys (used in DataFrames / dicts) to DB column names.
# Records may arrive with either key style, so both are tried.
_FIELD_MAP = {
    "Hazard":                "hazard",
    "Hazardous Situation":   "hazardous_situation",
    "Possible Harm":         "possible_harm",
    "Severity":              "severity",
    "Probability":           "probability",
    "Initial Risk Level":    "initial_risk_level",
    "Risk Control Measure":  "risk_control_measure",
    "Residual Risk":         "residual_risk",
    "Verification Method":   "verification_method",
    "Status":                "status",
}


def _get_field(record, display_name):
    col = _FIELD_MAP[display_name]
    return record.get(display_name) or record.get(col) or ""


def save_risk_records(rmf_id, records):
    """
    Insert risk records into risk_records, linked to rmf_id.
    records may be a pandas DataFrame or a list of dicts.
    Both Title Case and snake_case keys are accepted.
    """

    if hasattr(records, "to_dict"):
        records = records.to_dict(orient="records")

    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for record in records:
        cursor.execute("""
        INSERT INTO risk_records
            (rmf_id, hazard, hazardous_situation, possible_harm,
             severity, probability, initial_risk_level,
             risk_control_measure, residual_risk,
             verification_method, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rmf_id,
            _get_field(record, "Hazard"),
            _get_field(record, "Hazardous Situation"),
            _get_field(record, "Possible Harm"),
            _get_field(record, "Severity"),
            _get_field(record, "Probability"),
            _get_field(record, "Initial Risk Level"),
            _get_field(record, "Risk Control Measure"),
            _get_field(record, "Residual Risk"),
            _get_field(record, "Verification Method"),
            _get_field(record, "Status"),
            now,
        ))

    conn.commit()
    conn.close()


def get_risk_records_by_rmf(rmf_id):
    """
    Return all risk records for the given rmf_id as a list of dicts.
    Each dict key matches the DB column name.
    Returns an empty list if no records exist.
    """

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, rmf_id, hazard, hazardous_situation, possible_harm,
           severity, probability, initial_risk_level,
           risk_control_measure, residual_risk,
           verification_method, status, created_at
    FROM risk_records
    WHERE rmf_id = ?
    ORDER BY id ASC
    """, (rmf_id,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def update_risk_records(rmf_id, records):
    """
    Replace all risk records for rmf_id with the provided records.
    Accepts a DataFrame or list of dicts (Title Case or snake_case keys).
    """
    if hasattr(records, "to_dict"):
        records = records.to_dict(orient="records")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM risk_records WHERE rmf_id = ?", (rmf_id,))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for record in records:
        cursor.execute("""
        INSERT INTO risk_records
            (rmf_id, hazard, hazardous_situation, possible_harm,
             severity, probability, initial_risk_level,
             risk_control_measure, residual_risk,
             verification_method, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rmf_id,
            _get_field(record, "Hazard"),
            _get_field(record, "Hazardous Situation"),
            _get_field(record, "Possible Harm"),
            _get_field(record, "Severity"),
            _get_field(record, "Probability"),
            _get_field(record, "Initial Risk Level"),
            _get_field(record, "Risk Control Measure"),
            _get_field(record, "Residual Risk"),
            _get_field(record, "Verification Method"),
            _get_field(record, "Status"),
            now,
        ))

    conn.commit()
    conn.close()


def save_rmp_config(config, user_id):
    """
    Overwrite the RMP configuration record for this user.
    Preserves the original created_at if a record already exists.
    List/dict fields are serialised as JSON text.
    """
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        "SELECT created_at FROM rmp_config WHERE user_id = ? LIMIT 1", (user_id,)
    )
    existing = cursor.fetchone()
    created_at = existing[0] if existing else now

    cursor.execute("DELETE FROM rmp_config WHERE user_id = ?", (user_id,))

    cursor.execute("""
    INSERT INTO rmp_config
        (lifecycle_scope, risk_acceptability_criteria,
         residual_risk_method, residual_risk_basis,
         verification_methods, team_members, created_at, updated_at, is_confirmed, user_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
    """, (
        json.dumps(config.get("lifecycle_scope", [])),
        json.dumps(config.get("risk_acceptability_criteria", {})),
        config.get("residual_risk_method", ""),
        json.dumps(config.get("residual_risk_basis", [])),
        json.dumps(config.get("verification_methods", [])),
        config.get("team_members", ""),
        created_at,
        now,
        user_id,
    ))

    conn.commit()
    conn.close()


def get_latest_rmp_config(user_id):
    """
    Return the RMP configuration for this user as a dict, or None if not saved.
    JSON-encoded list/dict fields are decoded back to Python objects.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM rmp_config WHERE user_id = ? LIMIT 1", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    d = dict(row)
    for field in ("lifecycle_scope", "residual_risk_basis", "verification_methods"):
        d[field] = json.loads(d[field]) if d[field] else []
    d["risk_acceptability_criteria"] = (
        json.loads(d["risk_acceptability_criteria"])
        if d["risk_acceptability_criteria"]
        else {}
    )
    return d


def rmp_config_exists(user_id):
    """Return True if a confirmed RMP configuration exists for this user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM rmp_config WHERE user_id = ? AND is_confirmed = 1",
        (user_id,),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0