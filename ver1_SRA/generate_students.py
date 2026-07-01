from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
from sqlalchemy.engine.url import make_url
from typing import Optional
import os
import json
import random
from datetime import datetime
import statistics
import argparse

# ──────────────────────────────────────────────
# DB Connection — MySQL
# ──────────────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:NewPassword123!@localhost:3306/student_db"
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _mysql_database_url_parts():
    url = make_url(DATABASE_URL)
    if not url.drivername.startswith("mysql") or not url.database:
        return url, None, None

    db_name = url.database.replace("`", "``")
    server_url = url.set(database=None)
    return url, db_name, server_url


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────

class Student(Base):
    __tablename__ = "students"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    name             = Column(String(120), index=True, nullable=False)
    gender           = Column(String(1), nullable=False)          # 'M' or 'F'
    father_name      = Column(String(120), nullable=False)
    address          = Column(Text, nullable=False)
    branch           = Column(String(10), nullable=False)
    year             = Column(Integer, nullable=False)            # 1-4
    current_semester = Column(Integer, nullable=False)            # 1-8
    enroll_year      = Column(Integer, nullable=False)
    cgpa             = Column(Float, default=0.0)                 # cumulative across all completed sems
    created_at       = Column(DateTime, server_default=func.now())
    enrollments      = relationship("Enrollment", back_populates="student")


class Subject(Base):
    __tablename__ = "subjects"
    id       = Column(Integer, primary_key=True, autoincrement=True)
    code     = Column(String(30), index=True, nullable=False)
    name     = Column(String(120), nullable=False)
    branch   = Column(String(10), nullable=False)
    semester = Column(Integer, nullable=False)
    credits  = Column(Integer, default=3)


class Enrollment(Base):
    __tablename__ = "enrollments"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    active     = Column(Boolean, default=True)
    student    = relationship("Student", back_populates="enrollments")
    subject    = relationship("Subject")
    marks      = relationship("Mark", back_populates="enrollment")


class Mark(Base):
    __tablename__ = "marks"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    enrollment_id = Column(Integer, ForeignKey("enrollments.id"), nullable=False)
    marks         = Column(Integer, nullable=False)
    grade         = Column(String(3), nullable=False)
    grade_point   = Column(Float, nullable=False)
    recorded_by   = Column(Integer)
    recorded_at   = Column(DateTime, default=datetime.utcnow)
    enrollment    = relationship("Enrollment", back_populates="marks")


class SemesterGPA(Base):
    __tablename__ = "semester_gpa"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    student_id    = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    semester      = Column(Integer, nullable=False)
    gpa           = Column(Float, nullable=False)
    calculated_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    user_id        = Column(Integer)
    student_id     = Column(Integer, index=True)
    role           = Column(String(20))
    action         = Column(String(50))
    payload_before = Column(Text)
    payload_after  = Column(Text)
    timestamp      = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(Integer, unique=True, index=True, nullable=False)
    history_json = Column(Text, nullable=False, default="[]")
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id         = Column(String(80), primary_key=True)
    user_id    = Column(Integer, index=True, nullable=False)
    role       = Column(String(20), nullable=False)
    title      = Column(String(160), nullable=False, default="New chat")
    archived   = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    messages   = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(80), ForeignKey("chat_sessions.id"), index=True, nullable=False)
    user_id    = Column(Integer, index=True, nullable=False)
    role       = Column(String(20), nullable=False)
    content    = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    session    = relationship("ChatSession", back_populates="messages")


# ──────────────────────────────────────────────
# Init
# ──────────────────────────────────────────────
def init_db():
    _, db_name, server_url = _mysql_database_url_parts()

    if db_name and server_url:
        server_engine = create_engine(server_url, echo=False, isolation_level="AUTOCOMMIT")
        try:
            with server_engine.connect() as conn:
                conn.execute(text(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                ))
        finally:
            server_engine.dispose()

    Base.metadata.create_all(bind=engine)


