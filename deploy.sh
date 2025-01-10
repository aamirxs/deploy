#!/bin/bash

# Update system and install dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev build-essential libssl-dev libffi-dev python3-setuptools python3-venv nginx redis-server

# Create a Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
pip install gunicorn

# Create systemd service file
sudo bash -c 'cat > /etc/systemd/system/deploydashboard.service << EOL
[Unit]
Description=Deploy Dashboard
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/deploydashboard
Environment="PATH=/var/www/deploydashboard/venv/bin"
ExecStart=/var/www/deploydashboard/venv/bin/gunicorn --workers 4 --bind unix:deploydashboard.sock -m 007 app:app

[Install]
WantedBy=multi-user.target
EOL'

# Create Nginx config
sudo bash -c 'cat > /etc/nginx/sites-available/deploydashboard << EOL
server {
    listen 80;
    server_name _;

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/deploydashboard/deploydashboard.sock;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /socket.io {
        include proxy_params;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_pass http://unix:/var/www/deploydashboard/deploydashboard.sock;
    }

    client_max_body_size 5000M;
}
EOL'

# Create symbolic link and set permissions
sudo ln -s /etc/nginx/sites-available/deploydashboard /etc/nginx/sites-enabled
sudo chown -R www-data:www-data /var/www/deploydashboard
sudo chmod -R 755 /var/www/deploydashboard

# Start and enable services
sudo systemctl start redis-server
sudo systemctl enable redis-server
sudo systemctl start deploydashboard
sudo systemctl enable deploydashboard
sudo systemctl restart nginx

echo "Deployment complete! Access your dashboard at http://your_server_ip"
