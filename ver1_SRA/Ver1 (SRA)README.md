# Student Record Agent (SRA)

A LangChain-powered student records agent with FastAPI, MySQL, and Ollama (qwen2.5:3b).

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| MySQL | 8.0+ |
| Ollama | Latest |
| Node.js | 18+ (for React client) |

---

## 1. Pull the LLM

```bash
ollama pull qwen2.5:3b
ollama serve          # keep this running in a separate terminal
```

---

## 2. Set up MySQL

Open MySQL Workbench and create the database:

```sql
CREATE DATABASE student_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'sra_user'@'localhost' IDENTIFIED BY 'yourpassword';
GRANT ALL PRIVILEGES ON student_db.* TO 'sra_user'@'localhost';
FLUSH PRIVILEGES;
```

---

## 3. Configure environment

Create a `.env` file in the SRA root:

```env
DATABASE_URL=mysql+pymysql://sra_user:yourpassword@localhost:3306/student_db
JWT_SECRET=replace-with-a-strong-secret
```

---

## 4. Install Python dependencies

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
```

---

## 5. Seed the database

Run once to create tables and generate all 480 synthetic students:

```bash
python generate_students.py --generate
```

---

## 6. Run the SRA

```bash
uvicorn main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

---

## 7. Run the React client

```bash
cd sra-client
npm install
npm start         # runs on http://localhost:3000
```

---

## Default login credentials

| Role | Username | Password |
|---|---|---|
| Admin (Professor) | `admin` | `adminpass` |
| Assistant | `assistant` | `assistpass` |

---

## Project structure

```
SRA/
├── main.py               # FastAPI app + LangChain AgentExecutor
├── generate_students.py  # DB models, CRUD, synthetic data seed
├── requirements.txt
├── README.md
└── .env

sra-client/               # React frontend (separate repo)
└── src/
```

---

## Example queries (via /chat)

- "Show me details for student 42"
- "Search for students named Priya"
- "What is the average CGPA for CSE-S01-03 in semester 1?"
- "Update the address for student 15 to 'Plot 9, Madhapur, Hyderabad'"
- "List all students in subject ECE-S02-01"