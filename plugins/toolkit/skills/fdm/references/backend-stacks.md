# FDM — Backend Stacks

The doctrine is language-agnostic. The translation to each backend stack mostly comes down to (1) what the result type looks like idiomatically and (2) where the framework wants to inject things that fight "push I/O to the edge".

The invariant across all backends: **the domain has no imports from the I/O layer.** If `domain/email_verification.go` imports `database/sql`, `net/http`, or anything from `infrastructure/`, the shape is wrong.

---

## Go

Go is FDM's most natural home: no class hierarchies, no DI containers, no hidden state. The translation is nearly 1:1 with the canonical JS example.

**Result type:** two return values — `(entity, errors)` or `(value, err)`. Use a typed `[]ValidationError` rather than `error` for domain validation; reserve `error` for genuine failures (I/O, parse errors).

**Files:**

```
signup/
  email_verification.go              ← domain function (pure)
  email_verification_repository.go   ← I/O boundary
  handler.go                         ← orchestration
```

**Domain function:**

```go
package signup

type ValidationError struct {
    Field   string `json:"field"`
    Message string `json:"message"`
}

type EmailVerification struct {
    ID       string
    TenantID string
    IDPID    string
    Email    string
    Code     string
    Status   string
    TTL      int64
}

type CreateInput struct {
    Email                  string
    TenantID               string
    IDPID                  string
    VerificationTTLMinutes int
    Now                    time.Time
    NewID                  func() string // injected for testability
    NewCode                func() string
}

func Create(in CreateInput) (*EmailVerification, []ValidationError) {
    var errs []ValidationError
    if in.Email == "" {
        errs = append(errs, ValidationError{"email", "Email is required"})
    } else if !emailRegex.MatchString(in.Email) {
        errs = append(errs, ValidationError{"email", "Email is not a valid email address"})
    }
    if len(errs) > 0 {
        return nil, errs
    }

    ttl := 10
    if in.VerificationTTLMinutes > 0 {
        ttl = in.VerificationTTLMinutes
    }

    return &EmailVerification{
        ID:       in.NewID(),
        TenantID: in.TenantID,
        IDPID:    in.IDPID,
        Email:    in.Email,
        Code:     in.NewCode(),
        Status:   StatusPending,
        TTL:      in.Now().Add(time.Duration(ttl) * time.Minute).Unix(),
    }, nil
}
```

The handler constructs the `CreateInput` (passing `time.Now`, a UUID generator, a code generator), and tests pass fixed-value stubs (`func() string { return "fixed-id" }`). The domain function itself is pure.

**Handler:**

```go
func handleVerify(repo Repository, mailer Mailer) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        var body verifyRequest
        if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
            respondError(w, 400, "Invalid JSON")
            return
        }

        entity, errs := Create(CreateInput{
            Email:    body.Email,
            TenantID: chi.URLParam(r, "tenantId"),
            IDPID:    chi.URLParam(r, "idpId"),
            Now:      time.Now,
            NewID:    uuid.NewString,
            NewCode:  generateSixDigit,
        })
        if errs != nil {
            respondValidation(w, errs)
            return
        }

        if err := repo.Save(r.Context(), entity); err != nil {
            respondError(w, 500, "Persistence failed")
            return
        }
        if err := mailer.Send(r.Context(), entity); err != nil {
            log.Error("orphaned verification", "id", entity.ID, "err", err)
            // ... domain-defined error response
        }

        respondJSON(w, 200, map[string]string{"verificationId": entity.ID})
    }
}
```

**Repository:**