def reset_db():
    _, db_name, server_url = _mysql_database_url_parts()

    if db_name and server_url:
        server_engine = create_engine(server_url, echo=False, isolation_level="AUTOCOMMIT")
        try:
            with server_engine.connect() as conn:
                conn.execute(text(f"DROP DATABASE IF EXISTS `{db_name}`"))
                conn.execute(text(
                    f"CREATE DATABASE `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                ))
        finally:
            server_engine.dispose()
    else:
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)


# ──────────────────────────────────────────────
# Grading helper
# ──────────────────────────────────────────────

def grade_for_marks(m: int):
    if m >= 90: return "A+", 10.0
    if m >= 80: return "A",  9.0
    if m >= 70: return "B",  8.0
    if m >= 60: return "C",  7.0
    if m >= 50: return "D",  6.0
    if m >= 40: return "E",  5.0
    return "F", 0.0


# ──────────────────────────────────────────────
# CGPA helper — weighted average across all sems
# ──────────────────────────────────────────────

def _compute_cgpa(db, student_id: int) -> float:
    sem_gpas = db.query(SemesterGPA).filter(SemesterGPA.student_id == student_id).all()
    if not sem_gpas:
        return 0.0
    return round(statistics.mean([sg.gpa for sg in sem_gpas]), 2)


# ──────────────────────────────────────────────
# Audit helper
# ──────────────────────────────────────────────

def _record_audit(db, user_id, role, action, student_id, before, after):
    entry = AuditLog(
        user_id=user_id, student_id=student_id, role=role,
        action=action, payload_before=str(before), payload_after=str(after)
    )
    db.add(entry)
    db.commit()


def _latest_marks(marks):
    latest = {}
    for m in sorted(marks, key=lambda mk: ((mk.recorded_at or datetime.min), mk.id), reverse=True):
        if m.enrollment_id not in latest:
            latest[m.enrollment_id] = m
    return list(latest.values())


# ──────────────────────────────────────────────
# CRUD — Read
# ──────────────────────────────────────────────

def get_student_by_id(db, student_id: int):
    s = db.query(Student).filter(Student.id == student_id).first()
    if not s:
        return None

    semesters = {}
    for enr in s.enrollments:
        sem = enr.subject.semester
        semesters.setdefault(sem, {"semester": sem, "subjects": []})
        for mk in _latest_marks(enr.marks):
            semesters[sem]["subjects"].append({
                "subject_code": enr.subject.code,
                "subject_name": enr.subject.name,
                "marks":        mk.marks,
                "grade":        mk.grade,
                "grade_point":  mk.grade_point,
                "credits":      enr.subject.credits,
            })

    sem_list = []
    for sem, data in sorted(semesters.items()):
        gpa_entry = db.query(SemesterGPA).filter(
            SemesterGPA.student_id == s.id,
            SemesterGPA.semester   == sem
        ).first()
        sem_list.append({
            "semester": sem,
            "gpa":      round(gpa_entry.gpa, 2) if gpa_entry else None,
            "subjects": data["subjects"],
        })

    return {
        "id":               s.id,
        "name":             s.name,
        "gender":           s.gender,
        "father_name":      s.father_name,
        "address":          s.address,
        "branch":           s.branch,
        "year":             s.year,
        "current_semester": s.current_semester,
        "enroll_year":      s.enroll_year,
        "cgpa":             s.cgpa,
        "semesters":        sem_list,
    }

def get_student_subjects(db, student_id: int, semester: int):
    rows = (
        db.query(
            Subject.code,
            Subject.name,
            Mark.marks,
            Mark.grade,
            Mark.grade_point,
        )
        .join(Enrollment, Enrollment.subject_id == Subject.id)
        .outerjoin(Mark, Mark.enrollment_id == Enrollment.id)
        .filter(
            Enrollment.student_id == student_id,
            Subject.semester == semester,
        )
        .order_by(Subject.code)
        .all()
    )

    return [
        {
            "subject_code": r.code,
            "subject_name": r.name,
            "marks": r.marks,
            "grade": r.grade,
            "grade_point": r.grade_point,
        }
        for r in rows
    ]

def get_student_subject_mark(db, student_id: int, subject_code: str):
    row = (
        db.query(
            Subject.code,
            Subject.name,
            Mark.marks,
            Mark.grade,
            Mark.grade_point,
        )
        .join(Enrollment, Enrollment.subject_id == Subject.id)
        .join(Mark, Mark.enrollment_id == Enrollment.id)
        .filter(
            Enrollment.student_id == student_id,
            Subject.code == subject_code,
        )
        .first()
    )

    if row is None:
        return None

    return {
        "subject_code": row.code,
        "subject_name": row.name,
        "marks": row.marks,
        "grade": row.grade,
        "grade_point": row.grade_point,
    }

def search_students_by_name(db, name: str, limit: int = 10):
    q = db.query(Student).filter(Student.name.ilike(f"%{name}%"))
    return [
        {
            "student_id":       s.id,
            "name":             s.name,
            "gender":           s.gender,
            "branch":           s.branch,
            "year":             s.year,
            "current_semester": s.current_semester,
        }
        for s in q.limit(limit).all()
    ]


# ──────────────────────────────────────────────
# CRUD — Write
# ──────────────────────────────────────────────

def update_personal(db, user_id, role, student_id, fields: dict):
    s = db.query(Student).filter(Student.id == student_id).first()
    if not s:
        return None

    before = {
        "name": s.name, "gender": s.gender,
        "father_name": s.father_name, "address": s.address,
    }

    allowed = {"name", "gender", "father_name", "address"}
    for field, value in fields.items():
        if field in allowed:
            setattr(s, field, value)

    db.add(s)
    db.commit()

    after = {
        "name": s.name, "gender": s.gender,
        "father_name": s.father_name, "address": s.address,
    }
    _record_audit(db, user_id, role, "update_personal", student_id, before, after)
    return after


def update_marks(db, user_id, payload: dict):
    student_id   = payload["student_id"]
    semester     = payload["semester"]
    subject_code = payload["subject_code"]
    marks_val    = int(payload["marks"])
    grade        = payload["grade"]
    grade_point  = float(payload["grade_point"])

    s = db.query(Student).filter(Student.id == student_id).first()
    if not s:
        return None

    subj = db.query(Subject).filter(
        Subject.code     == subject_code,
        Subject.semester == semester
    ).first()
    if not subj:
        return None

    enr = db.query(Enrollment).filter(
        Enrollment.student_id == student_id,
        Enrollment.subject_id == subj.id
    ).first()
    if not enr:
        enr = Enrollment(student_id=student_id, subject_id=subj.id, active=True)
        db.add(enr)
        db.commit()

    existing = (
        db.query(Mark)
        .filter(Mark.enrollment_id == enr.id)
        .order_by(Mark.recorded_at.desc(), Mark.id.desc())
        .first()
    )
    before = {
        "marks": existing.marks if existing else None,
        "grade": existing.grade if existing else None,
        "grade_point": existing.grade_point if existing else None,
    }

    if existing:
        existing.marks       = marks_val
        existing.grade       = grade
        existing.grade_point = grade_point
        existing.recorded_by = user_id
        existing.recorded_at = datetime.utcnow()
        db.add(existing)
    else:
        mk = Mark(
            enrollment_id=enr.id, marks=marks_val,
            grade=grade, grade_point=grade_point, recorded_by=user_id
        )
        db.add(mk)
    db.commit()

    marks_rows = (
        db.query(Mark)
        .join(Enrollment)
        .join(Subject)
        .filter(Enrollment.student_id == student_id, Subject.semester == semester)
        .all()
    )
    marks_rows = _latest_marks(marks_rows)
    total_weight, total_points = 0, 0
    for m in marks_rows:
        credits       = m.enrollment.subject.credits
        total_weight += credits
        total_points += m.grade_point * credits
    sem_gpa = round((total_points / total_weight) if total_weight else 0.0, 2)

    sg = db.query(SemesterGPA).filter(
        SemesterGPA.student_id == student_id,
        SemesterGPA.semester   == semester
    ).first()
    if not sg:
        sg = SemesterGPA(student_id=student_id, semester=semester, gpa=sem_gpa)
        db.add(sg)
    else:
        sg.gpa = sem_gpa
        sg.calculated_at = datetime.utcnow()
    db.commit()

    s.cgpa = _compute_cgpa(db, student_id)
    db.add(s)
    db.commit()

    _record_audit(db, user_id, "Admin", "update_marks", student_id, before,
                  {"marks": marks_val, "grade": grade, "grade_point": grade_point, "semester_gpa": sem_gpa})

    return {
        "enrollment_id": enr.id,
        "marks":         marks_val,
        "grade":         grade,
        "grade_point":   grade_point,
        "semester_gpa":  sem_gpa,
        "cgpa":          s.cgpa,
    }


def create_student(db, payload: dict):
    current_semester = (payload["year"] - 1) * 2 + 1
    s = Student(
        name             = payload["name"],
        gender           = payload["gender"],
        father_name      = payload["father_name"],
        address          = payload["address"],
        branch           = payload["branch"],
        year             = payload["year"],
        current_semester = current_semester,
        enroll_year      = payload["enroll_year"],
        cgpa             = 0.0,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    _record_audit(db, None, "Admin", "create_student", s.id, None, {"student_id": s.id})
    return s.id


# ──────────────────────────────────────────────
# CRUD — Subject queries
# ──────────────────────────────────────────────

def calculate_subject_avg(db, subject_code: str, semester: int):
    subj = db.query(Subject).filter(Subject.code == subject_code, Subject.semester == semester).first()
    if not subj:
        return {"subject_code": subject_code, "semester": semester, "avg_marks": None,
                "avg_grade_point": None, "highest_marks": None, "lowest_marks": None,
                "pass_percentage": None, "student_count": 0}

    marks_q = (
        db.query(Mark)
        .join(Enrollment)
        .join(Student, Student.id == Enrollment.student_id)
        .filter(Enrollment.subject_id == subj.id, Enrollment.active == True,
                Student.current_semester == semester)
        .all()
    )
    marks_q = _latest_marks(marks_q)
    if not marks_q:
        return {"subject_code": subject_code, "semester": semester, "avg_marks": None,
                "avg_grade_point": None, "highest_marks": None, "lowest_marks": None,
                "pass_percentage": None, "student_count": 0}

    marks = [m.marks for m in marks_q]
    gps   = [m.grade_point for m in marks_q]
    passed = sum(1 for m in marks if m >= 40)
    return {
        "subject_code": subject_code, "subject_name": subj.name, "semester": semester,
        "avg_marks": round(statistics.mean(marks), 2),
        "avg_grade_point": round(statistics.mean(gps), 2),
        "highest_marks": max(marks), "lowest_marks": min(marks),
        "pass_percentage": round(passed / len(marks) * 100, 1),
        "student_count": len(marks_q),
    }


def count_students(db, year: Optional[int] = None, semester: Optional[int] = None,
                    branch: Optional[str] = None):
    q = db.query(Student)
    if year is not None:
        q = q.filter(Student.year == year)
    if semester is not None:
        q = q.filter(Student.current_semester == semester)
    if branch:
        q = q.filter(Student.branch == branch)
    return q.count()


def get_student_cgpa(db, student_id: int):
    s = db.query(Student).filter(Student.id == student_id).first()
    if not s:
        return None
    return {"student_id": s.id, "name": s.name, "cgpa": s.cgpa, "current_semester": s.current_semester}


def get_branch_average_cgpa(db, branch: str):
    students = db.query(Student).filter(Student.branch == branch).all()
    if not students:
        return None
    cgpas = [s.cgpa for s in students if s.cgpa is not None]
    return {
        "branch": branch,
        "avg_cgpa": round(statistics.mean(cgpas), 2) if cgpas else None,
        "student_count": len(students),
    }


def get_students_by_branch_or_year(db, branch: Optional[str] = None,
                                    year: Optional[int] = None, limit: int = 50):
    q = db.query(Student)
    if branch:
        q = q.filter(Student.branch == branch)
    if year is not None:
        q = q.filter(Student.year == year)
    rows = q.limit(limit).all()
    return [
        {"student_id": s.id, "name": s.name, "branch": s.branch,
         "year": s.year, "current_semester": s.current_semester, "cgpa": s.cgpa}
        for s in rows
    ]


def list_subject_students(db, subject_code: str, semester: int,
                           limit: int = 100, offset: int = 0):
    subj = db.query(Subject).filter(
        Subject.code     == subject_code,
        Subject.semester == semester
    ).first()
    if not subj:
        return {"students": [], "total": 0}

    enrollments = (
        db.query(Enrollment)
        .join(Student, Student.id == Enrollment.student_id)
        .filter(
            Enrollment.subject_id    == subj.id,
            Enrollment.active        == True,
            Student.current_semester == semester,
        )
        .offset(offset).limit(limit).all()
    )
    out = []
    for e in enrollments:
        for m in _latest_marks(e.marks):
            out.append({
                "student_id":  e.student_id,
                "name":        e.student.name,
                "gender":      e.student.gender,
                "marks":       m.marks,
                "grade":       m.grade,
                "grade_point": m.grade_point,
            })

    total = (
        db.query(Enrollment)
        .join(Student, Student.id == Enrollment.student_id)
        .filter(
            Enrollment.subject_id    == subj.id,
            Enrollment.active        == True,
            Student.current_semester == semester,
        )
        .count()
    )
    return {"students": out, "total": total}


def list_branch_subjects(db, branch: str, semester: int):
    subs = (
        db.query(Subject)
        .filter(Subject.branch == branch, Subject.semester == semester)
        .order_by(Subject.code)
        .all()
    )
    return [
        {"subject_code": s.code, "subject_name": s.name, "credits": s.credits}
        for s in subs
    ]


def list_branches(db):
    rows = db.query(Student.branch).distinct().order_by(Student.branch).all()
    return [row[0] for row in rows]


# ──────────────────────────────────────────────
# Audit logs
# ──────────────────────────────────────────────

def query_audit_logs(db, student_id: Optional[int] = None,
                     action: Optional[str] = None, limit: int = 100):
    q = db.query(AuditLog)
    if student_id:
        q = q.filter(AuditLog.student_id == student_id)
    if action:
        q = q.filter(AuditLog.action == action)
    q = q.order_by(AuditLog.timestamp.desc()).limit(limit)
    return [
        {
            "timestamp":  e.timestamp.isoformat(),
            "user_id":    e.user_id,
            "student_id": e.student_id,
            "role":       e.role,
            "action":     e.action,
            "before":     e.payload_before,
            "after":      e.payload_after,
        }
        for e in q.all()
    ]


# ──────────────────────────────────────────────
# Conversation memory 
# ──────────────────────────────────────────────

def load_conversation(db, user_id: int) -> Optional[str]:
    row = db.query(Conversation).filter(Conversation.user_id == user_id).first()
    return row.history_json if row else None


def save_conversation(db, user_id: int, history_json: str):
    row = db.query(Conversation).filter(Conversation.user_id == user_id).first()
    if row:
        row.history_json = history_json
        row.updated_at   = datetime.utcnow()
    else:
        row = Conversation(user_id=user_id, history_json=history_json)
        db.add(row)
    db.commit()


def _message_to_dict(message: ChatMessage):
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _session_to_dict(session: ChatSession, include_messages: bool = True):
    data = {
        "id": session.id,
        "user_id": session.user_id,
        "role": session.role,
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }
    if include_messages:
        data["messages"] = [_message_to_dict(message) for message in session.messages]
    else:
        data["message_count"] = len(session.messages)
    return data


def create_chat_session(db, user_id: int, role: str, session_id: str, title: str = "New chat"):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
    ).first()
    if session:
        return _session_to_dict(session)

    session = ChatSession(id=session_id, user_id=user_id, role=role, title=title or "New chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_to_dict(session)


def list_chat_sessions(db, user_id: int):
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id, ChatSession.archived == False)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [_session_to_dict(session) for session in sessions]


def load_chat_session_history(db, user_id: int, session_id: str):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
        ChatSession.archived == False,
    ).first()
    if not session:
        return []
    return [{"role": message.role, "content": message.content} for message in session.messages]


