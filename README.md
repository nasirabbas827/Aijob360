# Running Command 

## Into the Terminal First Write this Command to install Dependencies

pip install --upgrade pip
pip install -r requirements.txt


# Set Django Settings

## Edit myproject/settings.py:

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    ".ngrok.io",
    "50262bbfe646.ngrok-free.app"
]

CSRF_TRUSTED_ORIGINS = ['https://50262bbfe646.ngrok-free.app']

# Run Database Migrations

python manage.py migrate
python manage.py makemigrations

# Running Locally

python manage.py runserver 0.0.0.0:8000


# Running with Ngrok (Temporary Public Access)

## Start Django server using this command 

python manage.py runserver 0.0.0.0:8000

# Now Run the ngrok.exe 

## And then into the ngrok terminal type this command 

ngrok http 8000

### Copy the public URL from ngrok (e.g., https://50262bbfe646.ngrok-free.app) and open in your browser.

# Update settings.py to include ngrok domain:

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '50262bbfe646.ngrok-free.app']
CSRF_TRUSTED_ORIGINS = ['https://50262bbfe646.ngrok-free.app']



