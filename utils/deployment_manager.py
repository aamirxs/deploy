import os
import paramiko
import shutil
import tempfile
import zipfile
from datetime import datetime
from typing import Optional, Dict, Any
import git
from werkzeug.utils import secure_filename

class DeploymentManager:
    def __init__(self, host: str, username: str, key_path: str = None, password: str = None):
        self.host = host
        self.username = username
        self.key_path = key_path
        self.password = password
        self.ssh = None
        self.sftp = None

    def connect(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        if self.key_path:
            private_key = paramiko.RSAKey.from_private_key_file(self.key_path)
            self.ssh.connect(self.host, username=self.username, pkey=private_key)
        else:
            self.ssh.connect(self.host, username=self.username, password=self.password)
        
        self.sftp = self.ssh.open_sftp()

    def disconnect(self):
        if self.sftp:
            self.sftp.close()
        if self.ssh:
            self.ssh.close()

    def create_backup(self, remote_path: str) -> str:
        """Create a backup of the current deployment"""
        backup_path = f"{remote_path}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            self.connect()
            _, stdout, _ = self.ssh.exec_command(f"cp -r {remote_path} {backup_path}")
            if stdout.channel.recv_exit_status() == 0:
                return backup_path
            return None
        finally:
            self.disconnect()

    def restore_backup(self, backup_path: str, remote_path: str) -> bool:
        """Restore from a backup"""
        try:
            self.connect()
            _, stdout, _ = self.ssh.exec_command(f"rm -rf {remote_path} && cp -r {backup_path} {remote_path}")
            return stdout.channel.recv_exit_status() == 0
        finally:
            self.disconnect()

    def deploy_from_zip(self, zip_file, remote_path: str, env_vars: Dict[str, str] = None) -> Dict[str, Any]:
        """Deploy application from a ZIP file"""
        try:
            self.connect()
            
            # Create backup
            backup_path = self.create_backup(remote_path)
            
            # Create temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, secure_filename(zip_file.filename))
                zip_file.save(zip_path)
                
                # Extract ZIP
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Upload files
                for root, dirs, files in os.walk(temp_dir):
                    for dir_name in dirs:
                        remote_dir = os.path.join(remote_path, os.path.relpath(os.path.join(root, dir_name), temp_dir))
                        self.ssh.exec_command(f"mkdir -p {remote_dir}")
                    
                    for file_name in files:
                        local_path = os.path.join(root, file_name)
                        remote_file = os.path.join(remote_path, os.path.relpath(local_path, temp_dir))
                        self.sftp.put(local_path, remote_file)

                # Update environment variables if provided
                if env_vars:
                    env_file = os.path.join(remote_path, '.env')
                    env_content = '\n'.join([f"{k}={v}" for k, v in env_vars.items()])
                    with self.sftp.open(env_file, 'w') as f:
                        f.write(env_content)

            return {
                'success': True,
                'backup_path': backup_path,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            if backup_path:
                self.restore_backup(backup_path, remote_path)
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
        finally:
            self.disconnect()

    def deploy_from_git(self, git_url: str, branch: str, remote_path: str, env_vars: Dict[str, str] = None) -> Dict[str, Any]:
        """Deploy application from a Git repository"""
        try:
            self.connect()
            
            # Create backup
            backup_path = self.create_backup(remote_path)
            
            # Clone repository
            with tempfile.TemporaryDirectory() as temp_dir:
                repo = git.Repo.clone_from(git_url, temp_dir, branch=branch)
                
                # Upload files
                for root, dirs, files in os.walk(temp_dir):
                    for dir_name in dirs:
                        if dir_name != '.git':
                            remote_dir = os.path.join(remote_path, os.path.relpath(os.path.join(root, dir_name), temp_dir))
                            self.ssh.exec_command(f"mkdir -p {remote_dir}")
                    
                    for file_name in files:
                        if not file_name.startswith('.git'):
                            local_path = os.path.join(root, file_name)
                            remote_file = os.path.join(remote_path, os.path.relpath(local_path, temp_dir))
                            self.sftp.put(local_path, remote_file)

                # Update environment variables if provided
                if env_vars:
                    env_file = os.path.join(remote_path, '.env')
                    env_content = '\n'.join([f"{k}={v}" for k, v in env_vars.items()])
                    with self.sftp.open(env_file, 'w') as f:
                        f.write(env_content)

            return {
                'success': True,
                'backup_path': backup_path,
                'commit': repo.head.commit.hexsha,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            if backup_path:
                self.restore_backup(backup_path, remote_path)
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
        finally:
            self.disconnect()
