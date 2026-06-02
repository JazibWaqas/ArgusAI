import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.project_name = "ArgusAI"
        self.spectral_model_path = os.getenv("SPECTRAL_MODEL_PATH", "argusai_fuse_best")
        self.spectral_model_gcs_uri = os.getenv("SPECTRAL_MODEL_GCS_URI", "")
        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
        self.env_file = os.getenv("ENV_FILE", ".env")
        self.spectral_ai_index = int(os.getenv("SPECTRAL_AI_INDEX", "1"))
        self.spectral_input_size = int(os.getenv("SPECTRAL_INPUT_SIZE", "224"))
        self.spectral_normalize = os.getenv("SPECTRAL_NORMALIZE", "1") == "1"
        self.spectral_reference_real_dir = os.getenv("SPECTRAL_REFERENCE_REAL_DIR", "Images Dataset/Real Images")
        self.spectral_reference_ai_dir = os.getenv("SPECTRAL_REFERENCE_AI_DIR", "Images Dataset/AI Images")
        self.spectral_reference_sample_count = int(os.getenv("SPECTRAL_REFERENCE_SAMPLE_COUNT", "12"))
        self.video_max_frames = int(os.getenv("VIDEO_MAX_FRAMES", "2"))
        self.phoenix_api_key = os.getenv("PHOENIX_API_KEY")
        self.phoenix_collector_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "")
        self.phoenix_project_name = os.getenv("PHOENIX_PROJECT_NAME", "argusai-forensics")
        self.phoenix_dashboard_url = os.getenv("PHOENIX_DASHBOARD_URL", "")
        self.arize_health_governor = os.getenv("ARIZE_HEALTH_GOVERNOR", "1") == "1"
        self.detector_health_ttl_hours = int(os.getenv("DETECTOR_HEALTH_TTL_HOURS", "24"))
        self.firebase_project_id = os.getenv("FIREBASE_PROJECT_ID", "")
        self.firebase_service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
        self.serpapi_key = os.getenv("SERPAPI_KEY")
        self.tineye_api_key = os.getenv("TINEYE_API_KEY")
        # Audio deepfake detector settings
        self.audio_model_path = os.getenv("AUDIO_MODEL_PATH", "backend/models/wav2vec2-deepfake")
        self.hf_audio_space_id = os.getenv("HF_AUDIO_SPACE_ID", "Sameer121/deepfake-audio-detector")


settings = Settings()
