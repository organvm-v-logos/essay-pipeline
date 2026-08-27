# Essay Pipeline API Documentation

Welcome to the Essay Pipeline API. This REST API provides programmatic access to the ORGAN-V essay automation engine, allowing you to validate frontmatter schemas, draft essays using LLMs, and access our schema-enforced template library.

## Authentication

The Essay Pipeline API uses License Keys for authentication. You must include your license key in the `Authorization` header as a Bearer token for every request. 

```http
Authorization: Bearer EPK1.XXXX.YYYY...
```

Your license key determines your access tier (Free vs. Premium). To purchase a license key or manage your existing keys, visit our billing portal.

## Base URL

All API requests should be made to:

```text
https://api.organvm.com/v1/essay-pipeline
```

---

## Endpoints

### 1. List Templates

Retrieve a catalog of available schema-enforced essay templates.

**Endpoint:** `GET /templates`

**Headers:**
- `Authorization: Bearer <your-license-key>`

**Response (200 OK):**
```json
{
  "templates": [
    {
      "id": "field-note",
      "tier": "free",
      "description": "Short, single-claim observations"
    },
    {
      "id": "case-study",
      "tier": "premium",
      "description": "Documenting a piece of work end to end"
    }
  ]
}
```

### 2. Get Template Content

Retrieve the raw markdown scaffold for a specific template. Premium templates require a valid `premium-bundle` or `premium-single` license key.

**Endpoint:** `GET /templates/{template_id}`

**Headers:**
- `Authorization: Bearer <your-license-key>`

**Path Parameters:**
- `template_id` (string): The ID of the template (e.g., `case-study`).

**Response (200 OK):**
```json
{
  "id": "case-study",
  "content": "---\nlayout: post\ntitle: \"{{TITLE}}\"\ncategory: \"{{CATEGORY}}\"\n...\n---\n\n## Context\n\n{{CONTEXT_AND_BACKGROUND}}"
}
```

**Response (403 Forbidden):**
```json
{
  "error": "LOCKED",
  "message": "This template requires a premium license. Visit the billing portal to upgrade."
}
```

### 3. Validate Essay

Validate an essay's markdown frontmatter against the canonical editorial schema to ensure it will pass the publication pipeline.

**Endpoint:** `POST /validate`

**Headers:**
- `Authorization: Bearer <your-license-key>`
- `Content-Type: application/json`

**Request Body:**
```json
{
  "content": "---\nlayout: post\ntitle: My Essay\ndate: 2026-06-20\n...\n---\nBody text."
}
```

**Response (200 OK - Valid):**
```json
{
  "valid": true,
  "errors": []
}
```

**Response (400 Bad Request - Invalid):**
```json
{
  "valid": false,
  "errors": [
    "Missing required frontmatter key: 'category'",
    "Invalid type for 'reading_time': expected integer."
  ]
}
```

### 4. Generate Essay Draft

Generate a draft essay from a specific topic using our intelligence engine and LLM pipeline. The generated draft will adhere strictly to the requested template's schema.

**Endpoint:** `POST /draft`

**Headers:**
- `Authorization: Bearer <your-license-key>`
- `Content-Type: application/json`

**Request Body:**
```json
{
  "topic": "The Role of Automation in Infrastructure",
  "template_id": "argument-essay",
  "instructions": "Focus on CI/CD pipelines and deployment safety."
}
```

**Response (200 OK):**
```json
{
  "draft_id": "draft_abc123",
  "content": "---\nlayout: post\ntitle: \"The Role of Automation in Infrastructure\"\ncategory: \"Infrastructure\"\n...\n---\n\n## Introduction\n\nAutomation forms the backbone..."
}
```

---

## Error Handling

The API returns standard HTTP status codes to indicate the success or failure of an API request.

- `200 OK`: Request succeeded.
- `400 Bad Request`: Invalid parameters or validation failure.
- `401 Unauthorized`: Missing or invalid License Key.
- `403 Forbidden`: Valid License Key provided, but insufficient tier (e.g., trying to access a premium template with a free license).
- `429 Too Many Requests`: Rate limit exceeded.
- `500 Internal Server Error`: An unexpected internal error occurred.
