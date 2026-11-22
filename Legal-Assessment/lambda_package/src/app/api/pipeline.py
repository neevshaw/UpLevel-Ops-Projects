"""Pipeline blueprint: admin upload endpoint that stores client documents in S3
and kicks off the async processing worker."""

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

from ..models.user import User, db

logger = logging.getLogger(__name__)
router = Blueprint('pipeline', __name__)

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
        files = request.files.getlist('files')
        saved_files = []
        for f in files:
            filename = secure_filename(f.filename)
            temp_path = os.path.join("/tmp", filename)
            f.stream.seek(0)
            with open(temp_path, "wb") as tmp:
                tmp.write(f.read())

            s3.upload_file(temp_path, BUCKET_NAME, request.form.get("company") + "/" + filename)

            saved_files.append({"filename": filename, "key": request.form.get("company") + "/" + filename})
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
        return {"message": "processing"}, 202
    return {"message": "Forbidden"}, 403


