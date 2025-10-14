"""FastAPI router for the end‑to‑end pipeline.

This module exposes a set of endpoints to:

- Upload raw files for a given job (``/upload``)
- Ingest uploaded files into a chunked intermediate representation (``/ingest``)
- Run LLM-based extraction over the chunks (``/extract``)
- Synthesize/prioritize findings (``/synthesize``)
- Render a presentation deck (``/render``)
- Score a current-state baseline (``/current_state/baseline``)
- Render and view an HTML dashboard (``/dashboard`` and ``/dashboard/view/{job_id}``)
- Build a policy index over policy documents (``/policy/index``)
- Apply policy adjudication to the current state (``/current_state/policy``)
- Generate prioritized recommendations (``/recommendations``)

Notes
-----
- The concrete heavy lifting lives in ``app.services.*``. This router focuses on
  HTTP contracts, light validation, and predictable logging.
- JSON files read from disk are opened using UTF‑8 explicitly to avoid platform
  encoding surprises (e.g., Windows cp1252 defaults).
- Where appropriate, we surface short "preview" payloads so the client can
  render summaries without downloading whole artifacts.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from flask import Blueprint, request, redirect, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
import boto3
import botocore
from pydantic import BaseModel

# Local service layer imports
from ..models.user import User, db

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)
# -----------------------------------------------------------------------------
# Router
# -----------------------------------------------------------------------------
router = Blueprint('pipeline', __name__)


# =============================================================================
# Upload
# =============================================================================
BUCKET_NAME = os.getenv("BUCKET_NAME")
s3 = boto3.client('s3', config=botocore.config.Config(s3={'addressing_style':'path'}))
lambda_client = boto3.client(
    'lambda',
    region_name='us-west-2'
)

@router.route("/upload", methods=['POST'])
@login_required
def upload():
    if current_user.acc == "admin":
        user = User.query.filter_by(email=request.form.get("company")).first()
        if not user:
            user = User(email=request.form.get("company"), acc="client")
            db.session.add(user)
        user.set_password(request.form.get("password"))
        db.session.commit()
        print("0")
        files = request.files.getlist('files')
        saved_files = []
        i=1
        for f in files:
            print(i)
            # Determine a safe destination path under your inputs root.
            filename = secure_filename(f.filename)
            temp_path = os.path.join("/tmp", filename)   # Lambda's temp folder
            # Check incoming file size from Flask
            
            # Save file
            f.stream.seek(0)
            with open(temp_path, "wb") as tmp:
                tmp.write(f.read())
            
            # Check saved file size
            
            s3.upload_file(temp_path, BUCKET_NAME, request.form.get("company") + "/" + filename)
            print("S3")

            saved_files.append({"filename": filename, "key": request.form.get("company") + "/" + filename})
        print(os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))
        # Invoke this same Lambda function asynchronously as a worker
        lambda_client.invoke(
            FunctionName=os.getenv('AWS_LAMBDA_FUNCTION_NAME'),
            InvocationType='Event',  # Async invocation
            Payload=json.dumps({
                'worker': True,
                'task_type': 'file_processing',
                'data': {
                    'files': saved_files,
                    'company': request.form.get("company")
                }
            })
        )
        print("-2")
        
        return {"message": "proccssing"}, 202
    return {"message": "Forbidden"}, 403