def save_chat_exchange(db, user_id: int, role: str, session_id: str, title: str,
                       user_content: str, assistant_content: str):
    try:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        ).first()
        if not session:
            session = ChatSession(id=session_id, user_id=user_id, role=role, title=title or "New chat")
            db.add(session)
            db.flush()

        if title and (session.title == "New chat" or session.title != title):
            session.title = title[:160]
        session.role = role
        session.updated_at = datetime.utcnow()
        db.add(session)
        db.flush()

        db.add(ChatMessage(session_id=session_id, user_id=user_id, role="user", content=user_content))
        db.add(ChatMessage(session_id=session_id, user_id=user_id, role="assistant", content=assistant_content))
        db.commit()
        db.refresh(session)
        return _session_to_dict(session)
    except Exception:
        db.rollback()
        # Session already exists — just append messages
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        ).first()
        if session:
            db.add(ChatMessage(session_id=session_id, user_id=user_id, role="user", content=user_content))
            db.add(ChatMessage(session_id=session_id, user_id=user_id, role="assistant", content=assistant_content))
            db.commit()
            db.refresh(session)
            return _session_to_dict(session)
        return None


def rename_chat_session(db, user_id: int, session_id: str, title: str):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
    ).first()
    if not session:
        return None
    session.title = title[:160] or "New chat"
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return _session_to_dict(session)


