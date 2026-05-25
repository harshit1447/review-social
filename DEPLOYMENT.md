# Deploying Review Social

This project is ready for Render.

## 1. Commit the code

```bash
git add .
git commit -m "Prepare Django app for deployment"
```

If Git asks who you are, set your identity first:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## 2. Push to GitHub

Create an empty GitHub repo, then run the commands GitHub shows you. They usually look like:

```bash
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/review-social.git
git push -u origin main
```

## 3. Create the Render web service

In Render, create a new Web Service from the GitHub repo.

Use these settings:

```text
Runtime: Python
Build Command: bash build.sh
Start Command: python manage.py migrate && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

Set these environment variables:

```text
DJANGO_DEBUG=False
PYTHON_VERSION=3.11.9
DJANGO_SECRET_KEY=<generate a long random value>
DJANGO_ALLOWED_HOSTS=<your-service-name>.onrender.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-service-name>.onrender.com
```

For real saved user accounts/reviews, create a Render PostgreSQL database and set:

```text
DATABASE_URL=<your Render database internal connection string>
```

## 4. Enable Google sign in

In Google Cloud Console, create an OAuth Client ID for a web application.

Add this authorized redirect URI:

```text
https://<your-service-name>.onrender.com/accounts/google/login/callback/
```

Then add these Render environment variables:

```text
GOOGLE_CLIENT_ID=<your Google OAuth client ID>
GOOGLE_CLIENT_SECRET=<your Google OAuth client secret>
```

Render can also read `render.yaml`, but you still need to fill in the host and CSRF values after you know your Render URL.

## 5. After deploy

Open the Render URL, create an account, then add friends/reviews from the app.
