# iBokki Streaming Platform

iBokki is a Django application that brings together live streams from Kick, YouTube and Twitch with integrated chat using Django Channels. It is designed for easy local development and production deployment via Docker.

## Local Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **Create a `.env` file** – copy the variables from [deploy/README.md](deploy/README.md#environment-variables) and provide your own values.
3. **Apply migrations**
   ```bash
   python manage.py migrate
   ```
4. **Run the development server**
   ```bash
   python manage.py runserver
   ```

## Running Tests

Execute the Django test suite with:
```bash
python manage.py test
```

## Deployment

See the [Deployment Guide](deploy/README.md) for Docker compose usage and production configuration.
