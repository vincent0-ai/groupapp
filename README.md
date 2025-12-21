# GroupApp - Collaborative Learning Platform MVP

A Progressive Web App for collaborative learning, interactive whiteboards, group competitions, and real-time messaging built with modern web technologies.

## Features

### Feature Status
Below is a short status list indicating which features are already implemented and which are planned or partial.

#### Core Features
- [x] **User Authentication & Profiles** — Email/password signup, JWT login, Google social login, user profiles ✅
- [x] **Groups & Channels** — Create / join public & private groups, member management, moderators ✅
- [x] **Real-Time Messaging** — Instant messaging, emoji reactions, replies (threading via `reply_to`), mentions, read receipts, pinned messages, notifications ✅
- [x] **Interactive Whiteboard** — Real-time collaborative drawing, annotations, multiple users, LiveKit video integration ✅
- [x] **Competitions & Challenges** — Create/join competitions, submit answers, leaderboards ✅
- [x] **File Upload & Storage** — Secure uploads to MinIO, presigned download URLs, file sharing ✅
- [x] **Search & Discovery** — Meilisearch integration (client + helper) ✅
- [x] **PWA Features** — Installable, offline support (Service Worker, IndexedDB, background sync). Push notifications: client & subscription endpoints implemented; server push/send logic is partial/planned ⚠️

#### Technical Features
- [x] Socket.IO for realtime ✅
- [x] MongoDB for persistent storage ✅
- [x] Redis for caching & session management ✅
- [x] MinIO for file storage ✅
- [x] Meilisearch for indexed full-text search ✅
- [x] Bootstrap 5 & responsive UI ✅
- [x] Service Worker & IndexedDB for offline behavior ✅

---

### Planned / To be added
A short list of notable items that are not fully implemented yet or are planned enhancements:
- Add server-side push senders (VAPID / pywebpush) to deliver push notifications from the backend (subscriptions are stored already)
- Support for additional social/OAuth providers beyond Google (Facebook/GitHub/etc.)
- Optional automatic Meilisearch indexing hooks for all write operations (if desired)
- Advanced moderation tools & reporting/appeals workflow (more UI & audit trails)
- Export / import of data, analytics dashboards

If you'd like, I can open a second PR to turn any of the planned items into tracked issues or implement one of them next. ✅

## Tech Stack

### Backend
- **Framework**: Flask with Flask-CORS and Flask-JWT-Extended
- **Real-Time**: Socket.IO (python-socketio)
- **Database**: MongoDB
- **Cache**: Redis
- **Storage**: MinIO (S3-compatible)
- **Search**: Meilisearch
- **Authentication**: JWT with bcrypt password hashing
- **Language**: Python 3.11+

### Frontend
- **HTML5/CSS3/JavaScript**
- **Bootstrap 5** for UI components
- **Font Awesome** for icons
- **Socket.IO Client** for real-time updates
- **Service Worker** for PWA features
- **IndexedDB** for offline data storage

### Infrastructure
- **Container**: Docker & Docker Compose
- **Deployment**: Can be deployed on any cloud platform (AWS, Azure, DigitalOcean, etc.)

## Project Structure

```
groupapp/
├── main.py                 # Application entry point
├── app/
│   ├── __init__.py        # Flask app factory and Socket.IO setup
│   ├── models/
│   │   ├── models.py      # MongoDB document models
│   │   └── __init__.py
│   ├── routes/
│   │   ├── auth.py        # Authentication endpoints
│   │   ├── groups.py      # Groups and channels endpoints
│   │   ├── messages.py    # Messaging endpoints
│   │   ├── competitions.py # Competitions endpoints
│   │   ├── files.py       # File upload/download endpoints
│   │   ├── users.py       # User profile endpoints
│   │   └── __init__.py
│   ├── services/
│   │   ├── database.py    # MongoDB database service
│   │   └── __init__.py
│   └── utils/
│       ├── auth.py        # JWT and password utilities
│       ├── storage.py     # MinIO client
│       ├── cache.py       # Redis client
│       ├── search.py      # Meilisearch client
│       ├── helpers.py     # Common helper functions
│       └── __init__.py
├── config/
│   ├── config.py          # Configuration management
│   └── __init__.py
├── templates/
│   ├── index.html         # Main application template
│   └── auth.html          # Authentication template
├── static/
│   ├── css/
│   │   └── style.css      # Global styles
│   ├── js/
│   │   ├── app.js         # Main application logic
│   │   ├── auth.js        # Authentication logic
│   │   ├── pwa.js         # PWA functionality
│   │   └── service-worker.js # Service worker
│   ├── images/            # PNG icons for PWA
│   └── manifest.json      # PWA manifest
├── requirements.txt       # Python dependencies
├── docker-compose.yml     # Docker Compose configuration
├── Dockerfile            # Docker image definition
├── .env.example          # Environment variables template
└── README.md             # This file
```

