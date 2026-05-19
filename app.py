import os, logging, uuid, requests
from datetime import datetime
from functools import wraps
from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///crm.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL")

class Lead(db.Model):
    __tablename__ = "leads"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))
    address = db.Column(db.String(500))
    rating = db.Column(db.Float)
    review_count = db.Column(db.Integer)
    phone = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="raw")
    assigned_to = db.Column(db.String(100))
    customer_email = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    def to_dict(self):
        return {"id": self.id, "business_name": self.business_name, "category": self.category, "address": self.address, "rating": self.rating, "review_count": self.review_count, "phone": self.phone, "description": self.description, "status": self.status}

class Worker(db.Model):
    __tablename__ = "workers"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

with app.app_context():
    db.create_all()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "worker_username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def get_current_worker():
    return Worker.query.filter_by(username=session.get("worker_username")).first()

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.get_json() or request.form
        worker = Worker.query.filter_by(username=data.get("username", "").strip(), is_active=True).first()
        if worker and worker.password == data.get("password", ""):
            session["worker_username"] = worker.username
            return jsonify({"ok": True, "redirect": "/"}), 200
        return jsonify({"ok": False, "error": "Invalid credentials"}), 401
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route("/api/leads/next", methods=["GET"])
@login_required
def next_lead():
    try:
        worker = get_current_worker()
        lead = Lead.query.filter_by(status="raw", assigned_to=None).order_by(Lead.created_at.asc()).first()
        if not lead:
            return jsonify({"ok": True, "lead": None}), 200
        lead.assigned_to = worker.username
        db.session.commit()
        return jsonify({"ok": True, "lead": lead.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"next_lead error: {e}")
        return jsonify({"ok": False, "error": "Server error"}), 500

@app.route("/api/leads/<lead_id>/status", methods=["POST"])
@login_required
def update_status(lead_id):
    data = request.get_json()
    action = data.get("action", "").lower()
    if action not in ("yes", "maybe", "no"):
        return jsonify({"ok": False, "error": "Invalid action"}), 400
    worker = get_current_worker()
    lead = Lead.query.filter_by(id=lead_id, assigned_to=worker.username).first()
    if not lead:
        return jsonify({"ok": False, "error": "Lead not found"}), 404
    if action == "no":
        lead.status = "blacklist"
    elif action == "maybe":
        lead.status = "follow_up"
    else:
        email = data.get("customer_email", "").strip()
        if not email or "@" not in email:
            return jsonify({"ok": False, "error": "Invalid email"}), 400
        lead.status = "closed"
        lead.customer_email = email
    lead.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True}), 200

@app.route("/api/stats", methods=["GET"])
@login_required
def stats():
    return jsonify({"ok": True, "counts": {"raw": Lead.query.filter_by(status="raw").count(), "closed": Lead.query.filter_by(status="closed").count(), "follow_up": Lead.query.filter_by(status="follow_up").count(), "blacklist": Lead.query.filter_by(status="blacklist").count()}}), 200

@app.route("/api/admin/leads", methods=["POST"])
def ingest_leads():
    if request.headers.get("X-API-Key") != os.environ.get("ADMIN_API_KEY", "secret-key"):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    data = request.get_json()
    if not isinstance(data, list):
        data = [data]
    inserted = 0
    for item in data:
        if not item.get("phone") or not item.get("business_name"):
            continue
        db.session.add(Lead(business_name=item["business_name"], category=item.get("category"), address=item.get("address"), rating=item.get("rating"), review_count=item.get("review_count"), phone=item["phone"], description=item.get("description")))
        inserted += 1
    db.session.commit()
    return jsonify({"ok": True, "inserted": inserted}), 201

@app.route("/api/admin/workers", methods=["POST"])
def create_worker():
    if request.headers.get("X-API-Key") != os.environ.get("ADMIN_API_KEY", "secret-key"):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    data = request.get_json()
    db.session.add(Worker(username=data["username"], password=data["password"]))
    db.session.commit()
    return jsonify({"ok": True}), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