```go
type Repository interface {
    Save(ctx context.Context, e *EmailVerification) error
    FindByID(ctx context.Context, tenantID, idpID, id string) (*EmailVerification, error)
}

type DynamoRepository struct {
    client *dynamodb.Client
    table  string
}

func (r *DynamoRepository) Save(ctx context.Context, e *EmailVerification) error {
    _, err := r.client.PutItem(ctx, &dynamodb.PutItemInput{
        TableName: aws.String(r.table),
        Item: map[string]types.AttributeValue{
            "pk":     &types.AttributeValueMemberS{Value: fmt.Sprintf("TENANT#%s#IDP#%s#EMAIL_VERIFICATION#%s", e.TenantID, e.IDPID, e.ID)},
            "sk":     &types.AttributeValueMemberS{Value: "EMAIL_VERIFICATION"},
            "id":     &types.AttributeValueMemberS{Value: e.ID},
            "email":  &types.AttributeValueMemberS{Value: e.Email},
            "code":   &types.AttributeValueMemberS{Value: e.Code},
            "status": &types.AttributeValueMemberS{Value: e.Status},
            "ttl":    &types.AttributeValueMemberN{Value: strconv.FormatInt(e.TTL, 10)},
        },
    })
    return err
}
```

Define `Repository` as an interface in the domain package (`signup/repository.go`); the `DynamoRepository` concrete type lives in `infrastructure/dynamo/`. The domain owns the contract; the implementation lives outside.

---

## Java / Spring

Spring's idioms fight FDM in places — `@Service`, `@Repository`, `@Autowired`, and constructor injection encode an OOP-with-DI worldview where I/O and logic naturally co-mingle. FDM in Spring is **deliberately working around those idioms**, not embracing them.

**Result type:** a sealed interface with `Success` / `Failure` subtypes. Java 21+ supports this with pattern matching cleanly; pre-21 codebases can use a `Result<T>` class with `boolean isSuccess()`.

```java
public sealed interface CreateResult permits CreateResult.Success, CreateResult.Failure {
    record Success(EmailVerification entity) implements CreateResult {}
    record Failure(List<ValidationError> errors) implements CreateResult {}
}
```

**Domain function:** a `final` class with only `static` methods, **no Spring annotations**. This is the key adaptation — the domain doesn't know Spring exists.

```java
package com.example.signup.domain;

public final class EmailVerification {
    private EmailVerification() {}

    public static CreateResult create(CreateInput in) {
        var errors = new ArrayList<ValidationError>();
        if (in.email() == null || in.email().isBlank()) {
            errors.add(new ValidationError("email", "Email is required"));
        } else if (!EMAIL_REGEX.matcher(in.email()).matches()) {
            errors.add(new ValidationError("email", "Email is not a valid email address"));
        }
        if (!errors.isEmpty()) return new CreateResult.Failure(errors);

        int ttl = in.verificationTtlMinutes() > 0 ? in.verificationTtlMinutes() : 10;
        return new CreateResult.Success(new EmailVerification(
            in.idGenerator().get(),
            in.tenantId(),
            in.idpId(),
            in.email(),
            in.codeGenerator().get(),
            Status.PENDING,
            in.now().plusMinutes(ttl).toEpochSecond(ZoneOffset.UTC)
        ));
    }
}
```

**Handler:** a `@RestController` method that calls into the static domain function, branches on the sealed result, and invokes the injected repository for I/O.

```java
@RestController
@RequestMapping("/v1/tenants/{tenantId}/idps/{idpId}/signup")
public class SignupController {

    private final EmailVerificationRepository repo;
    private final Mailer mailer;
    private final Clock clock;
    private final Supplier<String> idGen;
    private final Supplier<String> codeGen;

    // ... constructor

    @PostMapping("/verify")
    public ResponseEntity<?> verify(
            @PathVariable String tenantId,
            @PathVariable String idpId,
            @RequestBody VerifyRequest body) {

        var result = EmailVerification.create(new CreateInput(
            body.email(), tenantId, idpId, 0,
            clock.instant().atZone(ZoneOffset.UTC), idGen, codeGen));

        return switch (result) {
            case CreateResult.Failure f -> ResponseEntity.badRequest()
                .body(new ValidationErrorResponse(f.errors()));
            case CreateResult.Success s -> {
                repo.save(s.entity());
                mailer.send(s.entity());
                yield ResponseEntity.ok(new VerifyResponse(s.entity().id()));
            }
        };
    }
}
```

**Repository:** Spring's `@Repository` annotation has different semantics from FDM's "repository" — Spring's marks a bean for exception translation. Keep the annotation on the concrete class, but **define the interface in the domain package** (the domain owns the contract).

