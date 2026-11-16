"""Request and response models for db-service (the API contract is in db-service/README.md).

Pipeline step: infrastructure. All endpoints use these models.
"""

from typing import Any

from pydantic import BaseModel


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool


class ForeignKeyInfo(BaseModel):
    columns: list[str]
    ref_table: str
    ref_columns: list[str]


class TableInfo(BaseModel):
    name: str
    description: str | None = None
    columns: list[ColumnInfo]
    primary_key: list[str]
    foreign_keys: list[ForeignKeyInfo]


class SchemaRequest(BaseModel):
    tables: list[str]
    fk_depth: int = 1


class SchemaResponse(BaseModel):
    dialect: str
    tables: list[TableInfo]
    discovered_tables: list[str]
    not_found: list[str]


class PlanRequest(BaseModel):
    sql: str


class PlanResponse(BaseModel):
    valid: bool
    error: str | None = None
    estimated_cost: float | None = None
    estimated_rows: int | None = None
    plan: dict[str, Any] | None = None


class QueryRequest(BaseModel):
    sql: str
    max_rows: int | None = None


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int
