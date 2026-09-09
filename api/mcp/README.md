# PDIS MCP

One client-neutral, employee-authenticated MCP server. The initial release exposes
Searcher only; it does not automatically expose other API routes or service methods.
The existing website and its HTTP contracts remain available.

## Ownership

```text
Web → api/routes/searcher.py ─┐
                             ├→ api/operations/searcher.py → services/searcher
MCP → api/mcp/tools/searcher.py┘
```

- `api/operations/`: transport-neutral input validation, provider/runtime preparation
  and public result assembly. Providers remain server-owned in `api/deps.py`.
- `api/execution.py`: one process-wide run-capacity limit, shared with web runs.
- `api/mcp/server.py`: explicit registration, SDK transport and authentication
  middleware, metadata, lifecycle and trusted host/origin settings.
- `api/mcp/settings.py`, `auth.py`: opt-in configuration and access-token verification.
- `api/mcp/execution.py`: worker/progress bridge and coded, sanitized MCP failures.
- `api/cors.py`: separate browser-origin policies for MCP and existing web endpoints.
- `api/mcp/tools/`: thin per-tool registrations, schemas and descriptions.

No search logic, provider credentials, document parsing, or result sessions live
in the MCP transport. The official Python SDK handles MCP messages and Streamable
HTTP. The SDK's authentication middleware is composed explicitly to advertise
metadata below `/api`, matching the existing ingress rather than adding root routes.

## Operations

| Name | Input | Structured result |
| --- | --- | --- |
| `searcher_sources` | None | `{ "sources": [...] }` with source capabilities and configuration state |
| `searcher_search` | `{ "request": { "query": "...", ... } }` | Existing `SearcherRunResponse`: `query`, `findings`, `lanes` |

Search fields are the same as the web application: `sources`, `condition`,
`intervention`, `product`, `population`, `outcome`, `region`, `published_since`,
and `entities`. MCP represents sources as an array and entities as objects with
`name` and `entity_type`; the HTTP adapter alone interprets its comma-separated form
strings. The service owns source keys and the entity-type vocabulary. Empty sources
select server defaults. Unknown fields, including caller-selected models/providers,
are rejected. Schemas are advertised through MCP tool discovery.

Errors have MCP `isError: true` and structured data
`{"error":{"code":"server_busy","message":"..."}}`. Codes include
`invalid_sources`, `unconfigured_sources`, `missing_configuration`, `server_busy`,
and `operation_failed`. Invalid tool arguments are handled by the SDK before an
operation runs. Service lane failures remain in `lanes`; they do not become
successful empty searches or fabricated findings. Returned excerpts are untrusted
source material, never instructions.

## Deployment configuration

MCP is **off by default**. No endpoint is mounted until `PDIS_MCP_ENABLED=true`.
Missing or malformed enabled configuration refuses startup; there is no anonymous
fallback. Supply these variables to the **API process**, using your platform's
configuration mechanism:

```dotenv
PDIS_MCP_ENABLED=true
PDIS_MCP_URL=https://pdis.example.org/api/mcp
PDIS_MCP_ISSUER=https://identity.example.org/tenant/
PDIS_MCP_JWKS_URL=https://identity.example.org/tenant/keys
PDIS_MCP_AUDIENCE=pdis-api
PDIS_MCP_SCOPE=pdis:search
# Optional: approved browser-based MCP clients, not needed for server/native clients.
PDIS_MCP_BROWSER_ORIGINS=https://client.example.org
```

These are illustrative values, not a working identity configuration. Compose reads
the API's `.env`; Nomad operators must supply the values through their approved job
configuration/secret mechanism. Existing jobs remain MCP-disabled. No identity
provider, firewall rule, public listing, or connector is provisioned by this code.

### Identity-provider requirements

Register PDIS as an OAuth-protected API and grant the intended employees delegated
access to its scope. The provider must issue JWT **access tokens** signed with RS256
or ES256. PDIS validates the signature against the configured JWKS, exact `iss`,
configured `aud`, expiry and nonempty `sub`. The scope must appear in the standard
space-separated `scope` claim or the commonly used `scp` claim. Missing scopes are
forbidden. An ID token or a token intended for another API is not a substitute.
Opaque tokens/introspection are not implemented in this release.

