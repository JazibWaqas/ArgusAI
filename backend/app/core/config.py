import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.project_name = "ArgusAI"
        self.spectral_model_path = os.getenv("SPECTRAL_MODEL_PATH", "argusai_fuse_best")
        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
        self.env_file = os.getenv("ENV_FILE", ".env")
        self.spectral_ai_index = int(os.getenv("SPECTRAL_AI_INDEX", "1"))
        self.spectral_input_size = int(os.getenv("SPECTRAL_INPUT_SIZE", "224"))
        self.spectral_normalize = os.getenv("SPECTRAL_NORMALIZE", "1") == "1"
        self.spectral_reference_real_dir = os.getenv("SPECTRAL_REFERENCE_REAL_DIR", "Images Dataset/Real Images")
        self.spectral_reference_ai_dir = os.getenv("SPECTRAL_REFERENCE_AI_DIR", "Images Dataset/AI Images")
        self.spectral_reference_sample_count = int(os.getenv("SPECTRAL_REFERENCE_SAMPLE_COUNT", "12"))


settings = Settings()
