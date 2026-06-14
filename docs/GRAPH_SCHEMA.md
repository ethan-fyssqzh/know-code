# Graph Schema

The graph is stored as newline-delimited `GraphFact` records.

```json
{
  "subject": "repo:h5:file:src/subscription.ts",
  "predicate": "calls_api",
  "object": "api:POST /subscriptions/cancel",
  "evidence": [
    {
      "repo": "h5",
      "commit": "abc123",
      "file": "src/subscription.ts",
      "line": 12,
      "snippet": "request.post(\"/subscriptions/cancel\", {})"
    }
  ],
  "confidence": 0.84,
  "source": "web",
  "repo": "h5",
  "commit": "abc123"
}
```

## Common Entities

- `repo:<name>`
- `repo:<name>:file:<path>`
- `module:<repo>:<name>`
- `screen:<repo>:<name>`
- `route:<repo>:<path>`
- `operation:<name>`
- `api:<METHOD> <PATH>`
- `rpc:<package.Service.Method>`
- `event:<topic>`
- `capability:<id>:<slug>`

## Common Predicates

- `is_repository`
- `has_language`
- `uses_build_system`
- `defines_module`
- `belongs_to_module`
- `defines_screen`
- `defines_route`
- `provides_operation`
- `calls_operation`
- `provides_api`
- `calls_api`
- `provides_rpc`
- `calls_rpc`
- `emits_event`
- `consumes_event`
- `capability_has_file`
- `capability_has_module`
- `capability_has_operation`
- `capability_depends_on`