PDIS never issues tokens or implements login. Configure the identity provider's
OAuth metadata, authorization-code/PKCE flow, resource/audience mapping and MCP-client
registrations there. Clients unable to dynamically register may need an administrator
to pre-register them and enter their client ID in the client platform. Never give
employees PDIS's OpenAI or retrieval-provider credentials.

Key sets are cached for five minutes and refreshed by the JWT library when necessary.
Key-network failures fail closed. Tokens and decoded identity claims are not logged.
Company deprovisioning/revocation behavior follows access-token expiry; this server
does not maintain a separate identity or token-revocation database.

### Network and discovery

Keep TLS at the ingress and preserve the configured public `Host`. The endpoint
accepts requests without an `Origin` header; when one is present it must match the
configured PDIS origin or an explicitly approved `PDIS_MCP_BROWSER_ORIGINS` entry.
The latter is a comma-separated list of HTTPS origins without paths or wildcards.
It configures MCP transport checks and CORS together, exposes `WWW-Authenticate`
for browser discovery, and does not widen the website's other API origins.
Do not disable host/origin checks to accommodate a client.

An unauthenticated request to `/api/mcp` returns a `401` whose `WWW-Authenticate`
header points to:

```text
https://pdis.example.org/api/.well-known/oauth-protected-resource
```

That public metadata document contains only the resource URL, issuer and scope.
Both paths use the existing `/api` ingress. The authentication challenge supplies
the discovery location as allowed by RFC 9728; root-level well-known paths are not
served. Ensure an upstream login redirect or gateway does not swallow this challenge
or block the metadata route. Allow Streamable HTTP responses/progress through the proxy.

Claude Enterprise custom connectors connect from Anthropic's infrastructure, not
the employee's VPN session. Your IT team must permit that network path while
retaining authentication. Internal-only endpoints can instead be used by compatible
clients on the internal network. Register the MCP URL in the external client after
networking, employee permissions and OAuth registration are configured.

### Capacity and cost

`MAX_CONCURRENT_RUNS` is shared across HTTP and MCP in the single API worker. Web
runs retain their queue behavior; MCP searches fail fast with `server_busy` when
capacity is full. MCP bodies are limited to 64 KiB. This is concurrency admission,
not a per-employee spending quota: configure gateway rate limits and provider budgets
according to company policy before enabling employee access.

Progress notifications carry a monotonic event number and stage/count message when
the client requests progress. No hidden jobs or result sessions are created. If a
client disconnects, an already running synchronous search may finish in its worker;
its capacity remains occupied until the worker actually exits. No stored result can
be recovered later. Provider calls retain their existing service timeouts.

## Adding another tool

1. Define/reuse its typed application operation under `api/operations/`, importing
   services only through their public package contracts.
2. Add `api/mcp/tools/<tool>.py` with explicit `<tool>_<action>` registrations,
   typed input and output, descriptions and accurate read-only/open-world annotations.
3. Reuse the MCP execution bridge; expensive operations must take shared capacity.
4. Register it in `create_server` and extend the access-scope policy explicitly.
   Do not assume permission to search also permits a different operation.
5. Test its advertised schema, service-to-HTTP/MCP parity, failure behavior and
   permissions. Document document transfer and large results before adding document
   tools; do not invent server-held uploads or duplicate parsing.

There is no generic route exporter, client-brand branch, duplicate pipeline, or
registry for tools not yet implemented.

## Verification and handoff

```sh
uv sync --frozen --all-groups
uv run python -m unittest tests.test_mcp_auth tests.test_mcp_server tests.test_searcher_operation tests.test_streaming
uv run python -m unittest discover -s tests
```

Tests use generated signing keys, the actual SDK client and mounted HTTP transport,
and controlled service responses. They do not make paid searches. Before employee
rollout, IT should verify a real sign-in/token exchange, denied-user behavior, scope,
issuer/audience, network reachability and one approved live search from each intended
client. Passing local protocol tests does not claim that tenant-specific setup is done.
