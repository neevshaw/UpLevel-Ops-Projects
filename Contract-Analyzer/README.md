# Contract Analyzer

An AI contract-review assistant built for UpLevel Ops. A user talks to a Custom GPT, uploads a contract (`.docx` or `.pdf`), and gets back a Word document with **tracked-change redlines and margin comments** that follow the client's legal playbook. Inserted and replacement text keeps the original run formatting (bold, italic, underline, font size).

## How it works

The GPT drives a four-step workflow by calling two AWS Lambda functions through API Gateway:

1. **Upload** – The GPT sends the user to an upload page served by `wordDocGenerator`. The file is normalized (collapsed whitespace in runs) and stored in S3 under an `upload_id`.
2. **Screening** – `helper` pulls the document text from S3 and asks the model to check it against a list of legal-review triggers (contract value, term length, data sharing, restrictive covenants, governing law, etc.). Result: `green` (deliver as-is) or `red` (generate redlines).
3. **Redline plan** – For red contracts, `helper` returns the document in ~1000-word chunks (`cursor` paging). The GPT proposes edits for each chunk using the redline rules embedded in the prompt.
4. **Apply redlines + deliver** – `helper` fuzzy-matches each edit's anchor text back to the original document (`rapidfuzz`), then calls `wordDocGenerator`, which writes the edits into the `.docx` as real Word tracked insertions/deletions with comments and returns a download link.

```
Custom GPT ──► API Gateway ──► helper (Lambda, container)
                     │              │  OpenAI API
                     │              └──► wordDocGenerator /editFileUpload
                     └──────────► wordDocGenerator (Lambda, container) ◄──► S3
```

## Layout

| Path | Purpose |
| --- | --- |
| `helper/helper/lambda_function.py` | Deployed helper Lambda: screening, chunking, anchor matching, delivery link |
| `helper/helper_system_prompt.txt` | Longer Custom GPT system prompt (playbook usage, step protocol) |
| `helper/lambda_function.py` | Earlier version of the helper, kept for reference (not built by `build.bat`) |
| `wordDocGenerator2/worddocGenerator2/lambda_function.py` | Upload page, document data API, tracked-change editing, download page |
| `wordDocGenerator2/worddocGenerator2/word_doc.py` | Low-level OOXML helpers (`w:ins`, `w:del`, comments, run splitting) |

### wordDocGenerator routes

| Route | Method | Description |
| --- | --- | --- |
| `/wordDocGenerator/fileUpload` | GET / POST | Upload page / file upload handler |
| `/wordDocGenerator/fileUploadData` | GET | Paged JSON view of an uploaded document's paragraphs and runs |
| `/wordDocGenerator/editFileUpload` | POST | Apply `replace` / `insert_text` edits as tracked changes |
| `/wordDocGenerator/document` | GET | Download page for the edited document |
| `/wordDocGenerator/chunk` | POST | Deprecated chunked-JSON upload |

## Configuration

**helper Lambda**

| Variable | Required | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | yes | OpenAI API key |
| `WORD_DOC_GENERATOR_BASE_URL` | yes | Base URL of the wordDocGenerator API, e.g. `https://<api-id>.execute-api.<region>.amazonaws.com/default/wordDocGenerator` |
| `WORD_DOC_GENERATOR_URL` | no | Override for the edit endpoint (defaults to `<base>/editFileUpload`) |
| `HELPER_MODEL` | no | Model for screening (default `gpt-4o-mini`) |
| `TMP_DOC_UPLOAD_BUCKET_NAME` | no | S3 bucket for uploads (default `tmp-word-doc-upload`) |

**wordDocGenerator Lambda** uses the S3 buckets `tmp-word-doc-upload` and `tmp-word-doc-json-upload` (constants at the top of `lambda_function.py`). Both functions need IAM permission to read/write those buckets.

## Build and deploy

Both functions are deployed as container images (`public.ecr.aws/lambda/python:3.12`) pushed to ECR:

```bat
set AWS_ACCOUNT_ID=123456789012
set AWS_REGION=us-west-2
cd helper && build.bat
cd ..\wordDocGenerator2 && build.bat
```

Each `build.bat` logs in to ECR, builds the image from its `Dockerfile`, and pushes it as `:latest`. Point the Lambda function at the new image afterwards. Requires the AWS CLI and Docker.

## Notes

- Only `replace` and `insert_text` edits are applied; `insert_paragraph` handling in `wordDocGenerator` is currently disabled.
- The wordDocGenerator uses Python's `cgi` module for multipart parsing, which was removed in Python 3.13; keep the image on 3.12 or swap in another parser before upgrading.
