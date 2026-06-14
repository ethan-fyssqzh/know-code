# Custom Framework Adapters

Many companies hide HTTP/RPC calls behind internal frameworks. Know Code lets
you add regex/annotation adapters without changing source code.

Example:

```json
{
  "adapters": [
    {
      "name": "company-biz-http",
      "provider_annotations": {
        "service": "BizService",
        "action": "BizAction"
      },
      "client_call_regexes": [
        "bizClient\\.call\\(\\s*\\\"(?P<operation>[A-Za-z0-9_.:-]+)\\\""
      ],
      "provider_call_regexes": [
        "registerService\\(\\s*\\\"(?P<operation>[A-Za-z0-9_.:-]+)\\\""
      ],
      "endpoint_mapping_regexes": [
        "mapOperation\\(\\s*\\\"(?P<operation>[A-Za-z0-9_.:-]+)\\\"\\s*,\\s*\\\"(?P<method>GET|POST|PUT|PATCH|DELETE)\\\"\\s*,\\s*\\\"(?P<path>[^\\\"]+)\\\""
      ]
    }
  ]
}
```

Run:

```bash
know-code index --adapter-config examples/framework-adapters.json
```

