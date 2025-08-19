# main.py
import ollama   
import re, os

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder


from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP

from typing import Any, Dict, List

from db.database import engine
from sqlalchemy import text


mcp = FastMCP("MCP LLM DB (Postgres + Ollama)")

# --- FastAPI setup ---
templates = Jinja2Templates(directory="templates")

FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\b", re.IGNORECASE)

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")  # change to the model you pulled


@mcp.tool
def hello(name: str) -> str:
    return f"Hello, {name}!"

@mcp.custom_route("/health", methods=["GET"])
async def health(_req: Request):
    return JSONResponse({"ok": True})

# Build the MCP ASGI app (streamable HTTP)
mcp_app = mcp.streamable_http_app()

# Important: give FastAPI MCP's lifespan so sessions are managed correctly
app = FastAPI(lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)

# dev run: uvicorn main:app --reload

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/ask")
async def ask(question: str = Form(...)):
    """
    API endpoint used by the HTML page.
    Uses the internal Python implementation (not the MCP tool object).
    """
    result = query_db_impl(question)  # <-- call the real function
    return JSONResponse(content=jsonable_encoder(result))

def _strip_code_fences(s: str) -> str:
    # Remove ```sql ... ``` or ``` ... ```
    return re.sub(r"^```(?:sql)?\s*|\s*```$", "", s.strip(), flags=re.IGNORECASE | re.MULTILINE)

def _clean_and_validate_sql(sql: str) -> str:
    """
    Keep this defensive: require SELECT-only, single statement, no forbidden keywords.
    """
    sql = _strip_code_fences(sql).strip().rstrip(";").strip()

    # Must start with SELECT
    if not sql.lower().startswith("select"):
        raise ValueError(f"Only SELECT queries are allowed. Got: {sql[:40]}...")

    # No forbidden keywords anywhere
    if FORBIDDEN.search(sql):
        raise ValueError("Detected forbidden SQL keyword (INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/CREATE).")

    # Single statement check: disallow any stray semicolons
    if ";" in sql:
        raise ValueError("Multiple statements are not allowed.")

    return sql


def _prompt_for_schema(question: str) -> str:
    """
    Schema + relationships + few-shot examples
    to guide Ollama into writing better SQL.
    """
    return f"""
        You are an expert PostgreSQL SQL assistant.

        Rules:
        - Database is PostgreSQL.
        - The schema is already provided. Do not use DESCRIBE, SHOW TABLES, or \d commands.
        - Only generate valid SELECT queries over the following tables:

        Table: users
        - id SERIAL PRIMARY KEY
        - name VARCHAR(100) NOT NULL
        - email VARCHAR(100) UNIQUE NOT NULL
        - created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        Table: products
        - id SERIAL PRIMARY KEY
        - name VARCHAR(100) NOT NULL
        - description TEXT
        - price NUMERIC(10,2) NOT NULL
        - created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        Table: inventories
        - product_id INT PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE
        - quantity INT NOT NULL DEFAULT 0
        - updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        Table: orders
        - id SERIAL PRIMARY KEY
        - user_id INT REFERENCES users(id) ON DELETE CASCADE
        - order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        - status VARCHAR(20) DEFAULT 'pending'

        Table: order_items
        - id SERIAL PRIMARY KEY
        - order_id INT REFERENCES orders(id) ON DELETE CASCADE
        - product_id INT REFERENCES products(id) ON DELETE CASCADE
        - quantity INT NOT NULL
        - price NUMERIC(10,2) NOT NULL  -- snapshot of product price
        - UNIQUE(order_id, product_id)

        ---
        Relationships:
        - orders.user_id → users.id
        - order_items.order_id → orders.id
        - order_items.product_id → products.id
        - inventories.product_id → products.id

        ---
        Examples:

        Q: "List top 5 products by price"
        SQL:
        SELECT name, price
        FROM products
        ORDER BY price DESC
        LIMIT 5;

        Q: "Which 5 products generated the highest total sales?"
        SQL:
        SELECT p.name, SUM(oi.price * oi.quantity) AS total_sales
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        GROUP BY p.name
        ORDER BY total_sales DESC
        LIMIT 5;

        Q: "Which user placed the most orders?"
        SQL:
        SELECT u.name, COUNT(o.id) AS total_orders
        FROM users u
        JOIN orders o ON o.user_id = u.id
        GROUP BY u.name
        ORDER BY total_orders DESC
        LIMIT 1;

        ---
        Task:
        Write a PostgreSQL **SELECT-only** SQL query to answer the question below.
        - Only use columns that exist in the schema.
        - Use proper JOINs when referencing multiple tables.
        - Do not include any explanation or commentary.
        - Output **only the SQL** (no backticks).

        Instructions:
        - Always write **SELECT-only** queries.
        - Never attempt to inspect the schema using DESCRIBE, SHOW, or \d.
        - If unsure, return the closest meaningful SELECT instead.
        - Prefer joining tables when needed, but stick to the schema above.

        Question: "{question}"
        """.strip()


# -----------------------------
# Core implementation (callable from API and MCP tool)
# -----------------------------
def query_db_impl(question: str) -> Dict[str, Any]:
    """
    1) Ask Ollama to generate a SELECT-only SQL query for our schema
    2) Validate the SQL defensively
    3) Execute it and return rows
    """
    prompt = _prompt_for_schema(question)

    try:
        chat = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_sql = chat["message"]["content"].strip()
    except Exception as e:
        return {"ok": False, "error": f"Ollama call failed: {e}"}

    try:
        sql = _clean_and_validate_sql(raw_sql)
    except Exception as e:
        return {"ok": False, "error": f"SQL validation failed: {e}", "llm_sql": raw_sql}

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            rows: List[Dict[str, Any]] = [dict(row._mapping) for row in result]
        return {"ok": True, "sql": sql, "rows": rows}
    except Exception as e:
        return {"ok": False, "error": f"DB execution failed: {e}", "sql": sql}



@mcp.tool
def query_db(question: str) -> str:
    return query_db_impl(question)