def delete_chat_session(db, user_id: int, session_id: str):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
    ).first()
    if not session:
        return False
    db.delete(session)
    db.commit()
    return True


# ──────────────────────────────────────────────
# Synthetic data
# ──────────────────────────────────────────────

_MALE_FIRST = [
    "Aarav", "Arjun", "Rohit", "Kiran", "Vikram", "Suresh", "Ramesh", "Nikhil",
    "Aditya", "Sai", "Rahul", "Pranav", "Harish", "Manoj", "Deepak", "Akash",
    "Varun", "Gaurav", "Tarun", "Mohit", "Yash", "Ankit", "Ravi", "Ajay", "Vijay",
    "Sachin", "Naveen", "Santosh", "Lokesh", "Charan",
]
_FEMALE_FIRST = [
    "Priya", "Ananya", "Divya", "Sneha", "Pooja", "Kavya", "Lakshmi", "Sravya",
    "Meghana", "Nithya", "Keerthi", "Bhavana", "Swathi", "Madhuri", "Ramya",
    "Sirisha", "Lavanya", "Mounika", "Haritha", "Deepika", "Anusha", "Chandana",
    "Padmaja", "Hema", "Sunitha", "Usha", "Rekha", "Gayatri", "Mythili", "Aparna",
]
_LAST = [
    "Reddy", "Kumar", "Sharma", "Rao", "Naidu", "Patel", "Gupta", "Singh",
    "Verma", "Nair", "Iyer", "Pillai", "Menon", "Joshi", "Mishra", "Tiwari",
    "Yadav", "Chauhan", "Pandey", "Sinha",
]
_AREAS = [
    "Madhapur", "Gachibowli", "Kukatpally", "Dilsukhnagar", "Secunderabad",
    "Begumpet", "Ameerpet", "Himayatnagar", "Banjara Hills", "Jubilee Hills",
    "Kondapur", "Miyapur", "Uppal", "LB Nagar", "Vanasthalipuram",
]

