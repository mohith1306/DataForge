# DataForge Enterprise API Documentation

## Overview

This document covers all enterprise API endpoints added in Phases 1-5 of the DataForge Enterprise MVP.

**Base URL:** `http://localhost:8000/api`

**Authentication:** All enterprise endpoints require authentication via API key or JWT token.

---

## Table of Contents

1. [Authentication](#authentication)
2. [AI Endpoints](#ai-endpoints)
3. [Reliability Graph](#reliability-graph)
4. [Metadata Engine](#metadata-engine)
5. [Incident Intelligence](#incident-intelligence)
6. [API Gateway](#api-gateway)

---

## Authentication

### Create API Key
```
POST /api/auth/api-keys
```

**Request:**
```json
{
  "name": "my-api-key",
  "scopes": ["read", "write", "admin"]
}
```

**Response:**
```json
{
  "api_key": "df_abc123...",
  "key_id": "key_123",
  "name": "my-api-key",
  "scopes": ["read", "write", "admin"]
}
```

### Get Current User
```
GET /api/auth/me
```

**Headers:**
- `X-API-Key: <api_key>` or `Authorization: Bearer <token>`

---

## AI Endpoints

### Risk Classification
```
POST /api/ai/risk/classify
```

**Request:**
```json
{
  "action_type": "database_migration",
  "target": "production_db",
  "parameters": {}
}
```

**Response:**
```json
{
  "risk_level": "high",
  "confidence": 0.85,
  "reasoning": "Production database modification"
}
```

### Get Autonomy Level
```
POST /api/ai/autonomy/level
```

**Request:**
```json
{
  "risk_level": "high"
}
```

### Create Agent Run
```
POST /api/ai/agents/run
```

**Request:**
```json
{
  "incident_id": "inc_123",
  "agent_type": "diagnosis",
  "input": {
    "error_message": "Connection timeout"
  }
}
```

### Get Agent Run
```
GET /api/ai/agents/run/{run_id}
```

### List Agent Runs
```
GET /api/ai/agents/runs?incident_id=inc_123
```

### Get Agent Trace
```
GET /api/ai/agents/run/{run_id}/trace
```

---

## Reliability Graph

### Get Full Graph
```
GET /api/graph/full
```

**Query Parameters:**
- `tenant_id` (optional) - Filter by tenant

**Response:**
```json
{
  "nodes": [...],
  "edges": [...],
  "metadata": {}
}
```

### Add Node
```
POST /api/graph/nodes
```

**Request:**
```json
{
  "node_id": "node_123",
  "node_type": "table",
  "name": "users",
  "metadata": {}
}
```

### Add Edge
```
POST /api/graph/edges
```

**Request:**
```json
{
  "source_node_id": "node_123",
  "target_node_id": "node_456",
  "edge_type": "depends_on",
  "metadata": {}
}
```

### Get Node Status
```
GET /api/graph/nodes/{node_id}/status
```

### Get Node History
```
GET /api/graph/nodes/{node_id}/history?days=7
```

### Get Impact Path
```
GET /api/graph/impact/{source_node_id}/{target_node_id}
```

---

## Metadata Engine

### Schema Discovery

#### Discover Schema from Data
```
POST /api/metadata/schemas/discover
```

**Request:**
```json
{
  "name": "users_table",
  "source_id": "postgres_prod",
  "data": [
    {"id": 1, "name": "Alice", "email": "alice@example.com"},
    {"id": 2, "name": "Bob", "email": "bob@example.com"}
  ],
  "sample_size": 100
}
```

**Response:**
```json
{
  "schema": {
    "id": "sch_abc123",
    "name": "users_table",
    "source_type": "dict",
    "source_id": "postgres_prod",
    "fields": [
      {"name": "id", "field_type": "integer", "nullable": false},
      {"name": "name", "field_type": "string", "nullable": false},
      {"name": "email", "field_type": "string", "nullable": false}
    ],
    "row_count": 2
  }
}
```

#### List Schemas
```
GET /api/metadata/schemas
```

#### Get Schema
```
GET /api/metadata/schemas/{schema_id}
```

#### Compare Schemas
```
GET /api/metadata/schemas/compare/{schema_id1}/{schema_id2}
```

**Response:**
```json
{
  "common_fields": ["id", "name"],
  "only_in_schema1": ["email"],
  "only_in_schema2": ["phone"],
  "type_mismatches": [],
  "similarity": 0.67
}
```

### Lineage Tracking

#### Add Lineage Node
```
POST /api/metadata/lineage/nodes
```

**Request:**
```json
{
  "name": "users_table",
  "node_type": "table",
  "source_id": "postgres_prod",
  "metadata": {"team": "data-engineering"}
}
```

#### Add Lineage Edge
```
POST /api/metadata/lineage/edges
```

**Request:**
```json
{
  "source_node_id": "node_123",
  "target_node_id": "node_456",
  "edge_type": "reads_from",
  "transformation": "SELECT * FROM users WHERE active = true"
}
```

#### Get Upstream Nodes
```
GET /api/metadata/lineage/upstream/{node_id}?depth=3
```

#### Get Downstream Nodes
```
GET /api/metadata/lineage/downstream/{node_id}?depth=3
```

#### Get Blast Radius
```
GET /api/metadata/lineage/blast-radius/{node_id}
```

**Response:**
```json
{
  "source_node": "node_123",
  "directly_affected": 2,
  "total_downstream": 5,
  "risk_score": 0.5
}
```

#### Get Lineage Summary
```
GET /api/metadata/lineage/summary
```

#### Detect Cycles
```
GET /api/metadata/lineage/cycles
```

---

## Incident Intelligence

### Correlation

#### Correlate Incidents
```
POST /api/intelligence/correlate
```

**Request:**
```json
{
  "incidents": [
    {"id": "i1", "affected_services": ["api-gateway"], "error_signatures": ["timeout"]},
    {"id": "i2", "affected_services": ["api-gateway"], "error_signatures": ["timeout"]}
  ],
  "strategy": "service"
}
```

**Strategies:** `service`, `error_type`, `time_window`, `failure_dna`, `tag`

#### List Correlations
```
GET /api/intelligence/correlations
```

#### Get Correlation
```
GET /api/intelligence/correlations/{correlation_id}
```

#### Get Correlations for Incident
```
GET /api/intelligence/correlations/incident/{incident_id}
```

### Deduplication

#### Check for Duplicate
```
POST /api/intelligence/deduplicate
```

**Request:**
```json
{
  "incident": {
    "id": "i_new",
    "title": "Database timeout",
    "error_signatures": ["ConnectionRefused"],
    "affected_services": ["api"]
  },
  "strategy": "signature_match"
}
```

**Strategies:** `exact_match`, `fuzzy_match`, `signature_match`, `dna_match`

**Response:**
```json
{
  "is_duplicate": true,
  "result": {
    "original_incident_id": "i_existing",
    "similarity_score": 0.95
  }
}
```

#### Get Deduplication Stats
```
GET /api/intelligence/deduplication/stats
```

### Blast Radius

#### Calculate Blast Radius
```
POST /api/intelligence/blast-radius
```

**Request:**
```json
{
  "incident": {
    "id": "inc_123",
    "affected_services": ["auth-service", "api-gateway"]
  },
  "affected_services": ["auth-service", "api-gateway"]
}
```

**Response:**
```json
{
  "blast_radius": {
    "risk_score": 0.7,
    "severity": "high",
    "affected_entities": {
      "services": ["auth-service", "api-gateway", "user-service"],
      "teams": ["platform", "backend"]
    },
    "recommendations": [
      "Initiate incident response procedure",
      "Notify affected team leads"
    ]
  }
}
```

#### Register Entity
```
POST /api/intelligence/blast-radius/entities
```

**Request:**
```json
{
  "entity_id": "auth-service",
  "entity_type": "service",
  "dependencies": ["user-service", "database"],
  "metadata": {"team": "platform"}
}
```

#### Get Dependencies
```
GET /api/intelligence/blast-radius/dependencies/{entity_id}
```

#### Get Dependents
```
GET /api/intelligence/blast-radius/dependents/{entity_id}
```

#### Get Blast Radius Stats
```
GET /api/intelligence/blast-radius/stats
```

---

## API Gateway

The API Gateway provides rate limiting, request validation, and audit logging for all endpoints.

### Rate Limiting

Rate limits are applied automatically based on client identification (API key, auth token, or IP address).

**Headers returned:**
- `X-RateLimit-Limit` - Maximum requests allowed
- `X-RateLimit-Remaining` - Remaining requests in window
- `X-RateLimit-Reset` - Unix timestamp when window resets
- `Retry-After` - Seconds to wait (only on 429)

**Default limits:**
- 60 requests per minute
- 1000 requests per hour
- 10000 requests per day

### Request Validation

Requests are validated for:
- HTTP method allowed
- Path patterns (blocked patterns)
- SQL injection attempts
- XSS attacks
- Body size limits (10MB)
- Content-Type validation

### Audit Logging

All API requests are logged with:
- Timestamp
- Client identifier
- Method and path
- Status code
- Duration
- IP address and user agent

---

## Error Responses

All endpoints return standard error responses:

```json
{
  "detail": "Error message"
}
```

**HTTP Status Codes:**
- `400` - Bad Request / Validation Error
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `429` - Rate Limit Exceeded
- `500` - Internal Server Error
