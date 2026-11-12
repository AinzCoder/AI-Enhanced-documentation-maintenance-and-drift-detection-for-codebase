from analyzer.java_analyzer import analyze_java_file
from approval.documentation_updater import update_method_documentation
from rag.documentation_generator import generate_update_for_change
from rag.indexer import index_repository_documentation
from rag.repository_context_retriever import get_repository_index_status
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
from git import Repo
from git.exc import GitCommandError
import tempfile
import uuid
from fastapi.middleware.cors import CORSMiddleware
import json
from datetime import datetime

from drift_analysis.drift_detector import (
    detect_documentation_drift,
    find_empty_documentation_files
)

from git_analysis.git_analyzer import get_java_file_changes
from models.code_model import CodeFile
from analyzer.repository_analyzer import analyze_full_repository
from documentation_generation.full_documentation_generator import (
    generate_full_documentation
)
from documentation_analysis.documentation_coverage import (
    analyze_documentation_coverage
)
from approval.generation_store import (
    create_pending_record,
    get_record,
    list_audit_records
)
from approval.generation_workflow import (
    GenerationConflictError,
    GenerationNotFoundError,
    approve_generation,
    reject_generation
)

from change_analysis.change_impact_analyzer import (
    compare_code_models
)

from documentation_analysis.documentation_mapper import (
    map_code_to_documentation
)
from repository_identity import get_repository_identity
from timing import timed
from llm.groq_client import GroqClientError

app = FastAPI(
    title="AI Documentation Maintenance System",
    description=(
        "Detects documentation drift in evolving codebases."
    ),
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RepositoryRequest(BaseModel):
    repository_path: str


class FullDocumentationGenerationRequest(BaseModel):
    repository_path: str
    target_documentation_file: str | None = None
    include_repository_overview: bool = True
    max_methods: int | None = Field(default=None, gt=0)


class GenerationDecisionRequest(BaseModel):
    decision: str


class AnalyzeRequest(BaseModel):
    repository_path: str
    mode: str = "working_tree"
    base_commit: str | None = None

# Persistent repository registry
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPOSITORY_FILE = DATA_DIR / "repositories.json"
HISTORY_FILE = DATA_DIR / "documentation_history.json"
GENERATION_STORE_PATH = DATA_DIR / "documentation_generations.sqlite3"

def load_history():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not HISTORY_FILE.exists():
        return []

    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_history(history):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=4)


def load_repositories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not REPOSITORY_FILE.exists():
        return []

    with open(REPOSITORY_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_repositories(repositories):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(REPOSITORY_FILE, "w", encoding="utf-8") as file:
        json.dump(repositories, file, indent=4)

class SuggestionRequest(BaseModel):
    repository_path: str
    file_path: str
    class_name: str
    method_name: str
    change_type: str


class RagIndexRequest(BaseModel):
    repository_path: str

class DecisionRequest(BaseModel):
    repository_path: str
    documentation_file: str
    class_name: str
    method_name: str
    decision: str
    documentation: str | None = None



@app.post("/suggest")
def generate_suggestion(request: SuggestionRequest):
    repository_path = Path(request.repository_path).expanduser().resolve()
    if not repository_path.exists() or not repository_path.is_dir():
        return {
            "error": "Repository path does not exist or is not a directory."
        }

    requested_file = Path(request.file_path)
    if requested_file.is_absolute() or ".." in requested_file.parts:
        return {"error": "Source file must be repository-relative."}
    code_path = (repository_path / requested_file).resolve()
    if (
        not code_path.is_relative_to(repository_path)
        or not code_path.exists()
        or not code_path.is_file()
    ):
        return {
            "error": f"Source file not found: {request.file_path}"
        }

    current_code = code_path.read_text(encoding="utf-8")

    # Parse the Java source and extract developer comments.
    code_model = analyze_java_file(str(code_path))

    developer_comment = None

    for class_info in code_model.classes:
        if class_info.name != request.class_name:
            continue

        for method in class_info.methods:
            if method.name == request.method_name:
                developer_comment = method.comment
                break

        break

    # Generate documentation using the extracted comment.
    try:
        result = generate_update_for_change(
            class_name=request.class_name,
            method_name=request.method_name,
            change_type=request.change_type,
            code=current_code,
            developer_comment=developer_comment,
            repository_path=str(repository_path),
            source_file=code_path.relative_to(repository_path).as_posix()
        )
    except GroqClientError as error:
        return {"error": error.public_message}
    except ValueError:
        return {"error": "Groq returned invalid documentation."}

    return {
        **result,
        "developer_comment": developer_comment
    }


@app.post("/rag/index")
def index_repository_rag(request: RagIndexRequest):
    repository_path = Path(request.repository_path).expanduser()
    if not repository_path.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="repository_path must be an absolute path."
        )
    try:
        return index_repository_documentation(str(repository_path))
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Repository path does not exist."
        ) from error
    except NotADirectoryError as error:
        raise HTTPException(
            status_code=400,
            detail="Repository path must be a directory."
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/rag/status")
def repository_rag_status(repository_path: str):
    path = Path(repository_path).expanduser()
    if not path.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="repository_path must be an absolute path."
        )
    try:
        return get_repository_index_status(str(path))
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Repository path does not exist."
        ) from error
    except NotADirectoryError as error:
        raise HTTPException(
            status_code=400,
            detail="repository_path must be a directory."
        ) from error



