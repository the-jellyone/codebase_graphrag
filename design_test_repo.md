# Test Repo Design

## Purpose
A small but real, working layered application used as the ground truth for validating the parser and graph builder.
Every node and edge in the graph must be knowable **before** the parser runs.

---

## Domain
**Task Manager** — Users create and manage Tasks. Simple enough to not think about, structured enough to cover all graph edge types.

---

## Stack
- **Backend** — Python (FastAPI)
- **Frontend** — TypeScript (no framework, just fetch-based client)

---

## Folder Structure
```
test_repo/
├── backend/
│   ├── config.py          # env/config values
│   ├── exceptions.py      # custom exceptions
│   ├── models/
│   │   ├── base.py        # BaseModel
│   │   ├── user.py        # inherits BaseModel
│   │   └── task.py        # inherits BaseModel
│   ├── db/
│   │   └── repository.py  # reads config, raises exceptions
│   ├── services/
│   │   ├── user_service.py
│   │   └── task_service.py  # calls user_service (cross-service)
│   ├── api/
│   │   └── routes.py      # FastAPI route decorators, calls services
│   └── utils/
│       └── validators.py  # pure functions, called by services
│
├── frontend/
│   ├── api/
│   │   └── client.ts      # centralised ENDPOINTS dict + fetch logic
│   ├── services/
│   │   └── userService.ts # calls client methods
│   ├── models/
│   │   └── types.ts       # User, Task interfaces → graph nodes
│   └── utils/
│       └── helpers.ts     # pure utility functions
│
└── README.md              # ground truth table — used for Neo4j verification
```

---

## Must-Have Graph Relationships (Ground Truth / Answer Key)

### CALLS
| Caller | Callee |
|---|---|
| `routes.create_user` | `user_service.create_user` |
| `routes.create_task` | `task_service.create_task` |
| `routes.get_user` | `user_service.get_user` |
| `user_service.create_user` | `repository.save` |
| `user_service.create_user` | `validators.validate_email` |
| `user_service.get_user` | `repository.find_by_id` |
| `task_service.create_task` | `repository.save` |
| `task_service.create_task` | `user_service.get_user` ← cross-service |
| `task_service.create_task` | `validators.validate_string` |
| `userService.getUser` (TS) | `client.get` (TS) |

### INHERITS
| Child | Parent |
|---|---|
| `User` | `BaseModel` |
| `Task` | `BaseModel` |

### IMPORTS (module level)
| Importer | Imported |
|---|---|
| `routes` | `user_service`, `task_service` |
| `user_service` | `repository`, `validators`, `models.user`, `exceptions` |
| `task_service` | `repository`, `validators`, `models.task`, `exceptions`, `user_service` |
| `repository` | `config`, `exceptions` |
| `models.user` | `models.base` |
| `models.task` | `models.base` |

### RAISES
| Function | Exception |
|---|---|
| `repository.find_by_id` | `NotFoundException` |
| `repository.save` | `DatabaseException` |
| `validators.validate_email` | `ValidationException` |

### READS (config)
| Function | Config Key |
|---|---|
| `repository.save` | `config.DB_URL` |
| `repository.find_by_id` | `config.MAX_CONNECTIONS` |

### DEFINES_TYPE (TypeScript)
| Module | Interface/Type |
|---|---|
| `types.ts` | `User` |
| `types.ts` | `Task` |

### USES_TYPE (TypeScript)
| Function | Type |
|---|---|
| `userService.getUser` | `User` |
| `userService.createUser` | `User` |
| `client.get` | `Task` |

---

## Problem Resolutions

### 1. Cross-Language Call Resolution — Known Limitation (v1)
`CALLS_ENDPOINT` edges (TS → Python route) will **not** be auto-extracted in v1.
Static resolution of HTTP URLs to route handlers is a research-level problem.
These edges will be **manually added** to the graph for now and documented as such.
Revisit in a later version.

### 2. Call Ambiguity — Import-Aware Resolution
Use the `IMPORTS` edges already in the graph as scope context.
If `user_service` imports `repository`, then `save()` inside `user_service` resolves to `repository.save`.
Resolution rule: **match call name against functions in imported modules first, then fall back to same-module scope.**
Unresolvable calls are logged and skipped — not guessed.

### 3. Config Reads — Two Patterns Only
Detect exactly two patterns:
- `config.SOME_KEY` — attribute access on the config module
- `os.getenv("SOME_KEY")` — stdlib env read

Everything else is a **known blind spot**. Not over-engineered.

### 4. TypeScript Interfaces → Graph Nodes
Interfaces are extracted as nodes with two edge types:
- `DEFINES_TYPE` — connects the module to the interface node
- `USES_TYPE` — connects a function to any interface it returns or accepts as a parameter

Not hard to extract from the TS AST. Useful for type-level impact analysis.

### 5. Dynamic / Indirect Calls — Known Blind Spot
Calls through variables, dicts, or decorators are not extracted.
This is a universal limitation of static analysis — Cursor, Sourcegraph, and every other tool has the same blind spot.
Documented clearly. Not a bug, it's a boundary.

---

## Test Repo README (Ground Truth Verification)

The `test_repo/README.md` will contain the full ground truth table above.

After parsing and loading into Neo4j, run Cypher queries against these expected edges to verify correctness.
This makes the test repo self-contained — the code AND the answer key live in the same place.