_SUBJECT_NAMES = {
    "CSE": [
        "Engineering Math I", "Engineering Physics", "Programming in C", "Engineering Graphics", "English Communication",
        "Engineering Math II", "Engineering Chemistry", "Data Structures", "Digital Logic Design", "Environmental Science",
        "Discrete Mathematics", "Object Oriented Programming", "Computer Organisation", "Database Management Systems", "Probability & Statistics",
        "Algorithms", "Operating Systems", "Computer Networks", "Software Engineering", "Formal Languages",
        "Machine Learning", "Web Technologies", "Compiler Design", "Cloud Computing", "Open Elective I",
        "Deep Learning", "Cyber Security", "Distributed Systems", "Big Data Analytics", "Open Elective II",
        "Artificial Intelligence", "IoT & Embedded Systems", "Mobile Computing", "DevOps", "Project Phase I",
        "Blockchain Technology", "NLP", "Data Mining", "Professional Ethics", "Project Phase II",
    ],
    "ECE": [
        "Engineering Math I", "Engineering Physics", "Basic Electrical Engg", "Engineering Graphics", "English Communication",
        "Engineering Math II", "Engineering Chemistry", "Circuit Theory", "Electronic Devices", "Environmental Science",
        "Signals & Systems", "Analog Circuits", "Digital Electronics", "EM Theory", "Probability & Random Processes",
        "Analog Communication", "Digital Communication", "Microprocessors", "Control Systems", "Linear Algebra",
        "VLSI Design", "DSP", "Antennas & Wave Propagation", "Embedded Systems", "Open Elective I",
        "RF Engineering", "Wireless Communication", "Image Processing", "Power Electronics", "Open Elective II",
        "Satellite Communication", "Optical Communication", "Radar Systems", "PCB Design", "Project Phase I",
        "Biomedical Electronics", "MEMS & Nanotechnology", "CAD Tools", "Professional Ethics", "Project Phase II",
    ],
    "ME":  [
        "Engineering Math I", "Engineering Physics", "Engineering Graphics", "Workshop Technology", "English Communication",
        "Engineering Math II", "Engineering Chemistry", "Engineering Mechanics", "Basic Electrical Engg", "Environmental Science",
        "Thermodynamics", "Materials Science", "Fluid Mechanics", "Manufacturing Processes", "Probability & Statistics",
        "Machine Design", "Heat Transfer", "Dynamics of Machinery", "Metrology & Measurements", "Numerical Methods",
        "CAD/CAM", "Automobile Engineering", "Turbomachinery", "Industrial Engineering", "Open Elective I",
        "Finite Element Methods", "Refrigeration & AC", "IC Engines", "Robotics", "Open Elective II",
        "Composite Materials", "Renewable Energy Systems", "Production Planning", "Quality Control", "Project Phase I",
        "Tool Design", "Supply Chain Management", "Operations Research", "Professional Ethics", "Project Phase II",
    ],
    "CE":  [
        "Engineering Math I", "Engineering Physics", "Engineering Graphics", "Basic Civil Engg", "English Communication",
        "Engineering Math II", "Engineering Chemistry", "Surveying", "Building Materials", "Environmental Science",
        "Fluid Mechanics", "Structural Analysis I", "Soil Mechanics", "Concrete Technology", "Probability & Statistics",
        "Structural Analysis II", "Geotechnical Engineering", "Hydraulics", "Transportation Engineering", "Numerical Methods",
        "RCC Design", "Environmental Engineering", "Water Supply Engineering", "Construction Management", "Open Elective I",
        "Steel Design", "Foundation Design", "Irrigation Engineering", "Bridge Engineering", "Open Elective II",
        "GIS & Remote Sensing", "Pavement Design", "Earthquake Engineering", "Town Planning", "Project Phase I",
        "Prestressed Concrete", "Tunnel Engineering", "Port & Harbour Engg", "Professional Ethics", "Project Phase II",
    ],
}


