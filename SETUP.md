# 🚀 CuePlex Setup Guide

## Quick Start

### 1. Install Dependencies
```bash
# Virtual environment already created
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Database Setup
Install PostgreSQL and create database:
```sql
CREATE DATABASE cueplex;
CREATE USER cueplex_user WITH PASSWORD 'CuePlexSecure2024!';
GRANT ALL PRIVILEGES ON DATABASE cueplex TO cueplex_user;
```

### 3. Environment Configuration
```bash
cp .env.example .env
```

Edit `.env` with your settings:
```env
DATABASE_URL=postgresql://cueplex_user:CuePlexSecure2024!@localhost/cueplex
PLEX_URL=http://your-plex-server:32400
PLEX_TOKEN=your-plex-token
PLEX_CLIENT_ID=stout-requests
TMDB_API_KEY=your-tmdb-key
RADARR_URL=http://localhost:7878
RADARR_API_KEY=your-radarr-key
SONARR_URL=http://localhost:8989
SONARR_API_KEY=your-sonarr-key
SECRET_KEY=change-this-secret-key
```

### 4. Run Application
```bash
python run.py
```

Visit: http://localhost:8000

## Features Implemented

✅ **Authentication & Authorization**
- Plex OAuth login
- Role-based access control (admin/user)
- Session management with JWT tokens

✅ **Search & Discovery**
- TMDB integration for movie/TV search
- Real-time search with HTMX
- Rich media information display

✅ **Request Management**
- User request submission
- Admin approval workflow
- Request status tracking
- Duplicate prevention

✅ **Smart Integrations**
- Plex library checking
- Radarr/Sonarr integration
- Automatic media addition on approval

✅ **Admin Features**
- User management
- Settings configuration
- Friend import from Plex
- Request oversight

✅ **UI/UX**
- Responsive design with Tailwind CSS
- Interactive HTMX components
- Toast notifications
- Clean, modern interface

## File Structure
```
stout-requests/
├── app/
│   ├── api/           # API endpoints
│   │   ├── auth.py    # Authentication
│   │   ├── search.py  # Search functionality
│   │   ├── requests.py # Request management
│   │   └── admin.py   # Admin features
│   ├── core/          # Core functionality
│   │   ├── config.py  # Configuration
│   │   ├── database.py # Database setup
│   │   └── auth.py    # Auth utilities
│   ├── models/        # Database models
│   │   ├── user.py
│   │   ├── media_request.py
│   │   └── plex_library_item.py
│   ├── services/      # External integrations
│   │   ├── plex_service.py
│   │   ├── tmdb_service.py
│   │   ├── radarr_service.py
│   │   └── sonarr_service.py
│   ├── templates/     # Jinja2 templates
│   └── static/        # Static files
├── venv/              # Virtual environment
├── requirements.txt
├── .env.example
├── run.py            # Startup script
└── README.md
```

## API Endpoints

### Authentication
- `GET /auth/plex/login` - Initiate Plex OAuth
- `POST /auth/plex/verify` - Verify PIN and login
- `POST /auth/import-friends` - Import Plex friends (admin)

### Search
- `GET /search?q=query` - Search TMDB for media

### Requests
- `POST /requests/` - Create new request
- `GET /requests/` - View user's requests
- `GET /requests/admin` - Admin view (admin only)
- `POST /requests/{id}/approve` - Approve request (admin)
- `POST /requests/{id}/reject` - Reject request (admin)

### Admin
- `GET /admin/settings` - Settings page (admin only)
- `GET /admin/users` - User management (admin only)
- `POST /admin/users/{id}/toggle-admin` - Toggle admin status
- `POST /admin/users/{id}/toggle-active` - Toggle user status

## Getting API Keys

### Plex Token
1. Log into Plex Web App
2. Open browser dev tools
3. Go to Network tab
4. Refresh page
5. Look for requests with `X-Plex-Token` header

### TMDB API
1. Create account at https://www.themoviedb.org/
2. Go to Settings > API
3. Request API key (v3 auth)

### Radarr/Sonarr API Keys
1. In app: Settings > General
2. Copy API Key value

## First Run
1. Start the application
2. Login with your Plex account (creates first admin)
3. Go to Admin Settings
4. Import your Plex friends
5. Configure integration settings in .env
6. Start making requests!

## Troubleshooting

**Database Connection Issues**
- Verify PostgreSQL is running
- Check DATABASE_URL format
- Ensure database exists and user has permissions

**Plex Authentication Issues**
- Verify PLEX_URL is accessible
- Check PLEX_TOKEN is valid
- Ensure PLEX_CLIENT_ID is unique

**API Integration Issues**
- Test API keys manually first
- Check URL formats (no trailing slashes)
- Verify services are accessible from app server