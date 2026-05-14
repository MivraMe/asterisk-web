from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AMI
    ami_host: str = Field(default="192.168.0.107", alias="AMI_HOST")
    ami_port: int = Field(default=5038, alias="AMI_PORT")
    ami_username: str = Field(default="manager", alias="AMI_USERNAME")
    ami_secret: str = Field(default="", alias="AMI_SECRET")

    # Asterisk server
    asterisk_ip: str = Field(default="192.168.0.107", alias="ASTERISK_IP")

    # Config file paths
    pjsip_conf: str = Field(default="/etc/asterisk/pjsip.conf", alias="PJSIP_CONF")
    extensions_conf: str = Field(default="/etc/asterisk/extensions.conf", alias="EXTENSIONS_CONF")
    features_conf: str = Field(default="/etc/asterisk/features.conf", alias="FEATURES_CONF")
    polycom_cfg_dir: str = Field(default="/var/www/html/polycom", alias="POLYCOM_CFG_DIR")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:////data/asterisk_web.db",
        alias="DATABASE_URL",
    )
    asterisk_cdr_db: str | None = Field(default=None, alias="ASTERISK_CDR_DB")

    # Backup
    backup_dir: str = Field(default="/data/backups", alias="BACKUP_DIR")

    # App
    http_port: int = Field(default=8080, alias="HTTP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    secret_key: str = Field(default="change_me", alias="SECRET_KEY")


settings = Settings()
