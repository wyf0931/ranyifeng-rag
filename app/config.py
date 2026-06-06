from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    database_path: str = Field(default="data/rag.db", description="SQLite database path")
    openai_api_base: str = Field(default="http://127.0.0.1:9092/v1", description="OpenAI API base URL")
    openai_api_key: str = Field(default="hebo0931", description="OpenAI API key")
    llm_model: str = Field(default="Qwen3.6-35B-A3B-nvfp4", description="LLM model name")

    flask_env: str = Field(default="development", description="Flask environment")
    flask_debug: bool = Field(default=True, description="Flask debug mode")
    flask_host: str = Field(default="127.0.0.1", description="Flask host")
    flask_port: int = Field(default=5000, description="Flask port")

    max_search_results: int = Field(default=100, description="Maximum search results")
    max_thinking_loops: int = Field(default=3, description="Maximum thinking loops")
    search_timeout: int = Field(default=30, description="Search timeout in seconds")

    jieba_dict_path: str = Field(default="data/jieba_custom.dict", description="Custom jieba dictionary")
    jieba_stopwords_path: str = Field(default="data/jieba_stopwords.txt", description="Jieba stopwords file")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
