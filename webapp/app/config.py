from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database (source of truth for extensions/trunks/routes; also holds the
    # cdr table that cdr_pgsql writes into directly).
    database_url: str = Field(
        default="postgresql+asyncpg://asterisk:asterisk@db:5432/asterisk",
        alias="DATABASE_URL",
    )

    # AMI — see docker-compose.yml comments: this container is on the Docker
    # bridge network while asterisk runs with network_mode: host, so
    # AMI_HOST needs to be something that resolves to the LXC host itself
    # (host.docker.internal), not "asterisk" or "127.0.0.1".
    ami_host: str = Field(default="host.docker.internal", alias="AMI_HOST")
    ami_port: int = Field(default=5038, alias="AMI_PORT")
    ami_user: str = Field(default="webapp", alias="AMI_USER")
    ami_secret: str = Field(default="", alias="AMI_SECRET")

    # Path where pjsip.conf / extensions.conf / voicemail.conf are generated.
    # Must be the same bind mount as the asterisk container's /etc/asterisk.
    asterisk_etc_dir: str = Field(default="/etc/asterisk", alias="ASTERISK_ETC_DIR")
    asterisk_spool_dir: str = Field(default="/var/spool/asterisk", alias="ASTERISK_SPOOL_DIR")

    # Auth — bootstraps a single admin user on first startup if the users
    # table is empty (see app/main.py). Change the password after first login.
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="", alias="ADMIN_PASSWORD")
    secret_key: str = Field(default="change_me", alias="SECRET_KEY")
    session_cookie_name: str = Field(default="asterisk_web_session", alias="SESSION_COOKIE_NAME")
    session_max_age_seconds: int = Field(default=60 * 60 * 12, alias="SESSION_MAX_AGE_SECONDS")
    login_rate_limit_attempts: int = Field(default=5, alias="LOGIN_RATE_LIMIT_ATTEMPTS")
    login_rate_limit_window_seconds: int = Field(default=60, alias="LOGIN_RATE_LIMIT_WINDOW_SECONDS")

    # Voicemail email-to-voicemail "From" address, generated into
    # voicemail.conf's serveremail — must match the asterisk container's
    # msmtprc "from" so the relay (Resend) accepts the envelope sender.
    voicemail_from_email: str = Field(default="voicemail@localhost", alias="VOICEMAIL_FROM_EMAIL")

    # App
    http_port: int = Field(default=8000, alias="HTTP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


settings = Settings()
