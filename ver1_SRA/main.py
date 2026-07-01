"""
main.py — FastAPI entrypoint for the Student Record Agent.
"""
from dotenv import load_dotenv
load_dotenv()

import json
import logging
import re
from typing import Optional, List, Dict, Any, Literal  # <-- Make sure Literal is here!

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from langchain_core.tools import tool

from Auth import AuthUser, LoginRequest, create_token, authenticate, get_current_user
from Agent import run_agent
from generate_students import (
    SessionLocal, init_db,
    Student, Subject, Enrollment, Mark,
    get_student_by_id, search_students_by_name,
    update_personal,
    calculate_subject_avg, list_subject_students,
    query_audit_logs, save_conversation, load_conversation,
    list_branch_subjects, get_student_subjects, get_student_subject_mark,
    get_student_cgpa as get_student_cgpa_query,
    get_branch_average_cgpa as get_branch_average_cgpa_query,
    get_students_by_branch_or_year as get_students_by_branch_or_year_query,
    count_students as count_students_query,
    update_marks as update_marks_query,
    create_student as create_student_query,
    create_chat_session, list_chat_sessions, load_chat_session_history,
    save_chat_exchange, rename_chat_session, delete_chat_session,
)

logger = logging.getLogger("sra")

app = FastAPI(title="Student Record Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: Optional[str] = None
    message: Optional[str] = None
    session_id: Optional[str] = None
    title: Optional[str] = None
    history: Optional[list[dict]] = None


class ChatSessionRequest(BaseModel):
    session_id: str
    title: Optional[str] = "New chat"


class RenameSessionRequest(BaseModel):
    title: str


def _subject_semester(subject_code: str) -> Optional[int]:
    match = re.search(r"-s(\d{2})-", subject_code.lower())
    return int(match.group(1)) if match else None


def _grade_point_for_grade(grade: str) -> Optional[float]:
    return {
        "A+": 10.0, "A": 9.0, "B": 8.0, "C": 7.0,
        "D": 6.0, "E": 5.0, "F": 0.0,
    }.get(grade.upper())


def _subject_rows(db: Session, subject_code: str, active_only: bool = True):
    subject = db.query(Subject).filter(Subject.code == subject_code).first()
    if not subject:
        return None, []
    
    query = (
        db.query(Student, Mark)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .join(Mark, Mark.enrollment_id == Enrollment.id)
        .filter(Enrollment.subject_id == subject.id)
    )
    
    if active_only:
        # subject.semester tells us which year: sem 1-2=Y1, 3-4=Y2, 5-6=Y3, 7-8=Y4
        subject_year = (subject.semester + 1) // 2
        query = query.filter(Student.year == subject_year)
    
    rows = query.order_by(Student.id, Mark.recorded_at.desc(), Mark.id.desc()).all()
    latest_by_student = {}
    for student, mark in rows:
        latest_by_student.setdefault(student.id, (student, mark))
    return subject, list(latest_by_student.values())


def _subject_roster(db: Session, subject_code: str, active_only: bool = True) -> dict:
    subject, rows = _subject_rows(db, subject_code, active_only)
    if not subject:
        return {"status": "NOT_FOUND", "message": f"No subject found with code {subject_code}."}
    return {
        "status": "OK",
        "subject_code": subject_code,
        "subject_name": subject.name,
        "student_count": len(rows),
        "students": [
            {"student_id": s.id, "name": s.name, "marks": m.marks, "grade": m.grade, "grade_point": m.grade_point}
            for s, m in rows
        ],
    }


def _subject_statistics(db: Session, subject_code: str, active_only: bool = True) -> dict:
    subject, rows = _subject_rows(db, subject_code, active_only)
    if not subject:
        return {"status": "NOT_FOUND", "message": f"No subject found with code {subject_code}."}
    if not rows:
        return {"status": "OK", "subject_code": subject_code, "subject_name": subject.name,
                "student_count": 0, "average_marks": None, "highest_marks": None,
                "highest_scorers": [], "lowest_marks": None, "pass_percentage": None}
    marks_list = [m.marks for _, m in rows]
    highest = max(marks_list)
    pass_count = sum(1 for _, m in rows if (m.grade or "").upper() != "F")
    return {
        "status": "OK",
        "subject_code": subject_code,
        "subject_name": subject.name,
        "student_count": len(rows),
        "average_marks": round(sum(marks_list) / len(rows), 2),
        "highest_marks": highest,
        "highest_scorers": [{"student_id": s.id, "name": s.name} for s, m in rows if m.marks == highest],
        "lowest_marks": min(marks_list),
        "pass_percentage": round(pass_count / len(rows) * 100, 2),
    }


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup_event():
    init_db()


def build_tools(db: Session, role: str, user_id: int):

    @tool
    def search_students(name: str, branch: Optional[str] = None, semester: Optional[int] = None, limit: int = 10) -> dict:
        """Find students by name (partial match). Use whenever the user gives a name instead of an ID.
        Call this IMMEDIATELY when a name appears in the query — do NOT ask for clarification first.

        branch: Optional filter. Convert user input to code before passing:
            CSE = "Computer Science", "CS", "Comp Sci", "CSE"
            ECE = "Electrical", "Electronics", "EC", "EEE", "ECE"
            ME  = "Mechanical", "Mech", "Mech Eng", "ME"
            CE  = "Civil", "Civil Eng", "CE"

        semester: Optional int 1-8. Use when user specifies a semester or year:
            Year 1 = Sem 1 or 2, Year 2 = Sem 3 or 4, Year 3 = Sem 5 or 6, Year 4 = Sem 7 or 8

        If multiple matches are returned, list them and ask the user which one they mean.
        Do NOT proceed with a guess.

        Examples:
            "find Priya in CSE semester 6" -> search_students(name="Priya", branch="CSE", semester=6)
            "search for Rahul" -> search_students(name="Rahul")
            "who is Bhavana Pandey?" -> search_students(name="Bhavana Pandey")
        """
        matches = search_students_by_name(db, name.strip(), limit)
        if branch:
            matches = [r for r in matches if r["branch"].upper() == branch.upper()]
        if semester is not None:
            matches = [r for r in matches if r["current_semester"] == semester]
        if not matches:
            return {"status": "NOT_FOUND", "message": f"No students found matching '{name}'."}
        return {"status": "OK", "results": matches}

    @tool
    def get_student_profile(student_id: int, detail_level: Literal['personal', 'summary', 'cgpa', 'full_history']) -> dict:
        """Get a student's profile by numeric ID. Call IMMEDIATELY when a numeric ID is given.

        detail_level — choose one:
            'basic_info'   — Returns name, gender, father_name, address, branch, year.
                             USE THIS for: "address", "where does he live", "father name",
                             "who is student X", "basic details".
            'summary'      — CGPA + all semester SGPAs. Use for "summarize", "performance".
            'cgpa'         — CGPA and current_semester only.
            'full_history' — Every semester, every subject, marks, grades.

        'personal' returns: id, name, gender, father_name, address, branch, year.
        These ARE stored and available: name, gender, father_name, address, branch, year.
        These are NOT stored (say unavailable, do not call tools): email, phone, DOB, nationality, religion.

        Examples:
            "show details for student 5"   -> get_student_profile(student_id=5, detail_level='summary')
            "what is student 10's CGPA?"   -> get_student_profile(student_id=10, detail_level='cgpa')
            "full academic history of ID 3" -> get_student_profile(student_id=3, detail_level='full_history')
        """
        res = get_student_by_id(db, student_id)
        if res is None:
            return {"status": "NOT_FOUND", "message": f"No student found with id {student_id}"}

        if detail_level == 'cgpa':
            return {"status": "OK", "id": res["id"], "name": res["name"],
                    "current_semester": res["current_semester"], "cgpa": res["cgpa"]}

        if detail_level == 'basic_info':
            return {"status": "OK", "student": {
                "id": res["id"], "name": res["name"], "gender": res["gender"],
                "father_name": res["father_name"], "address": res["address"],
                "branch": res["branch"], "year": res["year"],
            }}

        if detail_level == 'summary':
            return {"status": "OK", "student": {
                "id": res["id"], "name": res["name"], "branch": res["branch"],
                "year": res["year"], "current_semester": res["current_semester"],
                "cgpa": res["cgpa"],
                "semester_gpas": [{"semester": s["semester"], "sgpa": s["gpa"]} for s in res.get("semesters", [])],
            }}

        return {"status": "OK", "student": res}

    @tool
    def get_student_academic_records(student_id: int, semester: int, subject_code: Optional[str] = None) -> dict:
        """Get academic records for ONE student in ONE semester (1-8).

        subject_code optional:
            Omit  -> returns all subjects + marks + grades + SGPA for that semester.
                     Use the returned 'semester_gpa' field for SGPA. Never calculate it manually.
            Provide -> returns marks/grade/grade_point for that one subject only.

        Subject code format: BRANCH-S[sem]-[idx]  e.g. CSE-S05-01, ECE-S03-02
        Semester is encoded in the code: CSE-S05-01 is semester 5.

        Examples:
            "show semester 2 subjects for student 10"  -> get_student_academic_records(student_id=10, semester=2)
            "what did student 3 get in CSE-S01-02?"    -> get_student_academic_records(student_id=3, semester=1, subject_code="CSE-S01-02")
            "SGPA of student 10 in semester 2"         -> get_student_academic_records(student_id=10, semester=2)
        """
        res = get_student_by_id(db, student_id)
        if res is None:
            return {"status": "NOT_FOUND", "message": f"No student found with id {student_id}"}

        sem_data = next((s for s in res.get("semesters", []) if s["semester"] == semester), None)
        if not sem_data:
            return {"status": "NOT_FOUND", "message": f"No records found for semester {semester}."}

        if subject_code:
            subj = next((s for s in sem_data.get("subjects", [])
                         if s["subject_code"].upper() == subject_code.upper()), None)
            if not subj:
                return {"status": "NOT_FOUND", "message": f"Subject {subject_code} not found in semester {semester}."}
            return {"status": "OK", **subj}

        return {
            "status": "OK",
            "student_id": student_id,
            "semester": semester,
            "semester_gpa": sem_data.get("gpa"),
            "subjects": sem_data.get("subjects", []),
        }

    @tool
    def get_subject_roster_and_stats(subject_code: Optional[str] = None, name: Optional[str] = None,
                                      include_roster: bool = False, all_years: bool = False) -> dict:
        """Get statistics and optionally the full student roster for a subject.

        You can identify the subject by code OR by name — provide at least one.
        NEVER guess a subject code. If user gives a name, pass it as name= and let this tool resolve it.

        subject_code: Exact format BRANCH-S[sem]-[idx], e.g. CSE-S05-04.
        name: Subject name or partial name, e.g. "Earthquake Engineering", "Machine Learning".
              If name matches multiple subjects, all matches are returned — pick the right one and call again with subject_code.

        include_roster:
            False (default) -> stats only: average, highest, lowest, pass%, topper(s).
            True            -> stats + full list of every enrolled student with marks and grade.

        all_years:
            False (default) -> current enrolled students only.
            True            -> all students who ever took this subject across all years.
                               Use only when user explicitly asks for "all years" or "historical".

        Examples:
            "average marks in Earthquake Engineering"       -> get_subject_roster_and_stats(name="Earthquake Engineering")
            "class stats for CSE-S05-04"                    -> get_subject_roster_and_stats(subject_code="CSE-S05-04")
            "list all students in CSE-S05-04"               -> get_subject_roster_and_stats(subject_code="CSE-S05-04", include_roster=True)
            "all students ever enrolled in CSE-S05-04"      -> get_subject_roster_and_stats(subject_code="CSE-S05-04", include_roster=True, all_years=True)
        """
        if not subject_code and name:
            rows = db.query(Subject).filter(Subject.name.ilike(f"%{name}%")).all()
            if not rows:
                return {"status": "NOT_FOUND", "message": f"No subject found matching '{name}'."}
            if len(rows) == 1:
                subject_code = rows[0].code
            else:
                return {"status": "MULTIPLE_FOUND", "subjects": [
                    {"subject_code": s.code, "subject_name": s.name, "branch": s.branch, "semester": s.semester}
                    for s in rows
                ], "message": "Multiple subjects found. Call again with the correct subject_code."}

        if not subject_code:
            return {"status": "ERROR", "message": "Provide either subject_code or name."}

        active_only = not all_years
        stats = _subject_statistics(db, subject_code, active_only)
        if stats.get("status") == "NOT_FOUND":
            return stats
        if include_roster:
            roster = _subject_roster(db, subject_code, active_only)
            stats["roster"] = roster.get("students", [])
        return {"status": "OK", **stats}

    @tool
    def count_or_list_students(branch: Optional[str] = None, year: Optional[int] = None,
                                semester: Optional[int] = None, return_list: bool = False) -> dict:
        """Count or list students filtered by branch, year, and/or semester.

        branch: Convert user input to code before passing:
            CSE = "Computer Science", "CS", "Comp Sci"
            ECE = "Electrical", "Electronics", "EC", "EEE"
            ME  = "Mechanical", "Mech", "Mech Eng"
            CE  = "Civil", "Civil Eng"

        return_list=False -> count only (faster). Use for "how many students in CSE?"
        return_list=True  -> count + list of names. Use for "list all 1st year ECE students"

        To compare branches (e.g. "which branch has most students in sem 6"):
            Call this tool FOUR times, once per branch, with the same semester.
            Then compare the counts yourself and state the result.

        Do NOT pass year and semester together unless user explicitly asks for both.
        return_list=True also returns each student's cgpa.
        For branch average CGPA: call with return_list=True, then average the cgpa values yourself.
        Examples:
            "how many students in CSE?"              -> count_or_list_students(branch="CSE", return_list=False)
            "list 1st year ECE students"             -> count_or_list_students(branch="ECE", year=1, return_list=True)
            "which branch has most in semester 6?"   -> call four times with semester=6, each branch
            "how many are in semester 3?"            -> count_or_list_students(semester=3, return_list=False)
        """
        if not return_list:
            return {"status": "OK", "count": count_students_query(db, year, semester, branch)}

        res = get_students_by_branch_or_year_query(db, branch=branch, year=year) or []
        if semester is not None:
            res = [s for s in res if s.get("current_semester") == semester]
        if not res:
            return {"status": "NOT_FOUND", "message": "No students found matching those criteria."}
        return {
            "status": "OK",
            "total": len(res),
            "students": [{"name": s["name"], "student_id": s["student_id"]} for s in res],
        }

    @tool
    def update_student_record(student_id: int, update_type: Literal['personal', 'marks', 'grade'],
                               payload: dict) -> dict:
        """Modify a student record. Check role permissions before calling.

        ROLE PERMISSIONS:
            personal updates: Admin or Assistant only.
            marks updates: Admin only.
            grade updates: Admin only.

        update_type and payload formats:
            personal: Update name, gender, father_name, or address.
                payload = {"fields": {"name": "New Name", "address": "New Addr"}}

            marks: Update numeric score. Grade auto-calculates from marks.
                payload = {"semester": 5, "subject_code": "CSE-S05-01", "marks": 95.0}

            grade: Change letter grade only. Recalculates GPA and CGPA automatically.
                payload = {"subject_code": "CSE-S05-01", "grade": "C"}
        """
        if update_type == 'personal':
            if role not in ("Admin", "Assistant"):
                return {"status": "DENIED", "message": "Only Admin or Assistant can update personal details."}
            updated = update_personal(db, user_id, role, student_id, payload.get("fields", {}))
            if updated is None:
                return {"status": "NOT_FOUND", "message": f"Student ID {student_id} not found."}
            return {"status": "OK", "updated": updated}

        if role != "Admin":
            return {"status": "DENIED", "message": "Only Admins can modify academic records."}

        if update_type == 'marks':
            sem = payload.get("semester")
            sub_code = payload.get("subject_code")
            marks = payload.get("marks")
            m = int(marks)
            if m >= 90:   g, gp = "A+", 10.0
            elif m >= 80: g, gp = "A",  9.0
            elif m >= 70: g, gp = "B",  8.0
            elif m >= 60: g, gp = "C",  7.0
            elif m >= 50: g, gp = "D",  6.0
            elif m >= 40: g, gp = "E",  5.0
            else:         g, gp = "F",  0.0
            res = update_marks_query(db, user_id, {
                "student_id": student_id, "semester": sem, "subject_code": sub_code,
                "marks": marks, "grade": g, "grade_point": gp
            })
            if res is None:
                return {"status": "NOT_FOUND", "message": "Student or subject code not found."}
            return {"status": "OK", "new_record": res}

        if update_type == 'grade':
            sub_code = payload.get("subject_code")
            grade = payload.get("grade").upper()
            sem = _subject_semester(sub_code)
            gp = _grade_point_for_grade(grade)
            if sem is None or gp is None:
                return {"status": "ERROR", "message": "Invalid subject code or grade."}
            existing = get_student_subject_mark(db, student_id, sub_code)
            if existing is None:
                return {"status": "NOT_FOUND", "message": "No recorded marks found for this subject."}
            before = {s["subject_code"]: s for s in get_student_subjects(db, student_id, sem)}
            res = update_marks_query(db, user_id, {
                "student_id": student_id, "semester": sem, "subject_code": sub_code,
                "marks": existing["marks"], "grade": grade, "grade_point": gp
            })
            after = {s["subject_code"]: s for s in get_student_subjects(db, student_id, sem)}
            changed = [
                {"subject_code": code, "old_grade": before[code]["grade"], "new_grade": after[code]["grade"]}
                for code in after if code in before and before[code]["grade"] != after[code]["grade"]
            ]
            return {"status": "OK", "new_record": res, "changed_subjects": changed}

    @tool
    def get_audit_logs(student_id: Optional[int] = None, action: Optional[str] = None, limit: int = 50) -> dict:
        """View the audit trail of changes made to student records. Admin only.

        student_id: Filter to one student's change history.
        action: Filter by action type. Known values: 'update_marks', 'update_personal', 'create_student'.

        Use when user asks:
            "what changes were made to student 5?"
            "show audit log for Priya Menon" (search first to get ID, then call this)
            "who updated marks for student 12?"
        Do NOT call this if role is not Admin — return a denial message directly.    
        Do NOT call get_subject_roster_and_stats and present its output as audit data.
        Roster data (marks, grades) is NOT the same as audit log data (who changed what, when).
        NEVER call this tool unless the user explicitly uses words like:
        "audit", "log", "history of changes", "who changed", "modifications made".
        Do NOT call this after retrieving a student profile. It is unrelated to profile lookups.

        If asked for audit logs related to a subject:
            Step 1: get_subject_roster_and_stats to get student IDs.
            Step 2: call get_audit_logs(student_id=<id>, action='update_marks') per student.
            If no audit entries exist, say "No changes have been recorded for this subject."
        """
        if role != "Admin":
            return {"status": "DENIED", "message": "Only Admins can view audit logs."}
        entries = query_audit_logs(db, student_id=student_id, action=action, limit=limit)
        return {"status": "OK", "entries": entries}

    @tool
    def get_branch_stats(branch: str) -> dict:
        """Get average CGPA and total student count for an entire branch.
        branch codes: CSE, ECE, ME, CE (convert aliases before calling).

        Use IMMEDIATELY for: "average CGPA for CSE", "how is ME branch performing overall".
        Do NOT call count_or_list_students in a loop to calculate averages — use this instead.

        Examples:
            "average CGPA for CSE students"  -> get_branch_stats(branch="CSE")
            "what is the ECE branch average?" -> get_branch_stats(branch="ECE")
        """
        res = get_branch_average_cgpa_query(db, branch)
        if res is None:
            return {"status": "NOT_FOUND", "message": f"No data found for branch {branch}."}
        if isinstance(res, dict):
            return {"status": "OK", **res}
        return {"status": "OK", "branch": branch, "average_cgpa": res}

    return [
        search_students, get_student_profile, get_student_academic_records,
        get_subject_roster_and_stats, count_or_list_students,
        update_student_record, get_audit_logs, get_branch_stats
    ]

# ── Auth ──────────────────────────────────────

@app.post("/auth/login")
def login(payload: LoginRequest):
    user = authenticate(payload.username, payload.password)
    token = create_token(payload.username)
    return {"access_token": token, "token_type": "bearer",
            "role": user["role"], "user_id": user["user_id"]}


@app.post("/auth/token")
def login_swagger(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate(form_data.username, form_data.password)
    token = create_token(form_data.username)
    return {"access_token": token, "token_type": "bearer",
            "role": user["role"], "user_id": user["user_id"]}


# ── Chat sessions ─────────────────────────────

@app.get("/chat/sessions")
def api_list_chat_sessions(user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"status": "OK", "sessions": list_chat_sessions(db, user.user_id)}


@app.post("/chat/sessions")
def api_create_chat_session(payload: ChatSessionRequest, user: AuthUser = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    session = create_chat_session(db, user.user_id, user.role, payload.session_id, payload.title or "New chat")
    return {"status": "OK", "session": session}


@app.patch("/chat/sessions/{session_id}")
def api_rename_chat_session(session_id: str, payload: RenameSessionRequest,
                             user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    session = rename_chat_session(db, user.user_id, session_id, payload.title)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"status": "OK", "session": session}


@app.delete("/chat/sessions/{session_id}")
def api_delete_chat_session(session_id: str, user: AuthUser = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    if not delete_chat_session(db, user.user_id, session_id):
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"status": "OK"}


# ── Main chat endpoint ────────────────────────

@app.post("/chat")
def chat(payload: ChatRequest, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    query = (payload.query or payload.message or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query or message is required")

    if payload.history is None and payload.session_id:
        history = load_chat_session_history(db, user.user_id, payload.session_id)
    elif payload.history is None:
        raw = load_conversation(db, user.user_id)
        history = json.loads(raw) if raw else []
    else:
        history = payload.history

    tools = build_tools(db, user.role, user.user_id)
    agent_failed = False
    try:
        answer = run_agent(tools, user.role, query, history)
    except Exception:
        logger.exception("Agent failed on query: %r", query)
        answer = ""
        agent_failed = True

    if not answer:
        answer = "Sorry, I could not process that request. Please try rephrasing it, or try again."
        agent_failed = True

    if not agent_failed:
        updated_history = history + [
            {"role": "user", "content": query},
            {"role": "assistant", "content": answer},
        ]
        if payload.session_id:
            save_chat_exchange(db, user.user_id, user.role, payload.session_id,
                               payload.title or query[:42] or "New chat", query, answer)
        else:
            save_conversation(db, user.user_id, json.dumps(updated_history))
    else:
        # Don't persist failed turns — a bad response in history poisons
        # the next request's context and causes compounding failures.
        updated_history = history
        logger.warning("Skipped saving chat history for user %s due to agent failure.", user.user_id)

    return {"status": "OK", "response": answer, "history": updated_history}


# ── Debug tool endpoints ──────────────────────

@app.post("/tools/get_student")
def api_get_student(payload: dict, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    sid = payload.get("student_id")
    if sid is None:
        raise HTTPException(status_code=400, detail="student_id required")
    res = get_student_by_id(db, sid)
    return {"status": "NOT_FOUND"} if res is None else {"status": "OK", "student": res}


@app.post("/tools/search_student")
def api_search_student(payload: dict, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    return {"status": "OK", "results": search_students_by_name(db, name, payload.get("limit", 10))}


@app.post("/tools/update_personal")
def api_update_personal(payload: dict, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ("Admin", "Assistant"):
        return {"status": "DENIED"}
    sid = payload.get("student_id")
    fields = payload.get("fields", {})
    if not sid or not fields:
        raise HTTPException(status_code=400, detail="student_id and fields required")
    updated = update_personal(db, user.user_id, user.role, sid, fields)
    return {"status": "NOT_FOUND"} if updated is None else {"status": "OK", "updated": updated}


@app.post("/tools/update_marks")
def api_update_marks(payload: dict, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Admin":
        return {"status": "DENIED", "message": "Admins only"}
    required = ("student_id", "semester", "subject_code", "marks", "grade", "grade_point")
    if not all(k in payload for k in required):
        raise HTTPException(status_code=400, detail=f"Required: {required}")
    res = update_marks_query(db, user.user_id, payload)
    return {"status": "NOT_FOUND"} if res is None else {"status": "OK", "new_record": res}


@app.post("/tools/calc_subject_avg")
def api_calc_subject_avg(payload: dict, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    sc = payload.get("subject_code")
    sem = payload.get("semester")
    if not sc or sem is None:
        raise HTTPException(status_code=400, detail="subject_code and semester required")
    return {"status": "OK", **calculate_subject_avg(db, sc, sem)}


@app.post("/tools/list_subject_students")
def api_list_subject_students(payload: dict, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    sc = payload.get("subject_code")
    sem = payload.get("semester")
    if not sc or sem is None:
        raise HTTPException(status_code=400, detail="subject_code and semester required")
    res = list_subject_students(db, sc, sem, payload.get("limit", 100), payload.get("offset", 0))
    return {"status": "OK", "students": res["students"], "total": res["total"]}


@app.post("/tools/create_student")
def api_create_student(payload: dict, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Admin":
        return {"status": "DENIED", "message": "Admins only"}
    required = ("name", "father_name", "address", "gender", "branch", "year", "enroll_year")
    if not all(k in payload for k in required):
        raise HTTPException(status_code=400, detail=f"Required: {required}")
    return {"status": "OK", "student_id": create_student_query(db, payload)}


@app.get("/audit/logs")
def api_audit_logs(student_id: Optional[int] = None, action: Optional[str] = None,
                   limit: int = 100, user: AuthUser = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if user.role != "Admin":
        return {"status": "DENIED", "message": "Admins only"}
    return {"status": "OK", "entries": query_audit_logs(db, student_id=student_id, action=action, limit=limit)}