from flask import Flask, render_template, request, redirect, url_for, Blueprint, flash, send_from_directory, Response
from .api.pipeline import router as pipeline_router

from werkzeug.utils import secure_filename
import boto3
import logging
import os
import json
import botocore
import base64
from pydantic import BaseModel

# Local service layer imports
from .services.current_state_baseline import score_current_state_baseline
from .services.llm import extract_from_chunks
from .services.dashboard import render_dashboard
from .services.parsing import ingest_files
from .services.policy_adjudicator import apply_policy_to_current_state
from .services.recommendations import generate_recommendations
from .services.synthesis import synthesize
from .services.maturity import load_maturity_model
from sqlalchemy import text
from .models.user import User, db
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

login_manager = LoginManager()




BUCKET_NAME = os.getenv("BUCKET_NAME")
s3 = boto3.client('s3', config=botocore.config.Config(s3={'addressing_style':'path'}))
lambda_client = boto3.client(
    'lambda',
    region_name='us-west-2'
)
logger = logging.getLogger(__name__)

def process(data):
    with app.app_context():
        files = data.get('files', [])
        company = data.get('company')
        saved_files = []
        for file in files:
            filename = file['filename']
            local_path = f'/tmp/{file['filename']}'
            s3.download_file(BUCKET_NAME, file['key'], local_path)
            


            saved_files.append({"filename": filename, "path": local_path})

            logger.info(
                "[UPLOAD] saved %s -> %s", filename, local_path
            )

        """Chunk the uploaded files for a given ``job_id``.

        The underlying ``ingest_files`` service should write an artifacts file
        (e.g., JSON of chunks) and return its path.
        """
        try:
            chunks = ingest_files(saved_files)
        except FileNotFoundError as e:
            return {'status': 400, 'body': str(e)}
        max_chunks: int = 50

        """Run LLM-powered extraction over the previously ingested chunks."""
        try:
            data = extract_from_chunks(chunks, max_chunks=max_chunks)
        except FileNotFoundError as e:
            return {'status': 400, 'body': str(e)}

        counts = {
            "pain_points": len(data.get("pain_points", [])),
            "current_tools": len(data.get("current_tools", [])),
            "processes": len(data.get("processes", [])),
            "metrics": len(data.get("metrics", [])),
            "opportunities": len(data.get("opportunities", [])),
            "chunks_used": len(set(data.get("chunks_used", []))),
        }
        print(counts)

        """Aggregate, de-duplicate, and prioritize extracted signals."""
        try:
            synthesis = synthesize(data, top_n=8)
        except FileNotFoundError as e:
            return {'status': 400, 'body': str(e)}

        preview = [
            {
                "kind": p["kind"],
                "text": p["text"],
                "score": p["score"],
                "count": p["count"],
            }
            for p in synthesis.get("top_priorities", [])
        ]
        print(preview)

        chunks_json = json.dumps(chunks, indent=2)
        synthesis_json = json.dumps(synthesis, indent=2)
        # Upload to S3 (creates the directory path automatically)
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=f"{company}/chunks.json",
            Body=chunks_json,
            ContentType="application/json"
        )

        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=f"{company}/synthesis.json",
            Body=synthesis_json,
            ContentType="application/json"
        )
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=f"{company}/current_state.json",
            Body=json.dumps({"categories": []}, indent=2).encode("utf-8"),
            ContentType="application/json"
        )
        lambda_client.invoke(
            FunctionName=os.getenv('AWS_LAMBDA_FUNCTION_NAME'),
            InvocationType='Event',  # Async invocation
            Payload=json.dumps({
                'worker': True,
                'task_type': 'score_baseline',
                'data': {
                    'company': company,
                    'id': 0
                }
            })
        )
    return {'status': 'processing started'}, 202

def process2(data):
    with app.app_context():
        model, _ = load_maturity_model()
        print(data.get("id"))
        category = score_current_state_baseline(data.get("company"), threshold=55, i=data.get("id"))
        current_state = json.loads(s3.get_object(Bucket=BUCKET_NAME, Key=f"{data.get("company")}/current_state.json")['Body'].read().decode('utf-8'))
        current_state['categories'].append(category)
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=f"{data.get("company")}/current_state.json",
            Body=json.dumps(current_state, indent=2).encode("utf-8"),
            ContentType="application/json"
        )
        if data.get("id") < len(model.categories)-1:
            lambda_client.invoke(
                FunctionName=os.getenv('AWS_LAMBDA_FUNCTION_NAME'),
                InvocationType='Event',  # Async invocation
                Payload=json.dumps({
                    'worker': True,
                    'task_type': 'score_baseline',
                    'data': {
                        'company': data.get("company"),
                        'id': data.get("id")+1
                    }
                })
            )
        else:
            lambda_client.invoke(
                FunctionName=os.getenv('AWS_LAMBDA_FUNCTION_NAME'),
                InvocationType='Event',  # Async invocation
                Payload=json.dumps({
                    'worker': True,
                    'task_type': 'policy',
                    'data': {
                        'company': data.get("company"),
                    }
                })
            )
        return {'status': 'processing started'}, 202

