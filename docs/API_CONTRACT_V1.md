# API Contract V1 (Stable for UI)

Version: `v1`

Scope: contrato HTTP para `job_search` + `gen-cv`, basado en `src/structured_search/api/app.py`.

Fuente canónica machine-readable: `docs/openapi_v1.json` (generado con `structured-search tools export-openapi`).
Tipos UI generados: `ui/lib/generated/api-types.ts` (generado con `structured-search tools export-ui-types`).

## Base URL
- Local FastAPI: `http://localhost:8000/v1`
- UI mock fallback: `/api/mock/v1`

## Convenciones
- Content type request/response: `application/json`.
- Errores de recurso no encontrado: `404` con `{ "detail": "..." }`.
- Errores de validación de body (FastAPI/Pydantic): `422` estándar FastAPI.
- Guardado de bundle devuelve `200` con `ok=true|false` (errores de dominio en payload, no en status code).
- En `gen-cv`, errores de validación/dominio usan status HTTP (`422`/`503`), no `200` con payload de error.
- OpenAPI declara explícitamente errores de runtime para `run` y `gen-cv` (`404`/`500`/`503`).

## Estados UX recomendados
- `draft`, `valid`, `invalid`, `running`, `done`, `failed`

## Endpoints

### 1) GET `/job-search/profiles`
Lista perfiles disponibles.

Response `200`
```json
[
  {
    "id": "profile_1",
    "name": "Senior Python Engineer",
    "updated_at": "2026-02-22T04:38:01.123456"
  }
]
```

---

### 2) GET `/job-search/profiles/{profile_id}/bundle`
Carga bundle completo editable.

Response `200`
```json
{
  "profile_id": "profile_1",
  "constraints": { "domain": "job_search", "must": [], "prefer": [], "avoid": [] },
  "task": { "gates": {}, "soft_scoring": {} },
  "task_config": { "agent_name": "..." },
  "user_profile": { "role_focus": ["Senior Python Engineer"] },
  "domain_schema": { "type": "object" },
  "result_schema": { "type": "object" }
}
```

Errores:
- `404` si el perfil no existe.

---

### 3) PUT `/job-search/profiles/{profile_id}/bundle`
Valida y guarda bundle.

Request
```json
{
  "profile_id": "profile_1",
  "constraints": { "domain": "job_search", "must": [], "prefer": [], "avoid": [] },
  "task": { "gates": {}, "soft_scoring": {} },
  "task_config": {},
  "user_profile": {},
  "domain_schema": {},
  "result_schema": {}
}
```

Response `200` (válido, con warnings opcionales)
```json
{
  "ok": true,
  "version": "2026-02-22T05:01:12.332191",
  "errors": [
    {
      "path": "constraints.must[1].field",
      "code": "unknown_field_path",
      "message": "'totally_fake_field' is not a declared field on JobPosting — the scorer will score 0 for this rule",
      "severity": "warning"
    }
  ]
}
```

Response `200` (inválido, bloquea save)
```json
{
  "ok": false,
  "errors": [
    {
      "path": "constraints.must.0.value",
      "code": "list_type",
      "message": "Input should be a valid list",
      "severity": "error"
    },
    {
      "path": "task.gates",
      "code": "required_field_missing",
      "message": "task must contain 'gates'",
      "severity": "error"
    }
  ]
}
```

Notas:
- `warning` no bloquea guardado.
- `error` sí bloquea guardado.

---

### 4) POST `/job-search/prompt/generate`
Genera prompt por step.

Request
```json
{
  "profile_id": "profile_1",
  "step": "S3_execute"
}
```

Response `200`
```json
{
  "profile_id": "profile_1",
  "step": "S3_execute",
  "prompt": "...",
  "constraints_embedded": true,
  "prompt_hash": "sha256:5f1a..."
}
```

Errores:
- `404` si perfil inexistente.

---

### 5) POST `/job-search/jsonl/validate`
Parseo tolerante + validación de esquema.

Request
```json
{
  "profile_id": "profile_1",
  "raw_jsonl": "{\"id\":\"1\",...}\nthis is broken\n{\"bad\":true}"
}
```

Response `200`
```json
{
  "valid_records": [
    { "id": "1", "company": "Acme", "title": "Engineer" }
  ],
  "invalid_records": [
    {
      "line": 2,
      "error": "Expecting value",
      "raw": "this is broken",
      "kind": "json_parse"
    },
    {
      "line": 3,
      "error": "[...]",
      "raw": "{\"bad\":true}",
      "kind": "schema_validation"
    }
  ],
  "metrics": {
    "total_lines": 3,
    "json_valid_lines": 2,
    "schema_valid_records": 1,
    "invalid_lines": 2
  }
}
```

---

### 6) POST `/job-search/run/validate`
Preflight de `/run` sin ejecutar scoring real.

Usa el mismo payload que `/job-search/run` y valida end-to-end:
- perfil y bundle cargables,
- constraints + task config válidos para scoring,
- schema de `records`,
- I/O de snapshot (probe write/delete temporal).