def _random_name(gender: str, rng: random.Random):
    first = rng.choice(_MALE_FIRST if gender == "M" else _FEMALE_FIRST)
    last  = rng.choice(_LAST)
    return f"{first} {last}"


def _random_address(rng: random.Random):
    plot  = rng.randint(1, 200)
    area  = rng.choice(_AREAS)
    pin   = rng.randint(500001, 500100)
    return f"Plot {plot}, {area}, Hyderabad - {pin}"


def generate_synthetic(db, branches=None, years=None, per_group: int = 30, seed: int = 42):
    rng      = random.Random(seed)
    branches = branches or ["CSE", "ECE", "ME", "CE"]
    years    = years    or [1, 2, 3, 4]

    subj_map = {}
    for br in branches:
        names = _SUBJECT_NAMES.get(br, [])
        idx   = 0
        for sem in range(1, 9):
            for i in range(1, 6):
                subj_name = names[idx] if idx < len(names) else f"{br} Subject {sem}-{i}"
                code       = f"{br}-S{sem:02d}-{i:02d}"
                subj       = Subject(code=code, name=subj_name, branch=br, semester=sem, credits=3)
                db.add(subj)
                subj_map[(br, sem, i)] = subj
                idx += 1
    db.commit()

    created = 0
    used_names: set = set()

    for br in branches:
        for yr in years:
            current_sem = (yr) * 2  #even sem is current
            enrolled_sems = list(range(1, current_sem + 1))
            for n in range(per_group):
                gender = "M" if n < per_group // 2 else "F"

                for _ in range(20):
                    candidate = _random_name(gender, rng)
                    if candidate not in used_names:
                        used_names.add(candidate)
                        break
                else:
                    candidate = f"{_random_name(gender, rng)} {n}"

                father_name = f"{rng.choice(_MALE_FIRST)} {rng.choice(_LAST)}"
                address     = _random_address(rng)
                enroll_year = 2025 - yr + 1

                s = Student(
                    name             = candidate,
                    gender           = gender,
                    father_name      = father_name,
                    address          = address,
                    branch           = br,
                    year             = yr,
                    current_semester = current_sem,
                    enroll_year      = enroll_year,
                    cgpa             = 0.0,
                )
                db.add(s)
                db.commit()
                db.refresh(s)

                for sem in enrolled_sems:
                    sem_gpa_weight, sem_gpa_points = 0, 0
                    for i in range(1, 6):
                        subj = subj_map.get((br, sem, i))
                        if not subj:
                            continue
                        enr = Enrollment(student_id=s.id,subject_id=subj.id, active=(sem == current_sem))
                        db.add(enr)
                        db.commit()

                        mval          = int(max(0, min(100, rng.gauss(65, 12))))
                        grd, gp       = grade_for_marks(mval)
                        mk            = Mark(enrollment_id=enr.id, marks=mval,
                                            grade=grd, grade_point=gp, recorded_by=0)
                        db.add(mk)
                        db.commit()

                        sem_gpa_weight += subj.credits
                        sem_gpa_points += gp * subj.credits

                    sem_gpa = round((sem_gpa_points / sem_gpa_weight) if sem_gpa_weight else 0.0, 2)
                    sg      = SemesterGPA(student_id=s.id, semester=sem, gpa=sem_gpa)
                    db.add(sg)
                    db.commit()

                s.cgpa = _compute_cgpa(db, s.id)
                db.add(s)
                db.commit()
                created += 1

    print(f"[seed] Created {created} students across {len(branches)} branches × {len(years)} years.")
    return created


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true",
                        help="Create tables and seed 480 synthetic students")
    parser.add_argument("--reset", action="store_true",
                        help="Drop and recreate the configured database before seeding")
    args = parser.parse_args()

    if args.generate:
        if args.reset:
            reset_db()
        else:
            init_db()
        db = SessionLocal()
        try:
            generate_synthetic(db)
        finally:
            db.close()
    else:
        parser.print_help()
