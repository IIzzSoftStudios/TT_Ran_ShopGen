from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import UserMixin, LoginManager
from flask_bcrypt import Bcrypt
from flask_session import Session



db = SQLAlchemy()
migrate = Migrate()
user = UserMixin()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
session = Session()