@app.post("/decision")
def documentation_decision(request: DecisionRequest):

    decision = request.decision.lower()

    if decision == "reject":
        history = load_history()

        history.append({
            "repository_path": request.repository_path,
            "documentation_file": request.documentation_file,
            "class_name": request.class_name,
            "method_name": request.method_name,
            "decision": "rejected",
            "documentation": None,
            "timestamp": datetime.now().astimezone().isoformat()
        })

        save_history(history)

        return {
            "status": "rejected",
            "message": "Documentation was not modified."
        }

    if decision not in {"approve", "edit"}:
        return {
            "status": "error",
            "message": "Decision must be approve, reject, or edit."
        }

    if not request.documentation:
        return {
            "status": "error",
            "message": "Documentation is required for approve or edit."
        }

    try:
        update_result = update_method_documentation(
            repository_path=request.repository_path,
            documentation_file=request.documentation_file,
            class_name=request.class_name,
            method_name=request.method_name,
            new_documentation=request.documentation
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Repository path or documentation file does not exist."
        ) from error
    except NotADirectoryError as error:
        raise HTTPException(
            status_code=400,
            detail="Repository path must be a directory."
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if update_result:

        history = load_history()

        history.append({
            "repository_path": request.repository_path,
            "documentation_file": request.documentation_file,
            "class_name": request.class_name,
            "method_name": request.method_name,
            "decision": "approved" if decision == "approve" else "edited",
            "documentation": request.documentation,
            "timestamp": datetime.now().astimezone().isoformat()
        })

        save_history(history)

        return {
            "status": "approved" if decision == "approve" else "edited",
            "message": "Documentation updated successfully.",
            "file": request.documentation_file
        }

    return {
        "status": "error",
        "message": "Documentation was not updated."
    }


@app.get("/history")
def get_documentation_history():
    return {
        "history": load_history() + list_audit_records(
            GENERATION_STORE_PATH
        )
    }



@app.get("/repositories")
def get_repositories():
    """Return all registered repositories."""
    return {
        "repositories": load_repositories()
    }


@app.post("/repositories")
def add_repository(request: RepositoryRequest):
    """Validate and register a local Git repository."""

    repository_path = Path(request.repository_path).expanduser()

    if not repository_path.exists():
        return {
            "status": "error",
            "message": "Repository path does not exist."
        }

    if not repository_path.is_dir():
        return {
            "status": "error",
            "message": "The provided path is not a directory."
        }

    try:
        git_repository = Repo(str(repository_path))

        if git_repository.bare:
            return {
                "status": "error",
                "message": "Bare Git repositories are not supported."
            }

        branch = (
            git_repository.active_branch.name
            if not git_repository.head.is_detached
            else "Detached HEAD"
        )

    except Exception:
        return {
            "status": "error",
            "message": "The selected directory is not a valid Git repository."
        }

    repositories = load_repositories()

    resolved_path = str(repository_path.resolve())

    for repository in repositories:
        if repository["path"].lower() == resolved_path.lower():
            return {
                "status": "error",
                "message": "This repository is already registered."
            }

    repository_data = {
        "id": len(repositories) + 1,
        "name": repository_path.name,
        "path": resolved_path,
        "branch": branch
    }

    repositories.append(repository_data)
    save_repositories(repositories)

    return {
        "status": "success",
        "message": "Repository registered successfully.",
        "repository": repository_data
    }


@app.delete("/repositories/{repository_id}")
def delete_repository(repository_id: int):
    """Remove a registered repository."""

    repositories = load_repositories()

    updated_repositories = [
        repository
        for repository in repositories
        if repository["id"] != repository_id
    ]

    if len(updated_repositories) == len(repositories):
        return {
            "status": "error",
            "message": "Repository not found."
        }

    save_repositories(updated_repositories)

    return {
        "status": "success",
        "message": "Repository removed successfully."
    }


@app.get("/")
def root():

    return {
        "message": "AI Documentation Maintenance System is running"
    }


@app.post("/analyze/full")
@timed("request.analyze_full")
def analyze_full_repository_endpoint(request: RepositoryRequest):
    repository_path = Path(request.repository_path).expanduser()
    if not repository_path.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="repository_path must be an absolute path."
        )

    try:
        analysis = analyze_full_repository(str(repository_path))
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Repository path does not exist."
        ) from error
    except NotADirectoryError as error:
        raise HTTPException(
            status_code=400,
            detail="Repository path must be a directory."
        ) from error
    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail="Repository scan failed."
        ) from error

    documentationAnalysis = analyze_documentation_coverage(
        str(repository_path.resolve()),
        analysis
    )
    analysis["errors"].extend(documentationAnalysis["errors"])

    return {
        "repository": analysis["repository"],
        "analysis_mode": "full",
        "summary": analysis["summary"],
        "files": analysis["files"],
        "documentation_files": analysis["documentation_files"],
        "documentation_analysis": documentationAnalysis,
        "errors": analysis["errors"]
    }


