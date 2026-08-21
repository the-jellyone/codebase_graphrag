# Test Repo — Ground Truth Verification

This repository is a benchmark/ground truth application for validating AST parsers, tree-sitter extractors, and Neo4j graph builders.

---

## Must-Have Graph Relationships (Answer Key)

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
| `task_service.create_task` | `user_service.get_user` |
| `task_service.create_task` | `validators.validate_string` |
| `userService.getUser` (TS) | `client.get` (TS) |

### INHERITS
| Child | Parent |
|---|---|
| `User` | `BaseModel` |
| `Task` | `BaseModel` |

### IMPORTS (Module Level)
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

### READS (Config)
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
