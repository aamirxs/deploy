from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import json
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from models import db, Project, Deployment, ServerStats, EnvVar
from utils.server_monitor import ServerMonitor
from utils.deployment_manager import DeploymentManager

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///deploy.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 5000 * 1024 * 1024  # 50MB max file size

socketio = SocketIO(app)
db.init_app(app)

# Initialize server monitor and deployment manager
server_monitor = ServerMonitor(
    host=os.getenv('SERVER_HOST'),
    username=os.getenv('SERVER_USER'),
    password=os.getenv('SERVER_PASSWORD'),
    key_path=os.getenv('SSH_KEY_PATH')
)

deployment_manager = DeploymentManager(
    host=os.getenv('SERVER_HOST'),
    username=os.getenv('SERVER_USER'),
    password=os.getenv('SERVER_PASSWORD'),
    key_path=os.getenv('SSH_KEY_PATH')
)

def init_db():
    with app.app_context():
        db.create_all()

def update_server_stats():
    """Background job to update server statistics"""
    with app.app_context():
        projects = Project.query.all()
        for project in projects:
            stats = server_monitor.get_system_stats()
            server_stats = ServerStats(
                project_id=project.id,
                cpu_usage=stats['cpu_usage'],
                memory_usage=stats['memory_usage'],
                disk_usage=stats['disk_usage'],
                active_services=stats['active_services']
            )
            db.session.add(server_stats)
            db.session.commit()
            
            socketio.emit(f'server_stats_{project.id}', stats)

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=update_server_stats, trigger="interval", minutes=5)
scheduler.start()

@app.route('/')
def index():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template('index.html', projects=projects)

@app.route('/project/new', methods=['GET', 'POST'])
def new_project():
    if request.method == 'POST':
        name = request.form.get('name')
        server_path = request.form.get('server_path')
        git_url = request.form.get('git_url')
        git_branch = request.form.get('git_branch')
        service_name = request.form.get('service_name')
        
        project = Project(
            name=name,
            server_path=server_path,
            git_url=git_url,
            git_branch=git_branch,
            service_name=service_name
        )
        
        # Handle environment variables
        env_vars = {}
        env_keys = request.form.getlist('env_key[]')
        env_values = request.form.getlist('env_value[]')
        env_secrets = request.form.getlist('env_secret[]')
        
        for key, value, is_secret in zip(env_keys, env_values, env_secrets):
            if key and value:
                env_var = EnvVar(
                    project=project,
                    key=key,
                    value=value,
                    is_secret=is_secret == 'true'
                )
                db.session.add(env_var)
                env_vars[key] = value
        
        project.set_env_vars(env_vars)
        db.session.add(project)
        db.session.commit()
        
        flash('Project created successfully!', 'success')
        return redirect(url_for('index'))
    
    return render_template('new_project.html')

@app.route('/project/<int:project_id>/deploy', methods=['GET', 'POST'])
def deploy_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'POST':
        deployment = Deployment(project_id=project.id, status='in_progress')
        db.session.add(deployment)
        db.session.commit()

        try:
            if project.git_url:
                # Deploy from Git
                result = deployment_manager.deploy_from_git(
                    project.git_url,
                    project.git_branch or 'main',
                    project.server_path,
                    project.get_env_vars()
                )
            else:
                # Deploy from ZIP file
                if 'file' not in request.files:
                    flash('No file uploaded', 'error')
                    return redirect(request.url)
                    
                file = request.files['file']
                if file.filename == '':
                    flash('No file selected', 'error')
                    return redirect(request.url)

                result = deployment_manager.deploy_from_zip(
                    file,
                    project.server_path,
                    project.get_env_vars()
                )

            deployment.backup_path = result.get('backup_path')
            deployment.git_commit = result.get('commit')
            
            if result['success']:
                deployment.status = 'completed'
                deployment.completed_at = datetime.utcnow()
                
                # Restart service if configured
                if project.service_name:
                    if server_monitor.restart_service(project.service_name):
                        deployment.add_log(f"Service {project.service_name} restarted successfully")
                    else:
                        deployment.add_log(f"Failed to restart service {project.service_name}")
            else:
                deployment.status = 'failed'
                deployment.error = result.get('error')
            
            db.session.commit()
            socketio.emit(f'deployment_{deployment.id}', {
                'status': deployment.status,
                'timestamp': deployment.completed_at.isoformat() if deployment.completed_at else None
            })
            
        except Exception as e:
            deployment.status = 'failed'
            deployment.error = str(e)
            db.session.commit()
            flash(f'Deployment failed: {str(e)}', 'error')
            
        return redirect(url_for('project_details', project_id=project_id))
    
    return render_template('deploy.html', project=project)