@app.post("/documentation/generate/full")
def generate_full_documentation_endpoint(
    request: FullDocumentationGenerationRequest
):
    repository_path = Path(request.repository_path).expanduser()
    if not repository_path.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="repository_path must be an absolute path."
        )

    try:
        result = generate_full_documentation(
            repository_path=str(repository_path),
            target_documentation_file=request.target_documentation_file,
            include_repository_overview=request.include_repository_overview,
            max_methods=request.max_methods
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Repository path does not exist."
        ) from error
    except NotADirectoryError as error:
        raise HTTPException(
            status_code=400,
            detail="Repository path must be a directory."
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except GroqClientError as error:
        raise HTTPException(status_code=503, detail=error.public_message) from error
    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail="Repository analysis failed."
        ) from error

    if (
        result.get("generation_status") not in {"complete", "partial"}
        or not result.get("generated_markdown")
        or any(
            item.get("stage") in {
                "class_generation", "method_generation", "overview_generation"
            }
            for item in result.get("errors", [])
        )
    ):
        return {
            **result,
            "generation_id": None,
            "approval_status": "unavailable"
        }

    source_hashes = result.get("source_hashes", {})
    if len(source_hashes) > 5000:
        raise HTTPException(
            status_code=413,
            detail=(
                "The generation depends on too many Java files to create a "
                "bounded approval record."
            )
        )

    resolved_repository = repository_path.resolve()
    repository_identity = get_repository_identity(resolved_repository)
    generationId = uuid.uuid4().hex
    createdAt = datetime.now().astimezone().isoformat()
    record = {
        "generation_id": generationId,
        "repository": resolved_repository.name,
        "repository_identity": repository_identity,
        "repository_path": str(resolved_repository),
        "documentation_target": result["documentation_target"],
        "generated_markdown": result["generated_markdown"],
        "generated_classes": result.get("generated_classes", []),
        "generated_methods": result.get("generated_methods", []),
        "repository_overview": result.get("repository_overview"),
        "ambiguous_documentation_mappings": result.get(
            "ambiguous_documentation_mappings",
            []
        ),
        "generation_status": result["generation_status"],
        "created_at": createdAt,
        "source_hashes": source_hashes,
        "target_hash_before": result.get(
            "target_hash_at_generation",
            "__missing__"
        )
    }
    try:
        create_pending_record(GENERATION_STORE_PATH, record)
    except ValueError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail="Could not persist the generation approval preview."
        ) from error

    return {
        **result,
        "generation_id": generationId,
        "approval_status": "pending"
    }


