import paramiko
import json
from datetime import datetime
import psutil
import os
from typing import Dict, Any

class ServerMonitor:
    def __init__(self, host: str, username: str, key_path: str = None, password: str = None):
        self.host = host
        self.username = username
        self.key_path = key_path
        self.password = password
        self.ssh = None

    def connect(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        if self.key_path:
            private_key = paramiko.RSAKey.from_private_key_file(self.key_path)
            self.ssh.connect(self.host, username=self.username, pkey=private_key)
        else:
            self.ssh.connect(self.host, username=self.username, password=self.password)

    def disconnect(self):
        if self.ssh:
            self.ssh.close()

    def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics from the remote server"""
        try:
            self.connect()
            
            # CPU Usage
            _, stdout, _ = self.ssh.exec_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'")
            cpu_usage = float(stdout.read().decode().strip())

            # Memory Usage
            _, stdout, _ = self.ssh.exec_command("free -m | grep Mem | awk '{print $3,$2}'")
            mem_used, mem_total = map(int, stdout.read().decode().strip().split())
            memory_usage = (mem_used / mem_total) * 100

            # Disk Usage
            _, stdout, _ = self.ssh.exec_command("df -h / | tail -1 | awk '{print $5}'")
            disk_usage = float(stdout.read().decode().strip().replace('%', ''))

            # Active Services
            _, stdout, _ = self.ssh.exec_command("systemctl list-units --type=service --state=running | grep running | wc -l")
            active_services = int(stdout.read().decode().strip())

            return {
                'timestamp': datetime.utcnow().isoformat(),
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'disk_usage': disk_usage,
                'active_services': active_services
            }
        finally:
            self.disconnect()

    def check_service_status(self, service_name: str) -> bool:
        """Check if a service is running"""
        try:
            self.connect()
            _, stdout, _ = self.ssh.exec_command(f"systemctl is-active {service_name}")
            status = stdout.read().decode().strip()
            return status == "active"
        finally:
            self.disconnect()

    def restart_service(self, service_name: str) -> bool:
        """Restart a system service"""
        try:
            self.connect()
            _, stdout, _ = self.ssh.exec_command(f"sudo systemctl restart {service_name}")
            return stdout.channel.recv_exit_status() == 0
        finally:
            self.disconnect()

    def get_logs(self, service_name: str, lines: int = 100) -> str:
        """Get service logs"""
        try:
            self.connect()
            _, stdout, _ = self.ssh.exec_command(f"journalctl -u {service_name} -n {lines}")
            return stdout.read().decode()
        finally:
            self.disconnect()
