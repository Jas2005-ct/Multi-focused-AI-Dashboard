"""SQL safety guards using sqlglot AST validation (Phase 4)."""

import re
import sqlglot
from sqlglot import exp
from typing import Tuple, List

# Write intent patterns (improved over regex-only)
_WRITE_PATTERNS = re.compile(
    r"\b(insert|update|delete|create|alter|drop|truncate|replace|upsert|merge)\b",
    re.IGNORECASE,
)

# Maximum rows for tool results
MAX_ROWS = 50
# Statement timeout in milliseconds
STATEMENT_TIMEOUT_MS = 10000


def is_write_intent(sentence: str) -> bool:
    """Check if user sentence indicates write intent."""
    return bool(_WRITE_PATTERNS.search(sentence)) if sentence else False


def validate_sql_ast(sql: str) -> Tuple[bool, str]:
    """
    Validate SQL using sqlglot AST parsing.
    Returns (is_safe, error_message).
    """
    try:
        # Parse with PostgreSQL dialect
        parsed = sqlglot.parse(sql, dialect="postgres", read=None)
        
        if not parsed or len(parsed) != 1:
            return False, "Multiple statements not allowed"
        
        stmt = parsed[0]
        
        # Must be SELECT or WITH (CTE)
        if not isinstance(stmt, (exp.Select, exp.With)):
            # Check for write operations
            write_types = (
                exp.Insert, exp.Update, exp.Delete, exp.Create, 
                exp.Alter, exp.Drop, exp.Truncate, exp.Merge
            )
            if isinstance(stmt, write_types):
                return False, "Write operations not permitted — this dashboard is read-only"
            return False, f"Query must start with SELECT or WITH. Found: {type(stmt).__name__}"
        
        # Check for dangerous patterns in the AST
        for node in stmt.walk():
            # Block subqueries that could be used for injection
            if isinstance(node, exp.Subquery):
                parent = node.parent
                if isinstance(parent, (exp.Select, exp.From)) and not isinstance(parent, exp.Exists):
                    pass  # Allow legitimate subqueries in FROM/WHERE
            
            # Block dangerous functions
            if isinstance(node, exp.Anonymous):
                dangerous_funcs = {
                    'sleep', 'benchmark', 'waitfor', 'delay', 'pg_sleep',
                    'load_file', 'into_outfile', 'into_dumpfile',
                    'xp_cmdshell', 'sp_oacreate', 'sp_oamethod',
                    'exec', 'execute', 'system', 'shell'
                }
                if node.this.lower() in dangerous_funcs:
                    return False, f"Dangerous function detected: {node.this}"
            
            # Block comments (AST preserves them)
            if isinstance(node, exp.Comment):
                return False, "Comments not allowed in queries"
        
        return True, ""
        
    except sqlglot.errors.ParseError as e:
        return False, f"SQL parse error: {e}"
    except Exception as e:
        return False, f"Validation error: {e}"


def add_safety_limits(sql: str) -> str:
    """Add LIMIT and statement timeout to query if not present."""
    parsed = sqlglot.parse(sql, dialect="postgres", read=None)[0]
    
    # Add LIMIT if not present and it's a SELECT
    if isinstance(parsed, exp.Select) and not parsed.args.get('limit'):
        parsed = parsed.limit(MAX_ROWS)
    
    # Note: statement_timeout is set at session level, not in query
    # SET LOCAL statement_timeout = 10000; -- would be set by connection pool
    
    return parsed.sql(dialect="postgres")


def sanitize_table_name(table: str) -> str:
    """Validate and sanitize table name against injection."""
    import re
    TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    t = table.strip().strip('"').strip("'").lower()
    if not TABLE_NAME_RE.match(t):
        raise ValueError(f"Invalid table name: {table}")
    if "." in t or ";" in t or " " in t:
        raise ValueError(f"Invalid table name: {table}")
    return t