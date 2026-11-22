# Legal Assessment

A legal-operations maturity assessment tool built for UpLevel Ops. An UpLevel admin uploads a client's documents (policies, process docs, slide decks, interview notes); the app extracts pain points, tools, processes, and metrics with an LLM, scores the client against a legal-ops maturity model, and publishes an HTML dashboard with prioritized recommendations that the client can log in to view.

## How it works

The whole app is a single AWS Lambda function running a Flask app through `serverless_wsgi`. Long-running work is done by the function invoking **itself** asynchronously with a `worker` payload, so each stage stays within Lambda's time limit.

1. **Upload** (`POST /Legal_Assessment/pipeline/upload`, admin only) – creates or updates the client's login, stores the files in S3 under `<company>/`, and starts the worker.
2. **`file_processing`** – parses PDF, DOCX, PPTX, and TXT files into chunks (`services/parsing.py`), runs LLM extraction on up to 50 chunks (`services/llm.py`), and dedupes/scores the results with an impact × effort heuristic (`services/synthesis.py`).
3. **`score_baseline`** – scores one maturity category per invocation by fuzzy-matching each criterion's level descriptors against the chunks (`services/current_state_baseline.py`), then chains to the next category.
4. **`policy`** – retrieves relevant policy snippets by embedding similarity and asks the LLM for a policy-aligned level per category (`services/policy_adjudicator.py`), generates recommendations (`services/recommendations.py`), and renders the dashboard (`services/dashboard.py`) to `<company>/dashboard.html` in S3.

Clients log in at `/Legal_Assessment/` and are shown their dashboard (or a "coming soon" page while processing runs). User accounts live in MySQL via SQLAlchemy.

## Layout

| Path | Purpose |
| --- | --- |
| `lambda_package/src/lambda_function.py` | Lambda entry point: routes worker events vs. HTTP requests |
| `lambda_package/src/app/__init__.py` | Flask app, auth routes, and the three worker stages |
| `lambda_package/src/app/api/pipeline.py` | Admin upload endpoint |
| `lambda_package/src/app/services/` | Parsing, extraction, synthesis, scoring, policy adjudication, recommendations, dashboard |
| `lambda_package/src/app/schemas/` | Pydantic models for extraction results and the maturity model |
| `lambda_package/lib/` | Vendored third-party packages bundled with the function (PyMuPDF, Pillow, lxml, ...) |
| `dependencies/python/` | Vendored packages in Lambda layer format (Flask, OpenAI, boto3, SQLAlchemy, ...) |

The `lib/` and `dependencies/` folders are third-party code committed so the function can be zipped and deployed directly; they are not part of this project's source.

## Configuration

| Variable | Description |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI API key |
| `LLM_MODEL` | Model for extraction and recommendations (default `gpt-4o-mini`) |
| `BUCKET_NAME` | S3 bucket for uploads, intermediate JSON, and dashboards |
| `SECRET_KEY` | Flask session secret |
| `DB_USER`, `DB_PASS`, `DB_HOST`, `DB_PORT`, `DB_NAME` | MySQL connection |
| `ADMIN_USER`, `ADMIN_PASS` | Admin account, recreated on every cold start |

The function also needs:

- `src/assets/maturity_model.yaml` – categories, criteria, and level descriptors (1–4)
- `src/assets/policy_index.json` – policy chunks with OpenAI embeddings (`meta.engine = "openai"`)

These are client-specific and are **not** included in this repository.

## Deploy

- Runtime: Python 3.12 (the code uses 3.12 f-string syntax).
- Package `lambda_package/` as the function code with handler `src.lambda_function.handler`, and publish `dependencies/` as a layer.
- The function's role needs S3 access to `BUCKET_NAME`, permission to `lambda:InvokeFunction` on itself, and network access to the MySQL database.
- Expose it through API Gateway (or a function URL) so `/Legal_Assessment/*` reaches the Flask app.
