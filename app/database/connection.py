import psycopg2
from app.config.settings import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )