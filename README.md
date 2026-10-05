# Student Record Agent (SRA)

A natural-language agent for querying student records. Instead of clicking through portals, you ask questions like *"Which CSE students have attendance below 75%?"* and the agent answers by calling tools over a records backend.

I built it across several iterations, using each one to fix what the previous one got wrong, and to learn where tool-calling agents break in practice.

## Versions

| Version | What changed |
|---|---|
| **v1** | Full stack built from scratch: FastAPI, LangChain, MySQL, React. First agent with tool calling. |
| **v2** | Added JWT authentication, role-based access control and audit logging, plus a React client (`v2_SRA-client2`). |
| **v2.5** | Separated the records backend (`V2.5_SRS`) from the agent (`ver2.5 SRA`) and added an evaluation harness (`Eval/`) using DeepEval. |

## Repository layout

```
V2.5_SRS/          Student Records Service: backend serving student data
ver2.5 SRA/        The agent
  Agent.py           Agent logic and tool definitions
  Auth.py            Authentication
  main.py            API entry point
  Eval/              DeepEval test cases and evaluation scripts
v2_SRA-client2/    React client for the agent
```

## Key design decision: fewer tools

In v1 the agent had 19 tools running on a small local model (qwen2.5:3b), and it often picked the wrong one. A bigger model or longer prompts would have hidden the problem rather than fixed it. I merged overlapping tools down to about 8, which reduced the wrong-tool selection I was seeing.

The takeaway: an agent's tool surface is a design decision. A small, well-described set of tools beats a large one, especially on small models.

## Evaluation

I use DeepEval to measure tool-selection accuracy, faithfulness and task completion against a dataset of test queries (`Eval/`). The evaluation work is ongoing.

## Setup

```bash
pip install -r requirements.txt
python generate_students.py        # generate sample student data
python V2.5_SRS/srs_main.py        # start the records service
python "ver2.5 SRA/main.py"        # start the agent
```

Create a `.env` file with your own keys. Never commit real keys.

## Tech stack

Python · FastAPI · LangChain · MySQL · React · JWT · DeepEval

## Future work

**1. Evaluation-driven development.**
Right now the evals tell me how the agent performs. The next step is to make them drive changes. I plan to:
- Expand the test set with failure cases, such as ambiguous queries, fields that don't exist, and permission-restricted requests.
- Track pass rates across versions so each change (a prompt edit, a tool merge, a model swap) is judged by measured tool-selection accuracy, faithfulness and task completion rather than by trying a few queries by hand.
- Run the evals automatically on every change, so a regression gets caught before it ships.

**2. Observability.**
Evals only show that something failed. Tracing shows why. I plan to add Langfuse tracing to the agent so that every request records the model's reasoning steps, which tool it chose, the arguments it passed, latency and token cost. When an eval fails, I can then open the exact trace and see where the agent went wrong, instead of guessing.

**3. MCP server for the records tools.**
Today the agent talks to the records service through custom endpoints, which ties the tools to this one agent. I plan to expose them through an MCP (Model Context Protocol) server, using the Python MCP SDK. This would:
- Give the tools a standard interface any MCP-compatible agent or client can use.
- Separate tool definitions from agent logic, so I can change one without touching the other.
- Make it easier to test the tools on their own, for example with MCP Inspector.

The evals from (1) would be my safety net for this migration: if tool-selection accuracy drops after the switch, I'll know straight away.
