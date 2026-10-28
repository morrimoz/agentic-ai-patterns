"""Local HTTP facade. Workspace headers emulate an identity adapter, not authentication."""

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_id: str = Field(pattern=r"^INV-[0-9]+$")
    request: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=1, max_length=100)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "edit", "reject"]
    expected_version: int = Field(ge=0)
    amount_cents: int | None = Field(default=None, gt=0, strict=True)


def create_app(service):
    app = FastAPI(
        title="Invoice investigation workbench",
        description="Local-only demonstration. Workspace and actor headers must be supplied by a trusted identity gateway in production.",
    )

    def workspace(value):
        if not value:
            raise HTTPException(401, "Workspace identity required")
        return value

    def translate(operation):
        try:
            return operation()
        except KeyError:
            raise HTTPException(404, "Record not found")
        except PermissionError as exc:
            raise HTTPException(403, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/cases")
    def submit(body: Submission, x_workspace: str | None = Header(default=None)):
        tenant = workspace(x_workspace)
        return translate(lambda: service.submit(tenant, body.invoice_id, body.request, body.request_id))

    @app.get("/cases/{case_id}")
    def case(case_id: str, x_workspace: str | None = Header(default=None)):
        tenant = workspace(x_workspace)
        return translate(lambda: service.case(tenant, case_id))

    @app.get("/cases/{case_id}/events")
    def events(case_id: str, x_workspace: str | None = Header(default=None)):
        tenant = workspace(x_workspace)
        return translate(lambda: service.events(tenant, case_id))

    @app.post("/cases/{case_id}/decision")
    def decide(
        case_id: str,
        body: Decision,
        x_workspace: str | None = Header(default=None),
        x_actor: str | None = Header(default=None),
    ):
        tenant = workspace(x_workspace)
        if not x_actor:
            raise HTTPException(401, "Reviewer identity required")
        return translate(
            lambda: service.resolve(
                tenant, case_id, body.action, x_actor, body.expected_version, body.amount_cents
            )
        )

    @app.post("/worker/tick")
    def tick():
        from .service import Service

        return Service(service.path, model=service.model).work("http-local-worker") or {"status": "idle"}

    return app