```java
// com/example/signup/domain/EmailVerificationRepository.java  (NO Spring imports)
public interface EmailVerificationRepository {
    void save(EmailVerification entity);
    Optional<EmailVerification> findById(String tenantId, String idpId, String id);
}

// com/example/signup/infrastructure/DynamoEmailVerificationRepository.java
@Repository
public class DynamoEmailVerificationRepository implements EmailVerificationRepository {
    // ... DynamoDB-flavored impl, translates pk/sk and back
}
```

The Spring DI container wires the concrete bean into the controller. The domain package never imports `org.springframework.*`.

**Friction points to be honest about:**

- `@Service`-annotated classes that mix `@Autowired` JPA repositories with business logic are the OOP anti-pattern FDM rejects. In a Spring codebase already structured this way, the migration is incremental — extract pure methods out of services one at a time, leave the service as a thin wrapper, eventually the service becomes the handler.
- JPA's `@Entity` annotated classes are not domain entities in the FDM sense. They're storage objects. The repository translates between them and pure domain records (or vice versa). Don't let JPA's mutable `@Entity` types leak into domain functions.

---

## TypeScript / Node (Express / Fastify / Hono / NestJS)

Closest analog to the canonical JS example. Use TypeScript's discriminated union for the result type and you have a typed version of the same shape.

**Result type:**

```ts
type ValidationError = { field: string; message: string };
type CreateResult<T> =
    | { errors: ValidationError[] }
    | { entity: T };
```

**Domain function** (`signup/email-verification.ts`):

```ts
import { v7 as uuidv7 } from "uuid";

export type EmailVerification = {
    id: string;
    tenantId: string;
    idpId: string;
    email: string;
    code: string;
    status: "PENDING" | "CONFIRMED" | "EXPIRED";
    ttl: number;
};

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const create = (input: {
    email: string;
    tenantId: string;
    idpId: string;
    registration?: { verificationTtlMinutes?: number };
    now?: () => number;
    newId?: () => string;
    newCode?: () => string;
}): CreateResult<EmailVerification> => {
    const errors: ValidationError[] = [];
    if (!input.email) {
        errors.push({ field: "email", message: "Email is required" });
    } else if (!EMAIL_REGEX.test(input.email)) {
        errors.push({ field: "email", message: "Email is not a valid email address" });
    }
    if (errors.length > 0) return { errors };

    const now = input.now ?? Date.now;
    const newId = input.newId ?? uuidv7;
    const newCode = input.newCode ?? (() => String(Math.floor(100000 + Math.random() * 900000)));
    const ttlMinutes = input.registration?.verificationTtlMinutes ?? 10;

    return {
        entity: {
            id: newId(),
            tenantId: input.tenantId,
            idpId: input.idpId,
            email: input.email,
            code: newCode(),
            status: "PENDING",
            ttl: Math.floor(now() / 1000) + ttlMinutes * 60,
        },
    };
};
```

**Handler** (Hono example — Express and Fastify are nearly identical):

```ts
import { Hono } from "hono";
import * as emailVerification from "./email-verification";
import { save } from "./email-verification-repository";
import { sendTemplatedEmail } from "../infrastructure/mailer";

const api = new Hono();

api.post("/v1/tenants/:tenantId/idps/:idpId/signup/verify", async (c) => {
    const body = await c.req.json();
    const result = emailVerification.create({
        email: body.email,
        tenantId: c.req.param("tenantId"),
        idpId: c.req.param("idpId"),
    });

    if ("errors" in result) {
        return c.json({ violations: result.errors }, 400);
    }

    await save(result.entity);
    await sendTemplatedEmail({ /* ... */ });
    return c.json({ verificationId: result.entity.id }, 200);
});
```

