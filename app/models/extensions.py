from boto3 import client
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
s3 = client("s3")