@app.get("/documentation/generation/{generation_id}")
def get_documentation_generation(generation_id: str):
    record = get_record(GENERATION_STORE_PATH, generation_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Generation was not found."
        )
    public_record = dict(record)
    public_record.pop("repository_path", None)
    return public_record


@app.post("/documentation/generation/{generation_id}/approve")
def approve_documentation_generation(
    generation_id: str,
    request: GenerationDecisionRequest
):
    if request.decision != "approve":
        raise HTTPException(
            status_code=400,
            detail="Explicit decision 'approve' is required."
        )
    try:
        record = approve_generation(
            GENERATION_STORE_PATH,
            generation_id
        )
    except GenerationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GenerationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    if record.get("status") == "stale":
        raise HTTPException(
            status_code=409,
            detail=record.get("failure_reason")
            or "Generation preview is stale."
        )
    if record.get("status") == "failed":
        raise HTTPException(
            status_code=500,
            detail=record.get("failure_reason")
            or "Documentation approval failed."
        )
    return {
        "generation_id": generation_id,
        "status": record["status"],
        "generation_status": record.get("generation_status"),
        "documentation_target": record["documentation_target"],
        "audit": record.get("audit")
    }


@app.post("/documentation/generation/{generation_id}/reject")
def reject_documentation_generation(
    generation_id: str,
    request: GenerationDecisionRequest
):
    if request.decision != "reject":
        raise HTTPException(
            status_code=400,
            detail="Explicit decision 'reject' is required."
        )
    try:
        record = reject_generation(
            GENERATION_STORE_PATH,
            generation_id
        )
    except GenerationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GenerationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "generation_id": generation_id,
        "status": record["status"],
        "documentation_target": record["documentation_target"],
        "audit": record.get("audit")
    }