## Getting Started

### Prerequisites
- Docker & Docker Compose (recommended)
- Or: Python 3.11+, MongoDB, Redis, MinIO, Meilisearch

### Installation

#### Option 1: Using Docker Compose (Recommended)

1. Clone the repository:
```bash
cd groupapp
```

2. Create `.env` file from example:
```bash
cp .env.example .env
```

3. Start all services:
```bash
docker-compose up -d
```

4. Access the application:
- **Application**: http://localhost:5000
- **MinIO Console**: http://localhost:9001 (admin/minioadmin)
- **Meilisearch**: http://localhost:7700

#### Option 2: Manual Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Start MongoDB, Redis, MinIO, and Meilisearch separately

3. Create `.env` file:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Run the Flask application:
```bash
python main.py
```

## API Endpoints

### Authentication
- `POST /api/auth/signup` - Create new user account
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `POST /api/auth/refresh-token` - Refresh JWT token
- `POST /api/auth/verify-email` - Verify email address

### Users
- `GET /api/users/profile` - Get current user profile
- `PUT /api/users/profile` - Update user profile
- `GET /api/users/<user_id>` - Get public user profile
- `GET /api/users/leaderboard` - Get global leaderboard
- `GET /api/users/<user_id>/groups` - Get user's groups
- `GET /api/users/search?q=<query>` - Search for users

### Groups
- `POST /api/groups` - Create a group
- `GET /api/groups/<group_id>` - Get group details
- `PUT /api/groups/<group_id>` - Update group
- `DELETE /api/groups/<group_id>` - Delete group
- `POST /api/groups/<group_id>/join` - Join a group
- `POST /api/groups/<group_id>/leave` - Leave a group
- `GET /api/groups/<group_id>/members` - Get group members
- `GET /api/groups/<group_id>/channels` - Get group channels
- `POST /api/groups/<group_id>/channels` - Create a channel

### Messages
- `GET /api/messages/channel/<channel_id>` - Get channel messages
- `POST /api/messages` - Send a message
- `PUT /api/messages/<message_id>` - Edit a message
- `DELETE /api/messages/<message_id>` - Delete a message
- `POST /api/messages/<message_id>/react` - Add emoji reaction
- `POST /api/messages/<message_id>/pin` - Pin a message
- `POST /api/messages/<message_id>/unpin` - Unpin a message

### Competitions
- `POST /api/competitions` - Create a competition
- `GET /api/competitions/<comp_id>` - Get competition details
- `GET /api/competitions/group/<group_id>` - Get group competitions
- `POST /api/competitions/<comp_id>/join` - Join competition
- `POST /api/competitions/<comp_id>/submit-answer` - Submit answer
- `GET /api/competitions/<comp_id>/leaderboard` - Get leaderboard

### Files
- `POST /api/files/upload` - Upload a file
- `GET /api/files/<file_id>` - Download a file
- `DELETE /api/files/<file_id>` - Delete a file
- `GET /api/files/group/<group_id>` - Get group files
- `POST /api/files/<file_id>/share` - Make file public

## Socket.IO Events

### Client to Server
- `join_room` - Join a room (group/channel/whiteboard)
- `leave_room` - Leave a room
- `message` - Send a message
- `whiteboard_draw` - Draw on whiteboard
- `typing_indicator` - Indicate typing status
- `disconnect` - User disconnected

### Server to Client
- `connect_response` - Connection confirmed
- `new_message` - New message received
- `draw_update` - Whiteboard update
- `user_typing` - User is typing
- `user_joined` - User joined room
- `user_left` - User left room

## Database Models

### User
```javascript
{
  _id: ObjectId,
  email: String (unique),
  username: String (unique),
  password_hash: String,
  full_name: String,
  avatar_url: String,
  bio: String,
  badges: [String],
  groups: [ObjectId],
  channels: [ObjectId],
  created_at: DateTime,
  updated_at: DateTime,
  last_login: DateTime,
  is_active: Boolean,
  is_verified: Boolean,
  preferences: Object
}
```

