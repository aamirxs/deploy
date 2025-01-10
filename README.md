# Effortless Deploy

A modern, easy-to-use deployment dashboard for Flask applications and Python scripts. Deploy your applications to your Ubuntu server with just a few clicks.

## Features

- Beautiful, modern UI built with Tailwind CSS
- Project management dashboard
- Easy deployment process
- Deployment history tracking
- Real-time deployment status updates

## Setup Instructions

1. Clone this repository to your local machine:
```bash
git clone <your-repo-url>
cd deploy
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the required packages:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the root directory with your server credentials:
```
SERVER_HOST=your_server_ip
SERVER_USER=your_username
SERVER_PASSWORD=your_password  # Or use SSH key authentication
```

5. Run the application:
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Usage

1. Create a New Project:
   - Click "New Project" button
   - Enter project name and server deployment path
   - Click "Create Project"

2. Deploy Your Application:
   - Go to project details
   - Click "New Deployment"
   - Upload your application files (as ZIP)
   - Click "Deploy"

3. Monitor Deployments:
   - View deployment history in project details
   - Check deployment status and logs
   - Track all your projects from the dashboard

## Security Considerations

- Always use SSH key authentication instead of passwords when possible
- Keep your `.env` file secure and never commit it to version control
- Regularly update your dependencies to patch security vulnerabilities
- Use HTTPS when deploying to production

## Contributing

Feel free to open issues and pull requests to improve the application.

## License

MIT License
