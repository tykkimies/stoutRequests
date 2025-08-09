# 🎬 CuePlex

A self-hosted request platform for Plex servers built with FastAPI, HTMX, and Tailwind CSS.

## Features

- **Plex OAuth Authentication**: Users log in with their Plex accounts
- **Smart Request System**: Prevents duplicate requests and checks existing library content
- **TMDB Integration**: Search and display rich media information
- **Radarr/Sonarr Integration**: Automatically add approved requests
- **Admin Interface**: Manage users, settings, and requests
- **Role-Based Access Control**: Admin-only settings and user management

## Quick Start

### 🐳 Docker Installation (Recommended)

The easiest way to get CuePlex running with all dependencies included:

```bash
# Download and run the installer
curl -fsSL https://raw.githubusercontent.com/your-repo/cueplex/main/install.sh | bash

# Or manually with Docker Compose:
wget https://raw.githubusercontent.com/your-repo/cueplex/main/docker-compose.yml
docker compose up -d
```

This automatically includes:
- PostgreSQL database (pre-configured)
- Redis for caching  
- All necessary dependencies
- Automatic health checks and restarts

Access your instance at `http://localhost:8001`

### 📦 One-Line Installation

```bash
curl -fsSL https://get.cueplex.com | bash
```

### 🔧 Manual Installation

For advanced users who prefer manual setup:

### 1. Install Dependencies

```bash
# Activate virtual environment  
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example environment file and update with your API keys:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Database
DATABASE_URL=postgresql://cueplex_user:CuePlexSecure2024!@localhost/cueplex

# Plex Configuration
PLEX_URL=http://your-plex-server:32400
PLEX_TOKEN=your-plex-token-here
PLEX_CLIENT_ID=your-plex-client-id

# TMDB API
TMDB_API_KEY=your-tmdb-api-key

# Radarr Configuration
RADARR_URL=http://your-radarr-instance:7878
RADARR_API_KEY=your-radarr-api-key

# Sonarr Configuration
SONARR_URL=http://your-sonarr-instance:8989
SONARR_API_KEY=your-sonarr-api-key

# Application Settings
SECRET_KEY=your-secret-key-here
```

### 3. Set Up Database

Install and configure PostgreSQL, then create a database:

```sql
CREATE DATABASE cueplex;
CREATE USER cueplex_user WITH PASSWORD 'CuePlexSecure2024!';
GRANT ALL PRIVILEGES ON DATABASE cueplex TO cueplex_user;
```

### 4. Run the Application

```bash
# Development mode
python run.py

# Or with uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000` to access the application.

## Getting API Keys

### Plex Token
1. Follow the [Plex support guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/) to find your token

### TMDB API Key
1. Create account at [TMDB](https://www.themoviedb.org/)
2. Go to Settings > API and request an API key

### Radarr/Sonarr API Keys
1. In Radarr/Sonarr, go to Settings > General
2. Copy the API Key

## First Time Setup

1. Start the application
2. Log in with your Plex account (this creates the first admin user)
3. Go to Admin Settings and import your Plex friends
4. Configure your API settings in the `.env` file

## Project Structure

```
app/
├── api/            # API routes
├── core/           # Core functionality (auth, config, database)
├── models/         # Database models
├── services/       # External service integrations
├── templates/      # Jinja2 templates
└── static/         # Static files
```

## Technology Stack

- **Backend**: FastAPI
- **Frontend**: HTMX + Jinja2 templates
- **Styling**: Tailwind CSS
- **Database**: PostgreSQL with SQLModel
- **Authentication**: Plex OAuth