### Group
```javascript
{
  _id: ObjectId,
  name: String,
  description: String,
  owner_id: ObjectId,
  avatar_url: String,
  is_private: Boolean,
  members: [ObjectId],
  moderators: [ObjectId],
  channels: [ObjectId],
  created_at: DateTime,
  updated_at: DateTime,
  settings: Object
}
```

### Message
```javascript
{
  _id: ObjectId,
  content: String,
  user_id: ObjectId,
  channel_id: ObjectId,
  group_id: ObjectId,
  attachments: [Object],
  reply_to: ObjectId,
  reactions: {emoji: [user_ids]},
  created_at: DateTime,
  updated_at: DateTime,
  is_edited: Boolean,
  is_pinned: Boolean
}
```

### Competition
```javascript
{
  _id: ObjectId,
  title: String,
  description: String,
  group_id: ObjectId,
  created_by: ObjectId,
  competition_type: String (quiz/challenge/contest),
  questions: [Object],
  start_time: DateTime,
  end_time: DateTime,
  participants: [Object],
  leaderboard: [Object],
  created_at: DateTime,
  updated_at: DateTime,
  is_active: Boolean
}
```

## PWA Features

### Manifest
- App metadata (name, description, icons)
- Installation configuration
- Theme colors
- Shortcuts for quick access

### Service Worker
- Offline page support
- Network-first caching strategy
- Background sync for offline messages
- Push notifications
- Asset caching

### Offline Support
- IndexedDB for local data storage
- Service Worker caching
- Background sync queue
- Automatic sync when online

## MinIO Setup

1. Create bucket:
```bash
mc mb minio/groupapp
```

2. Set bucket policy (if needed):
```bash
mc policy set public minio/groupapp
```

3. Upload files:
- Files are organized by path: `groups/{group_id}/{filename}`

## Meilisearch Setup

Meilisearch automatically creates indexes as needed. You can define index settings:

```python
# Create indexes in app initialization
meilisearch_client.create_index('users', primary_key='_id')
meilisearch_client.create_index('groups', primary_key='_id')
meilisearch_client.create_index('messages', primary_key='_id')
```

## Development

### Running Tests
```bash
# Run tests (coming soon)
pytest
```

### Code Style
```bash
# Format code with Black
black app/

# Lint with Pylint
pylint app/
```

## Deployment

### Using Docker:
```bash
# Build image
docker build -t groupapp:latest .

# Run container
docker run -p 5000:5000 --env-file .env groupapp:latest
```

### Environment Variables
Create `.env` file with:
```
FLASK_ENV=production
SECRET_KEY=your_secret_key
JWT_SECRET_KEY=your_jwt_secret
MONGODB_URI=mongodb://user:password@host:27017/groupapp
REDIS_URL=redis://host:6379/0
MINIO_ENDPOINT=minio.example.com
MINIO_ROOT_USER=user
MINIO_ROOT_PASSWORD=password
MEILISEARCH_URL=http://meilisearch:7700
MEILISEARCH_API_KEY=your_api_key
```

## Performance Optimization

- Redis caching for user sessions and frequently accessed data
- Message pagination to reduce load
- Indexed MongoDB queries
- MinIO presigned URLs for efficient file downloads
- Meilisearch for fast full-text search
- Service Worker caching for offline access
- Lazy loading of components
- GZIP compression

## Security

- JWT token-based authentication
- Bcrypt password hashing
- CORS configuration for API access
- Input validation on all endpoints
- SQL injection protection (MongoDB)
- XSS protection with Content Security Policy
- HTTPS support for production
- Secure cookie handling

## Contributing

1. Create feature branch
2. Make changes
3. Test thoroughly
4. Submit pull request

## License

MIT License - See LICENSE file for details

## Support

For issues or questions:
- GitHub Issues: [Create an issue]
- Email: vinnyochi13249@gmail.com

## Roadmap

- [ ] Email verification
- [ ] Two-factor authentication
- [ ] Advanced user roles and permissions
- [ ] File encryption
- [ ] Video/audio conferencing
- [ ] Mobile apps (iOS/Android)
- [ ] Analytics dashboard
- [ ] API rate limiting
- [ ] Advanced search filters
- [ ] Team management features

## Acknowledgments

- Bootstrap team for UI framework
- Socket.IO for real-time communication
- MongoDB for database
- MinIO for S3-compatible storage
- Meilisearch for search engine