def process3(data):
    with app.app_context():
        company = data.get('company')
        
        current_state = json.loads(s3.get_object(Bucket=BUCKET_NAME, Key=f"{company}/current_state.json")['Body'].read().decode('utf-8'))
        synthesis = json.loads(s3.get_object(Bucket=BUCKET_NAME, Key=f"{company}/synthesis.json")['Body'].read().decode('utf-8'))

        preview = [
            {
                "id": c["id"],
                "name": c["name"],
                "level": c["level"],
                "coverage": c["coverage"],
                "confidence": c["confidence"],
            }
            for c in current_state.get("categories", [])[:5]
        ]
        print(preview)

        try:
            out = apply_policy_to_current_state(
                current_state,
                index_path="assets/policy_index.json",
                model_path=None,
                top_k=5,
                enforce=False,
            )
        except FileNotFoundError as e:
            return {'statusCode': 400, 'body': str(e)}

        policy = out
        preview = [
            {
                "name": c.get("name", c.get("id")),
                "baseline": c.get("level"),
                "policy": c.get("policy_level"),
                "final": c.get("final_level"),
                "conf": c.get("policy_confidence"),
            }
            for c in policy.get("categories", [])[:6]
        ]
        print(preview)

        try:
            recommendations = generate_recommendations(synthesis, policy, max_recommendations=5)
        except FileNotFoundError as e:
            return {'status': 400, 'body': str(e)}
        preview = [
            {
                "sequence": r["sequence"],
                "title": r["title"],
                "impact": r["impact"],
                "effort": r["effort"],
                "priority_score": r["priority_score"],
                "category": r["category"],
            }
            for r in recommendations.get("recommendations", [])[:5]
        ]
        print(preview)

        html = render_dashboard(current_state, policy, recommendations, synthesis, company.capitalize() + " Current State")
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=company + "/dashboard.html",
            Body=html.encode('utf-8'),
            ContentType='text/html',
            ContentDisposition='inline'  # Opens in browser instead of downloading
        )
        return {"message": "process complete!"}, 202

        

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

app = Flask(__name__, static_folder='static')
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size": 5,
    "max_overflow": 10,
    "pool_timeout": 30,
    "pool_recycle": 1800,
}

# Build connection string for MySQL (using pymysql)
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'main.index'
login_manager.login_message = 'Please log in to access this page.'


main = Blueprint('main', __name__)


@main.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.index"))  # or whatever your homepage route is

@main.route("/dashboard", methods=['GET'])
@login_required
def dashboard():
    if current_user.acc != "client":
        return redirect(url_for("main.up"))
    print(current_user.email + "/dashboard.html")
    try:
        s3_object = s3.get_object(Bucket=BUCKET_NAME, Key=current_user.email + "/dashboard.html")
        html_content = s3_object['Body'].read().decode('utf-8')
        return Response(html_content, mimetype='text/html')
    except:
        with open(os.path.dirname(os.path.realpath(__file__))+'/static/logo.png', 'rb') as f:
            logo_data = base64.b64encode(f.read()).decode('utf-8')
        return render_template("dashboard.html", logo_data=logo_data)
    

@main.route("/upload", methods=['GET'])
@login_required
def up():
    if current_user.acc != "admin":
        return redirect(url_for("main.dashboard"))
    
    with open(os.path.dirname(os.path.realpath(__file__))+'/static/logo.png', 'rb') as f:
        logo_data = base64.b64encode(f.read()).decode('utf-8')
    return render_template("upload.html", logo_data=logo_data)


@main.route("/", methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated:
        if current_user.acc == "admin":
            return redirect(url_for("main.up"))
        return redirect(url_for("main.dashboard"))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return redirect(url_for('main.index'))

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('main.index'))

        login_user(user, remember=True)

        # Redirect to next page if specified, otherwise dashboard

        if user.acc == "admin":
            return redirect(url_for('main.up'))
        else:
            return redirect(url_for('main.dashboard'))
    with open(os.path.dirname(os.path.realpath(__file__))+'/static/logo.png', 'rb') as f:
        logo_data = base64.b64encode(f.read()).decode('utf-8')
    return render_template("index.html", logo_data=logo_data)

main.register_blueprint(pipeline_router, url_prefix='/pipeline')
app.register_blueprint(main, url_prefix='/Legal_Assessment')

with app.app_context():
    db.create_all()
    db.session.commit()
    db.session.query(User).filter_by(acc="admin").delete(synchronize_session=False)
    admin = User(email=os.getenv("ADMIN_USER"), acc="admin")
    admin.set_password(os.getenv("ADMIN_PASS"))
    db.session.add(admin)
    db.session.commit()