@app.post("/analyze")
@timed("request.analyze_git")
def analyze_repository(request: AnalyzeRequest):
    repository_path = request.repository_path

    try:
        analysis = get_java_file_changes(
            repository_path,
            mode=request.mode,
            base_commit=request.base_commit
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except GitCommandError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Git comparison failed: {error}"
        ) from error

    root = analysis["root"]
    results = []

    for file_change in analysis["changes"]:
        oldPath = file_change["old_path"]
        newPath = file_change["new_path"]
        filePath = file_change["file"]
        errors = []
        changes = []
        oldModel = CodeFile(
            file_path=oldPath or newPath,
            language="Java"
        )
        newModel = CodeFile(
            file_path=newPath or oldPath,
            language="Java"
        )

        with tempfile.TemporaryDirectory() as tempDirectory:
            for side, sourcePath, sourceContent, isJava in (
                (
                    "old",
                    oldPath,
                    file_change["old_content"],
                    bool(oldPath and oldPath.lower().endswith(".java"))
                ),
                (
                    "new",
                    newPath,
                    file_change["new_content"],
                    bool(newPath and newPath.lower().endswith(".java"))
                )
            ):
                if not isJava:
                    continue
                if sourceContent is None:
                    errors.append({
                        "stage": "source_read",
                        "file": sourcePath,
                        "message": (
                            f"Java source contents are unavailable for "
                            f"{side} version."
                        )
                    })
                    continue

                tempPath = Path(tempDirectory) / f"{side}.java"
                try:
                    tempPath.write_bytes(sourceContent)
                    model = analyze_java_file(str(tempPath))
                    if side == "old":
                        oldModel = model
                    else:
                        newModel = model
                except Exception as error:
                    errors.append({
                        "stage": "java_analysis",
                        "file": sourcePath,
                        "message": str(error)
                    })

        if not any(
            error["stage"] in {"source_read", "java_analysis"}
            for error in errors
        ):
            changes = compare_code_models(oldModel, newModel)
            for change in changes:
                isRemoved = change["type"] in {
                    "class_removed",
                    "method_removed"
                }
                sourceFile = (
                    oldPath
                    if isRemoved and oldPath
                    else newPath or oldPath
                )
                change["source_file"] = sourceFile

                methodName = change.get("method")
                if methodName:
                    sourceModel = oldModel if isRemoved else newModel
                    classInfo = next(
                        (
                            item for item in sourceModel.classes
                            if item.name == change.get("class")
                        ),
                        None
                    )
                    candidateMethods = (
                        [
                            method for method in classInfo.methods
                            if method.name == methodName
                        ]
                        if classInfo
                        else []
                    )
                    eventLine = (
                        change.get("old_start_line")
                        if isRemoved
                        else change.get("start_line")
                    )
                    methodInfo = next(
                        (
                            method for method in candidateMethods
                            if method.start_line == eventLine
                        ),
                        candidateMethods[0]
                        if len(candidateMethods) == 1
                        else None
                    )
                    if methodInfo:
                        change["parameter_types"] = [
                            parameter.type
                            for parameter in methodInfo.parameters
                        ]
                        change["method_signature"] = (
                            f"{methodInfo.name}("
                            + ", ".join(change["parameter_types"])
                            + ")"
                        )

        documentation_files = []
        drift_results = []
        javaPath = (
            newPath
            if newPath and newPath.lower().endswith(".java")
            else oldPath
        )

        try:
            documentation_files = map_code_to_documentation(
                str(root),
                javaPath
            )
        except Exception as error:
            errors.append({
                "stage": "documentation_mapping",
                "file": javaPath,
                "message": str(error)
            })

        if not any(
            error["stage"] == "documentation_mapping"
            for error in errors
        ):
            try:
                detectedDrift = detect_documentation_drift(
                    str(root),
                    documentation_files,
                    changes
                )
                for finding in detectedDrift:
                    if finding.get("type") == "documentation_error":
                        errors.append({
                            "stage": "documentation_read",
                            "file": finding.get("documentation_file"),
                            "message": finding.get("reason")
                        })
                    else:
                        drift_results.append(finding)
            except Exception as error:
                errors.append({
                    "stage": "drift_detection",
                    "file": javaPath,
                    "message": str(error)
                })

            try:
                emptyResults = find_empty_documentation_files(
                    str(root),
                    documentation_files
                )
                for finding in emptyResults:
                    if finding.get("type") == "documentation_error":
                        errors.append({
                            "stage": "documentation_read",
                            "file": finding.get("documentation_file"),
                            "message": finding.get("reason")
                        })
                    else:
                        drift_results.append(finding)
            except Exception as error:
                errors.append({
                    "stage": "empty_documentation_check",
                    "file": javaPath,
                    "message": str(error)
                })

        result = {
            "file": filePath,
            "changes": changes,
            "documentation_files": documentation_files,
            "drift": drift_results,
            "change_type": file_change["change_type"],
            "git_change_type": file_change["git_change_type"],
            "old_file": oldPath,
            "new_file": newPath
        }
        if errors:
            result["errors"] = errors
        results.append(result)

    return {
        "repository": root.name,
        "current_commit": analysis["current_commit"],
        "previous_commit": analysis["previous_commit"],
        "results": results,
        "mode": analysis["mode"]
    }