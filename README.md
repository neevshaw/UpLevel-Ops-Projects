# UpLevel Ops Projects

Projects I built for [UpLevel Ops](https://uplevelops.com), a legal-operations consulting firm. Both are serverless Python apps on AWS Lambda that use the OpenAI API to automate parts of legal-ops work.

## [Contract Analyzer](Contract-Analyzer/)

An AI contract-review assistant. A Custom GPT walks the user through uploading a contract, screens it against legal-review triggers, plans redlines from a client playbook, and returns a Word document with **real tracked changes and comments**.

- Two container-based Lambdas behind API Gateway: a `helper` that runs screening and anchor matching, and a `wordDocGenerator` that edits the `.docx` XML directly
- Fuzzy anchor matching with `rapidfuzz` so model-proposed edits land on the right text
- Stack: Python, AWS Lambda + API Gateway + S3 + ECR, Docker, OpenAI API, python-docx / lxml, PyMuPDF

## [Legal Assessment](Legal%20Assessment/)

A legal-operations maturity assessment. Admins upload a client's documents; the app extracts pain points, tools, processes, and metrics, scores the client against a maturity model, adjusts scores using the client's policies, and publishes a dashboard with prioritized recommendations.

- Flask app on Lambda via `serverless_wsgi`, with async self-invocation to chain long-running stages
- LLM extraction + fuzzy-match scoring + embedding retrieval over policy documents
- Stack: Python, Flask, AWS Lambda + S3, MySQL (SQLAlchemy), OpenAI API, PyMuPDF / python-docx / python-pptx

See each project's README for architecture, configuration, and deployment details.
