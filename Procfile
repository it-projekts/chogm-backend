web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --timeout 120 --workers 2
release: python manage.py migrate && python manage.py create_admin
