from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import json

db = SQLAlchemy()

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    server_path = db.Column(db.String(200), nullable=False)
    git_url = db.Column(db.String(200))
    git_branch = db.Column(db.String(100))
    environment_vars = db.Column(db.Text)  # JSON string of env vars
    service_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deployments = db.relationship('Deployment', backref='project', lazy=True)
    server_stats = db.relationship('ServerStats', backref='project', lazy=True)

    def get_env_vars(self):
        if self.environment_vars:
            return json.loads(self.environment_vars)
        return {}

    def set_env_vars(self, env_vars):
        self.environment_vars = json.dumps(env_vars)

class Deployment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, failed, rolled_back
    deployed_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    backup_path = db.Column(db.String(200))
    git_commit = db.Column(db.String(40))
    log = db.Column(db.Text)
    error = db.Column(db.Text)

    def add_log(self, message):
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        new_log = f"[{timestamp}] {message}\n"
        if self.log:
            self.log += new_log
        else:
            self.log = new_log

class ServerStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    cpu_usage = db.Column(db.Float)
    memory_usage = db.Column(db.Float)
    disk_usage = db.Column(db.Float)
    active_services = db.Column(db.Integer)

class EnvVar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    key = db.Column(db.String(100), nullable=False)
    value = db.Column(db.String(500), nullable=False)
    is_secret = db.Column(db.Boolean, default=False)
