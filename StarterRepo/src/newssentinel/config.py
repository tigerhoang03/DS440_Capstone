from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "newssentinel"
    POSTGRES_USER: str = "newssentinel"
    POSTGRES_PASSWORD: str = "newssentinel"

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_STREAM: str = "news_items"
    REDIS_CONSUMER_GROUP: str = "ingest_group"
    REDIS_CONSUMER_NAME: str = "ingest_1"

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    RSS_DEMO_URL: str = "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"
    PRNEWSWIRE_RSS_SOURCE_URL: str = "https://www.prnewswire.com/rss/"
    GLOBENEWSWIRE_RSS_SOURCE_URL: str = "https://www.globenewswire.com/rss/list"
    WIRE_RSS_TIMEOUT_SEC: int = 15
    WIRE_RSS_MAX_FEEDS_PER_SOURCE: int = 15
    WIRE_RSS_MAX_ITEMS_PER_FEED: int = 50

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

settings = Settings()