@app.route('/project/<int:project_id>')
def project_details(project_id):
    project = Project.query.get_or_404(project_id)
    deployments = Deployment.query.filter_by(project_id=project_id).order_by(Deployment.deployed_at.desc()).all()
    
    # Get latest server stats
    latest_stats = ServerStats.query.filter_by(project_id=project_id).order_by(ServerStats.timestamp.desc()).first()
    
    # Get service status if configured
    service_status = None
    if project.service_name:
        service_status = server_monitor.check_service_status(project.service_name)
    
    return render_template('project_details.html',
                         project=project,
                         deployments=deployments,
                         latest_stats=latest_stats,
                         service_status=service_status)

@app.route('/project/<int:project_id>/rollback/<int:deployment_id>')
def rollback_deployment(project_id, deployment_id):
    project = Project.query.get_or_404(project_id)
    deployment = Deployment.query.get_or_404(deployment_id)
    
    if not deployment.backup_path:
        flash('No backup available for this deployment', 'error')
        return redirect(url_for('project_details', project_id=project_id))
    
    new_deployment = Deployment(project_id=project_id, status='in_progress')
    db.session.add(new_deployment)
    db.session.commit()
    
    try:
        if deployment_manager.restore_backup(deployment.backup_path, project.server_path):
            new_deployment.status = 'completed'
            new_deployment.completed_at = datetime.utcnow()
            new_deployment.add_log(f"Rolled back to backup: {deployment.backup_path}")
            
            # Restart service if configured
            if project.service_name:
                if server_monitor.restart_service(project.service_name):
                    new_deployment.add_log(f"Service {project.service_name} restarted successfully")
                else:
                    new_deployment.add_log(f"Failed to restart service {project.service_name}")
        else:
            new_deployment.status = 'failed'
            new_deployment.error = 'Failed to restore backup'
        
        db.session.commit()
        flash('Rollback completed successfully', 'success')
    except Exception as e:
        new_deployment.status = 'failed'
        new_deployment.error = str(e)
        db.session.commit()
        flash(f'Rollback failed: {str(e)}', 'error')
    
    return redirect(url_for('project_details', project_id=project_id))

@app.route('/project/<int:project_id>/env', methods=['POST'])
def update_env_vars(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Update environment variables
    env_vars = {}
    env_keys = request.form.getlist('env_key[]')
    env_values = request.form.getlist('env_value[]')
    env_secrets = request.form.getlist('env_secret[]')
    
    # Remove old env vars
    EnvVar.query.filter_by(project_id=project_id).delete()
    
    # Add new env vars
    for key, value, is_secret in zip(env_keys, env_values, env_secrets):
        if key and value:
            env_var = EnvVar(
                project=project,
                key=key,
                value=value,
                is_secret=is_secret == 'true'
            )
            db.session.add(env_var)
            env_vars[key] = value
    
    project.set_env_vars(env_vars)
    db.session.commit()
    
    flash('Environment variables updated successfully', 'success')
    return redirect(url_for('project_details', project_id=project_id))

@app.route('/project/<int:project_id>/logs')
def service_logs(project_id):
    project = Project.query.get_or_404(project_id)
    
    if not project.service_name:
        flash('No service configured for this project', 'error')
        return redirect(url_for('project_details', project_id=project_id))
    
    logs = server_monitor.get_logs(project.service_name)
    return render_template('logs.html', project=project, logs=logs)

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