Request
```json
{
  "profile_id": "profile_1",
  "records": [
    { "id": "1", "company": "Acme", "title": "Engineer" }
  ],
  "require_snapshot": true
}
```

Response `200`
```json
{
  "ok": true,
  "profile_id": "profile_1",
  "total_records": 1,
  "valid_records": 1,
  "invalid_records": 0,
  "errors": [],
  "checks": {
    "profile_exists": true,
    "constraints_valid": true,
    "scoring_config_valid": true,
    "all_records_schema_valid": true,
    "snapshot_io_checked": true,
    "snapshot_io_writable": true
  },
  "snapshot_probe_dir": "runs/_validate-profile_1-abcd1234",
  "snapshot_probe_error": null
}
```

Notas:
- `ok=false` cuando `require_snapshot=true` y el probe de snapshot falla.
- Si `require_snapshot=false`, un fallo de I/O de snapshot se refleja en `checks`/`snapshot_probe_error`, pero `ok` puede seguir en `true` (mismo comportamiento tolerante de `/run`).

Errores relevantes:
- `404`: perfil inexistente.
- `422`: request inválido o task config inválida para scoring.

---

### 7) POST `/job-search/run`
Scoring sobre `records` (normalmente salida válida de validate).

Request
```json
{
  "profile_id": "profile_1",
  "records": [
    { "id": "1", "company": "Acme", "title": "Engineer" }
  ],
  "require_snapshot": false
}
```

Response `200`
```json
{
  "run_id": "profile_1-20260222-050500-a1b2c3",
  "profile_id": "profile_1",
  "scored_records": [
    {
      "id": "1",
      "company": "Acme",
      "title": "Engineer",
      "modality": "remote",
      "seniority": { "level": "senior" },
      "score": 7.25,
      "gate_passed": true,
      "gate_failures": [],
      "anomalies": []
    }
  ],
  "metrics": {
    "loaded": 1,
    "processed": 1,
    "skipped": 0,
    "started_at": "2026-02-22T05:05:00.123456",
    "finished_at": "2026-02-22T05:05:00.223456"
  },
  "errors": [],
  "snapshot_dir": "runs/profile_1-20260222-050500-a1b2c3",
  "snapshot_status": "written",
  "snapshot_error": null
}
```

Notas de snapshot:
- `snapshot_status="written"`: snapshot persistido.
- `snapshot_status="failed"`: snapshot no persistido (si `require_snapshot=true`, el run falla con `500`).

Errores relevantes:
- `404`: perfil inexistente.
- `422`: request inválido o task config inválida para scoring.
- `500`: fallo de ejecución (ej: `require_snapshot=true` y no se pudo persistir snapshot).

---

### 8) POST `/gen-cv`
Genera CV markdown + JSON.

Request
```json
{
  "profile_id": "profile_1",
  "job": {
    "id": "job-001",
    "title": "Senior Engineer",
    "company": "Acme",
    "stack": ["Python", "FastAPI"],
    "description": "..."
  },
  "candidate_profile": {
    "id": "candidate_p2",
    "name": "Jane Doe",
    "seniority": "senior",
    "tech_stack": {
      "languages": ["Python"],
      "frameworks": ["FastAPI"]
    },
    "spoken_languages": ["es", "en"],
    "availability_days": 30
  },
  "selected_claim_ids": ["cl_1", "cl_4"],
  "llm_model": "mistral",
  "allow_mock_fallback": true
}
```

`candidate_profile`:
- `seniority` es obligatorio y debe ser `string` no vacío.
- `tech_stack` (si se envía) debe ser objeto con `languages/frameworks/platforms/domains`.
- si falta `id`, se autogenera como `{profile_id}_candidate`.
- `llm_model` es opcional; resolución por prioridad:
  1) `llm_model` del request,
  2) `STRUCTURED_SEARCH_LLM_MODEL`,
  3) `OLLAMA_MODEL`,
  4) `bundle.task_config.runtime.llm.model`,
  5) fallback final `"lfm2.5-thinking"`.

Response `200`
```json
{
  "cv_markdown": "# Generated CV\n\n## Summary\n...",
  "generated_cv_json": {
    "title": "Generated CV",
    "summary": "...",
    "highlights": ["..."],
    "grounded_claim_ids": ["cl_1"]
  },
  "model_info": {
    "model": "lfm2.5-thinking",
    "grounded_claim_count": 1,
    "profile_id": "profile_1",
    "markdown_hash": "c15d...",
    "fallback_used": false
  }
}
```

Errores relevantes:
- `404`: perfil inexistente.
- `422`: `job` o `candidate_profile` inválidos.
- `503`: proveedor de generación no disponible.

---

## Convención de campos
Todos los request payloads y response payloads del API usan `snake_case`.

## Configuración UI -> backend real
En `ui/.env.local`:
```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000/v1
```

Si no se define, la UI usa mock local en `/api/mock/v1`.
