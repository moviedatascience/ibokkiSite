# Deployment Guide for iBokki

This guide covers deploying the iBokki streaming application with full WebSocket support, Redis channel layers, and proper production configuration.

## Architecture Overview

The production deployment uses:
- **Gunicorn** (WSGI) for HTTP requests on port 8000
- **Daphne** (ASGI) for WebSocket connections on port 8001  
- **Redis** for Django Channels message passing
- **Nginx** as reverse proxy and load balancer

## Prerequisites

- Docker and Docker Compose
- Redis server (or use Docker)
- PostgreSQL database (or use Docker)
- SSL certificates for production

## Environment Variables

Create a `.env` file with the following variables:

```bash
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=False
ENVIRONMENT=production
BASE_URL=https://ibokki.com

# Database
DATABASE_URL=postgres://user:password@localhost:5432/ibokki
POSTGRES_PASSWORD=your-postgres-password

# Redis
REDIS_URL=redis://localhost:6379

# External APIs
DISCORD_CLIENT_ID=your-discord-client-id
DISCORD_CLIENT_SECRET=your-discord-client-secret
YOUTUBE_API_KEY=your-youtube-api-key
KICK_CLIENT_ID=your-kick-client-id
KICK_CLIENT_SECRET=your-kick-client-secret

# Admin Users
DISCORD_ADMIN_IDS=discord_user_id_1,discord_user_id_2
```

## Deployment Options

### Option 1: Docker Compose (Recommended)

1. **Build and start services:**
```bash
docker-compose -f deploy/docker-compose.yml up -d
```

2. **Run migrations:**
```bash
docker-compose exec web python manage.py migrate
```

3. **Create superuser:**
```bash
docker-compose exec web python manage.py createsuperuser
```

4. **Collect static files:**
```bash
docker-compose exec web python manage.py collectstatic --noinput
```

### Option 2: Manual Deployment

1. **Install Redis:**
```bash
# Ubuntu/Debian
sudo apt-get install redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Or use Docker
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Apply migrations:**
```bash
python manage.py migrate
```

4. **Collect static files:**
```bash
python manage.py collectstatic --noinput
```

5. **Start services:**

**Terminal 1 - Gunicorn (HTTP):**
```bash
chmod +x deploy/start_gunicorn.sh
./deploy/start_gunicorn.sh
```

**Terminal 2 - Daphne (WebSocket):**
```bash
chmod +x deploy/start_daphne.sh
```

## Nginx Configuration

1. **Install Nginx:**
```bash
sudo apt-get install nginx
```

2. **Copy configuration:**
```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ibokki
sudo ln -s /etc/nginx/sites-available/ibokki /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # Remove default site
```

3. **Test and reload:**
```bash
sudo nginx -t
sudo systemctl reload nginx
```

## SSL/HTTPS Setup

1. **Install Certbot:**
```bash
sudo apt-get install certbot python3-certbot-nginx
```

2. **Get SSL certificate:**
```bash
sudo certbot --nginx -d ibokki.com -d www.ibokki.com
```

3. **Auto-renewal:**
```bash
sudo crontab -e
# Add this line:
0 12 * * * /usr/bin/certbot renew --quiet
```

## Process Management

### Using systemd (Recommended for production)

1. **Create service files:**

**gunicorn.service:**
```ini
[Unit]
Description=Gunicorn instance to serve iBokki
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/ibokkiSite
Environment="PATH=/path/to/ibokkiSite/venv/bin"
ExecStart=/path/to/ibokkiSite/venv/bin/gunicorn --workers 3 --bind unix:/path/to/ibokkiSite/ibokki.sock ibokki.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**daphne.service:**
```ini
[Unit]
Description=Daphne instance to serve iBokki WebSockets
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/ibokkiSite
Environment="PATH=/path/to/ibokkiSite/venv/bin"
ExecStart=/path/to/ibokkiSite/venv/bin/daphne -u /path/to/ibokkiSite/daphne.sock ibokki.asgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```


2. **Enable and start services:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable gunicorn daphne
sudo systemctl start gunicorn daphne
```

## Monitoring and Logs

1. **View service status:**
```bash
sudo systemctl status gunicorn daphne
```

2. **View logs:**
```bash
sudo journalctl -u gunicorn -f
sudo journalctl -u daphne -f
```

3. **Application logs:**
```bash
tail -f debug.log
```

## Performance Tuning

### Redis Configuration
Add to `/etc/redis/redis.conf`:
```
maxmemory 512mb
maxmemory-policy allkeys-lru
```

### Django Settings for Production
```python
# Enable database connection pooling
DATABASES['default']['CONN_MAX_AGE'] = 60

# Cache configuration
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
```

## Scaling

### Horizontal Scaling
- Run multiple Gunicorn workers: `--workers 4`
- Run multiple Daphne instances on different ports
- Use Redis Cluster for high availability

### Monitoring
- Set up Redis monitoring
- Monitor WebSocket connection counts
- Track message queue length
- Monitor database performance

## Troubleshooting

### Common Issues

1. **WebSocket connections failing:**
   - Check if Daphne is running on port 8001
   - Verify Nginx WebSocket proxy configuration
   - Check firewall rules

2. **Chat messages not appearing:**
   - Verify Redis is running and accessible
   - Ensure proper Redis URL configuration

3. **High memory usage:**
   - Monitor Redis memory usage
   - Check for message queue backlog
   - Consider implementing message TTL

### Health Checks

```bash
# Check HTTP service
curl http://localhost:8000/health/

# Check WebSocket service
curl --include \
     --no-buffer \
     --header "Connection: Upgrade" \
     --header "Upgrade: websocket" \
     --header "Sec-WebSocket-Key: SGVsbG8sIHdvcmxkIQ==" \
     --header "Sec-WebSocket-Version: 13" \
     http://localhost:8001/ws/chat/

# Check Redis
redis-cli ping
```

## Security Considerations

1. **Firewall Configuration:**
   - Only expose ports 80 and 443 to the internet
   - Restrict Redis access to localhost
   - Use VPN for database access

2. **Environment Variables:**
   - Never commit `.env` files to version control
   - Use secrets management in production
   - Rotate secrets regularly

3. **Rate Limiting:**
   - Configure Nginx rate limiting for WebSocket connections
   - Implement application-level rate limiting
   - Monitor for abuse patterns
``` 