**NestJS adaptation:** in a NestJS codebase, the controller is the handler and the service is conventionally where logic lives — but **the domain module has no `@Injectable()`**. Export plain functions from a non-decorated module. The service becomes a thin Nest-wrapper that delegates to the pure module. Don't fight Nest's DI for the I/O ring (it's useful there); do fight it for the domain ring.

---

## Python / FastAPI

FastAPI's path operations are natural handlers. Python's dataclasses or Pydantic models give clean entity types.

**Result type:** a dataclass or Pydantic model with `errors` / `entity` fields, or a `Union` discriminated by an `is_success` flag. Pattern-match in Python 3.10+ for the cleanest call site.

```python
from dataclasses import dataclass
from typing import Union

@dataclass(frozen=True)
class ValidationError:
    field: str
    message: str

@dataclass(frozen=True)
class EmailVerification:
    id: str
    tenant_id: str
    idp_id: str
    email: str
    code: str
    status: str
    ttl: int

@dataclass(frozen=True)
class Failure:
    errors: list[ValidationError]

@dataclass(frozen=True)
class Success:
    entity: EmailVerification

CreateResult = Union[Success, Failure]
```

**Domain function** (`signup/email_verification.py`):

```python
import re
from datetime import datetime
from typing import Callable

EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

def create(
    *,
    email: str,
    tenant_id: str,
    idp_id: str,
    ttl_minutes: int = 10,
    now: Callable[[], datetime],
    new_id: Callable[[], str],
    new_code: Callable[[], str],
) -> CreateResult:
    errors = []
    if not email:
        errors.append(ValidationError("email", "Email is required"))
    elif not EMAIL_REGEX.match(email):
        errors.append(ValidationError("email", "Email is not a valid email address"))

    if errors:
        return Failure(errors=errors)

    return Success(entity=EmailVerification(
        id=new_id(),
        tenant_id=tenant_id,
        idp_id=idp_id,
        email=email,
        code=new_code(),
        status="PENDING",
        ttl=int(now().timestamp()) + ttl_minutes * 60,
    ))
```

**Handler:** a FastAPI path operation.

```python
from fastapi import APIRouter, Depends, HTTPException
from . import email_verification
from .email_verification_repository import save
from ..infrastructure.mailer import send_templated_email
from .deps import get_clock, get_id_factory, get_code_factory

router = APIRouter()

@router.post("/v1/tenants/{tenant_id}/idps/{idp_id}/signup/verify")
async def verify(
    tenant_id: str,
    idp_id: str,
    body: VerifyRequest,
    now=Depends(get_clock),
    new_id=Depends(get_id_factory),
    new_code=Depends(get_code_factory),
):
    result = email_verification.create(
        email=body.email,
        tenant_id=tenant_id,
        idp_id=idp_id,
        now=now,
        new_id=new_id,
        new_code=new_code,
    )
    match result:
        case Failure(errors):
            raise HTTPException(400, {"violations": [e.__dict__ for e in errors]})
        case Success(entity):
            await save(entity)
            await send_templated_email(entity)
            return {"verificationId": entity.id}
```

**Repository:** defined as a `Protocol` in the domain package (structural typing — the domain owns the contract, the infrastructure module conforms).

```python
# signup/repository.py  (domain package; imports nothing from infrastructure)
from typing import Protocol, Optional

class EmailVerificationRepository(Protocol):
    async def save(self, entity: EmailVerification) -> None: ...
    async def find_by_id(self, tenant_id: str, idp_id: str, id: str) -> Optional[EmailVerification]: ...

# infrastructure/dynamo/email_verification_repository.py
class DynamoEmailVerificationRepository:
    async def save(self, entity):
        # ... pk/sk translation, boto3 put_item
```

FastAPI's `Depends` handles wiring the concrete repository in. The domain function takes the clock and ID factories as keyword arguments — testable without monkey-patching.

---

## What's invariant across all backends

- The domain has **no imports** from the I/O layer.
- The domain function returns a binary result (success/failure), not throws / not returns null.
- Repositories translate, they do not decide. They have no validation, no business rules.
- The handler is a recipe: gather → decide → branch → act → respond.
- The result type is whatever's idiomatic for the language (sealed interface, discriminated union, two-value return, dataclass union), as long as it forces the caller to handle both outcomes.

If the domain function in your stack of choice can't be unit-tested with zero setup, the shape is wrong. Re-read `core-doctrine.md` and split again.
